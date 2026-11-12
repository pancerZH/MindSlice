"""Portable directory snapshots with content verification and isolated restore."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath

from ..errors import RecoveryError
from .config import Mount, MountTable, dump_mounts, load_mounts
from .fsutil import atomic_write_text, fsync_dir
from .history import ChangeHistory, event

MANIFEST = 'backup.json'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(root, exclude=()):
    """Do not follow symlinks, including directory links and special files."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise RecoveryError('snapshot source must be a real directory', path=str(root))
    files, directories = {}, []
    def unreadable(exc):
        raise RecoveryError('cannot read a snapshot directory', path=str(exc.filename)) from exc
    for directory, names, filenames in os.walk(root, followlinks=False, onerror=unreadable):
        current = Path(directory)
        for name in sorted(names + filenames):
            path = current / name
            rel = path.relative_to(root).as_posix()
            if any(rel == e or rel.startswith(e + '/') for e in exclude):
                if name in names:
                    names.remove(name)
                continue
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise RecoveryError('snapshot contains a symlink or special file; use ordinary files/directories', path=str(path))
            if stat.S_ISDIR(mode):
                directories.append(rel)
            else:
                files[rel] = {'sha256': digest(path), 'size': path.stat().st_size}
    return {'files': dict(sorted(files.items())), 'directories': sorted(directories)}


def _copy(source, target, listing):
    target.mkdir(parents=True, exist_ok=True)
    for name in listing['directories']:
        (target / name).mkdir(parents=True, exist_ok=True)
    for name, info in listing['files'].items():
        src, dst = source / name, target / name
        if src.is_symlink() or not stat.S_ISREG(src.stat().st_mode):
            raise RecoveryError('source changed during snapshot', path=str(src))
        dst.parent.mkdir(parents=True, exist_ok=True)
        with src.open('rb') as reader, dst.open('xb') as stream:
            shutil.copyfileobj(reader, stream)
            stream.flush()
            shutil.copystat(src, dst)
            os.fsync(stream.fileno())
        if digest(dst) != info['sha256'] or dst.stat().st_size != info['size']:
            raise RecoveryError('source changed during snapshot', path=str(src))
    for name in reversed(listing['directories']):
        fsync_dir(target / name)
    fsync_dir(target)


def _destination(path, sources):
    target = Path(path).expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise RecoveryError('destination already exists; choose a new directory', path=str(target))
    for root in sources:
        if target.resolve().is_relative_to(root.resolve()):
            raise RecoveryError('destination must be outside the source directories', path=str(target), source=str(root))
    return target


def _publish(temporary, target):
    if target.exists() or target.is_symlink():
        raise RecoveryError('destination appeared during operation; preserved', path=str(target))
    os.rename(temporary, target)
    fsync_dir(target.parent)


def _safe_relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value or '\x00' in value:
        raise RecoveryError('invalid path in backup manifest')
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ('', '.', '..') for p in value.split('/')):
        raise RecoveryError('unsafe path in backup manifest', path=value)
    return value


