"""Human review for workspace bake; prompts go to stderr so stdout carries only the plan or receipt."""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from ..baking import bake_batch
from ..model.addressing import normalize_alias
from ..errors import BakeConflictError, InvalidArgumentsError, MindSliceError
from .render import render_next_steps


def render_plan(plan, *, details=False):
    lines = [f"{len(plan['cards'])} overlay cards", "", "Destination       Cards   Action"]
    for item in plan["slices"]:
        lines.append(f"{item['alias']:<18}{len(item['cards']):>5}   {item['action']} → {item['path']} (v{item['version']})")
        if item["dependencies_added"]:
            lines.append("  New dependencies: " + ", ".join(item["dependencies_added"]))
        if item.get("rebased_baseline_cards"):
            lines.append("  Baseline references updated: " + ", ".join(item["rebased_baseline_cards"]))
    lines += [f"Needs destination: {len(plan['unassigned'])}", f"Deferred: {len(plan['deferred'])}",
              f"Remaining overlay cards after bake: {len(plan['remaining_overlay_cards'])}",
              f"Staged changes excluded: {len(plan['pending_review'])}"]
    if details:
        for card in plan["cards"]:
            lines.append(f"  {card['address']} → {card['destination'] or card['state']}: {card['summary']}")
            if card["state"] == "unassigned" and card["candidates"]:
                lines.append("    Related slices: " + ", ".join(card["candidates"]))
            for change in card.get("changes", []):
                if change.get("reason"):
                    lines.append("    Reason: " + change["reason"])
    for item in plan["retained_overlay_cards"]:
        lines.append(f"Retain {item['address']}: {item['reason']}")
    for item in plan["blockers"]:
        extra = [repr(item["ref"])] if item.get("ref") else []
        extra += [str(item[k]) for k in ("dependency", "path") if item.get(k)]
        extra += item.get("errors", []) + item.get("cards", [])
        lines.append(f"Blocked: {item.get('address', item.get('alias', 'workspace'))}: {item['reason']}"
                     + (f" ({'; '.join(extra)})" if extra else ""))
    return "\n".join(lines) + "\n"


def render_receipt(result):
    if result.get("cancelled"):
        return f"Bake cancelled; destination choices saved in {result['plan_path']}\n"
    lines = [f"Baked {len(result['baked'])} slice(s)"]
    lines += [f"{item['alias']}  v{item['version']}  {item['path']}" for item in result["baked"]]
    lines.append(f"Overlay: {len(result['remaining_overlay_cards'])} remaining cards. "
                 f"Staging: {result['pending_review']} pending changes.")
    return "\n".join(lines) + "\n"


def _choose_paths(plan, selector):
    selector = selector.removeprefix("@overlay/").removeprefix("./")
    ids = [c["id"] for c in plan["cards"]]
    if selector == "*":
        return ids
    if selector.endswith("/"):
        paths = [p for p in ids if p.startswith(selector)]
    else:
        paths = [p for p in ids if p == selector.removesuffix(".md")]
    if not paths:
        raise InvalidArgumentsError("selector matches no overlay cards; use an ID, folder/ or *", selector=selector)
    return paths


def _inspect(plan, paths, stream):
    for c in plan["cards"]:
        if c["id"] not in paths:
            continue
        stream.write(f"\n{c['address']} → {c['destination'] or c['state']}\n{c['summary']}\n")
        for change in c.get("changes", []):
            if change.get("reason"):
                stream.write(f"Reason ({change['op']}): {change['reason']}\n")
        stream.write(c.get("diff", "") + "\n")


def _answer(prompt):
    sys.stderr.write(prompt)
    sys.stderr.flush()
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line.strip()


def review(ws, plan):
    """Resume assignments by card hash, but never execute without a fresh final confirmation."""
    try:
        while True:
            sys.stderr.write(render_plan(plan))
            groups = defaultdict(list)
            for c in plan["cards"]:
                if c["state"] == "unassigned":
                    groups[(c["id"].partition("/")[0], tuple(c["candidates"]))].append(c)
            for (_, candidates), cards in groups.items():
                paths = [c["id"] for c in cards]
                sys.stderr.write("\nNeeds destination:\n")
                for c in cards:
                    sys.stderr.write(f"  {c['id']}: {c['summary']}\n")
                if candidates:
                    sys.stderr.write("Related slices: " + ", ".join(candidates) + "\n")
                sys.stderr.write("Mounted slices: " + (", ".join(m.alias for m in ws.table().mounts) or "none") + "\n")
                while True:
                    value = _answer("Destination alias (existing or new), inspect, split, defer, or cancel: ")
                    if value == "cancel":
                        return None
                    if value == "inspect":
                        _inspect(plan, paths, sys.stderr)
                        continue
                    if value == "split":
                        choices = dict(plan["assignments"])
                        for path in paths:
                            while True:
                                dest = _answer(f"{path}: alias, defer, or cancel: ")
                                if dest == "cancel":
                                    return None
                                try:
                                    choices[path] = None if dest == "defer" else normalize_alias(dest)
                                    plan = ws.plan_bake(choices, resume=False)
                                    bake_batch.save_plan(ws, plan)
                                    break
                                except (InvalidArgumentsError, ValueError) as exc:
                                    sys.stderr.write(str(exc) + "\n")
                        break
                    try:
                        dest = None if value == "defer" else normalize_alias(value)
                        choices = dict(plan["assignments"], **{p: dest for p in paths})
                        plan = ws.plan_bake(choices, resume=False)
                        bake_batch.save_plan(ws, plan)
                        break
                    except (InvalidArgumentsError, ValueError) as exc:
                        sys.stderr.write(str(exc) + "\n")
            sys.stderr.write("\n" + render_plan(plan))
            action = _answer("[Bake all] [Edit plan] [Inspect] [Cancel]: ").lower()
            if action in ("cancel", "c", ""):
                return None
            if action in ("inspect", "i"):
                _inspect(plan, [c["id"] for c in plan["cards"]], sys.stderr)
            elif action in ("edit", "edit plan", "e"):
                selector = _answer("Cards (ID, folder/, or *): ")
                value = _answer("Destination alias, or defer: ")
                try:
                    paths = _choose_paths(plan, selector)
                    dest = None if value == "defer" else normalize_alias(value)
                    plan = ws.plan_bake(dict(plan["assignments"], **{p: dest for p in paths}), resume=False)
                    bake_batch.save_plan(ws, plan)
                except (MindSliceError, ValueError) as exc:
                    sys.stderr.write(str(exc) + "\n")
            elif action in ("bake", "bake all", "b", "yes", "y"):
                if plan["ready"]:
                    return plan
                sys.stderr.write("Resolve the blockers or defer those cards before baking. Your plan is saved.\n"
                                 + render_next_steps(bake_batch.next_steps(plan)))
    except (EOFError, KeyboardInterrupt):
        sys.stderr.write("\nReview cancelled; destination choices saved.\n")
        return None


