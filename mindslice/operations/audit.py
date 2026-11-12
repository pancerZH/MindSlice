"""Human-facing history and read explanations, without guessing unrecorded reasons."""
from __future__ import annotations

from pathlib import Path

from ..errors import AmbiguousAddressError, NotFoundError
from ..model.addressing import format_address, parse_address
from ..retrieval import query


def history_path(ws, path, records=None):
    """Translate old absolute version pointers after a portable workspace restore."""
    raw = str(path).replace('\\', '/').rstrip('/')
    for record in reversed(ws.history.events() if records is None else records):
        if record['event'] != 'restored':
            continue
        for source, relative in sorted(record.get('path_map', {}).items(), key=lambda x: -len(x[0])):
            source = source.replace('\\', '/').rstrip('/')
            if raw == source or raw.startswith(source + '/'):
                return ws.root / relative / raw[len(source):].lstrip('/')
    return Path(path)


def _baked_revision(ws, root, path, sha, records):
    """Follow a bake's parent for unchanged cards; a recorded mismatch ends attribution."""
    versions = {str(history_path(ws, e['path'], records)): e for e in records if e['event'] == 'baked'}
    seen = set()
    current = str(root)
    while current not in seen and current in versions:
        seen.add(current)
        e = versions[current]
        card = next((c for c in e.get('cards', []) if c['target'].partition('/')[2] == path), None)
        if card:
            return (True, card['change_ids']) if card['after_sha256'] == sha else (False, [])
        if not e.get('previous_path'):
            break
        current = str(history_path(ws, e['previous_path'], records))
    return False, []


def _event_addresses(record):
    addresses = {record['address']} if record.get('address') else set()
    addresses.update(record.get('retired_overlay_cards', []))
    for card in record.get('cards', []):
        addresses.update(card[k] for k in ('source', 'target') if card.get(k))
    return addresses


def card_history(ws, address=None, limit=20, offset=0):
    query._nonneg(limit=limit, offset=offset)
    with ws._reading() as table:
        records = ws.history.events()
        canonical = None
        physical_versions = set()
        if address is not None:
            alias, path = parse_address(address)
            try:
                canonical, _ = query._select(query._Ctx(ws, table, False), address)
                selected_alias, _ = parse_address(canonical)
                selected_mount = table.get(selected_alias)
                if selected_mount.kind == 'slice':
                    version = str(selected_mount.root)
                    versions = {str(history_path(ws, e['path'], records)): e for e in records if e['event'] == 'baked'}
                    while version not in physical_versions:
                        physical_versions.add(version)
                        previous = versions.get(version, {}).get('previous_path')
                        if not previous:
                            break
                        version = str(history_path(ws, previous, records))
            except NotFoundError:
                if alias:
                    canonical = format_address(alias, path)
                else:
                    matches = sorted({a for e in records for a in _event_addresses(e) if a.partition('/')[2] == path})
                    if len(matches) > 1:
                        raise AmbiguousAddressError('historical address is ambiguous; use @alias/path', candidates=matches)
                    canonical = matches[0] if matches else format_address(table.overlay.alias, path)
        if canonical:
            def matches(card, record):
                return canonical in (card.get('source'), card.get('target')) or (
                    record.get('path') and str(history_path(ws, record['path'], records)) in physical_versions
                    and card.get('target', '').partition('/')[2] == canonical.partition('/')[2])
            ids = {e['change_id'] for e in records if e.get('address') == canonical and e.get('change_id')}
            for e in records:
                for card in e.get('cards', []):
                    if matches(card, e):
                        ids.update(card.get('change_ids', []))
            filtered = []
            for e in records:
                cards = [c for c in e.get('cards', []) if matches(c, e)
                         or ids.intersection(c.get('change_ids', []))]
                pointer_change = e['event'] == 'rolled_back' and e.get('alias') == canonical.partition('/')[0]
                retired = canonical in e.get('retired_overlay_cards', [])
                if e.get('address') == canonical or e.get('change_id') in ids or cards or pointer_change or retired:
                    entry = dict(e)
                    if 'retired_overlay_cards' in entry:
                        entry['retired_overlay_cards'] = [a for a in e['retired_overlay_cards'] if a == canonical
                                                         or any(c.get('source') == a for c in cards)]
                    if 'cards' in e:
                        entry['cards'] = cards
                        entry['change_ids'] = list(dict.fromkeys(i for c in cards for i in c.get('change_ids', [])))
                    filtered.append(entry)
            records = filtered
        details = ws.history.details()
        records = list(reversed(records))
        page = []
        for e in records[offset:offset + limit]:
            entry = dict(e)
            if 'reason' not in entry and entry.get('change_id') in details:
                entry['reason'] = details[entry['change_id']].get('reason')
            if entry.get('change_ids'):
                entry['changes'] = ws.history.descriptions(entry['change_ids'], records=details)
            page.append(entry)
        return {'address': canonical, 'events': page, 'total': len(records), 'offset': offset,
                'next_offset': query._page(len(records), offset, limit),
                'content_snapshots': False,
                'note': 'Metadata history only. External editor changes are not automatically logged; old text requires a slice version or backup.'}


