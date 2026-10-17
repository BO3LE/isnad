"""scripts/check_env.py: names and SET / EMPTY only, never a value; and safe local-secret generation."""

from __future__ import annotations

import importlib.util
import stat
import sys
from datetime import datetime
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_env.py"
spec = importlib.util.spec_from_file_location("check_env", SCRIPT)
check_env = importlib.util.module_from_spec(spec)
sys.modules["check_env"] = check_env  # dataclasses look their module up while the class is built
spec.loader.exec_module(check_env)

SECRETS = {
    "OPENAI_API_KEY": "sk-proj-CANARY-openai-0000",
    "OPENROUTER_API_KEY": "sk-or-CANARY-openrouter-0000",
    "SEARCH_API_KEY": "tvly-CANARY-search-0000",
    "GOOGLE_CLIENT_SECRET": "GOCSPX-CANARY-google-0000",
    "JWT_SECRET": "CANARY-jwt-" + "x" * 40,
    "CREDENTIALS_ENCRYPTION_KEY": "Zm9vYmFyZm9vYmFyZm9vYmFyZm9vYmFyZm9vYmFyMDA=",
    "SUPABASE_URL": "https://CANARYPROJECT.supabase.co",
    "LLM_BASE_URL": "http://user:CANARYPASS@localhost:1234/v1",
}


def run(tmp_path: Path, text: str, *args: str, environ: dict | None = None, capsys=None) -> tuple[int, str]:
    env_file = tmp_path / ".env"
    env_file.write_text(text)
    code = check_env.main(["--env-file", str(env_file), *args], environ=environ or {})
    return code, capsys.readouterr().out if capsys else ""


def test_no_value_of_a_key_secret_or_url_is_ever_printed(tmp_path, capsys):
    text = "".join(f"{k}={v}\n" for k, v in SECRETS.items()) + "GOOGLE_CLIENT_ID=id.apps.googleusercontent.com\n"
    for profile in check_env.PROFILES:
        _, out = run(tmp_path, text, "--profile", profile, capsys=capsys)
        assert "CANARY" not in out
        assert "googleusercontent" not in out
        assert "OPENAI_API_KEY" in out and "SET" in out


def test_choices_and_model_ids_are_shown(tmp_path, capsys):
    _, out = run(
        tmp_path,
        "FAKE_ADAPTERS=false\nLLM_PROVIDER=local\nLLM_MODEL=qwen3-30b\n",
        "--profile",
        "live-local",
        capsys=capsys,
    )
    assert "FAKE_ADAPTERS" in out and "= false" in out
    assert "= qwen3-30b" in out


def test_the_example_file_is_fine_for_dev_but_not_for_live_local(tmp_path, capsys):
    example = (SCRIPT.parents[1] / ".env.example").read_text()

    assert run(tmp_path, example, "--profile", "dev", capsys=capsys)[0] == 0
    code, out = run(tmp_path, example, "--profile", "live-local", capsys=capsys)
    assert code == 1
    assert "must be false for this profile" in out
    assert "the public example value" in out


def test_live_local_passes_with_real_mode_a_local_model_and_a_real_secret(tmp_path, capsys):
    text = f"FAKE_ADAPTERS=false\nLLM_PROVIDER=local\nLLM_MODEL=m\nJWT_SECRET={'s' * 48}\n"
    code, out = run(tmp_path, text, "--profile", "live-local", capsys=capsys)
    assert code == 0, out
    assert "OK for live-local" in out


@pytest.mark.parametrize(
    ("text", "says"),
    [
        ("FAKE_ADAPTERS=false\nLLM_PROVIDER=openai\nLLM_MODEL=m\n", "live-local runs the model on this machine"),
        ("FAKE_ADAPTERS=false\nLLM_PROVIDER=local\n", "lms ls"),
        ("FAKE_ADAPTERS=false\nOPENAI_API_KEY=sk-x\nLLM_MODEL=m\n", "resolves to openai"),
        ("FAKE_ADAPTERS=maybe\n", "not a boolean"),
        ("FAKE_ADAPTERS=false\nLLM_PROVIDER=ollama\n", "not one of"),
        ("FAKE_ADAPTERS=false\nLLM_MODEL=m\nLLM_BASE_URL=localhost:1234\n", "not an http(s) URL"),
        ("FAKE_ADAPTERS=false\nLLM_MODEL=m\nCREDENTIALS_ENCRYPTION_KEY=not-a-key\n", "not a valid Fernet key"),
    ],
)
def test_live_local_problems_are_named(tmp_path, capsys, text, says):
    code, out = run(tmp_path, text + f"JWT_SECRET={'s' * 48}\n", "--profile", "live-local", capsys=capsys)
    assert code == 1
    assert says in out


