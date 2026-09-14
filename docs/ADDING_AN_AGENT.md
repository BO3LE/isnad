# Adding an agent

This is acceptance test **AT-12** and the evidence for **NFR-04**: a new agent appears in the palette with a working configuration form, and **no file outside its own folder changes**.

## 1. Copy the shape

Every agent folder looks the same:

```
agents/<name>/
├── pyproject.toml                 # package gp-agent-<name>, entry point gp.agents:<name>
├── src/agents/<name>/
│   ├── __init__.py                # empty
│   ├── agent.py                   # the agent class — execute() and nothing else public
│   ├── manifest.json              # name, version, title, description, family, icon, types, approval
│   └── prompts/                   # optional prompt templates
└── tests/
    ├── fixtures/input.json
    └── test_agent.py
```

The quickest start is to copy `agents/publisher/` (simple, uses one port) and rename.

## 2. `pyproject.toml`

```toml
[project]
name = "gp-agent-reverser"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["gp-contracts"]          # add third-party libraries this agent needs here

[project.entry-points."gp.agents"]
reverser = "agents.reverser.agent:ReverserAgent"

[tool.setuptools.packages.find]
where = ["src"]
include = ["agents.reverser*"]
namespaces = true

[tool.setuptools.package-data]
"agents.reverser" = ["manifest.json", "prompts/*.md"]
```

The entry point **name** must equal the folder name and the manifest `name`.

## 3. `manifest.json`

```json
{
  "name": "reverser",
  "version": "0.1.0",
  "title": "Reverser",
  "description": "Reverses the article title.",
  "family": "create",
  "icon": "undo-2",
  "input_type": "ReverseInput",
  "output_type": "ReverseOutput",
  "requires_approval": false
}
```

- `family`: `create` makes content, `distribute` sends it out of the platform (and should set `requires_approval: true`).
- `icon`: any [Lucide](https://lucide.dev/icons) name.
- `input_type` / `output_type`: model names in `contracts/agent_io.py`. Adding models there is a `contracts` change (two approvals). For an experiment you can define models inside the agent — `scripts/validate_manifests.py` will flag it until they move to contracts.

## 4. `agent.py`

```python
from contracts.agent import BaseAgent
from contracts.agent_io import ReverseConfig, ReverseInput, ReverseOutput
from contracts.ports import Ports


class ReverserAgent(BaseAgent[ReverseInput, ReverseOutput]):
    manifest = BaseAgent.load_manifest(__file__)
    input_model = ReverseInput  # validated from upstream outputs + configuration
    output_model = ReverseOutput  # what the next agents receive
    config_model = ReverseConfig  # its JSON Schema builds the settings form

    async def execute(self, input_data: ReverseInput, ports: Ports) -> ReverseOutput:
        return ReverseOutput(title=input_data.title[::-1])
```

Rules:

- Talk to the outside world **only through `ports`** (`ports.llm`, `ports.search`, `ports.storage`, …). Never import `adapters`, `db`, `worker` or another agent — CI will fail.
- Raise `contracts.errors.AgentError("readable message")` for failures worth retrying, `NonRetryableAgentError` when retrying can't help. Don't write retry loops — the worker retries with backoff.
- Messages are shown to users: say what happened and what to do (DESIGN-SYSTEM.md §23).
- **Inputs come from every upstream agent's output**, merged, then the node's configuration on top. Use `validation_alias=AliasChoices(...)` to accept an upstream field under another name.

## 5. Test it alone

```python
# tests/test_agent.py
import pytest
from adapters.factory import AdapterSettings, build_ports
from agents.reverser.agent import ReverserAgent


@pytest.fixture()
def ports(tmp_path):
    return build_ports(AdapterSettings(fake=True, storage_root=str(tmp_path)))


async def test_reverses(ports):
    agent = ReverserAgent()
    out = await agent.execute(agent.input_model.model_validate({"title": "abc"}), ports)
    assert out.title == "cba"
```

```bash
pip install --config-settings editable_mode=compat -e agents/reverser
cd agents/reverser && python -m pytest
python scripts/validate_manifests.py
```

## 6. See it in the app

```bash
docker compose restart worker
docker compose logs worker | grep -E "installing new agent|published"
```

Refresh the canvas — the agent is in the palette, and its settings form is built from `config_model`.

## 7. Record the evidence (W8, Zain)

```bash
git diff --stat main
```

Paste the output into Notion → Results & Metrics. Every changed path should start with `agents/<name>/` — plus `contracts/agent_io.py` only if you added new shared models, which should be noted honestly in the report.
