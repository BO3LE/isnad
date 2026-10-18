from __future__ import annotations

from contracts.agent import BaseAgent, Revision
from contracts.agent_io import ResearchConfig, ResearchInput, ResearchOutput
from contracts.errors import NonRetryableAgentError
from contracts.ports import Ports

# A search service reads a short query best (Tavily suggests under 400 characters).
MAX_QUERY_CHARS = 400


class ResearcherAgent(BaseAgent[ResearchInput, ResearchOutput]):
    manifest = BaseAgent.load_manifest(__file__)
    input_model = ResearchInput
    output_model = ResearchOutput
    config_model = ResearchConfig

    async def execute(self, input_data: ResearchInput, ports: Ports) -> ResearchOutput:
        return await self._research(input_data.topic, input_data.num_sources, ports)

    async def revise(self, input_data: ResearchInput, ports: Ports, revision: Revision) -> ResearchOutput:
        """The reviewer's note steers the search: it is searched for along with the topic."""
        query = f"{input_data.topic} — {revision.note}" if revision.note else input_data.topic
        return await self._research(query[:MAX_QUERY_CHARS].strip(), input_data.num_sources, ports)

    async def _research(self, query: str, count: int, ports: Ports) -> ResearchOutput:
        sources = await ports.search.search(query, count)
        if not sources:
            raise NonRetryableAgentError(f"No sources found for “{query}”. Try a broader topic.", code="no_sources")
        notes = [s.snippet.strip() or s.title for s in sources]
        return ResearchOutput(notes=notes, sources=sources)
