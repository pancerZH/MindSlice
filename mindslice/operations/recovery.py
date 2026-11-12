"""Preview and journal a slice-pointer rollback without reverting overlay or staging."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..errors import RecoveryError
from ..model.addressing import normalize_alias
from ..storage.config import Mount, MountTable, dump_mounts, load_slice_manifest, portable_path
from ..storage.history import event, file_action, file_sha
from ..storage.snapshots import inventory
from .audit import history_path
from .validation import Report, SliceSource, lint


def _issues(ws, table):
    report = Report(str(ws.root))
    sources = []
    for m in table.all():
        if not m.root.is_dir():
            report.add('error', 'missing_mount', f'mount {m.alias} has no directory', address=m.alias)
            continue
        nested = tuple(o.root for o in table.all() if o.alias != m.alias and m.root in o.root.parents)
        sources.append(SliceSource(m.alias, m.root, load_slice_manifest(m.root), m.kind, tuple(ws._exclude()) + nested))
    lint(sources, report)
    return report.errors + report.warnings


def rollback(ws, alias, path=None, *, dry_run=False, revision=None):
    alias = normalize_alias(alias)
    with ws._writing() as table:
        current = table.get(alias)
        if current is None or current.kind == 'overlay':
            raise RecoveryError('rollback requires a mounted read-only slice', alias=alias)
        if path is None:
            previous = next((e.get('previous_path') for e in reversed(ws.history.events())
                             if e['event'] == 'baked' and e.get('alias') == alias
                             and history_path(ws, e['path']) == current.root), None)
            if not previous:
                raise RecoveryError('no recorded predecessor for this slice; specify --to /path/to/version', alias=alias)
            target = history_path(ws, previous)
        else:
            target = Path(path).expanduser().absolute()
        if target == current.root:
            raise RecoveryError('target is already mounted', path=str(target))
        if any(target.resolve() == m.root.resolve() for m in table.all()):
            raise RecoveryError('target is already mounted under another alias', path=str(target))
        if any(target.resolve() == p.resolve() or target.resolve().is_relative_to(p.resolve())
               for p in (table.overlay.root, ws.staging.root, ws.cache_dir, ws.history.root)):
            raise RecoveryError('rollback target must be a slice directory, not live or internal workspace storage')
        target_files = inventory(target)
        replacement = Mount(alias, portable_path(ws.root, target), current.precedence, current.role, 'slice', target)
        projected = MountTable(table.overlay, [replacement if m.alias == alias else m for m in table.mounts])
        before = _issues(ws, table)
        after = _issues(ws, projected)
        def identity(issue):
            return (issue['code'], issue.get('address'), issue['message'])
        existing = {identity(i) for i in before}
        blockers = [i for i in after if identity(i) not in existing and
                    (i['severity'] == 'error' or i['code'] in ('broken_wikilink', 'unmounted_dependency', 'missing_dependency'))]
        # A malformed destination is never accepted just because the current version has the same defect.
        blockers += [i for i in after if i['severity'] == 'error' and
                     (i.get('address', '').startswith(alias + '/') or
                      (i.get('file') and Path(i['file']).is_relative_to(target))) and i not in blockers]
        state = ws.status()
        overlay = [
            f"{table.overlay.alias}/{c['path']}" for c in ws.index.all_cards(table.overlay.alias)]
        plan = {'alias': alias, 'previous_path': str(current.root), 'path': str(target),
                'version': load_slice_manifest(target).version,
                'precedence': current.precedence, 'role': current.role,
                'overlay_preserved': overlay,
                'overlay_same_paths': [f"{table.overlay.alias}/{r['path']}" for r in ws.index.all_cards(table.overlay.alias)
                                       if (target / (r['path'] + '.md')).is_file()],
                'pending_preserved': [i['address'] for i in state['pending_review']['files']],
                'blockers': blockers, 'warnings': [i for i in after if i not in blockers], 'ready': not blockers,
                'note': 'Only the slice pointer changes. Existing overlay overrides and pending proposals remain; this does not undo the whole workspace.'}
        # Bind confirmation to the mount table, destination bytes, all live card bytes, and pending proposals.
        live_files = {f"{r['mount']}/{r['path']}": file_sha(table.get(r['mount']).root / (r['path'] + '.md'))
                      for r in ws.index.all_cards()}
        fingerprint = {'plan': plan, 'target': target_files, 'live': live_files,
                       'mounts': (ws.root / 'mounts.toml').read_text(encoding='utf-8'),
                       'staging': inventory(ws.staging.root)}
        plan['revision'] = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if dry_run:
            return plan
        if revision is not None and revision != plan['revision']:
            raise RecoveryError('rollback preview is stale; review the target and remaining overlay again')
        if blockers:
            raise RecoveryError('rollback would introduce invalid references or cards; resolve the blockers first', plan=plan)
        record = event('rolled_back', alias=alias, previous_path=str(current.root), path=str(target), version=plan['version'])
        guards = [{'path': str(target / name), 'sha256': info['sha256']} for name, info in target_files['files'].items()]
        ws.history.transact([file_action(ws.root / 'mounts.toml', dump_mounts(projected))], [record], guards=guards)
        ws._sync(ws._reload_table())
        return dict(plan, history_event_id=record['event_id'], rolled_back=True)


def render_rollback(plan):
    lines = [f"{plan['alias']}: {plan['previous_path']} -> {plan['path']} (v{plan['version'] or 'unspecified'})",
             plan['note'], f"Overlay cards retained: {len(plan['overlay_preserved'])}",
             f"Pending proposals retained: {len(plan['pending_preserved'])}"]
    for address in plan['overlay_preserved']:
        lines.append('  Overlay: ' + address)
    if plan['overlay_same_paths']:
        lines.append('Overlay cards sharing target paths: ' + ', '.join(plan['overlay_same_paths']))
        lines.append('Use explain CARD to check which version an unqualified read selects.')
    for address in plan['pending_preserved']:
        lines.append('  Pending: ' + address)
    for issue in plan['blockers']:
        lines.append('Blocked: ' + issue['message'])
    for issue in plan['warnings']:
        lines.append('Warning: ' + issue['message'])
    return '\n'.join(lines) + '\n'
