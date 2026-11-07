"""Initial workspace states for journeys: no slice, a few slices, many slices."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mindslice import Workspace, tomlfmt

from ..helpers import card_text


@dataclass
class SliceSpec:
    name: str
    alias: str
    precedence: int
    role: str
    description: str
    cards: dict[str, str]
    overview: str | None = None
    dependencies: list[str] = field(default_factory=list)


def write_slice(parent: Path, spec: SliceSpec) -> Path:
    root = parent / f"{spec.name}.slice"
    root.mkdir(parents=True)
    manifest = {"name": spec.name, "version": "1.0.0", "description": spec.description, "alias": spec.alias,
                "dependencies": spec.dependencies}
    (root / "slice.toml").write_text(tomlfmt.dumps_document(top=manifest), encoding="utf-8")
    if spec.overview is not None:
        (root / "overview.md").write_text(spec.overview, encoding="utf-8")
    for path, text in spec.cards.items():
        file = root / f"{path}.md"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
    return root


def mount_all(ws: Workspace, specs: list[SliceSpec]) -> Workspace:
    for spec in specs:
        root = write_slice(ws.root / "slices", spec)
        ws.mount(root, alias=spec.alias, precedence=spec.precedence, role=spec.role)
    return ws


# ---------------------------------------------------------------------------
# State 0: no slice at all
# ---------------------------------------------------------------------------


def empty_workspace(root: Path) -> Workspace:
    return Workspace.init(root)


# ---------------------------------------------------------------------------
# State 1: a few hand-written slices (English + Chinese)
# ---------------------------------------------------------------------------

PERSONA = SliceSpec(
    "core-persona", "@persona", 10, "baseline", "How the assistant talks and reviews code.",
    {
        "tone-and-style": card_text("Tone and style", "Be concise and answer in the user's language.",
                                    ["Prefer bullet points over long paragraphs.", "Never invent facts; say when unsure."],
                                    tags=["style"]),
        "code-review": card_text("Code review", "Review for correctness first, style last.",
                                 ["Flag missing tests.", "Ask before large refactors."], tags=["review"]),
    },
    overview="# Persona\n\nCommunication style and review habits.\n",
)

PROJECT = SliceSpec(
    "project-kb", "@project", 50, "curated", "Curated knowledge about the project API and operations.",
    {
        "api/auth-flow": card_text("Auth flow", "Clients authenticate with short-lived bearer tokens.",
                                   ["The token expiration is 15 minutes.", "Refresh via [[api/refresh]]."],
                                   tags=["api", "auth"], aliases=["authentication"]),
        "api/refresh": card_text("Refresh tokens", "Refresh tokens rotate daily.",
                                 ["A refresh token is single use."], tags=["api", "auth"]),
        "deploy/rollback": card_text("Rollback", "Rollbacks redeploy the previous container image.",
                                     ["Run `make rollback` from the release branch.", "Announce rollbacks in #ops."],
                                     tags=["deploy"]),
        "observability/logging": card_text("Structured logging", "Services log JSON lines with correlation IDs.",
                                           ["Never log tokens or passwords."], tags=["observability"]),
    },
    overview="# Project KB\n\nAPI, deployment and observability conventions. Start with [[api/auth-flow]].\n",
)

ZH_KB = SliceSpec(
    "zh-ops", "@zh", 40, "curated", "团队的中文运维知识库。",
    {
        "部署/发布流程": card_text("发布流程", "每周二下午发布到生产环境。",
                                 ["发布前必须通过预发布环境验收。", "回滚见 [[部署/回滚]]。"], tags=["部署"]),
        "部署/回滚": card_text("回滚", "回滚使用上一个镜像版本。", ["回滚后需要在群里通知。"], tags=["部署"]),
        "值班/告警": card_text("告警级别", "告警分为P0到P3四个级别。",
                             ["P0告警需要5分钟内响应。", "P3告警在工作时间处理即可。"], tags=["值班", "告警"]),
    },
    overview="# 中文运维\n\n发布、回滚与值班告警。\n",
)


def few_slices_workspace(root: Path) -> Workspace:
    return mount_all(Workspace.init(root), [PERSONA, PROJECT, ZH_KB])


# ---------------------------------------------------------------------------
# State 2: many generated slices (more than manifest's default page of 20)
# ---------------------------------------------------------------------------

SERVICES = [
    "billing", "search", "payments", "ledger", "gateway", "inventory", "catalog", "checkout",
    "notifications", "identity", "reporting", "scheduler", "storage", "media", "analytics",
    "recommendations", "shipping", "pricing", "fraud", "support", "onboarding", "audit", "exports", "webhooks",
]
ZH_NAMES = ["计费", "检索", "支付", "账本", "网关", "库存", "目录", "结算"]


def service_slice(i: int) -> SliceSpec:
    svc = SERVICES[i]
    title = svc.capitalize()
    cards = {
        "runbook/deploy": card_text(f"{title} deploy", f"Deploy {svc} with the standard pipeline in {2 + i % 5} stages.",
                                    [f"Owner: team {i}.", "Check dashboards after each stage."], tags=["deploy", svc]),
        "runbook/rollback": card_text(f"{title} rollback", f"Roll back {svc} to the previous image within {5 + i} minutes.",
                                      ["Page the owner if the rollback fails."], tags=["rollback", svc]),
        "api/endpoints": card_text(f"{title} API", f"The {svc} API exposes {3 + i} endpoints.",
                                   [f"GET /{svc}/health returns 200."], tags=["api", svc]),
    }
    if i % 3 == 0:
        zh = ZH_NAMES[i // 3]
        cards["运维/值班"] = card_text(f"{zh}值班", f"{zh}服务的值班告警需要在{5 + i}分钟内响应。",
                                     ["夜间告警直接电话通知。"], tags=["值班"])
    deps: list[str] = []
    if i == 1:
        cards["runbook/deploy"] = card_text(f"{title} deploy", "Deploy search right after billing.",
                                            ["Follow [[@svc-00/runbook/deploy]] first."], tags=["deploy", svc])
        deps = ["@svc-00"]
    return SliceSpec(f"svc-{i:02d}", f"@svc-{i:02d}", 5 + 10 * i, "curated" if i % 2 == 0 else "baseline",
                     f"Runbooks and API notes for the {svc} service.", cards,
                     overview=f"# {title}\n\nThe {svc} service, owned by team {i}.\n", dependencies=deps)


def many_slices_workspace(root: Path, n: int = 24) -> Workspace:
    return mount_all(Workspace.init(root), [service_slice(i) for i in range(n)])
