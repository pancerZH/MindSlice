"""The journeys: initial state -> sessions (user + scripted agent) / human steps -> end state."""

from __future__ import annotations

import os
import tarfile
from pathlib import Path
from typing import Any

from mindslice import ApplyConflictError, Workspace

from .fixtures import SERVICES, empty_workspace, few_slices_workspace, many_slices_workspace
from .harness import Agent, Human, Journey, JourneyFailure, JourneyRun, Session, addresses, expect, expect_eq

# ---------------------------------------------------------------------------
# Agent-agnostic outcome checks (reusable as the oracle for a real LLM agent)
# ---------------------------------------------------------------------------


def recalls(ws: Workspace, query: str, *must_contain: str, absent: tuple[str, ...] = (), top: int = 3) -> str:
    """Some card in the top results for ``query`` states every ``must_contain`` text (after redirects)."""
    for address in addresses(ws.search(query, k=top)):
        card = ws.read(address)
        text = card["title"] + "\n" + card["summary"] + "\n" + card["body"]
        if all(s in text for s in must_contain) and not any(s in text for s in absent):
            return address
    raise JourneyFailure(f"no top-{top} card for {query!r} states {must_contain} (without {absent})")


def stated_once(ws: Workspace, text: str, mount: str = "@overlay") -> None:
    """A fact is recorded exactly once in ``mount`` (no duplicate memories from retries)."""
    count = 0
    for row in ws.index.all_cards(mount):
        card = ws.read(f"{mount}/{row['path']}")
        count += (card["summary"] + "\n" + card["body"]).count(text)
    expect_eq(count, 1, f"occurrences of {text!r} in {mount}")


def editor_append(ws: Workspace, path: str, line: str) -> None:
    """A human edits an overlay card in their editor (the save lands on a later clock tick)."""
    file = ws.table().overlay.root / f"{path}.md"
    file.write_text(file.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
    st = file.stat()
    os.utime(file, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))


def apply_expecting_conflict(ws: Workspace) -> dict[str, Any]:
    try:
        ws.apply()
    except ApplyConflictError as exc:
        return {"conflicts": exc.details["conflicts"]}
    raise JourneyFailure("apply() should have aborted on a conflict")


def result_for(search_result: dict[str, Any], address: str) -> dict[str, Any]:
    for r in search_result["results"]:
        if r["address"] == address:
            return r
    raise JourneyFailure(f"{address} not in results {addresses(search_result)}")


