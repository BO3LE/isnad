from __future__ import annotations

from contracts.agent import BaseAgent
from contracts.agent_io import PublishConfig, PublishInput, PublishOutput
from contracts.errors import NonRetryableAgentError
from contracts.ports import Ports, PublishMetadata


class PublisherAgent(BaseAgent[PublishInput, PublishOutput]):
    """Same agent for YouTube and Drive — only the injected PublishPort differs (FR-05)."""

    manifest = BaseAgent.load_manifest(__file__)
    input_model = PublishInput
    output_model = PublishOutput
    config_model = PublishConfig

    async def execute(self, input_data: PublishInput, ports: Ports) -> PublishOutput:
        publisher = ports.publishers.get(input_data.platform)
        if publisher is None:
            raise NonRetryableAgentError(
                f"Publishing to {input_data.platform} isn't available.", code="platform_unavailable"
            )
        result = await publisher.publish(
            input_data.file_path,
            PublishMetadata(
                title=input_data.title,
                description=input_data.description,
                tags=input_data.tags,
                privacy=input_data.privacy,
            ),
        )
        return PublishOutput(platform=input_data.platform, remote_url=result.remote_url, platform_id=result.platform_id)
