"""The deterministic behavior matrix from section 6 of the design doc (scenarios 1-11).

Reference setup: @overlay (precedence=100, role="runtime"), @project (precedence=50, role="curated").
"""

from __future__ import annotations

import json
import tomllib
import unittest

from mindslice import ApplyConflictError, UnresolvedExportDependencyError, Workspace
from mindslice.card import sha256_bytes
from mindslice.staging import replay

from .helpers import WorkspaceTestCase, bump_mtime, card_text

AUTH = card_text("Auth flow", "Clients authenticate with short-lived tokens.", ["The token expiration is 15 minutes."],
                 tags=["api"])


class Scenario01PathCollision(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.project({"api/auth": AUTH})
        self.ws.write("api/auth", summary="Local auth notes for this machine.", content="- auth uses a dev token locally.")

    def test_search_returns_both_with_provenance(self):
        res = self.ws.search("auth")
        self.assertCountEqual(self.addresses(res), ["@project/api/auth", "@overlay/api/auth"])
        roles = {r["address"]: (r["role"], r["precedence"]) for r in res["results"]}
        self.assertEqual(roles["@project/api/auth"], ("curated", 50))
        self.assertEqual(roles["@overlay/api/auth"], ("runtime", 100))
        scores = [r["score"] for r in res["results"]]
        self.assertTrue(all(s > 0 for s in scores))
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_read_unqualified_selects_precedence_and_lists_shadows(self):
        res = self.ws.read("api/auth")
        self.assertEqual(res["address"], "@overlay/api/auth")
        self.assertEqual(res["shadows"], ["@project/api/auth"])
        self.assertEqual(self.ws.read("@project/api/auth")["address"], "@project/api/auth")


class Scenario02SamePathExtension(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.project({"api/auth": AUTH})
        self.ws.write("api/auth", summary="Exceptions for the internal admin API.",
                      content="- Admin tokens expire after 5 minutes.", extends=["@project/api/auth"])

    def test_search_returns_both_with_extends_metadata(self):
        res = {r["address"]: r for r in self.ws.search("auth")["results"]}
        self.assertEqual(set(res), {"@project/api/auth", "@overlay/api/auth"})
        self.assertEqual(res["@overlay/api/auth"]["extends"], ["@project/api/auth"])

    def test_unqualified_read_composes_baseline_and_delta(self):
        res = self.ws.read("api/auth")
        self.assertEqual(res["address"], "@overlay/api/auth")
        self.assertEqual([b["address"] for b in res["baselines"]], ["@project/api/auth"])
        self.assertIn("15 minutes", res["baselines"][0]["body"])
        self.assertNotIn("shadows", res)  # the baseline is linked, not shadowed

    def test_base_read_attaches_extension(self):
        res = self.ws.read("@project/api/auth")
        self.assertEqual(res["address"], "@project/api/auth")
        self.assertEqual([e["address"] for e in res["extensions"]], ["@overlay/api/auth"])
        self.assertIn("5 minutes", res["extensions"][0]["body"])
        self.assertEqual(res["total_extensions"], 1)


class Scenario03SupersessionTerminologyShift(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.project({"api/auth": AUTH})
        self.ws.write("api/jwt", summary="Sessions use signed JWTs.", content="- The JWT TTL is 30 minutes.",
                      supersedes=["@project/api/auth"])

    def test_search_redirects_through_superseded_card(self):
        res = self.ws.search("token expiration")
        self.assertEqual(self.addresses(res), ["@overlay/api/jwt"])
        self.assertEqual(res["results"][0]["matched_via_superseded"], ["@project/api/auth"])

    def test_read_follows_supersession(self):
        for address in ("api/auth", "@project/api/auth"):
            res = self.ws.read(address)
            self.assertEqual(res["address"], "@overlay/api/jwt")
            self.assertEqual(res["redirected_from"], "@project/api/auth")

    def test_trust_allowlist_and_disabled_following(self):
        for follow in (["curated"], False):
            res = self.ws.read("api/auth", follow_supersedes=follow)
            self.assertEqual(res["address"], "@project/api/auth")
            self.assertEqual(res["superseded_by_untrusted"], ["@overlay/api/jwt"])
            self.assertEqual(res["status"], "superseded_by: @overlay/api/jwt")
        trusted = self.ws.read("api/auth", follow_supersedes=["runtime"])
        self.assertEqual(trusted["address"], "@overlay/api/jwt")
        by_alias = self.ws.read("api/auth", follow_supersedes=["@overlay"])
        self.assertEqual(by_alias["address"], "@overlay/api/jwt")

    def test_untrusted_search_does_not_redirect(self):
        res = self.ws.search("token expiration", follow_supersedes=False)
        self.assertEqual(self.addresses(res), ["@project/api/auth"])
        self.assertEqual(res["results"][0]["superseded_by_untrusted"], ["@overlay/api/jwt"])


class Scenario04SourceScopedSearch(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.project({"api/auth": AUTH})
        self.ws.write("api/jwt", summary="Sessions use signed JWTs.", content="- The JWT TTL is 30 minutes.",
                      supersedes=["@project/api/auth"])

    def test_source_filter_is_honored_and_stamped(self):
        res = self.ws.search("token expiration", source="@project")
        self.assertEqual(self.addresses(res), ["@project/api/auth"])
        self.assertEqual(res["results"][0]["status"], "superseded_by: @overlay/api/jwt")
        self.assertNotIn("matched_via_superseded", res["results"][0])

    def test_read_without_following(self):
        res = self.ws.read("@project/api/auth", follow_supersedes=False)
        self.assertEqual(res["address"], "@project/api/auth")
        self.assertEqual(res["superseded_by"], ["@overlay/api/jwt"])


class Scenario05ReplacementChain(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.project({"api/auth": AUTH})
        self.ws.write("api/v1", summary="Auth v1 uses opaque session tokens.", content="- v1 sessions.",
                      supersedes=["@project/api/auth"])
        self.ws.write("api/v2", summary="Auth v2 uses JWTs.", content="- v2 signed JWT.", supersedes=["api/v1"])

    def test_search_redirects_to_terminal_leaf_with_max_score(self):
        res = self.ws.search("auth")
        self.assertEqual(self.addresses(res), ["@overlay/api/v2"])
        self.assertCountEqual(res["results"][0]["matched_via_superseded"], ["@project/api/auth", "@overlay/api/v1"])
        raw_scores = {f"{h.row['mount']}/{h.row['path']}": h.score for h in self.ws.index.search("auth")}
        self.assertAlmostEqual(res["results"][0]["score"], round(max(raw_scores.values()), 6), places=5)

    def test_read_resolves_transitively(self):
        for address in ("@project/api/auth", "@overlay/api/v1", "api/auth"):
            res = self.ws.read(address)
            self.assertEqual(res["address"], "@overlay/api/v2", address)
        self.assertEqual(self.ws.read("@project/api/auth")["lineage_path"],
                         ["@project/api/auth", "@overlay/api/v1", "@overlay/api/v2"])

    def test_competing_replacements_are_not_guessed(self):
        self.ws.write("api/v2b", summary="A rival auth proposal.", content="- rival.", supersedes=["api/v1"])
        res = self.ws.read("@project/api/auth")
        self.assertEqual(res["address"], "@overlay/api/v1")
        self.assertEqual(res["status"], "competing_replacements")
        self.assertCountEqual([c["address"] for c in res["competing_replacements"]], ["@overlay/api/v2", "@overlay/api/v2b"])


class Scenario05bTrustAcrossThreeMounts(WorkspaceTestCase):
    """The trust policy is applied hop by hop: @base (baseline, 10) <- @curated (curated, 50) <- @overlay (runtime, 100)."""

    def setUp(self):
        super().setUp()
        self.mount_slice("base-kb", {"a": card_text("Rate limits", "Anonymous clients are throttled at 100 requests.")},
                         "@base", 10, "baseline")
        self.mount_slice("curated-kb", {"b": card_text("Rate limits v2", "Clients get 300 requests.",
                                                       supersedes=["@base/a"])}, "@curated", 50, "curated")

    def test_untrusted_hop_stops_the_chain_mid_way(self):
        self.ws.write("c", summary="Runtime guess: the quota was lifted.", supersedes=["@curated/b"])
        res = self.ws.read("@base/a", follow_supersedes=["curated"])
        self.assertEqual(res["address"], "@curated/b")
        self.assertEqual(res["redirected_from"], "@base/a")
        self.assertEqual(res["lineage_path"], ["@base/a", "@curated/b"])
        self.assertEqual(res["superseded_by_untrusted"], ["@overlay/c"])
        hits = self.ws.search("throttled", follow_supersedes=["curated"])
        self.assertEqual(self.addresses(hits), ["@curated/b"])
        self.assertEqual(hits["results"][0]["matched_via_superseded"], ["@base/a"])
        self.assertEqual(hits["results"][0]["superseded_by_untrusted"], ["@overlay/c"])
        self.assertNotIn("resolves_to", hits["results"][0])  # the untrusted hop is not followed onward
        # c replaces the card returned, so it is reported there, not again as bypassed.
        self.assertNotIn("bypassed_replacements", res)
        self.assertNotIn("bypassed_replacements", hits["results"][0])
        self.assertEqual(self.ws.read("@base/a")["address"], "@overlay/c")  # trusting everything walks on

    def test_trust_filter_resolves_a_fork(self):
        self.ws.write("c", summary="Runtime guess: the quota was lifted.", supersedes=["@base/a"])
        forked = self.ws.read("@base/a", follow_supersedes=True)
        self.assertEqual(forked["address"], "@base/a")
        self.assertEqual(forked["status"], "competing_replacements")
        self.assertEqual([c["address"] for c in forked["competing_replacements"]], ["@overlay/c", "@curated/b"])
        self.assertNotIn("redirected_from", forked)
        self.assertNotIn("bypassed_replacements", forked)
        curated = self.ws.read("@base/a", follow_supersedes=["curated"])
        self.assertEqual(curated["address"], "@curated/b")
        self.assertEqual(curated["redirected_from"], "@base/a")
        self.assertEqual(curated["status"], "active")  # under the caller's policy b is the answer...
        rival = [{"address": "@overlay/c", "supersedes": "@base/a"}]
        self.assertEqual(curated["bypassed_replacements"], rival)  # ...but the skipped rival is not hidden
        self.assertNotIn("superseded_by_untrusted", curated)
        hits = self.ws.search("throttled", follow_supersedes=["curated"])
        self.assertEqual(self.addresses(hits), ["@curated/b"])
        self.assertEqual(hits["results"][0]["bypassed_replacements"], rival)

    def test_rival_of_a_card_passed_through_is_reported(self):
        # @base/a <- @curated/b <- @curated2/d, and an untrusted @overlay/c also replaces b.
        self.mount_slice("curated2-kb", {"d": card_text("Rate limits v3", "Clients get 500 requests.",
                                                        supersedes=["@curated/b"])}, "@curated2", 60, "curated")
        self.ws.write("c", summary="Runtime guess: the quota was lifted.", supersedes=["@curated/b"])
        res = self.ws.read("@base/a", follow_supersedes=["curated"])
        self.assertEqual(res["lineage_path"], ["@base/a", "@curated/b", "@curated2/d"])
        self.assertEqual(res["bypassed_replacements"], [{"address": "@overlay/c", "supersedes": "@curated/b"}])
        self.assertEqual(res["status"], "active")


class Scenario06UnrebasedExtension(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.project({"api/auth": AUTH})
        self.ws.write("api/auth-edge", summary="Edge cases for token expiry.",
                      content="- Clock skew of 30s is tolerated.", extends=["@project/api/auth"])
        self.ws.write("api/jwt", summary="Sessions use signed JWTs.", content="- The JWT TTL is 30 minutes.",
                      supersedes=["@project/api/auth"])

    def test_read_baseline_forwards_and_flags_unrebased(self):
        res = self.ws.read("@project/api/auth")
        self.assertEqual(res["address"], "@overlay/api/jwt")
        self.assertEqual(res["unrebased_extensions"], [{"address": "@overlay/api/auth-edge", "extends": "@project/api/auth"}])
        self.assertNotIn("extensions", res)  # never silently applied to the replacement

    def test_read_extension_composes_named_baseline(self):
        res = self.ws.read("@overlay/api/auth-edge")
        self.assertEqual([b["address"] for b in res["baselines"]], ["@project/api/auth"])
        self.assertEqual(res["baseline_superseded_by"], ["@overlay/api/jwt"])

    def test_search_surfaces_baseline_superseded_by(self):
        res = {r["address"]: r for r in self.ws.search("clock skew edge")["results"]}
        self.assertEqual(res["@overlay/api/auth-edge"]["baseline_superseded_by"], ["@overlay/api/jwt"])

    def test_rebasing_clears_notice(self):
        self.ws.write("api/auth-edge", op="replace", extends=["api/jwt"])
        self.assertNotIn("unrebased_extensions", self.ws.read("@project/api/auth"))
        self.assertEqual([e["address"] for e in self.ws.read("api/jwt")["extensions"]], ["@overlay/api/auth-edge"])


class Scenario06bTwoHopAndDeletedBaselines(WorkspaceTestCase):
    """Search previews carry read()'s baseline notices over the whole extends closure."""

    def setUp(self):
        super().setUp()
        self.project({"api/auth": AUTH})
        self.ws.write("api/auth-edge", summary="Edge cases for token expiry.",
                      content="- Clock skew of 30s is tolerated.", extends=["@project/api/auth"])
        self.ws.write("api/skew-mobile", summary="Mobile clients get extra clock skew.",
                      content="- Mobile clock skew of 60s is tolerated.", extends=["api/auth-edge"])
        self.ws.write("api/jwt", summary="Sessions use signed JWTs.", content="- The JWT TTL is 30 minutes.",
                      supersedes=["@project/api/auth"])

    def preview(self, query: str, address: str) -> dict:
        return {r["address"]: r for r in self.ws.search(query)["results"]}[address]

    def test_two_hop_dependent_flagged_in_preview_as_in_read(self):
        hit = self.preview("mobile clock skew", "@overlay/api/skew-mobile")
        self.assertEqual(hit["status"], "active")
        self.assertEqual(hit["extends"], ["@overlay/api/auth-edge"])
        self.assertEqual(hit["baseline_superseded_by"], ["@overlay/api/jwt"])
        self.assertEqual(self.ws.read("api/skew-mobile")["baseline_superseded_by"], hit["baseline_superseded_by"])

    def test_rebasing_the_middle_clears_the_two_hop_notice(self):
        self.ws.write("api/auth-edge", op="replace", extends=["api/jwt"])
        self.assertNotIn("baseline_superseded_by", self.preview("mobile clock skew", "@overlay/api/skew-mobile"))
        self.assertNotIn("baseline_superseded_by", self.ws.read("api/skew-mobile"))

    def test_deleted_baseline_flagged_in_preview_as_in_read(self):
        self.ws.write("api/auth-edge", op="delete")
        hit = self.preview("mobile clock skew", "@overlay/api/skew-mobile")
        expected = [{"source": "@overlay/api/skew-mobile", "ref": "api/auth-edge"}]
        self.assertEqual(hit["missing_baselines"], expected)
        self.assertEqual(self.ws.read("api/skew-mobile")["missing_baselines"], expected)

    def test_unaffected_card_carries_no_notice(self):
        hit = self.preview("JWT TTL", "@overlay/api/jwt")
        self.assertNotIn("baseline_superseded_by", hit)
        self.assertNotIn("missing_baselines", hit)


class Scenario06cDiamondBaselines(WorkspaceTestCase):
    """``D extends [B, C]``, ``B extends A``, ``C extends A``: the shared root is composed once."""

    def setUp(self):
        super().setUp()
        self.ws.write("a", summary="Root policy.")
        self.ws.write("b", summary="Branch B refines the root.", extends=["a"])
        self.ws.write("c", summary="Branch C refines the root.", extends=["a"])
        self.ws.write("d", summary="D joins both branches.", extends=["b", "c"])

    def test_shared_baseline_listed_once_in_composition_order(self):
        # Every baseline comes after the baselines it extends itself.
        res = self.ws.read("d")
        self.assertEqual([b["address"] for b in res["baselines"]], ["@overlay/a", "@overlay/b", "@overlay/c"])

    def test_superseded_shared_root_flagged_once(self):
        self.ws.write("r", summary="Root policy v2.", supersedes=["a"])
        self.assertEqual(self.ws.read("d")["baseline_superseded_by"], ["@overlay/r"])
        hit = {r["address"]: r for r in self.ws.search("joins both branches")["results"]}["@overlay/d"]
        self.assertEqual(hit["baseline_superseded_by"], ["@overlay/r"])


class Scenario07StagedOpTransition(WorkspaceTestCase):
    def test_tombstone_keeps_original_base_and_apply_aborts(self):
        file = self.put_overlay("api/a", card_text("A", "Card A.", ["one"]))
        h1 = sha256_bytes(file.read_bytes())
        self.ws.write("api/a", op="append", content="two", stage=True)
        manifest = json.loads((self.root / "staging/.manifest.json").read_text())
        self.assertEqual(manifest["entries"]["api/a"]["base_sha256"], h1)
        self.assertNotIn("two", self.ws.read("api/a")["body"])  # staging is invisible to live reads

        file.write_text(card_text("A", "Card A edited in the IDE.", ["one"]), encoding="utf-8")
        bump_mtime(file)
        h2 = sha256_bytes(file.read_bytes())
        self.assertEqual(self.ws.read("api/a")["sha256"], h2)  # lazy (mtime, size) check re-indexed h2
        self.assertEqual(self.addresses(self.ws.search("IDE")), ["@overlay/api/a"])

        self.ws.write("api/a", op="delete", stage=True)
        entry = json.loads((self.root / "staging/.manifest.json").read_text())["entries"]["api/a"]
        self.assertEqual(entry, entry | {"op": "delete", "base_sha256": h1})
        self.assertEqual(entry["history"], ["append", "delete"])
        self.assertFalse((self.root / "staging/api/a.md").exists())

        with self.assertRaises(ApplyConflictError) as ctx:
            self.ws.apply()
        self.assertEqual(ctx.exception.details["conflicts"][0]["base_sha256"], h1)
        self.assertTrue(file.exists())
        self.assertEqual(sha256_bytes(file.read_bytes()), h2)


class Scenario08StagedCreateVsExternalCreation(WorkspaceTestCase):
    def test_existence_conflict(self):
        self.ws.write("api/new", summary="Staged new card.", content="- staged", stage=True)
        self.assertEqual(self.ws.search("staged")["total_matches"], 0)
        external = self.put_overlay("api/new", card_text("New", "Created externally.", ["external"]))
        h2 = sha256_bytes(external.read_bytes())
        self.assertEqual(self.addresses(self.ws.search("externally")), ["@overlay/api/new"])
        diff = self.ws.diff("staging")
        self.assertFalse(diff["clean"])
        self.assertEqual(diff["items"][0]["conflict"], f"expected absent, found {h2[:12]}")
        with self.assertRaises(ApplyConflictError):
            self.ws.apply()
        self.assertEqual(sha256_bytes(external.read_bytes()), h2)


class Scenario09FilteredPackExcludedReference(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.ws.write("shared/prefs", summary="Shared team preferences.", content="- Prefer small PRs.")
        self.ws.write("team/profile", summary="Team profile.", content="- Uses [[shared/prefs]].", extends=["shared/prefs"])

    def test_rejects_without_include_deps(self):
        with self.assertRaises(UnresolvedExportDependencyError) as ctx:
            self.ws.pack(self.tmp / "team.slice", prefix="team/")
        missing = ctx.exception.details["missing"]
        self.assertEqual({m["target"] for m in missing}, {"@overlay/shared/prefs"})
        self.assertFalse((self.tmp / "team.slice").exists())

    def test_qualified_overlay_reference_also_rejected(self):
        self.ws.write("team/profile", op="replace", extends=["@overlay/shared/prefs"])
        with self.assertRaises(UnresolvedExportDependencyError):
            self.ws.pack(self.tmp / "team.slice", prefix="team/")

    def test_include_deps_pulls_transitive_cards(self):
        res = self.ws.pack(self.tmp / "team.slice", prefix="team/", include_deps=True)
        self.assertEqual(res["cards"], ["shared/prefs", "team/profile"])
        self.assertEqual(res["included_dependencies"], ["shared/prefs"])
        self.assertTrue((self.tmp / "team.slice/shared/prefs.md").exists())
        self.assertTrue(res["validation"]["ok"], res["validation"])


class Scenario09bTransitiveAliasedDependencies(WorkspaceTestCase):
    """``include_deps`` follows a multi-hop chain whose references are card aliases."""

    def setUp(self):
        super().setUp()
        self.project({"legacy": card_text("Legacy", "Legacy retry policy.")})
        self.ws.write("common/base", summary="Retry policy.", aliases=["base-alias"], supersedes=["@project/legacy"])
        self.ws.write("common/mid", summary="Retry policy for batch jobs.", aliases=["mid-alias"],
                      extends=["base-alias"])
        self.ws.write("team/entry", summary="Team entry point.", content="- See [[@overlay/mid-alias#sec|Mid]].")

    def test_pulls_chain_rewrites_alias_link_and_validates(self):
        out = self.tmp / "team.slice"
        res = self.ws.pack(out, prefix="team/", include_deps=True)
        self.assertEqual(res["cards"], ["common/base", "common/mid", "team/entry"])
        self.assertEqual(res["included_dependencies"], ["common/mid", "common/base"])
        self.assertEqual(res["dependencies"], ["@project"])
        self.assertEqual(res["warnings"], [])
        self.assertEqual(res["validation"], {"ok": True, "errors": [], "warnings": 0})
        entry = (out / "team/entry.md").read_text()
        self.assertIn("[[common/mid#sec|Mid]]", entry)
        self.assertNotIn("@overlay", entry)
        # Slice-relative alias refs are kept verbatim: they still resolve inside the exported slice.
        self.assertIn('extends = ["base-alias"]', (out / "common/mid.md").read_text())
        self.assertIn('supersedes = ["@project/legacy"]', (out / "common/base.md").read_text())
        self.assertEqual(tomllib.loads((out / "slice.toml").read_text())["dependencies"], ["@project"])
        check = self.ws.validate(out)
        self.assertEqual((check["errors"], check["warnings"]), ([], []))


class Scenario10PackValidateMountRead(WorkspaceTestCase):
    def test_slice_relative_scope_after_mount(self):
        self.ws.write("db/conn", summary="Connection settings v1.", content="- Pool size 10.")
        self.ws.write("db/pool", summary="Pool tuning.", content="- See [[@overlay/db/conn]].",
                      extends=["@overlay/db/conn"])
        res = self.ws.pack(self.tmp / "db.slice", prefix="db/")
        self.assertEqual(res["dependencies"], [])
        exported = (self.tmp / "db.slice/db/pool.md").read_text()
        self.assertIn('extends = ["db/conn"]', exported)
        self.assertIn("[[db/conn]]", exported)
        self.assertTrue(self.ws.validate(self.tmp / "db.slice")["ok"])

        self.ws.mount(self.tmp / "db.slice", alias="@db", precedence=40, role="curated")
        self.ws.write("db/conn", op="replace", summary="Connection settings v2 (overlay drifted).")
        res = self.ws.read("@db/db/pool")
        self.assertEqual([b["address"] for b in res["baselines"]], ["@db/db/conn"])
        self.assertIn("v1", res["baselines"][0]["summary"])
        self.assertEqual(res["links"], [{"ref": "db/conn", "address": "@db/db/conn"}])


class Scenario11CrashDuringApply(WorkspaceTestCase):
    def test_recovery_by_next_reader(self):
        self.ws.write("api/old", summary="Old card to delete.", content="- old")
        self.ws.write("api/old", op="delete", stage=True)
        self.ws.write("api/fresh", summary="Freshly applied knowledge about zebras.", content="- zebras", stage=True)
        # Simulate a crash after moving files and removing the manifest, before removing the journal.
        table = self.ws.table()
        staging = self.ws.staging
        entries = staging.entries()
        actions = [
            {"op": "delete", "id": "api/old", "base_sha256": entries["api/old"]["base_sha256"]},
            {"op": "move", "id": "api/fresh", "base_sha256": None,
             "sha256": sha256_bytes(staging.file("api/fresh").read_bytes()), "change": "create"},
        ]
        staging.write_journal({"version": 1, "actions": actions, "overlay_root": str(table.overlay.root)})
        (self.root / "staging/api/fresh.md").replace(self.overlay_file("api/fresh"))
        self.overlay_file("api/old").unlink()
        staging.manifest_path.unlink()
        self.ws.close()

        other = Workspace(self.root)  # a different "process"
        try:
            res = other.search("zebras")
            self.assertEqual(self.addresses(res), ["@overlay/api/fresh"])
            self.assertFalse(staging.journal_path.exists())
            self.assertEqual(other.search("old card delete")["total_matches"], 0)
            self.assertTrue(other.last_recovery["recovered"])
        finally:
            other.close()
        self.ws = Workspace(self.root)

    def test_writer_recovers_before_executing(self):
        self.ws.write("api/fresh", summary="Freshly applied.", content="- one", stage=True)
        staging = self.ws.staging
        sha = sha256_bytes(staging.file("api/fresh").read_bytes())
        staging.write_journal({"version": 1, "overlay_root": str(self.ws.table().overlay.root), "actions": [
            {"op": "move", "id": "api/fresh", "base_sha256": None, "sha256": sha, "change": "create"}]})
        # Crash before anything moved: the writer must finish the batch first.
        self.ws.write("api/fresh", op="append", content="- two")
        self.assertFalse(staging.journal_path.exists())
        self.assertIn("- two", self.ws.read("api/fresh")["body"])
        self.assertEqual(self.ws.diff()["items"], [])

    def test_replay_is_idempotent(self):
        self.ws.write("x", summary="X.", content="- x", stage=True)
        sha = sha256_bytes(self.ws.staging.file("x").read_bytes())
        journal = {"version": 1, "overlay_root": str(self.ws.table().overlay.root), "actions": [
            {"op": "move", "id": "x", "base_sha256": None, "sha256": sha, "change": "create"}]}
        with self.ws.lock.exclusive():
            first = replay(self.ws, self.ws.table(), journal)
            second = replay(self.ws, self.ws.table(), journal)
        self.assertEqual(first["created"], ["@overlay/x"])
        self.assertEqual(second["created"], ["@overlay/x"])
        self.assertTrue(self.overlay_file("x").exists())

    def test_replay_finishes_batch_without_clobbering_external_edits(self):
        self.ws.write("b-edit", summary="B as applied.", content="- b1")
        self.ws.write("c-gone", summary="C to delete.", content="- c1")
        self.ws.write("a-new", summary="A staged.", content="- a1", stage=True)
        self.ws.write("b-edit", op="replace", summary="B staged.", stage=True)
        self.ws.write("c-gone", op="delete", stage=True)
        staging = self.ws.staging
        entries = staging.entries()
        staged_b = staging.file("b-edit").read_bytes()
        journal = {"version": 1, "overlay_root": str(self.ws.table().overlay.root), "actions": [
            {"op": "move", "id": "a-new", "base_sha256": None,
             "sha256": sha256_bytes(staging.file("a-new").read_bytes()), "change": "create"},
            {"op": "move", "id": "b-edit", "base_sha256": entries["b-edit"]["base_sha256"],
             "sha256": sha256_bytes(staged_b), "change": "modify"},
            {"op": "delete", "id": "c-gone", "base_sha256": entries["c-gone"]["base_sha256"]},
        ]}
        staging.write_journal(journal)
        staging.file("a-new").replace(self.overlay_file("a-new"))  # move #1 landed, then the crash
        edited = {}
        for path in ("b-edit", "c-gone"):  # a human edits both remaining targets before recovery
            file = self.put_overlay(path, card_text(path, "Edited by a human mid-recovery."))
            bump_mtime(file)
            edited[path] = file.read_bytes()

        with self.ws.lock.exclusive():
            report = replay(self.ws, self.ws.table(), journal)
        self.assertEqual((report["applied"], report["created"], report["modified"], report["deleted"]),
                         (1, ["@overlay/a-new"], [], []))
        self.assertEqual([s["address"] for s in report["skipped"]], ["@overlay/b-edit", "@overlay/c-gone"])
        for path, data in edited.items():
            self.assertEqual(self.overlay_file(path).read_bytes(), data)
        self.assertEqual(staging.file("b-edit").read_bytes(), staged_b)  # kept for a human to reconcile
        self.assertFalse(staging.journal_path.exists())
        self.assertEqual(self.ws.read("a-new")["summary"], "A staged.")
        # Both skipped changes stay staged against the version they were based on, not as fresh creates.
        items = {i["id"]: i for i in self.ws.diff()["items"]}
        self.assertEqual(set(items), {"b-edit", "c-gone"})
        for path, op in (("b-edit", "write"), ("c-gone", "delete")):
            base, current = entries[path]["base_sha256"], sha256_bytes(edited[path])
            self.assertEqual((items[path]["op"], items[path]["base_sha256"]), (op, base))
            self.assertEqual(items[path]["conflict"], f"expected {base[:12]}, found {current[:12]}")
            self.assertNotIn("orphan", items[path])
        self.assertEqual(items["b-edit"]["history"], ["replace"])
        with self.assertRaises(ApplyConflictError):
            self.ws.apply()

    def test_skipped_delete_is_rebuilt_from_the_journal_if_the_manifest_is_gone(self):
        self.ws.write("gone", summary="To delete.")
        self.ws.write("gone", op="delete", stage=True)
        base = self.ws.staging.entries()["gone"]["base_sha256"]
        journal = {"version": 1, "overlay_root": str(self.ws.table().overlay.root),
                   "actions": [{"op": "delete", "id": "gone", "base_sha256": base}]}
        self.ws.staging.write_journal(journal)
        self.ws.staging.manifest_path.unlink()  # an earlier pass got past step (d), then crashed
        bump_mtime(self.put_overlay("gone", card_text("Gone", "Recreated by a human.")))
        self.assertEqual(self.ws.search("recreated human")["total_matches"], 1)  # recovery ran
        self.assertEqual([s["address"] for s in self.ws.last_recovery["skipped"]], ["@overlay/gone"])
        [item] = self.ws.diff()["items"]
        self.assertEqual((item["id"], item["op"], item["base_sha256"]), ("gone", "delete", base))
        self.assertTrue(item["conflict"])


if __name__ == "__main__":
    unittest.main()
