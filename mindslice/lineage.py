"""Lineage semantics: trust policies, supersession forwarding and cycle detection."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Hashable, Iterable, Sequence, TypeVar

from .addressing import format_address, normalize_alias
from .errors import InvalidAddressError

N = TypeVar("N", bound=Hashable)
FollowSpec = bool | Sequence[str] | None


class TrustPolicy:
    """Which ``supersedes`` edges may be followed automatically.

    * ``True``  - every active replacement is trusted (default)
    * ``False`` - never forward; replacements are only reported
    * ``["curated", "@team"]`` - trust replacements whose mount ``role`` or ``@alias`` is listed
    """

    def __init__(self, follow: FollowSpec = True) -> None:
        if follow is None:
            follow = True
        if isinstance(follow, str):
            follow = [follow]
        self.all = follow is True
        self.none = follow is False
        self.allow: set[str] = set()
        if not isinstance(follow, bool):
            for item in follow:
                item = str(item).strip()
                if not item:
                    continue
                if item.startswith("@"):
                    try:
                        item = normalize_alias(item)
                    except InvalidAddressError:
                        pass
                self.allow.add(item)

    def trusts(self, mount: str, role: str) -> bool:
        if self.all:
            return True
        if self.none:
            return False
        return mount in self.allow or role in self.allow


@dataclass
class Forward:
    """Result of following trusted ``supersedes`` edges from a starting node.

    ``node`` is where a read lands: the unique terminal replacement, or - when
    replacements compete - the fork point reached by following the unambiguous
    part of the chain (``start`` itself if it is directly contested or on a cycle).
    """

    start: str
    node: str
    terminals: list[str] = field(default_factory=list)
    path: list[str] = field(default_factory=list)  # start -> ... -> node
    superseded: set[str] = field(default_factory=set)  # nodes passed through before ``node``
    competing: bool = False
    cycle: bool = False

    @property
    def redirected(self) -> bool:
        return self.node != self.start

    @property
    def terminal(self) -> str | None:
        return None if (self.competing or self.cycle) else self.node


class LineageView:
    """Per-request lineage queries over an index (memoized)."""

    def __init__(self, index, policy: TrustPolicy) -> None:
        self.index = index
        self.policy = policy
        self._superseders: dict[str, list[tuple[str, bool, int, int]]] = {}

    @staticmethod
    def split(address: str) -> tuple[str, str]:
        mount, _, path = address.partition("/")
        return mount, path

    def superseders(self, address: str) -> list[tuple[str, bool, int, int]]:
        """Direct active inbound ``supersedes`` sources: ``(address, trusted, precedence, mtime_ns)``."""
        if address not in self._superseders:
            mount, path = self.split(address)
            rows = self.index.inbound("supersedes", mount, path)
            self._superseders[address] = [
                (
                    format_address(r["src_mount"], r["src_path"]),
                    self.policy.trusts(r["src_mount"], r["role"]),
                    r["precedence"],
                    r["mtime_ns"],
                )
                for r in rows
            ]
        return self._superseders[address]

    def trusted_superseders(self, address: str) -> list[str]:
        return [a for a, trusted, _, _ in self.superseders(address) if trusted]

    def untrusted_superseders(self, address: str) -> list[str]:
        return [a for a, trusted, _, _ in self.superseders(address) if not trusted]

    def all_superseders(self, address: str) -> list[str]:
        return [a for a, _, _, _ in self.superseders(address)]

    def forward(self, start: str) -> Forward:
        parent: dict[str, str] = {}
        seen = {start}
        queue = deque([start])
        order: dict[str, tuple[int, int]] = {}
        while queue:
            node = queue.popleft()
            for addr, trusted, precedence, mtime in self.superseders(node):
                if not trusted or addr in seen:
                    continue
                seen.add(addr)
                parent[addr] = node
                order[addr] = (precedence, mtime)
                queue.append(addr)
        reached = seen - {start}
        if not reached:
            return Forward(start, start, [start], [start], set())
        terminals = [n for n in reached if not self.trusted_superseders(n)]
        terminals.sort(key=lambda a: (-order[a][0], a))
        if not terminals:
            return Forward(start, start, [], [start], set(), cycle=True)
        if len(terminals) > 1:
            # Follow the chain while it is unambiguous; stop at the fork.
            path = [start]
            while True:
                nxt = self.trusted_superseders(path[-1])
                if len(nxt) != 1 or nxt[0] in path:
                    break
                path.append(nxt[0])
            return Forward(start, path[-1], terminals, path, set(path[:-1]), competing=True)
        terminal = terminals[0]
        path = [terminal]
        while path[-1] != start:
            path.append(parent[path[-1]])
        path.reverse()
        return Forward(start, terminal, [terminal], path, seen - {terminal})


# ---------------------------------------------------------------------------
# Graph algorithms
# ---------------------------------------------------------------------------


def cycle_through(start: N, successors: Callable[[N], Iterable[N]]) -> list[N] | None:
    """Return a cycle ``[start, ..., start]`` if ``start`` can reach itself, else None."""
    parent: dict[N, N] = {}
    queue: deque[N] = deque()
    for nxt in successors(start):
        if nxt not in parent:
            parent[nxt] = start
            queue.append(nxt)
    while queue:
        node = queue.popleft()
        if node == start:
            chain: list[N] = []
            cur = parent[start]
            while cur != start:
                chain.append(cur)
                cur = parent[cur]
            return [start, *reversed(chain), start]
        for nxt in successors(node):
            if nxt not in parent:
                parent[nxt] = node
                queue.append(nxt)
    return None


def strongly_connected_cycles(nodes: Iterable[N], successors: Callable[[N], Iterable[N]]) -> list[list[N]]:
    """Tarjan's algorithm (iterative); returns SCCs that contain a cycle."""
    index_of: dict[N, int] = {}
    low: dict[N, int] = {}
    on_stack: set[N] = set()
    stack: list[N] = []
    result: list[list[N]] = []
    counter = 0
    for root in nodes:
        if root in index_of:
            continue
        work: list[tuple[N, Iterable[N]]] = [(root, iter(list(successors(root))))]
        index_of[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:
                if nxt not in index_of:
                    index_of[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(list(successors(nxt)))))
                    advanced = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index_of[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index_of[node]:
                comp: list[N] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    comp.append(member)
                    if member == node:
                        break
                if len(comp) > 1 or node in set(successors(node)):
                    result.append(sorted(comp, key=str))
    return result
