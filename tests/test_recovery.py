"""Version rollback and portable byte-preserving backups, including failure isolation."""
import json
import shutil
from pathlib import Path
from unittest.mock import patch

from mindslice import RecoveryError, Workspace
from mindslice.storage import snapshots
from mindslice.storage.config import dump_mounts, Mount, MountTable

from .helpers import WorkspaceTestCase, card_text
from .test_interfaces import run_cli


class RollbackTests(WorkspaceTestCase):
    def versions(self):
        self.ws.write('a', summary='Version one.', reason='Initial knowledge.')
        first = Path(self.ws.bake('kb', prefix='')['path'])
        self.ws.write('a', summary='Version two.', reason='New policy.')
        second = Path(self.ws.bake('kb')['path'])
        return first, second

    def test_preview_and_switch_preserve_overlay_staging_and_mount_settings(self):
        first, second = self.versions()
        self.ws.write('a', summary='Local override still active.')
        self.ws.write('pending', summary='Unapproved.', stage=True)
        before = self.overlay_file('a').read_bytes()
        pending = self.ws.staging.file('pending').read_bytes()
        history = self.ws.history.events()
        plan = self.ws.rollback('kb', dry_run=True)
        self.assertTrue(plan['ready'], plan)
        self.assertEqual(plan['path'], str(first))
        self.assertEqual(self.ws.table().get('@kb').root, second)
        self.assertEqual(self.ws.history.events(), history)
        old_settings = self.ws.table().get('@kb')
        result = self.ws.rollback('kb', revision=plan['revision'])
        self.assertTrue(result['rolled_back'])
        self.assertEqual(self.ws.table().get('@kb').root, first)
        self.assertEqual(self.ws.table().get('@kb').precedence, old_settings.precedence)
        self.assertEqual(self.ws.table().get('@kb').role, old_settings.role)
        self.assertEqual(self.overlay_file('a').read_bytes(), before)
        self.assertEqual(self.ws.staging.file('pending').read_bytes(), pending)
        self.assertEqual(self.ws.read('a')['summary'], 'Local override still active.')
        self.assertEqual(self.ws.read('@kb/a', follow_supersedes=False)['summary'], 'Version one.')
        self.assertEqual(self.ws.history.events()[-1]['event'], 'rolled_back')
        self.assertEqual(self.ws.card_history('@kb/a')['events'][0]['event'], 'rolled_back')
        self.assertTrue(second.is_dir())

    def test_modified_target_or_new_overlay_invalidates_review(self):
        first, _ = self.versions()
        plan = self.ws.rollback('kb', dry_run=True)
        (first/'asset.bin').write_bytes(b'changed')
        with self.assertRaises(RecoveryError):
            self.ws.rollback('kb', revision=plan['revision'])
        plan = self.ws.rollback('kb', dry_run=True)
        self.ws.write('new', summary='Arrived after review.')
        with self.assertRaises(RecoveryError):
            self.ws.rollback('kb', revision=plan['revision'])

    def test_rollback_blocks_newly_broken_references(self):
        first, _ = self.versions()
        self.ws.write('only-new', summary='Added later.')
        self.ws.bake('kb', prefix='only-new')
        self.ws.write('consumer', summary='Read [[@kb/only-new]].')
        plan = self.ws.rollback('kb', first, dry_run=True)
        self.assertFalse(plan['ready'])
        self.assertTrue(any(i['code'] == 'broken_wikilink' for i in plan['blockers']))
        with self.assertRaises(RecoveryError):
            self.ws.rollback('kb', first)

    def test_missing_predecessor_invalid_target_and_overlay_are_actionable(self):
        first, second = self.versions()
        shutil.rmtree(first)
        for alias, path in [('kb', None), ('overlay', second), ('kb', self.root/'overlay'), ('kb', second)]:
            with self.assertRaises(RecoveryError):
                self.ws.rollback(alias, path)
        self.ws.unmount('kb')
        self.ws.mount(second, alias='other')
        with self.assertRaises(RecoveryError):
            self.ws.rollback('other')

    def test_failed_history_append_recovers_pointer_once(self):
        first, _ = self.versions()
        with patch.object(self.ws.history, 'append', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                self.ws.rollback('kb')
        with Workspace(self.root) as recovered:
            recovered.status()
            self.assertEqual(recovered.table().get('@kb').root, first)
            self.assertEqual(len([e for e in recovered.history.events() if e['event'] == 'rolled_back']), 1)

    def test_cli_requires_confirmation_and_supports_preview_and_yes(self):
        first, second = self.versions()
        code, out, _ = run_cli('-w', str(self.root), 'rollback', 'kb', '--dry-run', '--json')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['path'], str(first))
        code, _, err = run_cli('-w', str(self.root), 'rollback', 'kb', '--json')
        self.assertEqual(code, 1)
        self.assertIn('--yes', err)
        self.ws.status()
        self.assertEqual(self.ws.table().get('@kb').root, second)
        code, out, _ = run_cli('-w', str(self.root), 'rollback', 'kb', '--yes', '--json')
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)['rolled_back'])

    def test_recovery_refuses_modified_destination_after_interruption(self):
        first, _ = self.versions()
        with patch.object(self.ws.history, 'append', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                self.ws.rollback('kb')
        (first/'a.md').write_text(card_text('A', 'Changed during interruption.'))
        from mindslice import HistoryError
        with Workspace(self.root) as recovered:
            with self.assertRaises(HistoryError):
                recovered.status()
        self.assertTrue(self.ws.history.journal_path.exists())

    def test_invalid_destination_manifest_is_blocked_even_if_current_is_also_invalid(self):
        first, second = self.versions()
        for root in (first, second):
            (root/'slice.toml').write_text('[[invalid')
        plan = self.ws.rollback('kb', first, dry_run=True)
        self.assertFalse(plan['ready'])


class BackupTests(WorkspaceTestCase):
    def test_full_restore_survives_loss_of_original_workspace_and_external_mount(self):
        external = self.tmp/'external'
        external.mkdir()
        (external/'manual.md').write_text(card_text('Manual', 'Shared knowledge.'))
        (external/'asset.bin').write_bytes(b'\x00\xff\x01')
        self.ws.mount(external, alias='manual')
        self.ws.write('local', summary='Local knowledge.', reason='A useful lesson.')
        self.ws.write('local', op='replace', summary='Pending replacement.', stage=True, reason='Review me.')
        self.ws.write('draft', summary='Unassigned draft.', stage=True)
        (self.root/'custom.txt').write_bytes(b'user-owned file')
        (self.root/'empty').mkdir()
        (self.root/'.bake-plan.json').write_text('{}')
        self.ws.status()
        source = self.tmp/'backup'
        report = self.ws.backup(source)
        self.assertEqual(report['external_sources'], 1)
        self.assertFalse((source/'workspace/.cache').exists())
        history_before = self.ws.history.events()
        stage_before = self.ws.staging.file('local').read_bytes()
        self.ws.close()
        shutil.rmtree(self.root)
        shutil.rmtree(external)
        target = self.tmp/'recovered'
        Workspace.restore(source, target)
        with Workspace(target) as restored:
            self.assertEqual(restored.read('local')['summary'], 'Local knowledge.')
            self.assertEqual(restored.read('@manual/manual')['summary'], 'Shared knowledge.')
            self.assertEqual(restored.staging.file('local').read_bytes(), stage_before)
            self.assertEqual(restored.history.events()[:-1], history_before)
            self.assertEqual((restored.table().get('@manual').root/'asset.bin').read_bytes(), b'\x00\xff\x01')
            self.assertTrue(restored.table().get('@manual').root.is_relative_to(target))
            self.assertEqual((target/'custom.txt').read_bytes(), b'user-owned file')
            self.assertTrue((target/'empty').is_dir())
            self.assertFalse((target/'.bake-plan.json').exists())
            restored.apply(['local'])
            self.assertEqual(restored.read('local')['summary'], 'Pending replacement.')
            self.assertEqual(set(restored.staging.entries()), {'draft'})

    def test_external_old_versions_are_backed_up_and_rollback_works_after_restore(self):
        original = self.tmp/'original-slice'
        original.mkdir()
        (original/'a.md').write_text(card_text('A', 'Original baseline.'))
        self.ws.mount(original, alias='kb')
        self.ws.write('a', summary='New version.', reason='Changed baseline.')
        self.ws.bake('kb')
        backup = self.tmp/'backup'
        self.ws.backup(backup)
        self.ws.close()
        shutil.rmtree(original)
        shutil.rmtree(self.root)
        restored_root = self.tmp/'restored'
        Workspace.restore(backup, restored_root)
        with Workspace(restored_root) as ws:
            self.assertTrue(ws.explain('@kb/a')['sources'][1]['revision_recorded'])
            self.assertTrue(ws.rollback('kb', dry_run=True)['ready'])
            ws.rollback('kb')
            self.assertEqual(ws.read('@kb/a')['summary'], 'Original baseline.')
            ws.backup(self.tmp/'second-backup')
        Workspace.restore(self.tmp/'second-backup', self.tmp/'twice-restored')
        with Workspace(self.tmp/'twice-restored') as ws:
            self.assertEqual(ws.read('@kb/a')['summary'], 'Original baseline.')

    def test_missing_historical_versions_reported_but_missing_current_mount_blocks(self):
        self.ws.write('a', summary='A.')
        old = Path(self.ws.bake('kb', prefix='')['path'])
        self.ws.write('a', summary='B.')
        current = Path(self.ws.bake('kb')['path'])
        shutil.rmtree(old)
        result = self.ws.backup(self.tmp/'backup')
        self.assertIn(str(old), result['unavailable_versions'])
        shutil.rmtree(current)
        with self.assertRaises(RecoveryError):
            self.ws.backup(self.tmp/'missing')
        self.assertFalse((self.tmp/'missing').exists())

    def test_backup_and_restore_never_replace_existing_directories(self):
        output = self.tmp/'existing'
        output.mkdir()
        (output/'keep.txt').write_text('keep')
        with self.assertRaises(RecoveryError):
            self.ws.backup(output)
        source = self.tmp/'backup'
        self.ws.backup(source)
        with self.assertRaises(RecoveryError):
            Workspace.restore(source, output)
        self.assertEqual((output/'keep.txt').read_text(), 'keep')
        with self.assertRaises(RecoveryError):
            self.ws.backup(self.root/'nested-backup')
        with self.assertRaises(RecoveryError):
            Workspace.restore(source, source/'nested-restore')

    def test_modified_missing_and_extra_backup_files_fail_before_publication(self):
        self.ws.write('a', summary='A.')
        backup = self.tmp/'backup'
        self.ws.backup(backup)
        file = backup/'workspace/overlay/a.md'
        original = file.read_bytes()
        file.write_bytes(b'tampered')
        with self.assertRaises(RecoveryError):
            Workspace.restore(backup, self.tmp/'bad')
        file.write_bytes(original)
        (backup/'extra').write_text('unexpected')
        with self.assertRaises(RecoveryError):
            Workspace.restore(backup, self.tmp/'bad')
        (backup/'extra').unlink()
        file.unlink()
        with self.assertRaises(RecoveryError):
            Workspace.restore(backup, self.tmp/'bad')
        self.assertFalse((self.tmp/'bad').exists())

    def test_manifest_traversal_and_pending_journal_are_never_replayed(self):
        backup = self.tmp/'backup'
        self.ws.backup(backup)
        manifest = backup/'backup.json'
        original = manifest.read_text()
        data = json.loads(original)
        data['files']['../outside'] = {'sha256': 'x', 'size': 0}
        manifest.write_text(json.dumps(data))
        with self.assertRaises(RecoveryError):
            Workspace.restore(backup, self.tmp/'bad')
        manifest.write_text(original)
        pending = backup/'workspace/.history/.pending.json'
        pending.parent.mkdir(exist_ok=True)
        pending.write_text('{"actions": [{"path": "/outside"}]}')
        data = json.loads(original)
        data.update(snapshots.inventory(backup, ('backup.json',)))
        manifest.write_text(json.dumps(data))
        with self.assertRaises(RecoveryError):
            Workspace.restore(backup, self.tmp/'bad')
        self.assertFalse((self.tmp/'bad').exists())

    def test_symlink_is_rejected_without_following_it(self):
        link = self.root/'linked'
        try:
            link.symlink_to(self.tmp/'outside', target_is_directory=True)
        except OSError:
            self.skipTest('symlink creation not permitted')
        with self.assertRaises(RecoveryError):
            self.ws.backup(self.tmp/'backup')
        self.assertFalse((self.tmp/'backup').exists())

    def test_source_change_during_backup_fails_without_publishing(self):
        self.ws.write('a', summary='A.')
        real_copy = snapshots._copy
        def changed(source, target, listing):
            real_copy(source, target, listing)
            self.overlay_file('a').write_text(card_text('A', 'Changed while copying.'))
        with patch.object(snapshots, '_copy', side_effect=changed):
            with self.assertRaises(RecoveryError):
                self.ws.backup(self.tmp/'backup')
        self.assertFalse((self.tmp/'backup').exists())
        self.assertFalse(list(self.tmp.glob('.mindslice-backup-*')))

    def test_external_overlay_relocated_and_history_conflicts_preserved(self):
        external = self.tmp/'overlay-external'
        external.mkdir()
        table = self.ws.table()
        overlay = Mount('@overlay', str(external), 100, 'runtime', 'overlay', external)
        (self.root/'mounts.toml').write_text(dump_mounts(MountTable(overlay, table.mounts)))
        self.ws.write('a', summary='Original.')
        self.ws.write('a', op='replace', summary='Proposal.', stage=True)
        (external/'a.md').write_text(card_text('A', 'Editor change.'))
        self.ws.backup(self.tmp/'backup')
        Workspace.restore(self.tmp/'backup', self.tmp/'restored')
        with Workspace(self.tmp/'restored') as ws:
            self.assertTrue(ws.diff()['items'][0]['conflict'])
            self.assertTrue(ws.table().overlay.root.is_relative_to(ws.root))

    def test_cli_restore_does_not_require_an_open_current_workspace(self):
        code, out, err = run_cli('-w', str(self.root), 'backup', str(self.tmp/'backup'), '--json')
        self.assertEqual((code, err), (0, ''))
        code, out, err = run_cli('restore', str(self.tmp/'backup'), '--output', str(self.tmp/'restored'), '--json')
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(json.loads(out)['workspace'], str(self.tmp/'restored'))

    def test_nested_external_mounts_preserve_shared_physical_layout(self):
        external = self.tmp/'external'
        (external/'sub').mkdir(parents=True)
        (external/'a.md').write_text(card_text('A', 'Parent.'))
        (external/'sub/b.md').write_text(card_text('B', 'Child.'))
        self.ws.mount(external, alias='parent')
        self.ws.mount(external/'sub', alias='child')
        self.assertEqual(self.ws.backup(self.tmp/'backup')['external_sources'], 1)
        Workspace.restore(self.tmp/'backup', self.tmp/'restored')
        with Workspace(self.tmp/'restored') as ws:
            self.assertEqual(ws.table().get('@child').root.parent, ws.table().get('@parent').root)
            self.assertEqual(ws.read('@child/b')['summary'], 'Child.')

    def test_existing_restore_storage_namespace_is_preserved(self):
        (self.root/'.restored-mounts').mkdir()
        (self.root/'.restored-mounts/keep').write_text('existing user data')
        external = self.tmp/'external'
        external.mkdir()
        (external/'a.md').write_text(card_text('A', 'External.'))
        self.ws.mount(external, alias='kb')
        self.ws.backup(self.tmp/'backup')
        Workspace.restore(self.tmp/'backup', self.tmp/'restored')
        with Workspace(self.tmp/'restored') as ws:
            self.assertEqual((ws.root/'.restored-mounts/keep').read_text(), 'existing user data')
            self.assertIn('.restored-mounts-2', str(ws.table().get('@kb').root))

    def test_unfinished_apply_recovers_before_snapshot(self):
        from mindslice.operations import staging
        self.ws.write('a', summary='Accepted after recovery.', stage=True)
        with patch.object(staging, 'durable_move', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                self.ws.apply(['a'])
        self.ws.backup(self.tmp/'backup')
        self.assertFalse((self.tmp/'backup/workspace/staging/.apply_journal.json').exists())
        Workspace.restore(self.tmp/'backup', self.tmp/'restored')
        with Workspace(self.tmp/'restored') as ws:
            self.assertEqual(ws.read('a')['summary'], 'Accepted after recovery.')
            self.assertEqual(ws.diff()['items'], [])

    def test_restore_copy_failure_leaves_source_and_existing_workspaces_intact(self):
        self.ws.write('a', summary='Original.')
        self.ws.backup(self.tmp/'backup')
        with patch.object(snapshots, '_copy', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                Workspace.restore(self.tmp/'backup', self.tmp/'restored')
        self.assertFalse((self.tmp/'restored').exists())
        self.assertFalse(list(self.tmp.glob('.mindslice-restore-*')))
        self.assertTrue((self.tmp/'backup/backup.json').is_file())
        self.assertEqual(self.ws.read('a')['summary'], 'Original.')

    def test_partial_history_tail_is_not_silently_removed_by_backup(self):
        self.ws.write('a', summary='A.')
        with self.ws.history.path.open('ab') as stream:
            stream.write(b'{"incomplete":')
        with self.assertRaises(RecoveryError):
            self.ws.backup(self.tmp/'backup')
        self.assertTrue(self.ws.history.path.read_bytes().endswith(b'{"incomplete":'))

    def test_read_only_slice_files_can_be_copied_and_restored(self):
        root = self.mount_slice('kb', {'a': card_text('A', 'Read-only baseline.')}, '@kb', 50, 'curated')
        source = root/'a.md'
        source.chmod(0o444)
        try:
            self.ws.backup(self.tmp/'backup')
            Workspace.restore(self.tmp/'backup', self.tmp/'restored')
            with Workspace(self.tmp/'restored') as ws:
                self.assertEqual(ws.read('@kb/a')['summary'], 'Read-only baseline.')
        finally:
            # Windows also uses the read-only flag when deleting temporary fixtures.
            for file in self.tmp.rglob('a.md'):
                file.chmod(0o644)
