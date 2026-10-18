import itertools
from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts.agent import describe_inputs, describe_outputs
from contracts.agent_io import (
    EmailConfig,
    EmailInput,
    EmailOutput,
    ImageConfig,
    ImageInput,
    ImageOutput,
    PublishConfig,
    PublishInput,
    PublishOutput,
    ResearchOutput,
    VideoConfig,
    VideoInput,
    VideoOutput,
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


def test_outputs_carry_human_names_and_which_a_reviewer_may_edit():
    assert [(o.name, o.title, o.editable) for o in describe_outputs(WriteOutput)] == [
        ("title", "title", "text"),
        ("summary", "summary", "text"),
        ("article_md", "article", "text"),
        ("pdf_path", "PDF", None),
        ("docx_path", "Word document", None),
    ]
    assert [(o.name, o.editable) for o in describe_outputs(ResearchOutput)] == [("notes", "lines"), ("sources", None)]


def test_no_file_or_link_is_ever_editable():
    """An edited path could name another person's file (the API refuses one whatever a manifest says)."""
    for model in (ResearchOutput, WriteOutput, ImageOutput, VideoOutput, PublishOutput, EmailOutput):
        for output in describe_outputs(model):
            if output.name.endswith(("_path", "_paths")) or output.name == "remote_url":
                assert output.editable is None, (model.__name__, output.name)


def test_config_schemas_carry_what_the_form_shows():
    publish = PublishConfig.model_json_schema()["properties"]
    assert publish["platform"]["x-enum-labels"] == {"youtube": "YouTube", "drive": "Google Drive"}
    # The form checks each address itself, without knowing it is looking at the Email agent.
    assert EmailConfig.model_json_schema()["properties"]["recipients"]["items"]["format"] == "email"


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


@pytest.mark.parametrize(
    ("family", "manifest_says", "user_asks", "waits"),
    [
        ("distribute", False, False, True),  # sends content out: always waits, whatever anyone says
        ("distribute", True, False, True),
        ("create", True, False, True),  # the agent asks for it
        ("create", False, True, True),  # the user asks for it
        ("create", False, False, False),
    ],
)
def test_who_decides_that_a_step_waits_for_a_person(family, manifest_says, user_asks, waits):
    manifest = AgentManifest(
        name="x",
        version="1.0.0",
        title="X",
        description="d",
        family=family,
        input_type="A",
        output_type="B",
        requires_approval=manifest_says,
    )
    assert manifest.needs_approval(user_asks) is waits


@pytest.mark.parametrize(
    ("family", "manifest_says", "user_asks", "moment"),
    [
        ("distribute", False, False, "before"),  # what it is about to send is approved before it acts
        ("distribute", False, True, "before"),  # asking to review its result can't let it send first
        ("create", True, False, "before"),
        ("create", False, True, "after"),  # the user reviews what it made
        ("create", False, False, None),
    ],
)
def test_a_step_that_sends_waits_before_it_acts_and_a_reviewed_one_after(family, manifest_says, user_asks, moment):
    manifest = AgentManifest(
        name="x",
        version="1.0.0",
        title="X",
        description="d",
        family=family,
        input_type="A",
        output_type="B",
        requires_approval=manifest_says,
    )
    assert manifest.approval_moment(user_asks) == moment


def test_ancestors():
    from contracts.graph import ancestors

    a, b, c = _node(0), _node(100), _node(200)
    assert ancestors(_chain(a, b, c), c.id) == {a.id, b.id}


@pytest.mark.parametrize("model", [PublishConfig, EmailConfig])
def test_a_google_account_is_a_reference_never_a_token(model):
    prop = model.model_json_schema()["properties"]["credential_id"]
    assert prop["x-widget"] == "credential" and prop["x-provider"] == "google"
    assert prop["format"] == "uuid"
    extra = {"recipients": ["a@b.co"]} if model is EmailConfig else {}
    assert model(credential_id=str(uuid4()), **extra).credential_id
    with pytest.raises(ValidationError):
        model(credential_id="ya29.a0-an-access-token", **extra)
