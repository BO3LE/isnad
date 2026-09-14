from __future__ import annotations

import uuid

from contracts.agent import BaseAgent
from contracts.agent_io import ImageConfig, ImageInput, ImageOutput
from contracts.ports import Ports


class ImageAgent(BaseAgent[ImageInput, ImageOutput]):
    manifest = BaseAgent.load_manifest(__file__)
    input_model = ImageInput
    output_model = ImageOutput
    config_model = ImageConfig

    async def execute(self, input_data: ImageInput, ports: Ports) -> ImageOutput:
        batch = uuid.uuid4().hex[:8]
        paths = []
        for i in range(input_data.count):
            png = await ports.image.generate(input_data.prompt, aspect=input_data.aspect)
            paths.append(await ports.storage.put(f"artifacts/images/{batch}/image-{i + 1}.png", png, "image/png"))
        return ImageOutput(image_paths=paths)
