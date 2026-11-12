"""The agent-in-the-loop runner (evals/agent): prompts, transcripts, value judgments, scripted agents,
the MCP proxy and the agy adapter's offline parts. No language model and no benchmark data are needed:
the scripted agents run on the synthetic episodes of ``test_external_eval``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evals.agent import agy, prompts, score
from evals.agent.judge import Judge, card_text, is_stale, states
from evals.agent.run import gate
from evals.agent.runner import run_haystack
from evals.agent.sessions import MAB_BATCH, agent_sessions, flat
from evals.agent.tools import Dispatcher, summarize_calls
from evals.external.corpus import Session, Turn
from evals.external.datasets import Haystack, Question, fact_values, mab_haystack, meme, words
from mindslice import Workspace
from tests.test_external_eval import _write, meme_episode

REPO = Path(__file__).resolve().parents[1]
OFFLINE = ("flat", "oracle", "scripted-flat", "scripted-oracle", "scripted-overlay")


def synthetic_meme() -> Haystack:
    with tempfile.TemporaryDirectory() as tmp:
        _write(Path(tmp), "meme-nofiller", [meme_episode()])
        (h,) = list(meme("meme-nofiller", Path(tmp)))
    return h


def synthetic_mab(n_filler: int = 120) -> Haystack:
    """A MemoryAgentBench-shaped context: conflicting facts among unrelated ones, three judged questions."""
    facts = ["The capital of Romania is Bucharest.", "Leonte Rautu is employed by University of Bucharest.",
             "Le Petit Parisien was created in the country of France.", "The capital of France is Paris."]
    facts += [f"Person{i} Surname{i} is a citizen of Country{i % 7}." for i in range(n_filler)]
    facts += ["The capital of Romania is Rajanpur.", "The capital of France is Harare.",
              "The headquarters of University of Bucharest is located in the city of Bucharest.",
              "The headquarters of University of Bucharest is located in the city of Ankara."]
    context = "\n".join(f"{i}. {t}" for i, t in enumerate(facts))
    questions = ["What is the capital of Romania?", "What is the capital of France?",
                 "Which city is the headquarter of University of Bucharest located in?", "Who is Person3 Surname3 a citizen of?"]
    answers = [["Rajanpur"], ["Harare"], ["Ankara"], ["Country3"]]
    return mab_haystack("factconsolidation_sh_test", context, questions, answers, [f"q{i}" for i in range(4)])


class PromptTests(unittest.TestCase):
    def test_prompts_are_the_plans_verbatim(self):
        plan = (REPO / "evals" / "agent_test.md").read_text(encoding="utf-8")
        quotes = []
        for block in re.split(r"\n\s*\n", plan):
            lines = [l.strip() for l in block.split("\n")]
            if lines and all(l.startswith(">") for l in lines):
                quotes.append(" ".join(l.lstrip(">").strip() for l in lines))
        self.assertIn(prompts.TASK, quotes)
        self.assertIn(prompts.POLICY, quotes)
        self.assertIn(prompts.OVERLAY, quotes)
        # "> Session {i} of {n}, {date}:" / ">" / "> {transcript}": a header line, a blank line, the transcript.
        self.assertIn("Session {i} of {n}, {date}:  {transcript}", quotes)
        self.assertEqual(prompts.session_message(1, 5, "2023/03/01 (Wed) 09:00", "T"), "Session 1 of 5, 2023/03/01 (Wed) 09:00:\n\nT")

    def test_system_prompts(self):
        from mindslice.interfaces.mcp_server import INSTRUCTIONS

        self.assertEqual(prompts.system_prompt("agent-default"), INSTRUCTIONS + "\n\n" + prompts.TASK)
        self.assertTrue(prompts.system_prompt("agent-overlay").endswith(prompts.POLICY + "\n\n" + prompts.OVERLAY))
        self.assertEqual(prompts.session_message(2, 5, "", "x"), "Session 2 of 5:\n\nx")
        self.assertEqual(len(set(prompts.digests().values())), len(prompts.digests()))


class SessionTests(unittest.TestCase):
    def test_meme_transcripts_are_the_card_lines(self):
        h = synthetic_meme()
        s = agent_sessions(h)
        self.assertEqual([x.index for x in s], [0, 1, 2, 3])
        self.assertEqual(s[0].date, "2023/03/01 (Wed) 10:00")
        lines = s[0].transcript.split("\n")
        self.assertEqual(lines[0], "Assistant: Hi! How can I help you today?")
        self.assertEqual(lines[1], "User: My health condition is lactose intolerance.")
        card_bullets = [l for c in s[0].cards for l in c.body if not l.startswith("Date: ")]
        self.assertEqual(lines, card_bullets)  # exactly the turn lines of the session's round cards
        self.assertEqual(sum(len(x.cards) for x in s), len(flat(h).cards))

    def test_mab_batches(self):
        h = synthetic_mab()
        s = agent_sessions(h)
        n = len(h.sessions[0].turns)
        self.assertEqual(len(s), -(-n // MAB_BATCH))
        self.assertEqual(s[0].transcript.split("\n")[0], f"Facts 1-{MAB_BATCH} of {n}, in the order they were stated:")
        self.assertEqual(s[-1].transcript.split("\n")[0],
                         f"Facts {MAB_BATCH * (len(s) - 1) + 1}-{n} of {n}, in the order they were stated:")
        self.assertEqual(len(s[0].transcript.split("\n")), MAB_BATCH + 1)
        self.assertEqual(s[0].transcript.split("\n")[1], "The capital of Romania is Bucharest.")
        self.assertEqual(s[0].date, "")


class JudgeTests(unittest.TestCase):
    def test_states_whole_words_and_anchors(self):
        t = card_text("Facts", [], "Le Petit Parisien was created in the country of France.",
                      "- The capital of France is Paris.\n- Leonte Rautu is employed by University of Bucharest.")
        self.assertTrue(states(t, "paris"))
        self.assertFalse(states(card_text("x", [], "Le Petit Parisien", ""), "paris"))
        self.assertTrue(states(t, "paris", ["france", "capital"]))  # same line
        self.assertFalse(states(t, "bucharest", ["romania"]))  # anchors on no line with the value
        self.assertTrue(is_stale(t, ["paris"], ["harare"], ["france"]))
        self.assertFalse(is_stale(card_text("x", [], "France: capital Paris, now Harare", ""), ["paris"], ["harare"], ["france"]))
        self.assertTrue(states(card_text("x", [], "I drive a Therwyn Compact.", ""), "therwyn compact"))
        self.assertTrue(states(card_text("x", [], "Reading The Quorath Codex (book).", ""), "the quorath codex (book)"))

    def test_mab_values_never_anchor_on_themselves(self):
        h = synthetic_mab()
        v = {q.id: q.meta["values"] for q in h.questions}
        self.assertEqual(v["q2"]["stale"], ["bucharest"])
        self.assertNotIn("bucharest", v["q2"]["anchors"])
        self.assertEqual(v["q0"], {"current": ["rajanpur"], "stale": ["bucharest"], "anchors": ["romania"], "latest": True})


class ScriptedAgentTests(unittest.TestCase):
    """agent_test.md 7.4: the scripted agents reproduce flat and oracle through the four tools (CI gate)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.runs = {}
        for h in (synthetic_meme(), synthetic_mab()):
            for arm in OFFLINE:
                cls.runs.setdefault(arm, []).extend(run_haystack(h, arm, root / arm / h.key.replace("/", "__")))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_gate(self):
        g = gate(self.runs)
        for pair in ("scripted-flat vs flat", "scripted-oracle vs oracle"):
            for metric, row in g[pair].items():
                self.assertEqual(row["disagree"], 0, (pair, metric))
                self.assertEqual(row["only_one_side"], 0, (pair, metric))
        for metric, row in g["scripted-overlay vs oracle"].items():
            self.assertEqual(row["paired"]["mean"], 0.0, metric)

    def test_expected_values(self):
        u = {a: score.pooled(score.units(r)) for a, r in self.runs.items()}
        self.assertEqual(u["flat"]["retired"]["mean"], 0.0)
        self.assertEqual(u["oracle"]["retired"]["mean"], 1.0)
        self.assertEqual(u["oracle"]["stale-first"]["mean"], 0.0)
        self.assertGreater(u["flat"]["stale-first"]["mean"], 0.0)
        self.assertEqual(u["flat"]["lost"]["mean"], 0.0)
        self.assertEqual(u["oracle"]["lost"]["mean"], 0.0)
        self.assertEqual(u["flat"]["forgotten"]["mean"], 0.0)  # the request round itself states the value
        # Mode B deletes the partner card, but the anniversary-gift dependent ("I bought James a watch") stays.
        self.assertEqual(u["oracle"]["forgotten"]["mean"], 0.0)
        self.assertEqual(u["scripted-overlay"]["history-named@10"]["mean"], 1.0)

    def test_lost_follows_dependencies(self):
        """After the root change, the 1- and 2-hop dependents' old values no longer count as current."""
        recs = [r for r in self.runs["flat"] if r["kind"] == "value" and r["dataset"] == "meme-nofiller" and r["point"] == "end"]
        cats = {r["value"]: r["category"] for r in recs}
        self.assertNotIn("quelmithin", cats)
        self.assertNotIn("crysthene pool", cats)
        self.assertNotIn("james", cats)  # deleted
        self.assertEqual(cats["multivitamin"], "rule")
        self.assertEqual(cats["high blood pressure"], "plain")
        self.assertEqual(cats["xylorim scooter"], "plain")
        before = {r["value"] for r in self.runs["flat"] if r["kind"] == "value" and r["point"] == 2}
        self.assertIn("quelmithin", before)
        self.assertIn("james", before)

    def test_overlay_writes_lineage_only(self):
        sessions = [r for r in self.runs["scripted-overlay"] if r["kind"] == "session" and r["dataset"] == "meme-nofiller"]
        writes = sum(r["ops"].get("create", 0) for r in sessions)
        flat_writes = sum(r["ops"].get("create", 0) for r in self.runs["scripted-flat"] if r["kind"] == "session" and r["dataset"] == "meme-nofiller")
        self.assertLess(writes, flat_writes)
        self.assertGreater(sum(r["with_supersedes"] for r in sessions), 0)


