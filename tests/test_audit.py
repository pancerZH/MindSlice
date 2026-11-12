"""History remains inspectable after retirement; explanations match actual read policy."""
import json

from .helpers import WorkspaceTestCase, card_text
from .test_interfaces import run_cli


class AuditTests(WorkspaceTestCase):
    def test_history_connects_proposal_apply_bake_and_deleted_overlay(self):
        self.ws.write('rule', summary='New rule.', reason='A reviewed decision.', stage=True)
        self.ws.apply(['rule'])
        self.ws.bake('kb', prefix='')
        events = self.ws.card_history('@kb/rule')['events']
        self.assertEqual([e['event'] for e in events], ['baked', 'applied', 'proposed'])
        self.assertEqual(events[1]['reason'], 'A reviewed decision.')
        self.assertFalse(self.overlay_file('rule').exists())
        self.assertEqual(self.ws.card_history('@overlay/rule')['total'], 3)
        first = self.ws.card_history('@kb/rule', limit=1)
        self.assertEqual(first['next_offset'], 1)
        self.assertEqual(self.ws.card_history('@kb/rule', offset=1)['events'][0]['event'], 'applied')
        self.assertFalse(first['content_snapshots'])

    def test_history_filters_other_cards_reasons_in_batch_bake(self):
        self.ws.write('a', summary='A.', reason='Reason A.')
        self.ws.write('b', summary='B.', reason='Reason B.')
        self.ws.bake('kb', prefix='')
        result = self.ws.card_history('@kb/a')
        self.assertNotIn('Reason B.', json.dumps(result))
        self.assertEqual(len(result['events'][0]['cards']), 1)

    def test_discard_delete_and_unknown_addresses(self):
        self.ws.write('draft', summary='Wrong proposal.', stage=True, reason='Testing.')
        self.ws.discard(['draft'])
        self.assertEqual(self.ws.card_history('draft')['events'][0]['event'], 'discarded')
        self.ws.write('live', summary='Temporary fact.')
        self.ws.write('live', op='delete', reason='No longer wanted.')
        self.assertEqual(self.ws.card_history('live')['events'][0]['reason'], 'No longer wanted.')
        self.assertEqual(self.ws.card_history('@unknown/missing')['total'], 0)
        with self.assertRaises(ValueError):
            self.ws.card_history(limit=-1)

    def test_explain_matches_read_trust_policy_and_does_not_increment_telemetry(self):
        self.mount_slice('kb', {'rule': card_text('Rule', 'Original.')}, '@kb', 50, 'curated')
        self.ws.write('new-rule', summary='Replacement.', supersedes=['@kb/rule'], reason='Policy changed.')
        expected = self.ws.read('@kb/rule')['address']
        before = self.ws.index.conn.execute('SELECT * FROM telemetry').fetchall()
        result = self.ws.explain('@kb/rule')
        self.assertEqual(result['resolved'], expected)
        self.assertEqual(result['lineage_path'], ['@kb/rule', '@overlay/new-rule'])
        self.assertEqual(result['sources'][1]['changes'][0]['reason'], 'Policy changed.')
        self.assertEqual([tuple(r) for r in self.ws.index.conn.execute('SELECT * FROM telemetry')], [tuple(r) for r in before])
        restricted = self.ws.explain('@kb/rule', ['curated'])
        self.assertEqual(restricted['resolved'], '@kb/rule')
        self.assertIn('@overlay/new-rule', restricted['notices']['superseded_by_untrusted'])

    def test_external_editor_change_never_inherits_stale_reason(self):
        self.ws.write('note', summary='Recorded.', reason='Original reason.')
        self.put_overlay('note', card_text('Note', 'Changed directly in editor.'))
        result = self.ws.explain('note')
        self.assertTrue(all(not s['revision_recorded'] and not s['changes'] for s in result['sources']))
        self.assertEqual(self.ws.card_history('note')['events'][0]['reason'], 'Original reason.')

    def test_baked_reason_matches_bytes_and_physical_version(self):
        self.ws.write('note', summary='Recorded.', reason='Version reason.')
        result = self.ws.bake('kb', prefix='')
        explanation = self.ws.explain('@kb/note')
        self.assertTrue(explanation['sources'][1]['revision_recorded'])
        self.assertEqual(explanation['sources'][1]['changes'][0]['reason'], 'Version reason.')
        from pathlib import Path
        (Path(result['path'])/'note.md').write_text(card_text('Note', 'External change.'))
        self.assertFalse(self.ws.explain('@kb/note')['sources'][1]['revision_recorded'])

    def test_explain_shadows_extensions_pagination_and_pending(self):
        self.mount_slice('kb', {'base': card_text('Base', 'Original.')}, '@kb', 50, 'curated')
        self.ws.write('base', summary='Local override.')
        self.ws.write('extension', summary='Extra detail.', extends=['base'])
        self.ws.write('base', op='replace', summary='Pending.', stage=True)
        result = self.ws.explain('base', max_extensions=0)
        self.assertEqual(result['shadows'], ['@kb/base'])
        self.assertEqual(result['pending_review'], ['@overlay/base'])
        self.assertEqual(result['extensions_next_offset'], 0)
        self.assertEqual(self.ws.explain('extension')['sources'][-1]['role'], 'baseline')

    def test_cli_json_and_human_history_and_explain(self):
        self.ws.write('a', summary='A.', reason='CLI reason.')
        for command in ('history', 'explain'):
            code, out, err = run_cli('-w', str(self.root), command, 'a')
            self.assertEqual((code, err), (0, ''))
            self.assertIn('CLI reason.', out)
            code, out, err = run_cli('-w', str(self.root), command, 'a', '--json')
            self.assertEqual((code, err), (0, ''))
            self.assertIsInstance(json.loads(out), dict)

    def test_history_includes_retirement_on_mount_and_reasons_remain_metadata(self):
        self.ws.write('a', summary='Portable fact.', reason='Original discovery.')
        root = self.tmp/'imported'
        root.mkdir()
        (root/'a.md').write_bytes(self.overlay_file('a').read_bytes())
        self.ws.mount(root, alias='imported')
        history = self.ws.card_history('@overlay/a')
        self.assertEqual(history['events'][0]['event'], 'retired')
        self.assertEqual(history['events'][1]['reason'], 'Original discovery.')
        self.assertFalse(self.ws.explain('@imported/a')['sources'][1]['revision_recorded'])

    def test_unchanged_card_keeps_verified_reason_through_later_bake_and_alias_change(self):
        self.ws.write('a', summary='A.', reason='Keep this provenance.')
        self.ws.write('b', summary='B.')
        self.ws.bake('kb', prefix='')
        self.ws.write('b', summary='Changed B.')
        result = self.ws.bake('kb')
        self.assertEqual(self.ws.explain('@kb/a')['sources'][1]['changes'][0]['reason'], 'Keep this provenance.')
        self.ws.unmount('kb')
        self.ws.mount(result['path'], alias='renamed')
        self.assertEqual(self.ws.explain('@renamed/a')['sources'][1]['changes'][0]['reason'], 'Keep this provenance.')
        self.assertIn('Keep this provenance.', json.dumps(self.ws.card_history('@renamed/a')))
