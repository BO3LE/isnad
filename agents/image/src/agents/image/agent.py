from __future__ import annotations

import uuid

from contracts.agent import BaseAgent, Revision
from contracts.agent_io import ImageConfig, ImageInput, ImageOutput
from contracts.ports import Ports


class ImageAgent(BaseAgent[ImageInput, ImageOutput]):
    manifest = BaseAgent.load_manifest(__file__)
    input_model = ImageInput
    output_model = ImageOutput
    config_model = ImageConfig

    async def execute(self, input_data: ImageInput, ports: Ports) -> ImageOutput:
        return await self._draw(input_data.prompt, input_data, ports)

    async def revise(self, input_data: ImageInput, ports: Ports, revision: Revision) -> ImageOutput:
        """The reviewer's note is added to what the image should show."""
        prompt = f"{input_data.prompt}. {revision.note}" if revision.note else input_data.prompt
        return await self._draw(prompt, input_data, ports)

    async def _draw(self, prompt: str, input_data: ImageInput, ports: Ports) -> ImageOutput:
        batch = uuid.uuid4().hex[:8]
        paths = []
        for i in range(input_data.count):
            png = await ports.image.generate(prompt, aspect=input_data.aspect)
            paths.append(await ports.storage.put(f"artifacts/images/{batch}/image-{i + 1}.png", png, "image/png"))
        return ImageOutput(image_paths=paths)
