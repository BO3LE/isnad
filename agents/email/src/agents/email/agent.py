from __future__ import annotations

from datetime import UTC, datetime

from contracts.agent import BaseAgent
from contracts.agent_io import EmailConfig, EmailInput, EmailOutput
from contracts.ports import Ports


class EmailAgent(BaseAgent[EmailInput, EmailOutput]):
    manifest = BaseAgent.load_manifest(__file__)
    input_model = EmailInput
    output_model = EmailOutput
    config_model = EmailConfig

    async def execute(self, input_data: EmailInput, ports: Ports) -> EmailOutput:
        body = input_data.body.strip()
        if input_data.links:
            body += "\n\n" + "\n".join(input_data.links)
        message_id = await ports.email.send(input_data.recipients, input_data.subject, body)
        return EmailOutput(message_id=message_id, sent_at=datetime.now(UTC), recipients=input_data.recipients)