def backup(ws, output):
    from ..operations.audit import history_path

    with ws._writing() as table:
        # Recovery has completed before recording any bytes. A partial orphan log tail is not a backupable event.
        _, complete = ws.history._read()
        if ws.history.path.exists() and ws.history.path.stat().st_size != complete:
            raise RecoveryError('history has an incomplete final record; inspect it before backing up')
        roots = [ws.root]
        requested = [m.root for m in table.all()]
        unavailable = []
        records = ws.history.events()
        for e in records:
            if e['event'] in ('baked', 'rolled_back'):
                for field in ('path', 'previous_path'):
                    if e.get(field):
                        path = history_path(ws, e[field], records)
                        if path.is_dir():
                            requested.append(path)
                        else:
                            unavailable.append(str(path))
        for root in requested:
            if not root.is_dir():
                raise RecoveryError('a mounted source is missing; restore its path or unmount it first', path=str(root))
            if root != ws.root and ws.root.is_relative_to(root):
                raise RecoveryError('a mounted source contains the workspace; mount a narrower directory before backup', path=str(root))
        external = sorted(set(p for p in requested if not p.is_relative_to(ws.root)), key=lambda p: (len(p.parts), str(p)))
        for root in external:
            if not any(root.is_relative_to(r) for r in roots):
                roots.append(root)
        target = _destination(output, roots)
        locations = {root: ('workspace' if root == ws.root else f'external/{i}') for i, root in enumerate(roots)}
        def location(path):
            root = next(r for r in roots if path.is_relative_to(r))
            return (PurePosixPath(locations[root]) / path.relative_to(root).as_posix()).as_posix()
        snapshots = {root: inventory(root, ('.cache',) if root == ws.root else ()) for root in roots}
        if any(p in snapshots[ws.root]['files'] for p in ('staging/.apply_journal.json', '.history/.pending.json')):
            raise RecoveryError('unfinished transaction; recover it before backing up')
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix='.mindslice-backup-', dir=target.parent))
        try:
            for root in roots:
                _copy(root, temporary / locations[root], snapshots[root])
            for root in roots:
                if snapshots[root] != inventory(root, ('.cache',) if root == ws.root else ()):
                    raise RecoveryError('source changed during backup; retry after edits finish', path=str(root))
            listing = inventory(temporary)
            for name in list(listing['files']) + listing['directories']:
                _safe_relative(name)
            metadata = {'format': 'mindslice-workspace-backup', 'version': 1,
                        'workspace': str(ws.root), 'roots': {str(p): locations[p] for p in roots},
                        'mounts': [dict(m.to_toml(), kind=m.kind, stored=location(m.root)) for m in table.all()],
                        'unavailable_versions': sorted(set(unavailable)), **listing}
            atomic_write_text(temporary / MANIFEST, json.dumps(metadata, indent=2, ensure_ascii=False) + '\n')
            _publish(temporary, target)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return {'path': str(target), 'files': len(listing['files']), 'external_sources': len(roots) - 1,
                'unavailable_versions': metadata['unavailable_versions'],
                'note': 'Includes workspace files, staging, history, mounted external sources and available recorded versions; cache excluded.'}


