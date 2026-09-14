import io
import json
import wave

import pytest

from adapters.factory import AdapterSettings, build_ports
from adapters.image.fake import FakeImage
from adapters.llm.fake import FakeLLM
from adapters.storage.local import LocalStorage
from adapters.tts.fake import FakeTTS
from contracts.ports import EmailPort, ImagePort, LLMPort, PublishMetadata, SearchPort, StoragePort, TTSPort


def test_fake_ports_satisfy_the_protocols(tmp_path):
    ports = build_ports(AdapterSettings(fake=True, storage_root=str(tmp_path)))
    assert isinstance(ports.llm, LLMPort)
    assert isinstance(ports.search, SearchPort)
    assert isinstance(ports.tts, TTSPort)
    assert isinstance(ports.image, ImagePort)
    assert isinstance(ports.storage, StoragePort)
    assert isinstance(ports.email, EmailPort)
    assert set(ports.publishers) == {"youtube", "drive"}


async def test_fake_llm_json_mode_is_parseable():
    data = json.loads(await FakeLLM().complete("write", json_mode=True))
    assert {"title", "summary", "article_md"} <= data.keys()


async def test_fake_tts_returns_valid_wav():
    audio = await FakeTTS().speak("hello " * 40, voice="en")
    with wave.open(io.BytesIO(audio)) as wav:
        assert wav.getnframes() > 0


async def test_fake_image_is_png():
    assert (await FakeImage().generate("x", aspect="square")).startswith(b"\x89PNG")


async def test_local_storage_round_trip_and_refuses_traversal(tmp_path):
    storage = LocalStorage(tmp_path)
    await storage.put("artifacts/u/r/a.txt", b"hi", "text/plain")
    assert await storage.get("artifacts/u/r/a.txt") == b"hi"
    with pytest.raises(ValueError):
        await storage.put("../escape.txt", b"x", "text/plain")


async def test_fake_publisher_returns_a_link(tmp_path):
    ports = build_ports(AdapterSettings(fake=True, storage_root=str(tmp_path)))
    result = await ports.publishers["youtube"].publish("artifacts/u/r/v.mp4", PublishMetadata(title="t"))
    assert result.remote_url.startswith("https://youtu.be/")
