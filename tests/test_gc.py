"""gc(): older versions of mounted slices and leftovers of killed writes go; everything else stays."""
import json
import shutil
from pathlib import Path
from unittest.mock import patch

from mindslice import RecoveryError
from mindslice.storage.history import file_action

from .helpers import WorkspaceTestCase
from .test_interfaces import run_cli


class GcTests(WorkspaceTestCase):
    def versions(self):
        self.ws.write('a', summary='Version one.')
        first = Path(self.ws.bake('kb', prefix='')['path'])
        self.ws.write('a', summary='Version two.')
        second = Path(self.ws.bake('kb')['path'])
        return first, second

    def test_older_versions_go_and_the_mounted_one_stays(self):
        first, second = self.versions()
        self.ws.write('a', summary='Version three.')
        third = Path(self.ws.bake('kb')['path'])
        preview = self.ws.gc(dry_run=True)
        self.assertEqual([i['path'] for i in preview['old_versions']], sorted([str(first), str(second)]))
        self.assertTrue(first.is_dir() and second.is_dir())
        self.assertGreater(preview['bytes'], 0)
        result = self.ws.gc()
        self.assertFalse(result['dry_run'])
        self.assertEqual(result['old_versions'], preview['old_versions'])
        self.assertFalse(first.exists() or second.exists())
        self.assertEqual(self.ws.table().get('@kb').root, third)
        self.assertEqual(self.ws.read('@kb/a')['summary'], 'Version three.')
        self.assertTrue(self.ws.validate()['ok'])
        with self.assertRaises(RecoveryError):  # the recorded predecessor is gone
            self.ws.rollback('kb', dry_run=True)
        self.assertEqual(self.ws.gc()['old_versions'], [])

    def test_unmounted_slices_and_plain_folders_are_kept(self):
        self.versions()
        self.ws.write('x', summary='Other.')
        other = Path(self.ws.bake('other', prefix='')['path'])
        self.ws.unmount('other')
        notes = self.root / 'slices' / 'kb'  # a folder of notes named like the mounted alias, no slice.toml
        notes.mkdir()
        (notes / 'n.md').write_text('# Note\n', encoding='utf-8')
        git = self.root / 'slices' / '.git'
        git.mkdir()
        result = self.ws.gc()
        self.assertEqual({(i['path'], i['alias']) for i in result['kept_unmounted']},
                         {(str(other), '@other'), (str(notes), None)})
        self.assertTrue(other.is_dir() and notes.is_dir() and git.is_dir())

    def test_output_of_a_killed_bake_is_removed(self):
        first, second = self.versions()
        orphan = self.root / 'slices' / 'kb-9.slice'  # renamed into place, mount table never switched
        shutil.copytree(second, orphan)
        result = self.ws.gc()
        self.assertEqual(result['old_versions'], [{'path': str(orphan), 'alias': '@kb'},
                                                  {'path': str(first), 'alias': '@kb'}])
        self.assertTrue(second.is_dir())
        self.assertFalse(orphan.exists())

    def test_leftover_temporary_files_and_directories_are_removed(self):
        _, second = self.versions()
        self.ws.write('deep/card', summary='Nested.')
        leftovers = [self.root / '.mounts.toml.ab12cd_9.tmp', self.root / 'overlay' / 'deep' / '.card.md.qwertyui.tmp',
                     self.root / 'overlay' / '.top.md.lkjhgfds.tmp', self.root / 'staging' / '.manifest.json.zxcvbnm1.tmp',
                     self.root / 'staging' / 'deep' / '.card.md.mnbvcxz1.tmp',
                     self.root / '.history' / '.changes.jsonl.a1b2c3d4.tmp']
        for path in leftovers:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('partial', encoding='utf-8')
        staged_dirs = [self.root / 'slices' / '.bake-k3j4h5g6', self.root / 'slices' / f'.{second.name}.p0o9i8u7']
        for directory in staged_dirs:
            (directory / 'tree').mkdir(parents=True)
            (directory / 'tree' / 'a.md').write_text('# A\n', encoding='utf-8')
        (self.root / 'overlay' / '.git').mkdir()
        kept = [self.root / 'overlay' / '.notes', self.root / 'overlay' / '.card.md.short.tmp',
                self.root / 'overlay' / '.git' / '.index.lock.ab12cd34.tmp', self.root / 'slices' / 'a-notes.zip',  # a file sorts before the old version
                self.root / '.history' / '.batch.json.txt', self.ws.cache_dir / '.clients.json.ab12cd34.tmp',
                self.root / 'slices' / '.DS_Store']
        for path in kept:
            path.write_text('keep', encoding='utf-8')
        preview = self.ws.gc(dry_run=True)
        self.assertEqual(sorted(preview['temporary']), sorted(str(p) for p in leftovers + staged_dirs))
        self.assertEqual(preview['old_versions'], [{'path': str(self.root / 'slices' / 'kb.slice'), 'alias': '@kb'}])
        self.assertEqual(preview['kept_unmounted'], [])
        old = self.root / 'slices' / 'kb.slice'
        files = leftovers + [d / 'tree' / 'a.md' for d in staged_dirs] + [p for p in old.rglob('*') if p.is_file()]
        expected = sum(p.stat().st_size for p in files)  # write_text writes \r\n on Windows
        self.assertEqual(preview['bytes'], expected)
        self.assertTrue(all(p.exists() for p in leftovers + staged_dirs))
        self.ws.gc()
        self.assertFalse(any(p.exists() for p in leftovers + staged_dirs))
        self.assertTrue(all(p.exists() for p in kept))
        self.assertEqual(self.ws.read('deep/card')['summary'], 'Nested.')
        self.assertTrue(second.is_dir())

    def test_links_nested_mounts_and_a_missing_slices_folder(self):
        first, second = self.versions()
        link = self.root / 'slices' / 'link.slice'
        link.symlink_to(first, target_is_directory=True)
        bundle = self.root / 'slices' / 'bundle'  # looks like an old version, but a mount lives inside it
        shutil.copytree(second, bundle)
        (bundle / 'inner').mkdir()
        (bundle / 'inner' / 'n.md').write_text('# N\n', encoding='utf-8')
        self.ws.mount(bundle / 'inner', alias='inner')
        result = self.ws.gc()
        self.assertEqual(result['old_versions'], [{'path': str(first), 'alias': '@kb'}])
        self.assertTrue(link.is_symlink() and bundle.is_dir())
        self.ws.unmount('inner')
        shutil.rmtree(bundle)
        link.unlink()
        shutil.rmtree(self.root / 'slices', ignore_errors=True)
        self.ws.unmount('kb')
        self.assertEqual(self.ws.gc(), {'dry_run': False, 'old_versions': [], 'temporary': [], 'kept_unmounted': [],
                                        'bytes': 0})

    def test_render(self):
        from mindslice.operations.gc import render_gc
        result = {'dry_run': True, 'old_versions': [{'path': '/w/slices/a.slice', 'alias': '@a'}],
                  'temporary': ['/w/.x.abcdefgh.tmp'],
                  'kept_unmounted': [{'path': '/w/slices/b.slice', 'alias': '@b'}, {'path': '/w/slices/n', 'alias': None}],
                  'bytes': 42}
        self.assertEqual(render_gc(result), 'Would remove old version of @a: /w/slices/a.slice\n'
                                            'Would remove leftover: /w/.x.abcdefgh.tmp\n'
                                            'Kept unmounted slice (@b): /w/slices/b.slice\n'
                                            'Kept unmounted slice (no slice.toml alias): /w/slices/n\n'
                                            'Would remove 2 item(s), 42 bytes.\n')
        self.assertEqual(render_gc(dict(result, dry_run=False, kept_unmounted=[])),
                         'Removed old version of @a: /w/slices/a.slice\nRemoved leftover: /w/.x.abcdefgh.tmp\n'
                         'Removed 2 item(s), 42 bytes.\n')
        self.assertEqual(render_gc({'dry_run': True, 'old_versions': [], 'temporary': [],
                                    'kept_unmounted': [{'path': '/w/slices/b.slice', 'alias': '@b'}], 'bytes': 0}),
                         'Kept unmounted slice (@b): /w/slices/b.slice\nNothing to remove.\n')

    def test_the_patterns_match_the_names_writers_give_their_temporary_files(self):
        import tempfile
        from mindslice.operations.gc import TEMP_FILE, TEMP_SLICE
        made = []

        def recording(real):
            def wrapper(*args, **kwargs):
                result = real(*args, **kwargs)
                made.append(Path(result[1] if isinstance(result, tuple) else result))
                return result
            return wrapper

        with patch('mindslice.storage.fsutil.tempfile.mkstemp', recording(tempfile.mkstemp)), \
                patch('mindslice.baking.bake.tempfile.mkdtemp', recording(tempfile.mkdtemp)), \
                patch('mindslice.baking.bake_batch.tempfile.mkdtemp', recording(tempfile.mkdtemp)), \
                patch('mindslice.baking.archive.tempfile.mkstemp', recording(tempfile.mkstemp)):
            self.ws.write('a', summary='One.')
            self.ws.bake('kb', prefix='')  # named bake
            self.ws.bake('kb', self.root / 'slices' / 'kb.zip', drop=['a'])  # archive output
            self.ws.write('b', summary='Two.')
            self.ws.bake(plan=self.ws.plan_bake({'b': 'kb'}, resume=False))  # workspace bake
        in_slices = [p for p in made if p.parent == self.root / 'slices']
        others = [p for p in made if p.parent != self.root / 'slices' and self.root in p.parents]
        self.assertTrue(in_slices and others)
        self.assertEqual([p.name for p in in_slices if not TEMP_SLICE.fullmatch(p.name)], [])
        self.assertEqual([p.name for p in others if not TEMP_FILE.fullmatch(p.name)], [])

    def test_an_interrupted_transaction_is_finished_first(self):
        target = self.root / 'overlay' / 'late.md'
        journal = {'version': 1, 'actions': [file_action(target, '# Late\n')], 'events': [], 'guards': []}
        self.ws.history.root.mkdir(exist_ok=True)
        self.ws.history.journal_path.write_text(json.dumps(journal), encoding='utf-8')
        self.ws.gc()
        self.assertFalse(self.ws.history.has_journal())
        self.assertEqual(target.read_text(encoding='utf-8'), '# Late\n')

    def test_cli_preview_and_run(self):
        first, _ = self.versions()
        code, out, _ = run_cli('-w', str(self.root), 'gc', '--dry-run')
        self.assertEqual(code, 0)
        self.assertIn('Would remove old version of @kb', out)
        self.assertTrue(first.is_dir())
        code, out, _ = run_cli('-w', str(self.root), 'gc', '--json')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['old_versions'][0]['path'], str(first))
        self.assertFalse(first.exists())
        code, out, _ = run_cli('-w', str(self.root), 'gc')
        self.assertEqual((code, out), (0, 'Nothing to remove.\n'))
