from __future__ import annotations

from contracts.agent import BaseAgent
from contracts.agent_io import ResearchConfig, ResearchInput, ResearchOutput
from contracts.errors import NonRetryableAgentError
from contracts.ports import Ports


class ResearcherAgent(BaseAgent[ResearchInput, ResearchOutput]):
    manifest = BaseAgent.load_manifest(__file__)
    input_model = ResearchInput
    output_model = ResearchOutput
    config_model = ResearchConfig

    async def execute(self, input_data: ResearchInput, ports: Ports) -> ResearchOutput:
        sources = await ports.search.search(input_data.topic, input_data.num_sources)
        if not sources:
            raise NonRetryableAgentError(
                f"No sources found for “{input_data.topic}”. Try a broader topic.", code="no_sources"
            )
        notes = [s.snippet.strip() or s.title for s in sources]
        return ResearchOutput(notes=notes, sources=sources)
