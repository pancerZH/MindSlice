"""Run every journey; then prove the end state is stable (cold-cache restart, replay determinism)."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from .harness import restart_with_cold_cache, run_journey
from .journeys import cold_start, few_slices, many_slices


class JourneyTestCase(unittest.TestCase):
    journey = None  # set by subclasses

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mindslice-journey-"))
        self.runs = []

    def tearDown(self) -> None:
        for run in self.runs:
            run.ws.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_once(self, name: str):
        run = run_journey(type(self).journey(), self.tmp / name / "ws")
        self.runs.append(run)
        return run

    def test_journey_and_cold_restart(self):
        run = self.run_once("a")
        self.assertTrue(run.fingerprint["cards"])
        rebuilt = restart_with_cold_cache(run)
        self.assertEqual(rebuilt, run.fingerprint, "end state must be fully reconstructible from Markdown on disk")

    def test_replay_is_deterministic(self):
        first, second = self.run_once("a"), self.run_once("b")
        a = json.dumps(first.transcript.normalized(), ensure_ascii=False, indent=1).splitlines()
        b = json.dumps(second.transcript.normalized(), ensure_ascii=False, indent=1).splitlines()
        if a != b:
            diverge = next(i for i, (x, y) in enumerate(zip(a + [""], b + [""])) if x != y)
            self.fail(f"transcripts diverge at line {diverge}:\n  run a: {a[diverge:diverge + 3]}\n  run b: {b[diverge:diverge + 3]}")
        self.assertEqual(first.fingerprint, second.fingerprint)


class ColdStartJourney(JourneyTestCase):
    journey = staticmethod(cold_start)


class FewSlicesJourney(JourneyTestCase):
    journey = staticmethod(few_slices)


class ManySlicesJourney(JourneyTestCase):
    journey = staticmethod(many_slices)


del JourneyTestCase  # abstract base: keep unittest from collecting it

if __name__ == "__main__":
    unittest.main()
