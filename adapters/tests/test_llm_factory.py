"""Which LLM real mode uses (LLM_PROVIDER), and that a missing setting is a readable error, never a fake."""

from __future__ import annotations

import pytest

from adapters.factory import AdapterSettings, MisconfiguredLLM, build_llm, build_ports
from adapters.llm.fake import FakeLLM
from adapters.llm.openai_compatible import OpenAICompatibleLLM
from contracts.errors import AgentError


def real(**llm) -> AdapterSettings:
    return AdapterSettings(fake=False, storage_root="/tmp/gp-test", **llm)


def test_fake_adapters_mode_never_builds_a_real_llm(tmp_path):
    settings = AdapterSettings(fake=True, storage_root=str(tmp_path), llm_provider="openai", openai_api_key="k")
    assert isinstance(build_ports(settings).llm, FakeLLM)


def test_local_is_the_default_and_needs_no_key():
    llm = build_llm(real(llm_model="qwen3-30b-a3b"))

    assert isinstance(llm, OpenAICompatibleLLM)
    assert llm.config.provider == "local"
    assert llm.config.base_url == "http://localhost:1234/v1"
    assert llm.config.api_key is None


def test_inside_docker_local_points_at_the_host_and_llm_base_url_still_wins():
    in_docker = real(llm_model="m", llm_local_base_url="http://host.docker.internal:1234/v1")
    assert build_llm(in_docker).config.base_url == "http://host.docker.internal:1234/v1"

    ollama = real(llm_model="qwen3:30b", llm_base_url="http://localhost:11434/v1/")
    assert build_llm(ollama).config.base_url == "http://localhost:11434/v1"


def test_an_openai_key_alone_still_selects_openai_as_before():
    llm = build_llm(real(openai_api_key="sk-test"))

    assert llm.config.provider == "openai"
    assert llm.config.base_url == "https://api.openai.com/v1"
    assert llm.config.model == "gpt-4o"


def test_openrouter_takes_its_own_key_and_a_model():
    llm = build_llm(real(llm_provider="openrouter", openrouter_api_key="or-key", llm_model="qwen/qwen3-30b-a3b"))

    assert llm.config.base_url == "https://openrouter.ai/api/v1"
    assert llm.config.api_key == "or-key"


def test_llm_settings_reach_the_adapter():
    llm = build_llm(
        real(
            llm_model="m",
            llm_structured="json_object",
            llm_timeout_s=42,
            llm_max_output_tokens=2048,
            llm_temperature=0.2,
            llm_stream=False,
            llm_reasoning_effort="none",
        )
    )
    c = llm.config
    assert (c.structured, c.timeout_s, c.max_output_tokens, c.temperature, c.stream, c.reasoning_effort) == (
        "json_object",
        42,
        2048,
        0.2,
        False,
        "none",
    )
    assert build_llm(real(llm_model="m")).config.reasoning_effort is None


@pytest.mark.parametrize(
    ("settings", "says"),
    [
        (real(), "Set LLM_MODEL"),
        (real(llm_provider="openai"), "OPENAI_API_KEY"),
        (real(llm_provider="openrouter", llm_model="m"), "OPENROUTER_API_KEY"),
        (real(llm_provider="openrouter", openrouter_api_key="k"), "Set LLM_MODEL"),
    ],
    ids=["local-no-model", "openai-no-key", "openrouter-no-key", "openrouter-no-model"],
)
async def test_a_setting_that_cant_work_fails_each_step_readably_and_never_falls_back_to_a_fake(settings, says):
    llm = build_llm(settings)

    assert isinstance(llm, MisconfiguredLLM)
    with pytest.raises(AgentError) as failed:
        await llm.complete("Write.", json_mode=True)
    assert says in failed.value.message
    assert not failed.value.retryable
    assert failed.value.code == "llm_misconfigured"


def test_fake_can_still_be_chosen_explicitly_in_real_mode():
    assert isinstance(build_llm(real(llm_provider="fake")), FakeLLM)


def test_without_the_openai_sdk_installed_a_step_says_what_to_install(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_openai(name, *args, **kwargs):
        if name == "openai" or name.startswith("openai."):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_openai)
    llm = build_llm(real(llm_model="m"))

    assert isinstance(llm, MisconfiguredLLM)
    assert "gp-adapters[openai]" in llm.message
