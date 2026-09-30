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
            image = await ports.image.generate(input_data.prompt, aspect=input_data.aspect)
            extension, content_type = _image_type(image)
            paths.append(
                await ports.storage.put(f"artifacts/images/{batch}/image-{i + 1}.{extension}", image, content_type)
            )
        return ImageOutput(image_paths=paths)


def _image_type(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    return "bin", "application/octet-stream"
