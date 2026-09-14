"""Seed data: one demo user and three template workflows.

    python -m db.seed            # idempotent — safe to run repeatedly

Anyone can demo the system 30 seconds after a fresh install (GP-plan W2).
"""

from __future__ import annotations

import itertools
import os
import uuid
from typing import Any

from sqlalchemy import delete, select

from db.models import AgentNode, User, Workflow
from db.session import make_engine, make_session_factory

DEMO_EMAIL = os.environ.get("SEED_DEMO_EMAIL", "demo@gp.local")

# Fixed namespace so template node ids are stable across re-seeds.
_NS = uuid.UUID("6b1f7c3e-2f0a-4d8e-9a55-3c1d0f5e7a10")


def _node(
    template: str, key: str, agent_type: str, x: int, configuration: dict[str, Any], approval: bool = False
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid5(_NS, f"{template}:{key}")),
        "agent_type": agent_type,
        "configuration": configuration,
        "requires_approval": approval,
        "position": {"x": x, "y": 120},
    }


def _graph(template: str, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    edges = [
        {"id": f"{template}-e{i}", "source": a["id"], "target": b["id"]}
        for i, (a, b) in enumerate(itertools.pairwise(nodes))
    ]
    return {"nodes": nodes, "edges": edges}


TOPIC = {"topic": "The future of solar energy in Saudi Arabia", "num_sources": 5}

TEMPLATES: list[tuple[str, dict[str, Any]]] = [
    (
        "Blog post",
        _graph(
            "blog",
            [
                _node("blog", "research", "researcher", 0, TOPIC),
                _node(
                    "blog", "write", "writer", 320, {"length": "medium", "style": "informative", "format": "blog_post"}
                ),
            ],
        ),
    ),
    (
        "Blog → Video → YouTube",
        _graph(
            "video",
            [
                _node("video", "research", "researcher", 0, TOPIC),
                _node(
                    "video",
                    "write",
                    "writer",
                    320,
                    {"length": "short", "style": "conversational", "format": "video_script"},
                ),
                _node("video", "video", "video", 640, {"voice": "en", "resolution": "720p"}),
                _node(
                    "video", "publish", "publisher", 960, {"platform": "youtube", "privacy": "unlisted"}, approval=True
                ),
            ],
        ),
    ),
    (
        "Research → PDF → Email",
        _graph(
            "email",
            [
                _node("email", "research", "researcher", 0, TOPIC),
                _node("email", "write", "writer", 320, {"length": "long", "style": "academic", "format": "article"}),
                _node("email", "email", "email", 640, {"recipients": [DEMO_EMAIL]}, approval=True),
            ],
        ),
    ),
]


def seed(database_url: str) -> None:
    session_factory = make_session_factory(make_engine(database_url))
    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None:
            user = User(id=uuid.uuid5(_NS, DEMO_EMAIL), email=DEMO_EMAIL)
            session.add(user)
            session.flush()

        for name, graph in TEMPLATES:
            workflow = session.scalar(select(Workflow).where(Workflow.user_id == user.id, Workflow.name == name))
            if workflow is None:
                workflow = Workflow(id=uuid.uuid5(_NS, f"workflow:{name}"), user_id=user.id, name=name)
                session.add(workflow)
            workflow.graph_definition = graph
            session.flush()
            session.execute(delete(AgentNode).where(AgentNode.workflow_id == workflow.id))
            for order, node in enumerate(graph["nodes"]):
                session.add(
                    AgentNode(
                        id=uuid.UUID(node["id"]),
                        workflow_id=workflow.id,
                        agent_type=node["agent_type"],
                        configuration=node["configuration"],
                        position_order=order,
                    )
                )
        session.commit()
    print(f"Seeded demo user {DEMO_EMAIL} with {len(TEMPLATES)} template workflows.")


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set.")
    seed(url)


if __name__ == "__main__":
    main()