def _steps(plan, *, saved):
    """Next steps for a CLI user: what blocks the plan, then how to run it.

    ``saved`` is False for ``--dry-run``, which keeps no choices: its flags have to be repeated.
    """
    steps = bake_batch.next_steps(plan)
    if steps:
        return steps + [
            "Destination choices made so far are saved. Finish with `mindslice bake --yes`; "
            "`mindslice bake --dry-run` previews the plan." if saved else
            "Once that is done, re-run this command (with any new `--assign`/`--defer` choices) and "
            "replace `--dry-run` with `--yes` to bake."]
    if not plan["cards"]:
        return []
    if saved:
        return ["The plan is ready and saved: run `mindslice bake --yes` to execute it as shown, "
                "or `mindslice bake` in a terminal to review it card by card."]
    return ["The plan is ready: replace `--dry-run` with `--yes` to bake it as shown."]


def run(ws, args, out):
    """``out(result, renderer)`` prints human text, or JSON under ``--json``."""
    single_options = (args.output, args.prefix, args.tags, args.include_deps, args.name, args.description, args.slice_version)
    if any(x is not None and x is not False for x in single_options):
        raise InvalidArgumentsError("workspace bake uses --assign/--defer; output/filter/version options require bake @alias")
    if args.plan and args.fresh:
        raise InvalidArgumentsError("use either --plan or --fresh")
    if args.plan:
        old = bake_batch.load_plan(Path(args.plan))
        plan = ws.plan_bake(old["assignments"], resume=False)
        if (old.get("workspace") != plan["workspace"] or old.get("revision") != plan["revision"]
                or old.get("slices") != plan["slices"]):
            raise BakeConflictError("saved input plan is stale; regenerate with bake --dry-run", code="stale_bake_plan", next_steps=[
                "Regenerate the plan from the current workspace: re-run the `mindslice bake ... --dry-run --json` "
                f"command that produced it and save its output to {args.plan}.",
                f"Review it, then run `mindslice bake --plan {args.plan} --yes`."])
    else:
        plan = ws.plan_bake(resume=not args.fresh)
    choices = dict(plan["assignments"])
    for assignment in args.assign or []:
        selector, sep, alias = assignment.rpartition("=")
        if not sep:
            raise InvalidArgumentsError("--assign expects CARD_OR_FOLDER=ALIAS")
        for path in _choose_paths(plan, selector):
            choices[path] = normalize_alias(alias)
    for selector in args.defer or []:
        for path in _choose_paths(plan, selector):
            choices[path] = None
    plan = ws.plan_bake(choices, resume=False)
    if args.dry_run:
        out(plan, lambda p: render_plan(p, details=True) + render_next_steps(_steps(p, saved=False)))
        return 0
    bake_batch.save_plan(ws, plan)
    if not plan["cards"]:
        out({"baked": [], "remaining_overlay_cards": [], "pending_review": len(plan["pending_review"]), "dry_run": False},
            render_receipt)
        return 0
    if not args.yes and sys.stdin.isatty() and not args.json:
        plan = review(ws, plan)
        if plan is None:
            out({"cancelled": True, "plan_path": str(ws.root / bake_batch.PLAN_FILE)}, render_receipt)
            return 0
    elif not plan["ready"]:
        raise BakeConflictError(bake_batch.blocked_message(plan), plan=plan,
                                plan_path=str(ws.root / bake_batch.PLAN_FILE), next_steps=_steps(plan, saved=True))
    elif not args.yes:
        raise BakeConflictError("review required; run in a terminal or use --yes with a reviewed plan",
                                code="bake_review_required", plan=plan, next_steps=_steps(plan, saved=True))
    out(ws.bake(plan=plan), render_receipt)
    return 0