class ToolTests(unittest.TestCase):
    def test_dispatcher_cap_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace.init(Path(tmp) / "ws")
            try:
                d = Dispatcher(ws, None, 0, cap=2)
                ok = d("write", {"id": "a", "content": ["- x"], "summary": "x"})
                self.assertFalse(ok["isError"])
                bad = d("read", {"address": "@overlay/missing"})
                self.assertTrue(bad["isError"])
                refused = d("manifest", {})
                self.assertTrue(refused["isError"])
                self.assertEqual(json.loads(refused["content"][0]["text"])["error"], "CallLimit")
                self.assertTrue(d.cap_hit)
            finally:
                ws.close()
        rows = [{"tool": "write", "arguments": {"op": "create", "supersedes": ["@overlay/x"]}},
                {"tool": "write", "arguments": {"op": "delete"}, "is_error": True},
                {"tool": "search", "arguments": {}}, {"tool": "read", "arguments": {}, "refused": True}]
        s = summarize_calls(rows)
        self.assertEqual((s["tool_calls"], s["ops"], s["with_supersedes"], s["tool_errors"], s["cap_hit"]),
                         (4, {"create": 1, "delete": 1}, 1, 1, True))

    def test_mcp_proxy_relays_logs_and_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            Workspace.init(Path(tmp) / "ws").close()
            log = Path(tmp) / "calls.jsonl"
            msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "write", "arguments": {"id": "a", "content": ["- x"], "summary": "x"}}},
                    {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "search", "arguments": {"query": "x"}}},
                    {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "manifest", "arguments": {}}}]
            proc = subprocess.run([sys.executable, "-m", "evals.agent.mcp_proxy", "--workspace", str(Path(tmp) / "ws"),
                                   "--log", str(log), "--session", "7", "--cap", "2", "--context", '{"arm": "t"}'],
                                  input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True,
                                  cwd=REPO, env={**os.environ, "PYTHONPATH": str(REPO)}, timeout=60)
            answers = [json.loads(l) for l in proc.stdout.splitlines()]
            self.assertEqual([a["id"] for a in answers], [1, 2, 3, 4, 5])
            self.assertIn("instructions", answers[0]["result"])
            self.assertEqual([t["name"] for t in answers[1]["result"]["tools"]], ["manifest", "search", "read", "write"])
            self.assertFalse(answers[3]["result"]["isError"])
            self.assertTrue(answers[4]["result"]["isError"])
            rows = [json.loads(l) for l in log.read_text().splitlines()]
            calls = [r for r in rows if r["kind"] == "tools/call"]
            self.assertEqual([(r["tool"], r["refused"], r["session"], r["arm"]) for r in calls],
                             [("write", False, 7, "t"), ("search", False, 7, "t"), ("manifest", True, 7, "t")])
            self.assertTrue(log.with_name("calls.jsonl.cap").exists())