def sha256_file(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


# ===========================================================================
# Journey A - cold start: no slice at all
# ===========================================================================


def _a_boot(a: Agent) -> None:
    m = a.manifest()
    expect_eq([x["alias"] for x in m["mounts"]], ["@overlay"], "mounts at cold start")
    expect_eq(m["mounts"][0]["card_count"], 0, "empty overlay")
    expect_eq(a.search("python tooling")["total_matches"], 0, "nothing to recall yet")


def _a_onboarding(a: Agent) -> None:
    expect_eq(a.search("uv pip")["total_matches"], 0, "no prior preference")
    r = a.write("user-preferences/tooling", title="Python tooling preferences",
                summary="The user prefers uv over pip and runs tests with pytest -q.",
                content=["Use `uv run` for scripts and `uv add` for dependencies.", "Run tests with `pytest -q`."],
                tags=["tooling", "python"])
    expect(r["changed"], "tooling card created")


def _a_pin_python(a: Agent) -> None:
    expect_eq(addresses(a.search("python version"))[:1], ["@overlay/user-preferences/tooling"], "existing card found")
    card = a.read("@overlay/user-preferences/tooling")
    r = a.write("user-preferences/tooling", op="append", content="- Pin Python 3.12 for new projects.",
                if_match=card["sha256"])
    expect_eq(r["added_statements"], 1, "fact appended")
    retry = a.write("user-preferences/tooling", op="append", content="- Pin Python 3.12 for new projects.")
    expect(not retry["changed"], "a retried append is idempotent")


def _a_zh_auth(a: Agent) -> None:
    expect_eq(a.search("接口令牌 过期")["total_matches"], 0, "no prior Chinese memory")
    a.write("项目/认证", title="接口认证", summary="接口令牌15分钟过期。", content=["令牌通过请求头传递。"], tags=["认证"])
    expect_eq(addresses(a.search("令牌"))[:1], ["@overlay/项目/认证"], "2-character Chinese recall")


def _a_zh_correction(a: Agent) -> None:
    expect_eq(addresses(a.search("令牌有效期"))[:1], ["@overlay/项目/认证"], "partial overlap still finds the card")
    seen = a.read("项目/认证")["sha256"]
    a.write("项目/认证", op="replace", summary="接口令牌30分钟过期。", if_match=seen)
    # A second client still holding the old revision must be rejected, not silently win.
    a.write("项目/认证", op="replace", summary="接口令牌60分钟过期。", if_match=seen, expect_error="precondition_failed")
    expect_eq(a.read("项目/认证")["summary"], "接口令牌30分钟过期。", "the fresh write survived")


def _a_code_style(a: Agent) -> None:
    a.search("indentation python")
    a.write("user-preferences/code-style", title="Code style", summary="Python code uses 4-space indentation.",
            content=["Format with ruff; see [[user-preferences/tooling]]."], tags=["python", "style"])
    tooling = a.read("user-preferences/tooling")
    expect_eq([b["address"] for b in tooling["backlinks"]], ["@overlay/user-preferences/code-style"], "backlinks")


def _a_finale(run: JourneyRun) -> None:
    ws = run.ws
    kinds = {i["id"]: i["kind"] for i in ws.diff("overlay")["items"]}
    expect_eq(kinds, {"user-preferences/code-style": "new", "user-preferences/tooling": "new", "项目/认证": "new"},
              "overlay review before baking")
    # Bake the preferences into a curated slice and retire the overlay copies.
    baked = run.human("pack preferences", lambda: ws.pack(ws.root / "slices" / "prefs.slice", prefix="user-preferences/"))
    expect_eq(baked["cards"], ["user-preferences/code-style", "user-preferences/tooling"], "baked cards")
    expect_eq(baked["dependencies"], [], "self-contained slice")
    expect(baked["validation"]["ok"], f"baked slice validates: {baked['validation']}")
    mounted = run.human("mount prefs", lambda: ws.mount(ws.root / "slices" / "prefs.slice", alias="@prefs", precedence=60,
                                                        role="curated"))
    expect_eq(mounted.get("retired_overlay_cards"), [f"@overlay/{c}" for c in baked["cards"]],
              "mounting the baked slice retires its overlay copies")
    expect_eq(addresses(ws.search("uv")), ["@prefs/user-preferences/tooling"], "recall now served by the baked slice")
    links = ws.read("@prefs/user-preferences/code-style")["links"]
    expect_eq(links, [{"ref": "user-preferences/tooling", "address": "@prefs/user-preferences/tooling"}],
              "links resolve inside the baked slice")
    recalls(ws, "Python 3.12", "3.12")
    # Export what is left in the overlay as a portable archive.
    export = run.human("export overlay", lambda: ws.pack(run.root.parent / "exports" / "overlay.zip"))
    expect_eq(export["cards"], ["项目/认证"], "remaining overlay export")
    expect_eq([m["alias"] for m in ws.manifest()["mounts"]], ["@overlay", "@prefs"], "final mounts")


def cold_start() -> Journey:
    return Journey(
        name="cold-start",
        setup=empty_workspace,
        steps=[
            Session("Hi! Do you remember anything about me?", _a_boot),
            Session("I prefer uv over pip, and I run tests with pytest -q.", _a_onboarding,
                    outcome=lambda ws: recalls(ws, "uv", "uv")),
            Session("Also, pin Python 3.12 for new projects.", _a_pin_python,
                    outcome=lambda ws: stated_once(ws, "Pin Python 3.12")),
            Session("我们的接口令牌15分钟过期。", _a_zh_auth, outcome=lambda ws: recalls(ws, "令牌", "15分钟")),
            Session("更正：令牌有效期改成30分钟了。", _a_zh_correction,
                    outcome=lambda ws: recalls(ws, "令牌", "30分钟", absent=("15分钟",))),
            Session("Use 4-space indentation in Python.", _a_code_style,
                    outcome=lambda ws: recalls(ws, "indentation", "4-space")),
        ],
        finale=_a_finale,
        probes=("uv", "python", "令牌", "过期", "indentation", ""),
    )


# ===========================================================================
# Journey B - a few curated slices (English + Chinese) and a reviewing human
# ===========================================================================


def _b_boot(a: Agent) -> None:
    m = a.manifest()
    expect_eq([x["alias"] for x in m["mounts"]], ["@overlay", "@project", "@zh", "@persona"], "mount order")
    project = next(x for x in m["mounts"] if x["alias"] == "@project")
    expect_eq({f["name"] for f in project["folders"]}, {"api", "deploy", "observability"}, "project folders")
    zh = next(x for x in m["mounts"] if x["alias"] == "@zh")
    expect_eq((zh["description"], zh["card_count"]), ("团队的中文运维知识库。", 3), "Chinese slice summary")
    expect("[[api/auth-flow]]" in a.read("@project/overview")["body"], "overview points at the entry card")


def _b_admin_exception(a: Agent) -> None:
    expect_eq(addresses(a.search("admin token expire"))[:1], ["@project/api/auth-flow"], "base card found")
    a.write("api/admin-tokens", title="Admin tokens", summary="Admin tokens are a stricter exception to the auth flow.",
            content=["Admin tokens expire after 5 minutes."], extends=["@project/api/auth-flow"], tags=["auth"])
    base = a.read("@project/api/auth-flow")
    expect_eq([e["address"] for e in base["extensions"]], ["@overlay/api/admin-tokens"], "extension composed")


def _b_jwt_replacement(a: Agent) -> None:
    # The admin exception matches too; the agent picks the base card it is about to replace.
    expect_eq(result_for(a.search("token expiration"), "@project/api/auth-flow")["coverage"], 1.0, "outdated card found")
    a.write("api/jwt-ttl", title="JWT session TTL", summary="Sessions use signed JWTs with a 30 minute TTL.",
            content=["The JWT TTL is 30 minutes.", "Keys rotate like [[@project/api/refresh]]."],
            supersedes=["@project/api/auth-flow"], tags=["auth"])
    res = a.search("token expiration")
    expect_eq(result_for(res, "@overlay/api/jwt-ttl").get("matched_via_superseded"), ["@project/api/auth-flow"],
              "search redirects through the superseded card")
    expect("@project/api/auth-flow" not in addresses(res), "the superseded card itself is not returned")
    card = a.read("api/auth-flow")
    expect_eq((card["address"], card["redirected_from"]), ("@overlay/api/jwt-ttl", "@project/api/auth-flow"), "read redirect")
    expect_eq(card["unrebased_extensions"], [{"address": "@overlay/api/admin-tokens", "extends": "@project/api/auth-flow"}],
              "the old extension is flagged, never silently rebased")


def _b_cautious_reader(a: Agent) -> None:
    card = a.read("@project/api/auth-flow", follow_supersedes=["curated"])
    expect_eq((card["address"], card["superseded_by_untrusted"]), ("@project/api/auth-flow", ["@overlay/api/jwt-ttl"]),
              "untrusted runtime replacement is reported, not followed")
    res = a.search("token expiration", follow_supersedes=False)
    expect_eq(result_for(res, "@project/api/auth-flow").get("superseded_by_untrusted"), ["@overlay/api/jwt-ttl"],
              "no redirect without trust; the replacement is only reported")
    expect("@overlay/api/jwt-ttl" not in addresses(res), "no redirect target without trust")


def _b_zh_replacement(a: Agent) -> None:
    expect_eq(addresses(a.search("P0告警 响应"))[:1], ["@zh/值班/告警"], "Chinese base card found")
    a.read("@zh/值班/告警")
    a.write("值班/告警-更新", title="告警响应时限（更新）", summary="P0告警需要3分钟内响应。",
            content=["其余级别不变，见 [[@zh/值班/告警]]。"], supersedes=["@zh/值班/告警"], tags=["值班", "告警"])
    hit = a.search("告警 响应")["results"][0]
    expect_eq((hit["address"], hit.get("matched_via_superseded")),
              ("@overlay/值班/告警-更新", ["@zh/值班/告警"]), "Chinese search redirect")
    expect_eq(a.read("@zh/值班/告警")["address"], "@overlay/值班/告警-更新", "Chinese read redirect")


def _b_checklist(a: Agent) -> None:
    expect("@project/deploy/rollback" in addresses(a.search("deploy test")), "related base knowledge surfaced")
    args = dict(title="Deploy checklist", summary="Run `make test` before every deploy.",
                content=["Run `make test` before deploying."], tags=["deploy"])
    expect(a.write("deploy/checklist", **args)["changed"], "checklist created")
    expect(not a.write("deploy/checklist", **args)["changed"], "a retried create is idempotent")


def _b_staged_proposals(a: Agent) -> None:
    r1 = a.write("deploy/rollback-approval", title="Rollback approval",
                 summary="Rollbacks need approval from the on-call lead.", extends=["@project/deploy/rollback"],
                 content=["Ask the on-call lead before running `make rollback`."], tags=["deploy"])
    r2 = a.write("deploy/checklist", op="append", content="- Announce deploys in #ops.")
    expect(r1["staged"] and r2["staged"], "policy forces staging")
    expect_eq(a.search("approval")["total_matches"], 0, "staged memory is invisible until applied")


def _b_review_and_apply(ws: Workspace) -> dict[str, Any]:
    diff = ws.diff()
    expect_eq(diff["summary"], {"total": 2, "create": 1, "modify": 1, "delete": 0, "conflicts": 0}, "staged review")
    expect("+- Announce deploys in #ops." in diff["patch"], "the human sees the proposed bullet")
    return ws.apply()


def _b_friday_freeze(a: Agent) -> None:
    expect(a.write("deploy/checklist", op="append", content="- Deploys are frozen on Fridays.")["staged"], "staged")


def _b_consolidate(a: Agent) -> None:
    review = {i["id"]: i for i in a.server.ws.diff("overlay")["items"]}
    expect_eq(review["api/admin-tokens"]["unrebased"],
              [{"baseline": "@project/api/auth-flow", "superseded_by": ["@overlay/api/jwt-ttl"]}], "consolidation todo")
    ext = a.read("@overlay/api/admin-tokens")
    a.write("api/admin-tokens", op="replace", extends=["api/jwt-ttl"], if_match=ext["sha256"])
    expect("unrebased_extensions" not in a.read("@project/api/auth-flow"), "extension rebased onto the replacement")
    expect_eq([e["address"] for e in a.read("api/jwt-ttl")["extensions"]], ["@overlay/api/admin-tokens"], "rebased")


def _b_finale(run: JourneyRun) -> None:
    ws = run.ws
    kinds = {i["id"]: i["kind"] for i in ws.diff("overlay")["items"]}
    expect_eq(kinds, {"api/admin-tokens": "extends", "api/jwt-ttl": "supersedes", "deploy/checklist": "new",
                      "deploy/rollback-approval": "extends", "值班/告警-更新": "supersedes"}, "overlay before baking")
    baked = run.human("pack api", lambda: ws.pack(ws.root / "slices" / "api-v2.slice", prefix="api/"))
    expect_eq(baked["cards"], ["api/admin-tokens", "api/jwt-ttl"], "baked API cards")
    expect_eq(baked["dependencies"], ["@project"], "external lineage kept qualified")
    expect(baked["validation"]["ok"], f"baked slice validates: {baked['validation']}")
    mounted = run.human("mount api-v2", lambda: ws.mount(ws.root / "slices" / "api-v2.slice", alias="@api-v2",
                                                         precedence=60, role="curated"))
    expect_eq(mounted.get("retired_overlay_cards"), [f"@overlay/{c}" for c in baked["cards"]],
              "mounting the baked slice retires its overlay copies")
    res = ws.search("token expiration")
    expect_eq(result_for(res, "@api-v2/api/jwt-ttl").get("matched_via_superseded"), ["@project/api/auth-flow"],
              "supersession survives baking")
    expect(not any(a.startswith("@overlay/api/") for a in addresses(res)), "overlay copies are retired")
    expect_eq(ws.read("@project/api/auth-flow")["address"], "@api-v2/api/jwt-ttl", "read redirect after baking")
    expect_eq([b["address"] for b in ws.read("@api-v2/api/admin-tokens")["baselines"]], ["@api-v2/api/jwt-ttl"],
              "slice-relative extends resolves inside the baked slice")
    exports = run.root.parent / "exports"
    first = run.human("export 值班", lambda: ws.pack(exports / "zh-updates.tar.gz", prefix="值班/"))
    expect_eq(first["dependencies"], ["@zh"], "Chinese export depends on @zh")
    run.human("export 值班 again", lambda: ws.pack(exports / "again" / "zh-updates.tar.gz", prefix="值班/"))
    expect_eq(sha256_file(exports / "zh-updates.tar.gz"), sha256_file(exports / "again" / "zh-updates.tar.gz"),
              "exports are byte-for-byte deterministic")
    recalls(ws, "make test", "make test")
    recalls(ws, "告警", "3分钟")


def few_slices() -> Journey:
    return Journey(
        name="few-slices",
        setup=few_slices_workspace,
        steps=[
            Session("Hi, what do you know about this project?", _b_boot),
            Session("Note: admin tokens expire after only 5 minutes.", _b_admin_exception,
                    outcome=lambda ws: recalls(ws, "admin tokens", "5 minutes")),
            Session("We changed auth: sessions now use signed JWTs with a 30 minute TTL.", _b_jwt_replacement,
                    outcome=lambda ws: recalls(ws, "token expiration", "30 minute")),
            Session("(audit) What does the curated knowledge base itself say about token expiry?", _b_cautious_reader),
            Session("P0告警现在要求3分钟内响应，不是5分钟。", _b_zh_replacement,
                    outcome=lambda ws: recalls(ws, "P0告警", "3分钟")),
            Session("Remember: always run `make test` before deploying.", _b_checklist,
                    outcome=lambda ws: stated_once(ws, "Run `make test` before deploying.")),
            Session("Rollbacks now need approval from the on-call lead; also announce deploys in #ops.",
                    _b_staged_proposals, stage_writes=True),
            Human("review staged proposals and apply", _b_review_and_apply),
            Session("Deploys are frozen on Fridays.", _b_friday_freeze, stage_writes=True),
            Human("edit deploy/checklist in an editor", lambda ws: editor_append(ws, "deploy/checklist", "- Tag releases.")),
            Human("apply (conflicts with the editor change)", apply_expecting_conflict),
            Human("discard the stale proposal", lambda ws: ws.discard()),
            Session("Please consolidate the auth memories.", _b_consolidate),
        ],
        finale=_b_finale,
        probes=("token expiration", "admin", "告警 响应", "回滚", "deploy", "make test", "Fridays", ""),
    )


# ===========================================================================
# Journey C - many slices (more than manifest's default page of 20)
# ===========================================================================

N_SERVICES = 24


def _expected_mount_order() -> list[str]:
    prec = {f"@svc-{i:02d}": 5 + 10 * i for i in range(N_SERVICES)} | {"@overlay": 100}
    return sorted(prec, key=lambda a: (-prec[a], a))


def _c_boot(a: Agent) -> None:
    first = a.manifest()
    expect_eq((first["total_mounts"], len(first["mounts"]), first["truncated"], first["next_offset"]),
              (N_SERVICES + 1, 20, True, 20), "default manifest page")
    rest = a.manifest(offset=first["next_offset"])
    expect_eq((len(rest["mounts"]), rest["next_offset"]), (N_SERVICES + 1 - 20, None), "last manifest page")
    seen = [m["alias"] for m in first["mounts"] + rest["mounts"]]
    expect_eq(seen, _expected_mount_order(), "every mount exactly once, by precedence")


def _c_paginate(a: Agent) -> None:
    results, offset = [], 0
    while offset is not None:
        page = a.search("rollback", offset=offset)
        expect(len(page["results"]) <= 10, "k=10 bound")
        results += page["results"]
        offset = page["next_offset"]
    expect_eq(len(results), N_SERVICES, "one rollback runbook per service")
    expect_eq(len({r["address"] for r in results}), N_SERVICES, "no duplicates across pages")
    expect(all(r["address"].endswith("/runbook/rollback") for r in results), "only rollback runbooks")
    scores = [r["score"] for r in results]
    expect(scores == sorted(scores, reverse=True), "pages are globally ordered by BM25 score")
    scoped = a.search("rollback", source=["@svc-03", "@svc-04"])
    expect_eq(sorted(addresses(scoped)), ["@svc-03/runbook/rollback", "@svc-04/runbook/rollback"], "source filter")


def _c_chinese(a: Agent) -> None:
    res = a.search("值班 告警")
    expect_eq(res["total_matches"], N_SERVICES // 3, "Chinese on-call cards")
    expect(all(r["address"].endswith("/运维/值班") for r in res["results"]), "only on-call cards")
    expect_eq(addresses(a.search("计费值班"))[:1], ["@svc-00/运维/值班"], "unspaced compound query")


def _c_collision(a: Agent) -> None:
    card = a.read("runbook/deploy")
    order = [x for x in _expected_mount_order() if x != "@overlay"]
    expect_eq(card["address"], f"{order[0]}/runbook/deploy", "highest precedence wins")
    expect_eq(card["shadows"], [f"{x}/runbook/deploy" for x in order[1:]], "all other same-path cards are shadows")
    links = a.read("@svc-01/runbook/deploy")["links"]
    expect_eq(links, [{"ref": "@svc-00/runbook/deploy", "address": "@svc-00/runbook/deploy"}], "cross-slice link")


def _c_incident(a: Agent) -> None:
    a.write("incidents/2026-11-06", title="Checkout outage 2026-11-06",
            summary="Checkout failed after a ledger deploy; ledger and checkout were rolled back.",
            content=["Followed [[@svc-03/runbook/rollback]].", "Followed [[@svc-07/runbook/rollback]].",
                     "Root cause: a ledger schema migration."], tags=["incident"])
    a.write("freeze/ledger", title="Ledger deploy freeze", summary="Ledger deploys are frozen until the migration fix ships.",
            supersedes=["@svc-03/runbook/deploy"], tags=["deploy", "ledger"])
    backlinks = [b["address"] for b in a.read("@svc-03/runbook/rollback")["backlinks"]]
    expect_eq(backlinks, ["@overlay/incidents/2026-11-06"], "incident linked from the runbook")
    expect_eq(a.read("@svc-03/runbook/deploy")["address"], "@overlay/freeze/ledger", "freeze overrides the runbook")


def _c_after_unmount(a: Agent) -> None:
    found = addresses(a.search("rollback", k=50))
    runbooks = [x for x in found if x.endswith("/runbook/rollback")]
    expect_eq(len(runbooks), N_SERVICES - 1, "unmounted slice no longer searchable")
    expect("@svc-07/runbook/rollback" not in runbooks, "svc-07 is gone")
    expect("@overlay/incidents/2026-11-06" in found, "the incident mentions rollback runbooks via its links")
    links = {l["ref"]: l["address"] for l in a.read("incidents/2026-11-06")["links"]}
    expect_eq(links, {"@svc-03/runbook/rollback": "@svc-03/runbook/rollback", "@svc-07/runbook/rollback": None},
              "link into the unmounted slice is unresolved")
    warnings = a.server.ws.validate()["warnings"]
    expect(any(w["code"] == "unmounted_dependency" for w in warnings), "validate warns about the dangling link")


def _c_finale(run: JourneyRun) -> None:
    ws = run.ws
    exports = run.root.parent / "exports"
    first = run.human("export incidents", lambda: ws.pack(exports / "incidents.tar.gz", prefix="incidents/"))
    expect_eq(first["dependencies"], ["@svc-03", "@svc-07"], "both referenced slices become dependencies")
    expect(any("@svc-07" in w for w in first["warnings"]), "the unresolved reference is reported")
    run.human("export incidents again", lambda: ws.pack(exports / "again" / "incidents.tar.gz", prefix="incidents/"))
    expect_eq(sha256_file(exports / "incidents.tar.gz"), sha256_file(exports / "again" / "incidents.tar.gz"),
              "exports are byte-for-byte deterministic")

    def extract() -> list[str]:
        with tarfile.open(exports / "incidents.tar.gz") as tar:
            tar.extractall(ws.root / "slices", filter="data")
            return sorted(tar.getnames())

    names = run.human("extract archive", extract)
    expect_eq(names, ["incidents.slice", "incidents.slice/incidents", "incidents.slice/incidents/2026-11-06.md",
                      "incidents.slice/slice.toml"], "archive layout")
    report = run.human("validate extracted slice", lambda: ws.validate(ws.root / "slices" / "incidents.slice"))
    expect(report["ok"], f"extracted slice validates: {report['errors']}")
    mounted = run.human("mount incidents", lambda: ws.mount(ws.root / "slices" / "incidents.slice", alias="@incidents",
                                                            precedence=50, role="curated"))
    expect_eq(mounted.get("retired_overlay_cards"), ["@overlay/incidents/2026-11-06"],
              "the overlay copy is retired when the exported slice is mounted")
    card = ws.read("incidents/2026-11-06")
    expect_eq((card["address"], card.get("shadows")), ("@incidents/incidents/2026-11-06", None),
              "the imported slice is no longer shadowed by the overlay copy")
    run.human("remount svc-07", lambda: ws.mount(ws.root / "slices" / "svc-07.slice", alias="@svc-07", precedence=75,
                                                 role="baseline"))
    expect(all(l["address"] for l in ws.read("incidents/2026-11-06")["links"]), "links resolve again after remount")
    recalls(ws, "ledger deploy", "frozen")


def many_slices() -> Journey:
    return Journey(
        name="many-slices",
        setup=lambda root: many_slices_workspace(root, N_SERVICES),
        steps=[
            Session("What systems do you know about?", _c_boot),
            Session("List every rollback runbook.", _c_paginate),
            Session("哪些服务有值班告警规则？", _c_chinese),
            Session("How do I deploy?", _c_collision),
            Session("Record today's checkout outage, and freeze ledger deploys.", _c_incident,
                    outcome=lambda ws: recalls(ws, "checkout outage", "ledger")),
            Human("unmount svc-07", lambda ws: ws.unmount("@svc-07")),
            Session("Which runbooks are still available?", _c_after_unmount),
        ],
        finale=_c_finale,
        probes=("rollback", "值班 告警", "ledger deploy", "checkout outage", "deploy", ""),
    )


JOURNEYS = (cold_start, few_slices, many_slices)
assert len(SERVICES) >= N_SERVICES
