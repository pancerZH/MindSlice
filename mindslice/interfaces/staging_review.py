"""Interactive staged-card review; gather choices before mutating the workspace."""

from __future__ import annotations

import sys

from ..errors import InvalidArgumentsError
from ..operations.staging import select_entries


def _answer(prompt):
    sys.stderr.write(prompt)
    sys.stderr.flush()
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line.strip().lower()


def run(ws, ids=None):
    if not sys.stdin.isatty():
        raise InvalidArgumentsError("review needs an interactive terminal; use diff --json, apply ID... or discard ID...")
    snapshot = ws.diff()
    items = {item["id"]: item for item in snapshot["items"]}
    chosen = select_entries(items, ids)
    if not chosen:
        return {"applied": 0, "discarded": 0, "remaining": len(items)}
    accept, reject = [], []
    retry = False
    try:
        for path, item in chosen.items():
            sys.stderr.write(f"\n{item['address']} ({item['change']})\n")
            for change in item.get("changes", []):
                if change.get("reason"):
                    sys.stderr.write(f"Reason: {change['reason']}\n")
            if item.get("requires_approval"):
                sys.stderr.write(f"Approval: {item['requires_approval']}\n")
            if item.get("conflict"):
                sys.stderr.write(f"Conflict: {item['conflict']}\n")
            for kind, refs in item.get("references", {}).items():
                if refs:
                    sys.stderr.write(f"{kind}: {', '.join(refs)}\n")
            impact = item.get("impact", {})
            for field in ("affected_backlinks", "affected_extensions"):
                affected = impact.get(field, [])
                if affected:
                    sys.stderr.write(f"{field} ({impact.get('total_' + field, len(affected))} live cards): "
                                     + ", ".join(c["address"] for c in affected) + "\n")
            sys.stderr.write(item["diff"])
            while True:
                action = _answer("[Accept] [Reject] [Leave pending] [Cancel]: ")
                if action in ("a", "accept"):
                    if item.get("conflict"):
                        sys.stderr.write("Resolve the conflict first, reject this proposal, or leave it pending.\n")
                        continue
                    accept.append(path)
                elif action in ("r", "reject"):
                    reject.append(path)
                elif action in ("", "l", "leave", "leave pending", "skip"):
                    pass
                elif action in ("c", "cancel"):
                    return {"cancelled": True}
                else:
                    continue
                break
        sys.stderr.write(f"\nAccept: {len(accept)}; reject: {len(reject)}; "
                         f"leave pending: {len(items) - len(accept) - len(reject)}.\n")
        if not accept and not reject:
            return {"applied": 0, "discarded": 0, "remaining": len(items)}
        plan = ws.review(accept, reject, revision=snapshot["revision"], dry_run=True)
        if not plan["ready"]:
            for conflict in plan["conflicts"]:
                sys.stderr.write(f"Blocked: {conflict.get('address', '')}: "
                                 f"{conflict.get('detail', conflict['reason'])}\n")
            retry = _answer("Review choices again? [yes/No]: ") in ("y", "yes")
            if not retry:
                return {"cancelled": True, "conflicts": plan["conflicts"]}
        elif _answer("Execute these choices? [yes/No]: ") not in ("y", "yes"):
            return {"cancelled": True}
    except (EOFError, KeyboardInterrupt):
        sys.stderr.write("\nReview cancelled; no review choices were executed.\n")
        return {"cancelled": True}

    if retry:
        return run(ws, ids)
    result = ws.review(accept, reject, revision=snapshot["revision"])
    result["remaining"] = len(ws.diff()["items"])
    if result["applied"]:
        sys.stderr.write("Accepted memory is saved and available now. Bake is optional packaging/versioning.\n")
    else:
        sys.stderr.write("No live memory changes applied; see the receipt for rejected or skipped proposals.\n")
    return result