class QuotaGateTests(unittest.TestCase):
    """The runner pauses new sessions while a quota bucket is low, until its reset (no model call involved)."""

    def make(self, readings):
        clock = {"t": 1000.0}
        seq = iter(readings)
        last = {"q": None}

        def reader():
            last["q"] = next(seq, last["q"])
            return last["q"]

        def sleep(s):
            clock["t"] += s

        gate = agy.QuotaGate(min_5h=0.12, min_weekly=0.05, reader=reader, sleep=sleep, now=lambda: clock["t"], ttl_s=60)
        return gate, clock

    @staticmethod
    def q(five, weekly=0.8, reset=5000.0):
        return {"5h": {"remaining": five, "reset": reset}, "weekly": {"remaining": weekly, "reset": 9e9}}

    def test_no_wait_when_quota_is_fine(self):
        gate, clock = self.make([self.q(0.5)])
        self.assertEqual(gate.wait(), 0.0)
        self.assertEqual(gate.pauses, [])

    def test_waits_for_the_reset(self):
        gate, clock = self.make([self.q(0.10), self.q(0.10), self.q(0.95)])
        waited = gate.wait()
        self.assertGreater(waited, 0)
        self.assertEqual(len(gate.pauses), 1)
        self.assertEqual(gate.pauses[0]["window"], "5h")
        self.assertGreaterEqual(gate.pauses[0]["end"], 1000.0 + 30)

    def test_weekly_and_unreadable(self):
        gate, _ = self.make([self.q(0.9, weekly=0.03), self.q(0.9, weekly=0.9)])
        self.assertEqual(gate.low(self.q(0.9, weekly=0.03)), "weekly")
        self.assertIsNone(gate.low(None))  # can't read the quota: don't block on it

    def test_quota_failures_are_recognized(self):
        from evals.agent.agents import SessionOutcome

        gate, _ = self.make([self.q(0.5)])
        self.assertTrue(gate.is_quota_failure(SessionOutcome(meta={"error": "RESOURCE_EXHAUSTED: quota exceeded"})))
        self.assertFalse(gate.is_quota_failure(SessionOutcome(meta={"error": "timeout after 1800s"})))
        gate, _ = self.make([self.q(0.05)])
        self.assertTrue(gate.is_quota_failure(SessionOutcome(meta={"error": "exit 3"})))  # failed while quota is low

    def test_schedule_follows_the_matrix(self):
        from evals.agent.run import EXCLUDED, MATRIX, MAIN_MODEL

        self.assertEqual(len(MATRIX), 4)
        self.assertEqual({m for _, m in MATRIX if _ != "agent-policy"}, {MAIN_MODEL})
        self.assertFalse(set(MATRIX) & set(EXCLUDED))


