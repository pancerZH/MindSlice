"""Functional "journey" tests: initial state -> scripted sessions -> end state.

Each journey starts from a workspace fixture, replays user sessions in which a *scripted
agent* drives MindSlice through the real MCP server (JSON-RPC, the same interface an LLM
agent uses), interleaves human actions (reviewing staging, editing files, mounting), and
ends by consolidating, baking and exporting slices.

Separation that lets a real LLM replace the scripted agent later:

* ``Session.user``    - what the user says (an LLM would receive this as input)
* ``Session.script``  - the scripted agent's tool calls, with exact checkpoints
* ``Session.outcome`` - agent-agnostic checks on workspace state (the future LLM oracle)
"""