def _load_backup(source):
    if source.is_symlink() or (source / MANIFEST).is_symlink():
        raise RecoveryError('backup and its manifest must not be symlinks')
    try:
        metadata = json.loads((source / MANIFEST).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise RecoveryError('cannot read backup manifest', path=str(source)) from exc
    if not isinstance(metadata, dict) or metadata.get('format') != 'mindslice-workspace-backup' or metadata.get('version') != 1:
        raise RecoveryError('unsupported backup format')
    files, directories = metadata.get('files'), metadata.get('directories')
    if not isinstance(files, dict) or not isinstance(directories, list):
        raise RecoveryError('invalid backup inventory')
    for name in list(files) + directories:
        _safe_relative(name)
    for info in files.values():
        if not isinstance(info, dict) or not isinstance(info.get('sha256'), str) or not isinstance(info.get('size'), int):
            raise RecoveryError('invalid file checksum in backup')
    actual = inventory(source, (MANIFEST,))
    if actual != {'files': files, 'directories': directories}:
        raise RecoveryError('backup contents do not match the manifest; no workspace restored')
    if 'workspace/mounts.toml' not in files:
        raise RecoveryError('backup has no workspace mount table')
    if any(p in files for p in ('workspace/staging/.apply_journal.json', 'workspace/.history/.pending.json')):
        raise RecoveryError('backup contains an unfinished transaction; refusing to replay old absolute paths')
    roots = metadata.get('roots')
    if not isinstance(roots, dict) or not isinstance(metadata.get('mounts'), list):
        raise RecoveryError('invalid backup source mapping')
    stored_roots = list(roots.values())
    if stored_roots.count('workspace') != 1 or len(set(stored_roots)) != len(stored_roots):
        raise RecoveryError('backup must contain one workspace and unique external roots')
    for original, stored in roots.items():
        if not isinstance(original, str):
            raise RecoveryError('invalid original source path')
        _safe_relative(stored)
        if stored != 'workspace' and (len(PurePosixPath(stored).parts) != 2 or not stored.startswith('external/')):
            raise RecoveryError('invalid stored source path')
        if stored not in directories:
            raise RecoveryError('missing stored source directory', path=stored)
    for mount in metadata['mounts']:
        if not isinstance(mount, dict):
            raise RecoveryError('invalid mount record')
        stored = _safe_relative(mount.get('stored'))
        if not any(stored == r or stored.startswith(r + '/') for r in stored_roots) or stored not in directories:
            raise RecoveryError('mount points outside stored sources', path=stored)
    return metadata


def restore(source, destination):
    source = Path(source).expanduser().absolute()
    metadata = _load_backup(source)
    target = _destination(destination, [source])
    # Reserve a namespace for external sources without replacing any backed-up files.
    external_dir = '.restored-mounts'
    n = 1
    while f'workspace/{external_dir}' in metadata['directories'] or f'workspace/{external_dir}' in metadata['files']:
        n += 1
        external_dir = f'.restored-mounts-{n}'
    def relocated(stored):
        if stored == 'workspace':
            return '.'
        if stored.startswith('workspace/'):
            return stored[len('workspace/'):]
        return external_dir + '/' + stored[len('external/'):]
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.mindslice-restore-', dir=target.parent))
    try:
        for stored in metadata['roots'].values():
            prefix = stored + '/'
            subset = {'files': {p[len(prefix):]: v for p, v in metadata['files'].items() if p.startswith(prefix)},
                      'directories': [p[len(prefix):] for p in metadata['directories'] if p.startswith(prefix)]}
            _copy(source / stored, temporary / relocated(stored), subset)
        mounts = []
        for entry in metadata['mounts']:
            rel = relocated(entry['stored'])
            mounts.append(Mount(entry['alias'], './' + rel, entry['precedence'], entry['role'], entry['kind'], temporary / rel))
        overlays = [m for m in mounts if m.kind == 'overlay']
        if len(overlays) != 1 or any(m.kind not in ('overlay', 'slice') for m in mounts):
            raise RecoveryError('backup needs exactly one overlay')
        atomic_write_text(temporary / 'mounts.toml', dump_mounts(MountTable(overlays[0], [m for m in mounts if m.kind == 'slice'])))
        # Parse only the rewritten local paths, never access original paths from the manifest.
        load_mounts(temporary)
        history = ChangeHistory(temporary / '.history')
        _, complete = history._read()
        if history.path.exists() and complete != history.path.stat().st_size:
            raise RecoveryError('backup history has an incomplete record')
        path_map = {original: relocated(stored) for original, stored in metadata['roots'].items()}
        history.append([event('restored', backup=str(source), path=str(target), path_map=path_map)])
        # A reviewed bake plan is bound to the original workspace and must be reviewed again.
        (temporary / '.bake-plan.json').unlink(missing_ok=True)
        if _load_backup(source) != metadata:
            raise RecoveryError('backup changed during restore; retry with an unchanged backup')
        _publish(temporary, target)
    except (KeyError, TypeError, ValueError) as exc:
        raise RecoveryError('invalid backup metadata; no workspace restored') from exc
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {'workspace': str(target), 'backup': str(source), 'mounts': [dict(m.to_toml(), path=str(target / m.path)) for m in mounts],
            'unavailable_versions': metadata.get('unavailable_versions', []),
            'note': 'Restored into a new directory. Overlay and staging preserved; cache rebuilds on first use. '
                    'Review bake choices again and point the client at this workspace.'}