class AgyOfflineTests(unittest.TestCase):
    def test_config_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp) / "cwd"
            agy.write_config(cwd, "SYSTEM PROMPT", Path(tmp) / "ws", Path(tmp) / "calls.jsonl", 3, 40, {"arm": "x"})
            md = (cwd / ".agents" / "agents" / f"{agy.AGENT}.md").read_text()
            self.assertTrue(md.startswith("---\n") and md.endswith("---\nSYSTEM PROMPT\n"))
            self.assertIn("excludeDefaultComponents: true", md)
            cfg = json.loads((cwd / ".agents" / "plugins" / agy.PLUGIN / "mcp_config.json").read_text())
            server = cfg["mcpServers"][agy.SERVER]
            self.assertEqual(server["args"][:2], ["-m", "evals.agent.mcp_proxy"])
            self.assertIn("--cap", server["args"])

    def test_trace_parsing(self):
        """The CLI's stream-json shape (agy 1.5.3): one ACTIVE and one DONE step_update per tool call."""
        name = lambda t: f"mcp_{agy.PLUGIN}_{agy.SERVER}_{t}"
        self.assertEqual(agy.mcp_name(name("search")), "search")
        self.assertIsNone(agy.mcp_name("read_file"))
        self.assertIsNone(agy.mcp_name("list_resources"))
        step = lambda i, state, tool, **kw: {"event": "step_update", "step_update": {"conversation_id": "c", "step_index": i,
                                              "state": state, "step_type": "tool", "tool_name": tool, "tool_info": {"name": tool, **kw}}}
        events = [{"event": "init", "init": {"tools": ["run_command"]}},
                  {"event": "step_update", "step_update": {"step_index": 0, "state": "DONE", "step_type": "user_input"}},
                  step(2, "ACTIVE", name("manifest")), step(2, "DONE", name("manifest"), output="{}"),
                  step(4, "ACTIVE", "run_command"), step(4, "DONE", "run_command", error="denied"),
                  {"event": "step_update", "step_update": {"step_index": 5, "state": "DONE", "step_type": "error_message"}},
                  {"event": "result", "result": {"status": "SUCCESS", "response": "DONE\n", "usage": {"input_tokens": 5}}}]
        calls = agy.tool_calls(events)
        self.assertEqual([(c["name"], c["states"]) for c in calls], [(name("manifest"), ["ACTIVE", "DONE"]), ("run_command", ["ACTIVE", "DONE"])])
        self.assertEqual(calls[1]["error"], "denied")
        self.assertEqual(agy.error_steps(events), 1)
        self.assertEqual(agy.result_of(events)["response"], "DONE\n")

    def test_trace_check(self):
        c = lambda tool, *states, error=None: {"name": f"mcp_{agy.PLUGIN}_{agy.SERVER}_{tool}", "states": list(states),
                                                 **({"error": error} if error else {})}
        rows = [{"tool": "manifest"}, {"tool": "search"}, {"tool": "write"}]
        # A search the CLI rejected (missing query) and the model retried: consistent.
        traced = [c("manifest", "ACTIVE", "DONE"), c("search", "ACTIVE", "ERROR", error="invalid arguments:\n- missing property 'query'"),
                  c("search", "ACTIVE", "DONE"), c("write", "ACTIVE", "DONE")]
        self.assertTrue(agy.rejected_by_cli(traced[1]))
        self.assertFalse(agy.rejected_by_cli(c("read", "ACTIVE", "ERROR", error='{"error": "NotFoundError"}')))  # the server's
        self.assertEqual(agy.trace_check(traced, rows), {"ok": True, "client_rejected": 1, "untraced_refused": 0})
        # A traced call that ran but never reached the proxy: mismatch.
        self.assertFalse(agy.trace_check(traced[:1] + [c("read", "ACTIVE", "DONE")] + traced[2:], rows)["ok"])
        # Stopped at the cap with a refused call in flight: consistent; an unrefused untraced call: mismatch.
        self.assertTrue(agy.trace_check(traced, rows + [{"tool": "read", "refused": True}])["ok"])
        self.assertFalse(agy.trace_check(traced, rows + [{"tool": "read"}])["ok"])
        self.assertTrue(agy.trace_check(traced + [c("write", "ACTIVE")], rows)["ok"])  # still running when stopped

