import itertools
from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts.agent import describe_inputs, describe_outputs
from contracts.agent_io import (
    EmailInput,
    ImageConfig,
    ImageInput,
    PublishInput,
    VideoConfig,
    VideoInput,
    WriteConfig,
    WriteInput,
    WriteOutput,
)
from contracts.graph import CycleError, descendants, find_cycle, topological_order
from contracts.manifest import AgentManifest
from contracts.run import GraphEdge, GraphNode, Position, WorkflowGraph


def _node(x: float, agent: str = "researcher") -> GraphNode:
    return GraphNode(id=uuid4(), agent_type=agent, position=Position(x=x))


def _chain(*nodes: GraphNode) -> WorkflowGraph:
    edges = [GraphEdge(id=f"e{i}", source=a.id, target=b.id) for i, (a, b) in enumerate(itertools.pairwise(nodes))]
    return WorkflowGraph(nodes=list(nodes), edges=edges)


def test_topological_order_follows_edges_not_list_order():
    a, b, c = _node(0), _node(100), _node(200)
    graph = _chain(a, b, c)
    graph.nodes.reverse()
    assert [n.id for n in topological_order(graph)] == [a.id, b.id, c.id]


def test_cycle_is_detected_and_reported():
    a, b = _node(0), _node(100)
    graph = WorkflowGraph(
        nodes=[a, b],
        edges=[GraphEdge(id="1", source=a.id, target=b.id), GraphEdge(id="2", source=b.id, target=a.id)],
    )
    assert find_cycle(graph) is not None
    with pytest.raises(CycleError):
        topological_order(graph)


def test_descendants():
    a, b, c = _node(0), _node(100), _node(200)
    assert descendants(_chain(a, b, c), a.id) == {b.id, c.id}


def test_agent_type_must_be_snake_case():
    with pytest.raises(ValidationError):
        GraphNode(id=uuid4(), agent_type="Writer Agent")


def test_upstream_aliases_let_outputs_flow_into_inputs():
    writer_out = {"title": "Solar", "summary": "Short", "article_md": "# Solar"}
    assert VideoInput.model_validate(writer_out).script == "# Solar"
    publish = PublishInput.model_validate({**writer_out, "video_path": "runs/1/video.mp4"})
    assert publish.file_path == "runs/1/video.mp4" and publish.description == "Short"
    email = EmailInput.model_validate({**writer_out, "remote_url": "https://youtu.be/x", "recipients": ["a@b.co"]})
    assert email.links == ["https://youtu.be/x"] and email.subject == "Solar"


def test_inputs_say_where_each_value_can_come_from():
    video = {i.name: i for i in describe_inputs(VideoInput, VideoConfig)}
    # Only an earlier step can supply the script, and it arrives as Writer's article.
    assert video["script"].accepts == ["script", "article_md"]
    assert video["script"].required and not video["script"].settable
    assert video["voice"].settable and not video["voice"].required

    image = {i.name: i for i in describe_inputs(ImageInput, ImageConfig)}
    # Required, but the user may leave it empty and inherit the title instead.
    assert image["prompt"].accepts == ["prompt", "title"]
    assert image["prompt"].required and image["prompt"].settable

    writer = {i.name: i for i in describe_inputs(WriteInput, WriteConfig)}
    assert writer["notes"].required and not writer["notes"].settable


def test_outputs_carry_human_names():
    assert [(o.name, o.title) for o in describe_outputs(WriteOutput)] == [
        ("title", "title"),
        ("summary", "summary"),
        ("article_md", "article"),
    ]


def test_email_recipients_are_checked():
    with pytest.raises(ValidationError):
        EmailInput.model_validate({"recipients": ["not-an-email"], "subject": "x"})


def test_writer_needs_notes():
    with pytest.raises(ValidationError):
        WriteInput.model_validate({"notes": []})


def test_manifest_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        AgentManifest.model_validate(
            {
                "name": "x",
                "version": "1.0.0",
                "title": "X",
                "description": "d",
                "input_type": "A",
                "output_type": "B",
                "extra": 1,
            }
        )


def test_ancestors():
    from contracts.graph import ancestors

    a, b, c = _node(0), _node(100), _node(200)
    assert ancestors(_chain(a, b, c), c.id) == {a.id, b.id}
