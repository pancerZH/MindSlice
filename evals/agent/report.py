"""Markdown rendering of a run's summary (``run.summarize``) and of Gate 1 (``run.gate``)."""

from __future__ import annotations

import math
from typing import Any

from .score import LINES

ORDER = ("stale-first", "stale@10", "current@10", "retired", "lost", "forgotten", "history-named@10")


def ci(s: dict[str, float] | None) -> str:
    if not s or s.get("n", 0) == 0 or math.isnan(s["mean"]):
        return "–"
    return f"{s['mean']:.3f} [{s['low']:.3f}, {s['high']:.3f}]"


def pt(s: dict[str, float] | None) -> str:
    return "–" if not s or s.get("n", 0) == 0 or math.isnan(s["mean"]) else f"{s['mean']:.3f}"


def render_run(name: str, summary: dict[str, Any]) -> str:
    arms = summary["arms"]
    o = [f"# Run `{name}`", "",
         "Value-based metrics (agent_test.md 6); brackets are 95% bootstrap intervals over units (2,000 "
         "replicates, seed 20261106); differences are paired by unit.", "",
         "## Pooled", "", "| Arm | " + " | ".join(ORDER) + " |", "| --- |" + " --- |" * len(ORDER)]
    for a, s in arms.items():
        o.append(f"| {a} | " + " | ".join(ci(s["pooled"].get(m)) for m in ORDER) + " |")
    o += ["", "n per metric: " + "; ".join(f"{a}: " + ", ".join(f"{m} {s['pooled'][m]['n']}" for m in ORDER if m in s["pooled"])
                                          for a, s in list(arms.items())[:1]), ""]
    with_lines = {a: s for a, s in arms.items() if "lines" in s}
    if with_lines:
        o += ["## Lines (G1-G5)", "", "| Arm | " + " | ".join(l["id"] for l in LINES) + " |", "| --- |" + " --- |" * len(LINES)]
        for a, s in with_lines.items():
            o.append(f"| {a} | " + " | ".join(f"{l['point']:.3f} [{l['low']:.3f}, {l['high']:.3f}] **{l['verdict']}**"
                                               if not math.isnan(l["point"]) else "–" for l in s["lines"]) + " |")
        o += ["", "; ".join(f"{l['id']}: {l['stat']}, line {l['line']}" for l in LINES), ""]
    if summary.get("audit") and all(e.get("two_way") for e in summary["audit"].values()):
        o += ["## Audit of value matching, both ways (6.3 and the matcher-v2 audit)", "",
              "Flagged: up to 50 `retired` failures and 50 `lost` cases per cell (seed 20261106; cases the tier-1 audit "
              "judged keep their verdict). More than 20% matching errors in either: that cell's lines are reported as "
              "unreliable (PLAN.md section 6). The other way: 15 updates v2 counts as retired, and up to 20 values the "
              "frozen matcher called lost that v2 keeps. The corrected values remove the flagged matching errors and add "
              "the misses at the sampled share; they are not lines.", "",
              "| Cell | `retired` errors | `lost` errors | Lines | Missed in passes | Wrong in flips | "
              "`retired` raw / corrected | `lost` raw / corrected |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for a, e in summary["audit"].items():
            t, c = e["tally"], e["corrected"]
            fmt = lambda k: f"{t[k]['errors']} / {t[k]['judged']} ({t[k]['share']:.0%})" if t.get(k) and t[k]["judged"] else "–"
            o.append(f"| {a} | {fmt('retired')} | {fmt('lost')} | {'reliable' if t['reliable'] else '**unreliable**'} | "
                     f"{fmt('passes')} | {fmt('flips')} | {c['retired']['raw']:.3f} / {c['retired']['corrected']:.3f} | "
                     f"{c['lost']['raw']:.3f} / {c['lost']['corrected']:.3f} |")
        o.append("")
    elif summary.get("audit"):
        o += ["## Audit of value matching (6.3)", "",
              "Each `retired` failure and `lost` case (all of them when fewer than 50, else a fixed sample, seed "
              "20261106) judged from the workspace as it was at the judgment point. More than 20% matching errors "
              "in either sample: that cell's lines are reported as unreliable (PLAN.md section 6). The corrected "
              "values count the matching errors as passes (exact when every case was judged); they are not lines.", "",
              "| Cell | `retired` errors | `lost` errors | Lines | `retired` raw / corrected | `lost` raw / corrected |",
              "| --- | --- | --- | --- | --- | --- |"]
        for a, e in summary["audit"].items():
            t, c = e["tally"], e["corrected"]
            fmt = lambda k: f"{t[k]['matching_errors']} / {t[k]['judged']} ({t[k]['share']:.0%})" if t.get(k) and t[k]["judged"] else "–"
            o.append(f"| {a} | {fmt('retired')} | {fmt('lost')} | {'reliable' if t['reliable'] else '**unreliable**'} | "
                     f"{c['retired']['raw']:.3f} / {c['retired']['corrected']:.3f} | {c['lost']['raw']:.3f} / {c['lost']['corrected']:.3f} |")
        o.append("")
    if summary.get("comparisons"):
        o += ["## Paired comparisons", "", "Mean difference over the units both cells scored, with the paired 95% interval.", "",
              "| Comparison | " + " | ".join(ORDER) + " |", "| --- |" + " --- |" * len(ORDER)]
        for name, ms in summary["comparisons"].items():
            o.append(f"| {name} | " + " | ".join(ci(ms.get(m)) for m in ORDER) + " |")
        o.append("")
    if summary.get("variance"):
        v = summary["variance"]
        o += ["## Run-to-run variance (agent-policy, main model)", "",
              f"{v['episodes']} fixed MEME episodes, {v['runs']} runs (tier 1 and the repeats); pooled value of each metric per run.", "",
              "| Metric | n per run | Per run | Mean | SD | Range |", "| --- | --- | --- | --- | --- | --- |"]
        for m, e in v["metrics"].items():
            o.append(f"| {m} | {e['n_per_run']} | {', '.join(f'{x:.3f}' for x in e['per_run'])} | {e['mean']:.3f} | {e['sd']:.3f} | "
                     f"{e['min']:.3f}-{e['max']:.3f} |")
        o.append("")
    o += ["## By group", ""]
    groups = sorted({g for s in arms.values() for g in s["groups"]})
    for g in groups:
        metrics = sorted({m for s in arms.values() for m in s["groups"].get(g, {})}, key=lambda m: ORDER.index(m) if m in ORDER else 99)
        o += [f"### {g}", "", "| Arm | n | " + " | ".join(metrics) + " |", "| --- | --- |" + " --- |" * len(metrics)]
        for a, s in arms.items():
            row = s["groups"].get(g)
            if not row:
                continue
            n = max(v["n"] for v in row.values())
            o.append(f"| {a} | {n} | " + " | ".join(ci(row.get(m)) for m in metrics) + " |")
        o.append("")
    o += ["## Telemetry", "", "| Arm | Haystacks (failed) | Sessions | Calls/session mean (median, max) | Ops | supersedes / extends writes | "
          "Tool errors | Cap hits | Non-MCP calls run (denied) | Trace ≠ proxy (CLI-rejected calls) | No DONE | Wall s median (total) | Overlay cards / haystack | Tokens in (uncached + cache read) / out (of which thinking) |",
          "| --- |" + " --- |" * 13]
    for a, s in arms.items():
        t = s["telemetry"]
        if not t:
            continue
        ops = ", ".join(f"{k} {v}" for k, v in sorted(t["ops"].items())) or "–"
        o.append(f"| {a} | {t['haystacks']} ({len(t['failed_haystacks'])}) | {t['sessions']} | {t['calls_per_session_mean']} "
                 f"({t['calls_per_session_median']}, {t['calls_per_session_max']}) | {ops} | {t['writes_with_supersedes']} / "
                 f"{t['writes_with_extends']} | {t['tool_errors']} | {t['cap_hits']} | {t['non_mcp_tool_calls']} ({t.get('non_mcp_denied', 0)}) | {t.get('trace_mismatches', 0)} ({t.get('client_rejected_calls', 0)}) | {t['no_done']} | "
                 f"{t['wall_s_median']} ({t['wall_s_total']}) | {t['overlay_cards_per_haystack']} | "
                 f"{t['input_tokens'] / 1e6:.2f}M + {t['cached_tokens'] / 1e6:.2f}M / {t['output_tokens'] / 1e6:.2f}M ({t['thinking_tokens'] / 1e6:.2f}M) |")
    return "\n".join(o) + "\n"


def render_gate(g: dict[str, Any], summary: dict[str, Any]) -> str:
    o = ["# Gate 1: scripted agents through the MCP tools vs the harness's own arms", "",
         "Each scripted agent drives a fresh workspace through `manifest` / `search` / `read` / `write` only. "
         "`disagree` counts units (questions, updates, values, deletions) whose judgment differs from the reference "
         "arm; the paired difference is scripted minus reference (pooled groups as for the lines).", ""]
    for pair, rows in g.items():
        o += [f"## {pair}", "", "| Metric | Units | Disagree | Scripted | Reference | Paired difference | First disagreements |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
        for m, r in rows.items():
            o.append(f"| {m} | {r['units']} | {r['disagree']} | {ci(r['scripted'])} | {ci(r['reference'])} | {ci(r['paired'])} | "
                     f"{', '.join('`' + e.split('|', 1)[1] + '`' for e in r['examples'][:3]) or '–'} |")
        o.append("")
    o.append(render_run("gate", summary).split("\n", 2)[2])
    return "\n".join(o) + "\n"


def render_levels(name: str, cmp: dict[str, Any]) -> str:
    o = [f"# Value-based vs card-level judgments (`{name}`)", "",
         "Same first pages, two judges: card-level marks a result stale or current when it is the card holding the "
         "annotated turn (evals/external, Mode B); value-based when its text states the value (agent_test.md 6.1). "
         "`Disagree` counts questions scored by both whose 0/1 (or share) differs.", ""]
    for arm, groups in cmp.items():
        o += [f"## {arm}", "", "| Group | Metric | n (value / card) | Value-based | Card-level | Disagree | Examples |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
        for g, ms in groups.items():
            for m, e in ms.items():
                o.append(f"| {g} | {m} | {e['value']['n']} / {e['card']['n']} | {ci(e['value'])} | {ci(e['card'])} | "
                         f"{e['disagree']} | {', '.join(e['examples'][:3]) or '–'} |")
        o.append("")
    return "\n".join(o) + "\n"
