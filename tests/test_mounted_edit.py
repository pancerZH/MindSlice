"""replace / append of a card that lives only in a read-only slice edit a copy in the overlay."""

from mindslice.errors import NotFoundError, PreconditionFailedError, ReadOnlyMountError

from .helpers import WorkspaceTestCase, card_text


class MountedEditTests(WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.slice = self.mount_slice("story", {
            "plot/state": card_text("State", "Session one state.", ["fact one", "see [[plot/people]]"], aliases=["progress"]),
            "plot/people": card_text("People", "Who is who.", ["Lu is a courier"]),
        }, "@story", 50, "curated")
        self.before = {p: p.read_bytes() for p in self.slice.rglob("*.md")}

    def tearDown(self):
        self.assertEqual({p: p.read_bytes() for p in self.slice.rglob("*.md")}, self.before)  # the slice is never edited
        super().tearDown()

    def test_append_after_bake_saves_a_superseding_copy(self):
        result = self.ws.write("plot/state", op="append", content=["fact two"], reason="session two")
        self.assertEqual((result["address"], result["changed"], result["staged"]), ("@overlay/plot/state", True, False))
        self.assertEqual(result["forked_from"], "@story/plot/state")
        self.assertIsNone(result["previous_sha256"])
        text = self.overlay_file("plot/state").read_text(encoding="utf-8")
        self.assertIn('supersedes = ["@story/plot/state"]', text)
        self.assertIn('aliases = ["progress"]', text)  # the fields of the base carry over
        self.assertIn("- fact one\n", text)
        self.assertIn("- fact two\n", text)
        # Inside the slice [[plot/people]] meant the slice's card; from the overlay it has to say so.
        self.assertIn("[[@story/plot/people]]", text)
        # One card answers for the topic: reads and hits of the base forward to the copy.
        self.assertEqual(self.ws.read("plot/state")["address"], "@overlay/plot/state")
        exact = self.ws.read("@story/plot/state")
        self.assertEqual((exact["address"], exact["redirected_from"]), ("@overlay/plot/state", "@story/plot/state"))
        self.assertEqual(self.addresses(self.ws.search("fact")), ["@overlay/plot/state"])
        # A later edit is an ordinary overlay write.
        again = self.ws.write("plot/state", op="append", content=["fact three"])
        self.assertNotIn("forked_from", again)
        self.assertEqual(again["previous_sha256"], result["sha256"])

    def test_replace_keeps_what_it_does_not_pass_and_bake_folds_the_copy_in(self):
        result = self.ws.write("plot/people", op="replace", summary="Who is who, after session two.")
        self.assertEqual(result["forked_from"], "@story/plot/people")
        text = self.overlay_file("plot/people").read_text(encoding="utf-8")
        self.assertIn("Who is who, after session two.", text)
        self.assertIn("- Lu is a courier", text)
        status = self.ws.status()
        self.assertEqual([c["address"] for c in status["dirty_slices"][0]["cards"]], ["@overlay/plot/people"])
        baked = self.ws.bake("story")
        self.assertFalse(self.overlay_file("plot/people").exists())
        card = self.ws.read("@story/plot/people")
        self.assertEqual(card["address"], "@story/plot/people")
        self.assertIn("after session two", card["summary"])
        new_text = (self.ws.table().get("@story").root / "plot" / "people.md").read_text(encoding="utf-8")
        self.assertNotIn("@story/plot/people", new_text)  # the reference to itself is gone
        self.assertTrue(baked)

    def test_a_write_that_changes_nothing_makes_no_copy(self):
        result = self.ws.write("plot/people", op="append", content=["Lu is a courier"])
        self.assertEqual((result["changed"], result["address"]), (False, "@story/plot/people"))
        self.assertNotIn("forked_from", result)
        self.assertFalse(self.overlay_file("plot/people").exists())
        self.assertEqual(self.ws.history.events(), [])

    def test_if_match_is_the_sha_read_returned(self):
        sha = self.ws.read("plot/state")["sha256"]
        with self.assertRaises(PreconditionFailedError):
            self.ws.write("plot/state", op="append", content=["x"], if_match="0" * 64)
        self.assertTrue(self.ws.write("plot/state", op="append", content=["x"], if_match=sha)["changed"])

    def test_explicit_supersedes_keeps_the_base_too(self):
        self.ws.write("plot/old", summary="An older note.")
        self.ws.write("plot/state", op="replace", supersedes=["@overlay/plot/old"])
        text = self.overlay_file("plot/state").read_text(encoding="utf-8")
        self.assertIn('supersedes = ["@overlay/plot/old", "@story/plot/state"]', text)

    def test_staged_copy_and_standing_cards_wait_for_approval(self):
        staged = self.ws.write("plot/state", op="append", content=["staged fact"], stage=True)
        self.assertEqual((staged["staged"], staged["forked_from"]), (True, "@story/plot/state"))
        self.assertFalse(self.overlay_file("plot/state").exists())
        self.ws.apply(["plot/state"])
        self.assertEqual(self.ws.read("@story/plot/state")["address"], "@overlay/plot/state")
        # A standing card of a slice: its edited copy changes every session, so the user approves it,
        # and once approved it replaces the slice's card in the boot set instead of loading next to it.
        rules = self.make_slice("rules", {"tone": "+++\ntitle = \"Tone\"\nload = \"always\"\n+++\n\nBe brief.\n"}, alias="@rules")
        self.ws.mount(rules, alias="@rules", precedence=40, role="curated")
        result = self.ws.write("tone", op="append", content=["Use plain words."])
        self.assertTrue(result["staged"])
        self.assertIn("requires_approval", result)
        self.assertEqual([c["address"] for c in self.ws.boot()["cards"]], ["@rules/tone"])
        self.ws.apply(["tone"])
        self.assertEqual([c["address"] for c in self.ws.boot()["cards"]], ["@overlay/tone"])

    def test_what_still_fails_and_says_why(self):
        with self.assertRaises(NotFoundError):
            self.ws.write("plot/nowhere", op="replace", summary="No such card in any mount.")
        with self.assertRaises(ReadOnlyMountError) as caught:
            self.ws.write("@story/plot/state", op="append", content=["x"])
        self.assertIn("without the alias", caught.exception.details["next_steps"][0])
        self.assertIn("'plot/state'", caught.exception.details["next_steps"][0])
        # create keeps its meaning: a new overlay card at that path, not a copy.
        created = self.ws.write("plot/people", summary="A new card.")
        self.assertNotIn("forked_from", created)
        self.assertNotIn("Lu is a courier", self.overlay_file("plot/people").read_text(encoding="utf-8"))
