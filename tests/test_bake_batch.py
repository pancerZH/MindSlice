"""Workspace bake: mixed destinations, full-plan validation, review and recoverable execution."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from mindslice import BakeConflictError, Workspace
from mindslice.baking import bake_batch
from .helpers import WorkspaceTestCase, card_text
from .test_interfaces import run_cli


class BatchBakeTests(WorkspaceTestCase):
    def test_mixed_updates_new_cards_and_new_slices(self):
        original = self.project({'api/auth': card_text('Auth', 'Original token policy.')})
        before = (original / 'api/auth.md').read_bytes()
        self.ws.write('api/auth', summary='Revised token policy.', reason='Changed policy.')
        self.ws.write('project/support', summary='New support process.')
        self.ws.write('research/data', summary='Dataset procedure.')
        self.ws.write('research/eval', summary='Use [[research/data]] and [[api/auth]].')
        plan = self.ws.bake(dry_run=True)
        self.assertEqual(plan['assignments'], {'api/auth': '@project'})
        self.assertEqual(set(plan['unassigned']), {'project/support', 'research/data', 'research/eval'})
        self.assertFalse((self.root / bake_batch.PLAN_FILE).exists())
        plan = self.ws.plan_bake({'project/support': 'project', 'research/data': 'research', 'research/eval': 'research'})
        self.assertTrue(plan['ready'], plan['blockers'])
        result = self.ws.bake(plan=plan)
        self.assertEqual(len(result['baked']), 2)
        self.assertEqual(result['remaining_overlay_cards'], [])
        records = {r['alias']: r for r in result['baked']}
        self.assertEqual(records['@project']['previous_path'], str(original))
        self.assertEqual(records['@project']['version'], '1.0.1')
        self.assertEqual(records['@research']['dependencies'], ['@project'])
        self.assertIn('[[@project/api/auth]]', (Path(records['@research']['path'])/'research/eval.md').read_text())
        self.assertEqual((original/'api/auth.md').read_bytes(), before)
        self.assertTrue(self.ws.validate()['ok'])
        baked = [e for e in self.ws.history.events() if e['event'] == 'baked']
        self.assertEqual(len(baked), 2)
        self.assertEqual(len(baked[0]['change_ids']) + len(baked[1]['change_ids']), 4)

    def test_ambiguous_relationships_require_assignment(self):
        self.project({'rule': card_text('Rule', 'Project rule.')})
        self.mount_slice('other', {'rule': card_text('Rule', 'Other rule.')}, '@other', 40, 'baseline')
        self.ws.write('rule', summary='Ambiguous update.')
        plan = self.ws.plan_bake()
        self.assertEqual(plan['cards'][0]['candidates'], ['@other', '@project'])
        self.assertEqual(plan['unassigned'], ['rule'])
        with self.assertRaises(BakeConflictError):
            self.ws.bake()
        self.assertTrue(self.overlay_file('rule').exists())

    def test_pending_edits_are_excluded_and_staged_only_references_keep_copies(self):
        self.ws.write('existing', summary='Applied content.')
        self.ws.write('existing', op='append', content='- Pending edit.', stage=True)
        self.ws.write('topic/rule', summary='Shared rule.')
        self.ws.write('draft', summary='See [[topic/rule]].', stage=True)
        staged_before = self.ws.staging.file('draft').read_bytes()
        plan = self.ws.plan_bake({'topic/rule': 'topic'})
        self.assertTrue(plan['ready'], plan['blockers'])
        self.assertEqual(plan['deferred'], ['existing'])
        self.assertEqual(len(plan['pending_review']), 2)
        self.assertEqual(plan['retained_overlay_cards'][0]['address'], '@overlay/topic/rule')
        result = self.ws.bake(plan=plan)
        self.assertEqual(result['remaining_overlay_cards'], ['existing', 'topic/rule'])
        self.assertEqual(self.ws.staging.file('draft').read_bytes(), staged_before)
        self.ws.apply()
        self.assertTrue(self.ws.validate()['ok'])

    def test_assigning_pending_card_blocks_whole_plan(self):
        self.ws.write('a', summary='A.')
        self.ws.write('b', summary='B.')
        self.ws.write('b', op='append', content='- Draft.', stage=True)
        plan = self.ws.plan_bake({'a': 'first', 'b': 'second'})
        self.assertFalse(plan['ready'])
        with self.assertRaises(BakeConflictError):
            self.ws.bake(plan=plan)
        self.assertFalse((self.root/'slices/first.slice').exists())
        self.assertTrue(self.overlay_file('a').exists())

    def test_deferred_referrer_is_rewritten_once_for_multiple_destinations(self):
        self.ws.write('a', summary='A.')
        self.ws.write('b', summary='B.')
        self.ws.write('diary', summary='See [[a]] and [[b]].')
        plan = self.ws.plan_bake({'a':'one', 'b':'two', 'diary':None})
        self.assertTrue(plan['ready'])
        self.ws.bake(plan=plan)
        text = self.overlay_file('diary').read_text()
        self.assertIn('[[@one/a]]', text)
        self.assertIn('[[@two/b]]', text)
        self.assertEqual(len([e for e in self.ws.history.events() if e.get('op') == 'rebase']), 1)

    def test_selected_card_cannot_depend_on_deferred_overlay(self):
        self.ws.write('a', summary='See [[b]].')
        self.ws.write('b', summary='B.')
        plan = self.ws.plan_bake({'a':'one', 'b':None})
        self.assertFalse(plan['ready'])
        self.assertTrue(any('needs a destination' in b['reason'] for b in plan['blockers']))

    def test_baseline_refs_to_moving_cards_are_rewritten_in_the_new_version(self):
        self.ws.write('topic/item', summary='Item.')
        original = self.mount_slice('project-kb', {'guide': card_text('Guide', 'See [[@overlay/topic/item]].')},
                                    '@project', 50, 'curated', dependencies=['topic'])
        self.ws.write('addition', summary='New project fact.', extends=['@project/guide'])
        plan = self.ws.plan_bake({'topic/item':'topic'})
        self.assertTrue(plan['ready'], plan['blockers'])
        result = self.ws.bake(plan=plan)
        project = next(r for r in result['baked'] if r['alias'] == '@project')
        self.assertIn('[[@topic/topic/item]]', (Path(project['path'])/'guide.md').read_text())
        self.assertEqual(project['dependencies'], ['@topic'])
        self.assertEqual(project['dependencies_added'], [])
        self.assertIn('[[@overlay/topic/item]]', (original/'guide.md').read_text())
        self.assertFalse(self.overlay_file('topic/item').exists())
        self.assertTrue(self.ws.validate()['ok'])

    def test_unchanged_read_only_references_preserve_overlay_copy(self):
        self.ws.write('note', summary='Note.')
        self.project({'pointer': card_text('Pointer', 'See [[@overlay/note]].')})
        plan = self.ws.plan_bake({'note':'notes'})
        self.assertTrue(plan['ready'])
        result = self.ws.bake(plan=plan)
        self.assertEqual(result['remaining_overlay_cards'], ['note'])
        self.assertTrue(self.ws.validate()['ok'])

    def test_self_extension_and_broken_reference_block_before_output(self):
        self.project({'rule':card_text('Rule', 'Original.')})
        self.ws.write('rule', summary='Extension.', extends=['@project/rule'])
        self.ws.write('bad', summary='Missing [[target]].')
        plan = self.ws.plan_bake({'bad':'new'})
        self.assertFalse(plan['ready'])
        reasons = ' '.join(b['reason'] for b in plan['blockers'])
        self.assertIn('consolidate', reasons)
        self.assertIn('unresolved', reasons)
        with self.assertRaises(BakeConflictError):
            self.ws.bake(plan=plan)
        self.assertFalse((self.root/'slices/new.slice').exists())

    def test_explicit_new_slice_refs_and_projected_cycles(self):
        self.put_overlay('a', card_text('A', 'A.', extends=['@new/b']))
        self.put_overlay('b', card_text('B', 'B.', extends=['@new/a']))
        plan = self.ws.plan_bake({'a':'new', 'b':'new'})
        self.assertFalse(plan['ready'])
        self.assertTrue(any('cycle' in b['reason'] for b in plan['blockers']))
        self.put_overlay('b', card_text('B', 'B.'))
        plan = self.ws.plan_bake({'a':'new', 'b':'new'})
        self.assertTrue(plan['ready'], plan['blockers'])
        self.ws.bake(plan=plan)
        self.assertTrue(self.ws.validate()['ok'])

    def test_resume_remembers_unchanged_choices_and_rechecks_changed_cards(self):
        self.ws.write('a', summary='A.')
        self.ws.write('b', summary='B.')
        plan = self.ws.plan_bake({'a':'one', 'b':None})
        bake_batch.save_plan(self.ws, plan)
        self.assertEqual(self.ws.plan_bake()['assignments'], {'a':'@one', 'b':None})
        self.ws.write('a', op='append', content='- Changed.')
        resumed = self.ws.plan_bake()
        self.assertNotIn('a', resumed['assignments'])
        self.assertEqual(resumed['unassigned'], ['a'])
        self.assertIn('b', resumed['deferred'])
        with self.assertRaises(BakeConflictError):
            self.ws.bake(plan=plan)
        with self.assertRaises(BakeConflictError):
            self.ws.bake(plan=plan, dry_run=True)

    def test_stale_baseline_asset_and_output_collisions_require_new_review(self):
        baseline = self.project({'base':card_text('Base', 'Base.')})
        asset = baseline/'asset.txt'
        asset.write_text('before')
        self.ws.write('note', summary='Note.', extends=['@project/base'])
        plan = self.ws.plan_bake()
        asset.write_text('after')
        with self.assertRaises(BakeConflictError):
            self.ws.bake(plan=plan)
        plan = self.ws.plan_bake()
        Path(plan['slices'][0]['path']).mkdir()
        with self.assertRaises(BakeConflictError):
            self.ws.bake(plan=plan)
        self.assertTrue(self.overlay_file('note').exists())

    def test_output_names_are_reserved_across_batch(self):
        self.mount_slice('same', {'a':card_text('A','A.')}, '@a', 30, 'curated')
        other = self.tmp/'elsewhere/same.slice'
        other.mkdir(parents=True)
        (other/'b.md').write_text(card_text('B','B.'))
        self.ws.mount(other, alias='b')
        self.ws.write('a', summary='New A.')
        self.ws.write('b', summary='New B.')
        plan = self.ws.plan_bake()
        self.assertEqual(len({s['path'] for s in plan['slices']}), 2)
        self.assertEqual(len(self.ws.bake(plan=plan)['baked']), 2)
        from mindslice.storage.config import load_slice_manifest
        self.assertEqual(load_slice_manifest(self.ws.table().get('@b').root).version, '0.1.0')

    def test_precommit_publication_failure_cleans_up_outputs(self):
        self.ws.write('a', summary='A.')
        self.ws.write('b', summary='B.')
        plan = self.ws.plan_bake({'a':'one','b':'two'})
        mounts = (self.root/'mounts.toml').read_bytes()
        real_rename = bake_batch.os.rename
        calls = []
        def fail_second(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                raise OSError('publication failed')
            return real_rename(src, dst)
        with patch('mindslice.baking.bake_batch.os.rename', side_effect=fail_second):
            with self.assertRaises(OSError):
                self.ws.bake(plan=plan)
        self.assertEqual((self.root/'mounts.toml').read_bytes(), mounts)
        self.assertTrue(self.overlay_file('a').exists())
        self.assertTrue(all(not Path(s['path']).exists() for s in plan['slices']))

    def test_batch_history_failure_recovers_all_mounts_once(self):
        self.ws.write('a', summary='A.', reason='First topic.')
        self.ws.write('b', summary='See [[a]].', reason='Second topic.')
        plan = self.ws.plan_bake({'a':'one','b':'two'})
        bake_batch.save_plan(self.ws, plan)
        with patch.object(self.ws.history, 'append', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.ws.bake(plan=plan)
        self.assertTrue(self.ws.history.has_journal())
        self.ws.close()
        self.ws = Workspace(self.root)
        self.assertTrue(self.ws.validate()['ok'])
        self.assertIsNotNone(self.ws.table().get('@one'))
        self.assertIsNotNone(self.ws.table().get('@two'))
        self.assertFalse(self.ws.history.has_journal())
        self.assertFalse((self.root/bake_batch.PLAN_FILE).exists())
        events = [e for e in self.ws.history.events() if e['event'] == 'baked']
        self.assertEqual(len(events), 2)
        self.assertEqual(self.ws.plan_bake()['cards'], [])

    def test_editor_change_during_publication_never_gets_retired(self):
        self.ws.write('a', summary='Before.')
        plan = self.ws.plan_bake({'a':'one'})
        rename = bake_batch.os.rename
        def edit_during_publish(src, dst):
            rename(src, dst)
            self.overlay_file('a').write_text(card_text('A','Edited while baking.'))
        with patch('mindslice.baking.bake_batch.os.rename', side_effect=edit_during_publish):
            with self.assertRaises(BakeConflictError):
                self.ws.bake(plan=plan)
        self.assertIn('Edited while baking.', self.overlay_file('a').read_text())
        self.assertFalse(Path(plan['slices'][0]['path']).exists())
        self.assertIsNone(self.ws._reload_table().get('@one'))

    def test_same_size_same_mtime_edits_do_not_reuse_stale_reasons(self):
        import os
        self.ws.write('a', summary='Before.', reason='Old reason.')
        file = self.overlay_file('a')
        stat = file.stat()
        file.write_text(file.read_text().replace('Before.', 'After!.'))
        os.utime(file, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        plan = self.ws.plan_bake({'a':'one'})
        self.assertNotIn('changes', plan['cards'][0])
        self.assertEqual(plan['cards'][0]['summary'], 'After!.')

    def test_all_deferred_and_empty_workspaces_have_uniform_receipts(self):
        self.assertEqual(self.ws.bake()['baked'], [])
        self.ws.write('a', summary='A.')
        self.ws.write('draft', summary='Draft.', stage=True)
        result = self.ws.bake(plan=self.ws.plan_bake({'a':None}))
        self.assertEqual(result['baked'], [])
        self.assertEqual(result['pending_review'], 1)
        self.assertEqual(result['remaining_overlay_cards'], ['a'])

    def test_snapshot_rechecked_between_plan_reads(self):
        self.ws.write('a', summary='A.')
        real = bake_batch.overlay_cards
        def read_then_edit(ws, table):
            result = real(ws, table)
            self.overlay_file('a').write_text(card_text('A', 'Changed after read.'))
            return result
        with patch('mindslice.baking.bake_batch.overlay_cards', side_effect=read_then_edit):
            with self.assertRaises(BakeConflictError):
                self.ws.plan_bake({'a':'one'}, resume=False)


class BatchBakeCLITests(WorkspaceTestCase):
    def cli(self, *args, **kw):
        return run_cli('-w', str(self.root), 'bake', *args, **kw)

    def test_noninteractive_dry_run_then_assignment_and_receipt(self):
        self.ws.write('topic/a', summary='A.')
        code, out, err = self.cli('--dry-run', '--json')
        self.assertEqual((code, err), (0,''))
        self.assertEqual(json.loads(out)['unassigned'], ['topic/a'])
        self.assertFalse((self.root/bake_batch.PLAN_FILE).exists())
        code, out, err = self.cli('--yes', '--json')
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(err)['code'], 'bake_conflict')
        self.assertFalse(out)
        code, out, err = self.cli('--assign', 'topic/=topic', '--yes', '--json')
        self.assertEqual((code, err), (0,''))
        self.assertTrue(Path(json.loads(out)['baked'][0]['path']).is_dir())

    def test_json_plan_file_and_stale_review(self):
        self.ws.write('a', summary='A.')
        code, out, err = self.cli('--assign', 'a=one', '--dry-run', '--json')
        plan_file = self.tmp/'plan.json'
        plan_file.write_text(out)
        self.ws.write('a', op='append', content='- New information.')
        code, _, err = self.cli('--plan', str(plan_file), '--yes', '--json')
        self.assertEqual(code,1)
        self.assertIn('stale', json.loads(err)['message'])
        code, out, _ = self.cli('--assign', 'a=one', '--dry-run', '--json')
        plan_file.write_text(out)
        code, out, err = self.cli('--plan', str(plan_file), '--yes', '--json')
        self.assertEqual((code,err),(0,''))
        self.assertEqual(len(json.loads(out)['baked']),1)

    def test_resolved_noninteractive_plan_requires_yes_and_explicit_alias_unchanged(self):
        self.ws.write('a', summary='A.')
        code, _, err = self.cli('--assign', 'a=one', '--json')
        self.assertEqual(code, 1)
        self.assertIn('review required', json.loads(err)['message'])
        code, out, err = self.cli('one', '--prefix', '', '--json')
        self.assertEqual((code,err),(0,''))
        self.assertEqual(json.loads(out)['alias'], '@one')

    def test_interactive_group_assignment_inspection_and_confirmation(self):
        self.ws.write('topic/a', summary='A.', reason='User requested it.')
        self.ws.write('topic/b', summary='B.')
        with patch('sys.stdin.isatty', return_value=True), patch('mindslice.interfaces.bake_review._answer',
                side_effect=['inspect','new','inspect','bake all']):
            code, out, err = self.cli()
        self.assertEqual(code,0,err)
        self.assertIn('User requested it.',err)
        self.assertIn('Baked 1 slice(s)', out)
        self.assertIn('@new  v0.1.0', out)

    def test_cancel_persists_group_choices_for_resume(self):
        self.ws.write('topic/a',summary='A.')
        with patch('sys.stdin.isatty',return_value=True), patch('mindslice.interfaces.bake_review._answer',side_effect=['new','cancel']):
            code,out,err=self.cli()
        self.assertEqual(code,0,err)
        self.assertIn('Bake cancelled', out)
        self.assertTrue(self.overlay_file('topic/a').exists())
        self.assertEqual(self.ws.plan_bake()['assignments'],{'topic/a':'@new'})
        code,out,err=self.cli('--yes', '--json')
        self.assertEqual(code,0,err)
        self.assertEqual(len(json.loads(out)['baked']),1)

    def test_defer_and_invalid_selections(self):
        self.ws.write('a',summary='A.')
        self.ws.write('b',summary='B.')
        code,out,err=self.cli('--assign','a=one','--defer','b','--yes','--json')
        self.assertEqual(code,0,err)
        self.assertEqual(json.loads(out)['remaining_overlay_cards'],['b'])
        for args in [('--assign','missing=new'),('--assign','b=overlay'),('--prefix',''),('one','--yes')]:
            with self.subTest(args=args):
                code,_,err=self.cli(*args)
                self.assertEqual(code,1)

    def test_plan_output_collision_is_not_silently_replanned(self):
        self.ws.write('a', summary='A.')
        _, out, _ = self.cli('--assign', 'a=one', '--dry-run', '--json')
        plan = json.loads(out)
        plan_file = self.tmp/'plan.json'
        plan_file.write_text(out)
        Path(plan['slices'][0]['path']).mkdir()
        code, _, err = self.cli('--plan', str(plan_file), '--yes', '--json')
        self.assertEqual(code, 1)
        self.assertIn('stale', json.loads(err)['message'])
        self.assertTrue(self.overlay_file('a').exists())

    def test_interactive_split_edit_and_eof(self):
        self.ws.write('topic/a', summary='A.')
        self.ws.write('topic/b', summary='B.')
        with patch('sys.stdin.isatty', return_value=True), patch('mindslice.interfaces.bake_review._answer',
                side_effect=['split', 'bad alias', 'one', 'two', 'edit', 'topic/b', 'one', 'bake']):
            code, out, err = self.cli()
        self.assertEqual(code, 0, err)
        self.assertIn('Baked 1 slice(s)', out)
        self.ws.write('next', summary='Next.')
        with patch('sys.stdin.isatty', return_value=True), patch('mindslice.interfaces.bake_review._answer', side_effect=EOFError):
            code, out, err = self.cli()
        self.assertEqual(code, 0, err)
        self.assertIn('Bake cancelled', out)

    def test_invalid_plan_is_a_structured_error(self):
        plan = self.tmp/'invalid.json'
        plan.write_text('{"schema_version": 1, "assignments": {}, "cards": [null]}')
        code, out, err = self.cli('--plan', str(plan), '--yes', '--json')
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(err)['code'], 'invalid_arguments')
        self.assertEqual(out, '')

    def test_human_dry_run_shows_card_destinations_and_reasons(self):
        self.ws.write('a', summary='A.', reason='User correction.')
        from mindslice.interfaces.bake_review import render_plan
        text = render_plan(self.ws.plan_bake({'a':'one'}), details=True)
        self.assertIn('@overlay/a → @one', text)
        self.assertIn('User correction.', text)
        # Format follows --json only, not whether stdout is a terminal (run_cli's stdout is not).
        code, out, err = self.cli('--assign', 'a=one', '--dry-run')
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(out, text)