class _MockStrata:
    """A stand-in for the Strata server: answers /v1/chat/completions with ``script(body, n)``; keeps every request."""

    def __init__(self, script):
        import http.server
        import threading

        outer = self
        self.requests: list[dict] = []
        self.script = script

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def do_GET(self):
                body = json.dumps({"object": "list", "data": [{"id": "mock-model", "meta": {"n_ctx": 4096}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(req)
                status, answer = outer.script(req, len(outer.requests))
                data = json.dumps(answer).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _answer(content=None, calls=(), prompt=100, cached=40, completion=10, finish=None):
    msg = {"role": "assistant", "content": content, "reasoning_content": "thinking..."}
    if calls:
        msg["tool_calls"] = [{"id": f"call_{i}_{name}", "type": "function", "function": {"name": name, "arguments": args}}
                             for i, (name, args) in enumerate(calls)]
    return 200, {"choices": [{"message": msg, "finish_reason": finish or ("tool_calls" if calls else "stop")}],
                 "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion,
                           "prompt_tokens_details": {"cached_tokens": cached}},
                 "timings": {"cache_n": cached, "prompt_n": prompt - cached, "prompt_ms": 5.0, "predicted_ms": 7.0}}


class StrataTests(unittest.TestCase):
    """The Strata client (``strata.py``) against a mocked server, with the real MCP proxy and MindSlice server."""

    def _task(self, tmp: Path, h=None):
        from evals.agent.agents import SessionTask
        from evals.agent.sessions import agent_sessions, flat

        h = h or synthetic_meme()
        s = agent_sessions(h, flat(h))[0]
        ws = Workspace.init(tmp / "ws")
        self.addCleanup(ws.close)
        return SessionTask("agent-policy", h, s, "SYSTEM", "SESSION MESSAGE", ws, tmp)

    def test_session_loop_over_mcp(self):
        from evals.agent import strata

        def script(req, n):
            msgs = req["messages"]
            if len(msgs) == 2:
                return _answer(calls=[("manifest", "{}")])
            if len(msgs) == 4:
                return _answer(calls=[("search", json.dumps({"query": "health condition"}))], prompt=150, cached=120)
            return _answer("DONE", prompt=200, cached=180)

        srv = _MockStrata(script)
        self.addCleanup(srv.close)
        with tempfile.TemporaryDirectory() as tmp:
            task = self._task(Path(tmp))
            out = strata.StrataAgent("agent-policy", model="mock-model", url=srv.url).run_session(task)
        self.assertFalse(out.failed, out.meta)
        self.assertEqual(out.reply, "DONE")
        self.assertEqual([r["tool"] for r in out.calls], ["manifest", "search"])
        self.assertTrue(out.meta["trace_matches_proxy"])
        self.assertEqual(out.meta["num_turns"], 3)
        self.assertEqual(out.meta["usage"]["input_tokens"], (100 - 40) + (150 - 120) + (200 - 180))
        self.assertEqual(out.meta["usage"]["cached_tokens"], 40 + 120 + 180)
        self.assertEqual(out.meta["usage"]["output_tokens"], 30)
        first, last = srv.requests[0], srv.requests[-1]
        self.assertEqual([t["function"]["name"] for t in first["tools"]], ["manifest", "search", "read", "write"])
        self.assertEqual(first["messages"], [{"role": "system", "content": "SYSTEM"}, {"role": "user", "content": "SESSION MESSAGE"}])
        self.assertEqual((first["temperature"], first["top_k"], first["model"]), (1.0, 20, "mock-model"))
        self.assertEqual(last["messages"][2]["reasoning_content"], "thinking...")  # the assistant turn goes back whole
        self.assertEqual(last["messages"][3]["role"], "tool")
        self.assertEqual(last["messages"][3]["tool_call_id"], "call_0_manifest")
        self.assertIn("cards", last["messages"][3]["content"])  # the real manifest result

    def test_cap_ends_the_session(self):
        from evals.agent import strata

        srv = _MockStrata(lambda req, n: _answer(calls=[("manifest", "{}")]))
        self.addCleanup(srv.close)
        with tempfile.TemporaryDirectory() as tmp:
            out = strata.StrataAgent("agent-policy", model="mock-model", url=srv.url, cap=3).run_session(self._task(Path(tmp)))
        self.assertFalse(out.failed)
        self.assertTrue(out.meta["cap_hit"])
        self.assertEqual(out.meta["finished_reason"], "call_cap")
        self.assertEqual(len(out.calls), 4)
        self.assertEqual([r["refused"] for r in out.calls], [False, False, False, True])
        self.assertEqual(len(srv.requests), 4)  # no model turn after the refused call

    def test_unknown_tools_and_bad_arguments_are_not_forwarded(self):
        from evals.agent import strata

        def script(req, n):
            if n == 1:
                return _answer(calls=[("run_command", "{}"), ("search", "not json"), ("read", "[1]")])
            return _answer("DONE")

        srv = _MockStrata(script)
        self.addCleanup(srv.close)
        with tempfile.TemporaryDirectory() as tmp:
            out = strata.StrataAgent("agent-policy", model="mock-model", url=srv.url).run_session(self._task(Path(tmp)))
        self.assertEqual(out.calls, [])
        self.assertEqual((out.meta["non_mcp_denied"], out.meta["client_rejected_calls"]), (1, 2))
        self.assertEqual(out.meta["non_mcp_denied_tools"], ["run_command"])
        tool_msgs = [m for m in srv.requests[1]["messages"] if m["role"] == "tool"]
        self.assertEqual(len(tool_msgs), 3)
        self.assertIn("Unknown tool", tool_msgs[0]["content"])

    def test_http_failure_is_retried_then_fails(self):
        from evals.agent import strata

        srv = _MockStrata(lambda req, n: (500, {"error": "boom"}))
        self.addCleanup(srv.close)
        with tempfile.TemporaryDirectory() as tmp:
            task = self._task(Path(tmp))
            (task.ws.root / "overlay" / "keep.md").write_text("---\ntitle: Keep\n---\nkept\n")
            out = strata.StrataAgent("agent-policy", model="mock-model", url=srv.url, retries=1, backoff=(0,)).run_session(task)
            self.assertTrue((task.ws.root / "overlay" / "keep.md").exists())
        self.assertTrue(out.failed)
        self.assertIn("HTTP 500", out.meta["error"])
        self.assertEqual(out.meta["retries"], 1)
        self.assertEqual(len(srv.requests), 2)

    def test_run_haystack_with_strata(self):
        from evals.agent import strata

        def script(req, n):
            return _answer(calls=[("manifest", "{}")]) if len(req["messages"]) == 2 else _answer("DONE")

        srv = _MockStrata(script)
        self.addCleanup(srv.close)
        h = synthetic_meme()
        with tempfile.TemporaryDirectory() as tmp:
            recs = run_haystack(h, "agent-policy", Path(tmp) / "out", agent=strata.StrataAgent("agent-policy", model="mock-model", url=srv.url))
        sess = [r for r in recs if r["kind"] == "session"]
        self.assertTrue(sess)
        self.assertTrue(all(r["tool_calls"] == 1 and r["reply"] == "DONE" and not r["failed"] for r in sess))
        self.assertTrue(all(r["usage"]["input_tokens"] == 60 * 2 and r["usage"]["cached_tokens"] == 80 for r in sess))
        self.assertIsNone(next(r for r in recs if r["kind"] == "haystack")["failed"])


class MatcherV2Test(unittest.TestCase):
    """The rules matcher v2 documents (``matcher2.py``), and the two-way audit correction (``audit2``)."""

    def test_paraphrase_and_formats(self) -> None:
        from evals.agent import matcher2 as m2

        self.assertTrue(m2.states(m2.Text("Current anime: Thyrelion"), "thyrelion (anime)"))  # type tag optional
        self.assertTrue(m2.states(m2.Text("Meets every Thursday at 2 pm"), "every thursday 2pm"))
        self.assertTrue(m2.states(m2.Text("Commute: about ten minutes"), "10 min"))
        self.assertFalse(m2.states(m2.Text("Thyrelion is a game"), "a history documentary series"))

    def test_past_markers_aliases_and_masks(self) -> None:
        from evals.agent import matcher2 as m2

        self.assertFalse(m2.presents_old(m2.Text("Subscribed to Thyranote (switched from Xelvoria)"), "xelvoria"))
        self.assertTrue(m2.presents_old(m2.Text("Subscribed to Xelvoria"), "xelvoria"))
        self.assertFalse(m2.presents_old(m2.Text(title="Subscription", aliases=["Xelvoria"], body="Thyranote"), "xelvoria"))
        self.assertFalse(m2.presents_old(m2.Text("Packages via Synthari Modules"), "synthari", others=["synthari modules"]))
        self.assertFalse(m2.is_stale(m2.Text("Xelvoria\nNow Thyranote"), ["xelvoria"], ["thyranote"]))
        self.assertFalse(m2.states_current(m2.Text("Previously cooking"), "cooking"))
        self.assertTrue(m2.states_current(m2.Text("Cooking, previously cycling"), "cooking"))

    def test_two_way_correction(self) -> None:
        from evals.agent import audit2

        recs = ([{"kind": "update", "matchable": True, "retired": False}] * 10 + [{"kind": "update", "matchable": True, "retired": True}] * 90
                + [{"kind": "value", "matchable": True, "lost": True}] * 4 + [{"kind": "value", "matchable": True, "lost": False}] * 96)
        ws = {"population": {"retired": 10, "lost": 4, "passes": 90, "flips": 0},
              "cases": {"retired": [{"verdict": "matching error"}] * 2 + [{"verdict": "correct"}] * 8,
                        "lost": [{"verdict": "matching error"}] * 4,
                        "passes": [{"verdict": "missed"}] + [{"verdict": "correct"}] * 9, "flips": []}}
        t = audit2.tally(ws)
        self.assertEqual((t["retired"]["errors"], t["lost"]["share"], t["passes"]["share"]), (2, 1.0, 0.1))
        self.assertFalse(t["reliable"])
        c = audit2.corrected(recs, ws)
        self.assertEqual((c["retired"]["raw"], c["retired"]["corrected"]), (0.9, 0.83))  # 8 real + 9 missed of 100
        self.assertEqual((c["lost"]["raw"], c["lost"]["corrected"]), (0.04, 0.0))
        self.assertTrue(c["retired"]["exact"])


class MatcherV3Test(unittest.TestCase):
    """v3's changes over v2 (``matcher3.py``), each on the wording the audits found."""

    def test_lcs(self) -> None:
        import random

        from evals.agent.matcher3 import lcs

        def dp(a, b):
            prev = [0] * (len(b) + 1)
            for x in a:
                cur = [0]
                for j, y in enumerate(b, 1):
                    cur.append(prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1]))
                prev = cur
            return prev[-1]

        r = random.Random(7)
        for _ in range(200):
            a = [r.choice("abcd") for _ in range(r.randint(0, 30))]
            b = [r.choice("abcde") for _ in range(r.randint(0, 60))]
            self.assertEqual(lcs(a, b), dp(a, b))

    def test_formats_and_inflection(self) -> None:
        from evals.agent import matcher3 as m3

        cur = lambda text, v: m3.states_current(m3.Text(text), v)
        self.assertTrue(cur("Sleeps 11:00 PM to 5:30 AM; an early riser", "11pm-5:30am (early riser)"))
        self.assertTrue(cur("Every Thursday at 2:00 PM", "every thursday 2pm"))
        self.assertTrue(cur("Any team member is allowed to approve", "any team member can approve"))
        self.assertEqual(m3._norm_word("continuously"), m3._norm_word("continuous"))
        self.assertEqual(m3._norm_word("stories"), m3._norm_word("story"))
        for a, b in (("engaged", "engaging"), ("separated", "separate"), ("engaged", "engagement"), ("dating", "date")):
            self.assertNotEqual(m3._norm_word(a), m3._norm_word(b))  # MEME's statuses stay apart from ordinary words
        self.assertFalse(m3.presents_old(m3.Text("An engaging book about separate rooms"), "engaged"))
        self.assertTrue(cur("I have a college reunion coming up. Everyone's paths have changed.", "college reunion"))

    def test_long_values(self) -> None:
        from evals.agent import matcher3 as m3

        v = ("try not to become a man of success, but rather try to become a man of value. look around at how people "
             "want to get more out of life than they put in. a man of value will give more than he receives")
        abridged = 'Philosophy: "Try not to become a man of success, but rather try to become a man of value... A man of value will give more than he receives."'
        full = '- Word for word: "' + v + '"'
        self.assertTrue(m3.states_current(m3.Text("Life Philosophy\n" + abridged + "\n" + full), v))  # v2: 0.61
        self.assertFalse(m3.states_current(m3.Text("Life Philosophy\n" + abridged), v))
        log = "deadlockdetected: transactions 4821 and 4823 are deadlocked on table aurora_orders. query 1 was update orders set status shipped"
        bullets = "- Line 1: DeadlockDetected: transactions 4821 and 4823 are deadlocked on table aurora_orders.\n- Line 2: Query 1 was UPDATE orders SET status shipped"
        self.assertTrue(m3.states_current(m3.Text(bullets), log))

    def test_past_markers(self) -> None:
        from evals.agent import matcher3 as m3

        old = lambda text, v: m3.presents_old(m3.Text(text), v)
        self.assertFalse(old("Moving to Orinthal Serve also invalidates the Docker image (velturis-cr/aurora:main).", "velturis-cr/aurora:main"))
        self.assertFalse(old("Assigned to Seoyun Choi, which is subject to change now that Sarah Chen leads.", "seoyun choi"))
        self.assertFalse(old("Switching frameworks changes the build tool from Karnex Bundler to Tarvex CLI.", "karnex bundler"))
        self.assertFalse(old("[[events/baby-shower]] (superseded by [[events/half-marathon]])", "baby shower"))
        self.assertTrue(old("The user has a fixed 9-to-5 schedule; if their studies change, it would change.", "9-to-5 fixed"))
        self.assertTrue(old("Routine remains yoga 2x/week following the change in health condition.", "yoga 2x/week"))
        self.assertFalse(m3.states_current(m3.Text("Switched from Xelvoria to Thyranote"), "xelvoria"))
        self.assertFalse(old("Health changed from A to B, so medication [[m/dyntheral]] (Dyntheral likely changed).", "dyntheral"))
        self.assertTrue(m3.states_current(m3.Text("The hobby is not affected: still cooking"), "cooking"))


if __name__ == "__main__":
    unittest.main()