def explain(ws, address, follow_supersedes=True, max_extensions=5, extensions_offset=0):
    query._nonneg(max_extensions=max_extensions, extensions_offset=extensions_offset)
    with ws._reading() as table:
        ctx = query._Ctx(ws, table, follow_supersedes)
        selected, shadows = query._select(ctx, address)
        result = query.resolve(ctx, address, max_backlinks=0, max_extensions=max_extensions,
                               extensions_offset=extensions_offset, bump_telemetry=False)
        records = ws.history.events()
        sources = []
        parts = [('selected', ctx.card_payload(selected)), ('resolved', result)]
        parts += [('baseline', c) for c in result.get('baselines', [])]
        parts += [('extension', c) for c in result.get('extensions', [])]
        for role, card in parts:
            alias, path = parse_address(card['address'])
            mount = table.get(alias)
            changes = []
            matched = False
            if mount.kind == 'overlay':
                changes = ws.history.changes_for(card['address'], card['sha256'])
                matched = bool(changes)
            else:
                matched, ids = _baked_revision(ws, mount.root, path, card['sha256'], records)
                changes = ws.history.descriptions(ids)
            sources.append({'role': role, 'address': card['address'], 'path': str(mount.root / f'{path}.md'),
                            'sha256': card['sha256'], 'mount_role': mount.role, 'precedence': mount.precedence,
                            'revision_recorded': matched, 'changes': changes})
        notices = {k: result[k] for k in ('status', 'competing_replacements', 'superseded_by_untrusted',
                   'bypassed_replacements', 'unrebased_extensions', 'baseline_superseded_by', 'missing_baselines') if k in result}
        return {'requested': address, 'selected': selected, 'resolved': result['address'],
                'follow_supersedes': follow_supersedes, 'lineage_path': result.get('lineage_path', [selected]),
                'shadows': shadows, 'sources': sources, 'notices': notices,
                'total_extensions': result.get('total_extensions', 0),
                'extensions_next_offset': result.get('extensions_next_offset'),
                'pending_review': [i['address'] for i in ws.diff()['items'] if i['address'] in {c['address'] for _, c in parts}],
                'note': 'Selection uses mount precedence, then explicit lineage under the supplied trust policy. '
                        'Unrecorded revisions have no verified reason; pending edits do not affect this result.'}


def render_history(result):
    lines = [f"History: {result['address'] or 'workspace'} ({result['total']} events; newest first)"]
    for e in result['events']:
        lines.append(f"{e['timestamp']}  {e['event']}  {e.get('address', e.get('alias', ''))}")
        if e.get('reason'):
            lines.append('  Reason: ' + e['reason'])
        for c in e.get('changes', []):
            if c.get('reason'):
                lines.append('  Reason: ' + c['reason'])
        for key in ('previous_path', 'path'):
            if e.get(key):
                lines.append(f"  {key}: {e[key]}")
    if result['next_offset'] is not None:
        lines.append(f"More events: --offset {result['next_offset']}")
    return '\n'.join(lines + [result['note']]) + '\n'


def render_explain(result):
    lines = [f"Selected: {result['selected']}", f"Resolved: {result['resolved']}",
             'Lineage: ' + ' -> '.join(result['lineage_path'])]
    if result['shadows']:
        lines.append('Shadows: ' + ', '.join(result['shadows']))
    for source in result['sources']:
        if source['role'] == 'selected' and result['selected'] == result['resolved']:
            continue
        lines.append(f"{source['role']}: {source['address']} ({source['path']}; precedence={source['precedence']}, role={source['mount_role']})")
        for change in source['changes']:
            if change.get('reason'):
                lines.append('  Reason: ' + change['reason'])
        if not source['revision_recorded']:
            lines.append('  No history record matching these current bytes.')
    if result['pending_review']:
        lines.append('Pending, not active: ' + ', '.join(result['pending_review']))
    for name, value in result['notices'].items():
        lines.append(f'{name}: {value}')
    if result['extensions_next_offset'] is not None:
        lines.append(f"More extensions: --extensions-offset {result['extensions_next_offset']}")
    return '\n'.join(lines + [result['note']]) + '\n'