def test_live_providers_needs_search_google_and_the_hosted_key(tmp_path, capsys):
    text = f"FAKE_ADAPTERS=false\nLLM_PROVIDER=openrouter\nLLM_MODEL=m\nJWT_SECRET={'s' * 48}\n"
    code, out = run(tmp_path, text, "--profile", "live-providers", capsys=capsys)
    assert code == 1
    for needed in (
        "OPENROUTER_API_KEY",
        "the Researcher's real search",
        "Google connections",
        "store Google connections",
    ):
        assert needed in out


def test_the_process_environment_wins_and_is_marked(tmp_path, capsys):
    code, out = run(
        tmp_path,
        "FAKE_ADAPTERS=true\n",
        "--profile",
        "live-local",
        environ={"FAKE_ADAPTERS": "false", "LLM_MODEL": "m", "JWT_SECRET": "e" * 40, "HOME": "/x"},
        capsys=capsys,
    )
    assert code == 0, out
    assert "(env) = false" in out
    assert "HOME" not in out  # only the variables ISNAD reads


@pytest.mark.parametrize(
    ("line", "value"),
    [("A=1", "1"), ("export A=1", "1"), ('A="x y"', "x y"), ("A='#x'", "#x"), ("A=v # note", "v"), ("A=", "")],
)
def test_parse_env_reads_lines_as_dotenv_does(line, value):
    assert check_env.parse_env(line) == {"A": value}


# ---------------------------------------------------------------- --write-local-secrets
FIXED = datetime(2026, 10, 17, 9, 30, 0)


def test_missing_secrets_are_generated_into_the_file_and_never_printed(tmp_path, capsys):
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"# comment\nJWT_SECRET={check_env.PLACEHOLDER_JWT_SECRET}\nCREDENTIALS_ENCRYPTION_KEY=\nKEEP=me\n"
    )

    written = check_env.generate_missing_values(env_file, now=lambda: FIXED)

    assert written == ["JWT_SECRET", "CREDENTIALS_ENCRYPTION_KEY"]
    values = check_env.parse_env(env_file.read_text())
    assert check_env.jwt_secret_problem(values["JWT_SECRET"]) is None
    assert check_env.is_fernet_keys(values["CREDENTIALS_ENCRYPTION_KEY"])
    assert values["KEEP"] == "me" and env_file.read_text().startswith("# comment\n")
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    backup = tmp_path / ".env.bak-20261017-093000"
    assert check_env.PLACEHOLDER_JWT_SECRET in backup.read_text()
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600

    check_env.main(["--env-file", str(env_file), "--write-local-secrets"], environ={})
    out = capsys.readouterr().out
    assert "nothing to generate" in out
    assert values["JWT_SECRET"] not in out and values["CREDENTIALS_ENCRYPTION_KEY"] not in out


def test_a_set_encryption_key_is_never_replaced(tmp_path):
    env_file = tmp_path / ".env"
    key = SECRETS["CREDENTIALS_ENCRYPTION_KEY"]
    env_file.write_text(f"JWT_SECRET=short\nCREDENTIALS_ENCRYPTION_KEY={key}\n")

    assert check_env.generate_missing_values(env_file, now=lambda: FIXED) == ["JWT_SECRET"]
    assert check_env.parse_env(env_file.read_text())["CREDENTIALS_ENCRYPTION_KEY"] == key


@pytest.mark.parametrize(
    ("text", "refusal"),
    [
        ("ENVIRONMENT=production\nJWT_SECRET=\n", "ENVIRONMENT=production"),
        ("CREDENTIALS_ENCRYPTION_KEY=broken\n", "Fix it by hand"),
    ],
)
def test_it_refuses_rather_than_risk_production_or_stored_connections(tmp_path, text, refusal):
    env_file = tmp_path / ".env"
    env_file.write_text(text)

    with pytest.raises(SystemExit, match=refusal):
        check_env.generate_missing_values(env_file)
    assert env_file.read_text() == text
    assert not list(tmp_path.glob(".env.bak-*"))


def test_it_does_not_create_an_env_file(tmp_path):
    with pytest.raises(SystemExit, match=r"copy \.env\.example"):
        check_env.generate_missing_values(tmp_path / ".env")
