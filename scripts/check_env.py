#!/usr/bin/env python3
"""Check an env file for a way of running ISNAD — printing variable NAMES and SET / EMPTY, never values.

    python scripts/check_env.py                         # .env, profile "dev"
    python scripts/check_env.py --profile live-local    # real adapters, the Writer on LM Studio
    python scripts/check_env.py --profile live-providers --env-file .env

Profiles:
    dev             FAKE_ADAPTERS=true. Nothing is required; shapes are still checked.
    live-local      FAKE_ADAPTERS=false, the LLM on this machine (LLM_PROVIDER=local, LLM_MODEL),
                    and a real JWT_SECRET. No paid service, no key.
    live-providers  live-local's needs, plus search, Google connections and the hosted LLM's key
                    when LLM_PROVIDER is openai or openrouter.

A variable set in the process environment wins over the file, as it does for the API and worker
(pydantic-settings); such a line is marked "(env)". Only choices and booleans — FAKE_ADAPTERS,
LLM_PROVIDER, LLM_MODEL and the like — are ever shown with their value; a key, secret or URL never is.

    python scripts/check_env.py --write-local-secrets

generates JWT_SECRET (when it is the example value, short or empty) and CREDENTIALS_ENCRYPTION_KEY
(when empty) straight into the file, after copying it to <file>.bak-<time>. It prints which ones it
wrote, never what. It refuses a file with ENVIRONMENT=production, and never replaces an encryption
key that is already set: that would make every stored Google connection unreadable.

Exit status: 0 when the profile's requirements are met, 1 when not, 2 for a usage error.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import os
import re
import secrets
import shutil
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PLACEHOLDER_JWT_SECRET = "change-me-in-.env-at-least-32-characters-long"
MIN_SECRET_LENGTH = 32
PROFILES = ("dev", "live-local", "live-providers")
GENERATED = ("JWT_SECRET", "CREDENTIALS_ENCRYPTION_KEY")  # what --write-local-secrets may write
LLM_PROVIDERS = ("local", "openai", "openrouter", "fake")
# Values safe to show: choices, booleans, numbers and model ids. Everything else is SET / EMPTY only.
SHOWN = {
    "ENVIRONMENT",
    "FAKE_ADAPTERS",
    "ENABLE_DEV_LOGIN",
    "STORAGE_BACKEND",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_STRUCTURED",
    "LLM_TIMEOUT_S",
    "LLM_MAX_OUTPUT_TOKENS",
    "OPENAI_MODEL",
    "VITE_AUTH_MODE",
}

Env = dict[str, str]


@dataclass(frozen=True)
class Finding:
    name: str
    set: bool
    source: str  # "file", "env" or ""
    level: str  # "ok", "warn" or "error"
    note: str
    shown: str | None = None


# ---------------------------------------------------------------- reading
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")


def parse_env(text: str) -> Env:
    """KEY=VALUE lines as python-dotenv and docker compose read them. Never expands anything."""
    values: Env = {}
    for line in text.splitlines():
        match = _LINE.match(line)
        if not match:
            continue
        name, raw = match.groups()
        raw = raw.strip()
        if raw[:1] in ("'", '"') and raw[-1:] == raw[:1] and len(raw) >= 2:
            value = raw[1:-1]
        else:
            value = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
        values[name] = value
    return values


def effective(file_values: Env, environ: Env) -> tuple[Env, dict[str, str]]:
    merged, sources = {}, {}
    for name in set(file_values) | {n for n in environ if n in file_values or n in KNOWN}:
        if environ.get(name):
            merged[name], sources[name] = environ[name], "env"
        elif name in file_values:
            merged[name], sources[name] = file_values[name], "file"
    return merged, sources


# ---------------------------------------------------------------- shapes
def is_url(value: str) -> bool:
    return bool(re.match(r"^https?://[^\s/]+", value))


def is_fernet_keys(value: str) -> bool:
    keys = [k.strip() for k in value.split(",") if k.strip()]
    if not keys:
        return False
    for key in keys:
        try:
            if len(base64.urlsafe_b64decode(key.encode())) != 32:
                return False
        except (binascii.Error, ValueError):
            return False
    return True


def jwt_secret_problem(value: str) -> str | None:
    if not value:
        return "empty"
    if value == PLACEHOLDER_JWT_SECRET:
        return "the public example value"
    if len(value) < MIN_SECRET_LENGTH:
        return f"shorter than {MIN_SECRET_LENGTH} characters"
    return None


def truthy(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    return None


def llm_provider(env: Env) -> str:
    """As adapters.factory.llm_provider: explicit, else openai if OPENAI_API_KEY, else local."""
    return env.get("LLM_PROVIDER") or ("openai" if env.get("OPENAI_API_KEY") else "local")


# ---------------------------------------------------------------- rules
Rule = Callable[[str, Env, str], tuple[str, str]]  # (value, env, profile) -> (level, note)


def _fake_adapters(value: str, env: Env, profile: str) -> tuple[str, str]:
    flag = truthy(value) if value else True  # unset = the default, true
    if flag is None:
        return "error", "not a boolean"
    if profile == "dev":
        return ("ok", "fakes everywhere") if flag else ("warn", "real adapters: check with --profile live-local")
    return ("error", "must be false for this profile") if flag else ("ok", "real adapters")


def _jwt_secret(value: str, env: Env, profile: str) -> tuple[str, str]:
    problem = jwt_secret_problem(value)
    if problem is None:
        return "ok", f"{len(value)} characters"
    if profile == "dev":
        return "warn", f"{problem} — fine on your own machine; --write-local-secrets makes a real one"
    return "error", f"{problem} — run with --write-local-secrets"


def _encryption_key(value: str, env: Env, profile: str) -> tuple[str, str]:
    if value:
        return ("ok", "valid Fernet key(s)") if is_fernet_keys(value) else ("error", "not a valid Fernet key")
    if profile == "live-providers":
        return "error", "needed to store Google connections — run with --write-local-secrets"
    return "ok", "not needed without Google connections"


def _llm_provider(value: str, env: Env, profile: str) -> tuple[str, str]:
    if value and value not in LLM_PROVIDERS:
        return "error", f"not one of {', '.join(LLM_PROVIDERS)}"
    resolved = llm_provider(env)
    if profile == "live-local" and resolved != "local":
        return "error", f"resolves to {resolved}; live-local runs the model on this machine (LLM_PROVIDER=local)"
    return "ok", f"resolves to {resolved}" + ("" if value else " (unset)")


def _llm_model(value: str, env: Env, profile: str) -> tuple[str, str]:
    resolved = llm_provider(env)
    if profile == "dev" or resolved == "fake" or value:
        return "ok", ""
    if resolved == "openai":
        return "ok", "OPENAI_MODEL is used"
    return "error", "the model id LM Studio shows (`lms ls`)" if resolved == "local" else "required for openrouter"


def _required_in(*profiles: str, why: str = "") -> Rule:
    def rule(value: str, env: Env, profile: str) -> tuple[str, str]:
        if value or profile not in profiles:
            return "ok", ""
        return "error", why or f"required for {profile}"

    return rule


def _key_for(provider: str, name: str) -> Rule:
    def rule(value: str, env: Env, profile: str) -> tuple[str, str]:
        if value or profile == "dev" or llm_provider(env) != provider or env.get("LLM_API_KEY"):
            return "ok", ""
        return "error", f"LLM_PROVIDER={provider} needs {name} (or LLM_API_KEY)"

    return rule


def _url(required_in: tuple[str, ...] = ()) -> Rule:
    def rule(value: str, env: Env, profile: str) -> tuple[str, str]:
        if not value:
            return ("error", f"required for {profile}") if profile in required_in else ("ok", "")
        return ("ok", "") if is_url(value) else ("error", "not an http(s) URL")

    return rule


def _environment(value: str, env: Env, profile: str) -> tuple[str, str]:
    if value and value not in ("development", "test", "production"):
        return "error", "not development, test or production"
    return "ok", ""


def _choice(*options: str) -> Rule:
    def rule(value: str, env: Env, profile: str) -> tuple[str, str]:
        return ("ok", "") if not value or value in options else ("error", f"not one of {', '.join(options)}")

    return rule


def _google_pair(other: str) -> Rule:
    def rule(value: str, env: Env, profile: str) -> tuple[str, str]:
        if not value and profile == "live-providers":
            return "error", "required for Google connections (publishing, Gmail)"
        if bool(value) != bool(env.get(other)):
            return "warn", f"set without {other}: Google connections stay off"
        return "ok", ""

    return rule


RULES: dict[str, Rule] = {
    "ENVIRONMENT": _environment,
    "FAKE_ADAPTERS": _fake_adapters,
    "JWT_SECRET": _jwt_secret,
    "CREDENTIALS_ENCRYPTION_KEY": _encryption_key,
    "LLM_PROVIDER": _llm_provider,
    "LLM_MODEL": _llm_model,
    "LLM_BASE_URL": _url(),
    "LLM_STRUCTURED": _choice("json_schema", "json_object", "none"),
    "OPENAI_API_KEY": _key_for("openai", "OPENAI_API_KEY"),
    "OPENROUTER_API_KEY": _key_for("openrouter", "OPENROUTER_API_KEY"),
    "SEARCH_API_KEY": _required_in("live-providers", why="the Researcher's real search (Tavily)"),
    "GOOGLE_CLIENT_ID": _google_pair("GOOGLE_CLIENT_SECRET"),
    "GOOGLE_CLIENT_SECRET": _google_pair("GOOGLE_CLIENT_ID"),
    "GOOGLE_REDIRECT_URI": _url(),
    "FRONTEND_URL": _url(),
    "STORAGE_BACKEND": _choice("local", "supabase"),
    "SUPABASE_URL": _url(),
    "VITE_SUPABASE_URL": _url(),
    "VITE_AUTH_MODE": _choice("dev", "supabase"),
}
KNOWN = set(RULES)


def check(env: Env, sources: dict[str, str], profile: str) -> list[Finding]:
    findings = []
    for name, rule in RULES.items():
        value = env.get(name, "")
        level, note = rule(value, env, profile)
        findings.append(
            Finding(
                name=name,
                set=bool(value),
                source=sources.get(name, ""),
                level=level,
                note=note,
                shown=value if name in SHOWN and value else None,
            )
        )
    return findings


def report(findings: list[Finding], profile: str, path: Path) -> str:
    marks = {"ok": "✓", "warn": "!", "error": "✗"}
    width = max(len(f.name) for f in findings)
    lines = [f"{path} — profile {profile}"]
    for f in findings:
        state = "SET  " if f.set else "EMPTY"
        detail = f" = {f.shown}" if f.shown else ""
        origin = " (env)" if f.source == "env" else ""
        note = f"  {f.note}" if f.note else ""
        lines.append(f"  {marks[f.level]} {f.name.ljust(width)}  {state}{origin}{detail}{note}")
    errors = sum(f.level == "error" for f in findings)
    warnings = sum(f.level == "warn" for f in findings)
    lines.append(f"{'OK' if not errors else 'NOT READY'} for {profile}: {errors} problem(s), {warnings} warning(s).")
    return "\n".join(lines)


# ---------------------------------------------------------------- writing local secrets
def generate_missing_values(path: Path, now: Callable[[], datetime] = datetime.now) -> list[str]:
    """Generate the missing local secrets into `path`. Returns the names written — never values."""
    if not path.exists():
        raise SystemExit(f"{path} doesn't exist — copy .env.example to it first")
    text = path.read_text(encoding="utf-8")
    values = parse_env(text)
    if values.get("ENVIRONMENT") == "production":
        raise SystemExit("refusing: this file has ENVIRONMENT=production — generate production secrets deliberately")
    if values.get("CREDENTIALS_ENCRYPTION_KEY") and not is_fernet_keys(values["CREDENTIALS_ENCRYPTION_KEY"]):
        raise SystemExit(
            "refusing: CREDENTIALS_ENCRYPTION_KEY is set but invalid. Fix it by hand — replacing it would make "
            "any stored Google connection unreadable."
        )
    updates: dict[str, str] = {}
    if jwt_secret_problem(values.get("JWT_SECRET", "")):
        updates["JWT_SECRET"] = secrets.token_urlsafe(48)
    if not values.get("CREDENTIALS_ENCRYPTION_KEY"):
        updates["CREDENTIALS_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
    if not updates:
        return []

    backup = path.with_name(f"{path.name}.bak-{now():%Y%m%d-%H%M%S}")
    shutil.copy2(path, backup)
    backup.chmod(stat.S_IRUSR | stat.S_IWUSR)
    lines = text.splitlines()
    for name, value in updates.items():
        for i, line in enumerate(lines):
            match = _LINE.match(line)
            if match and match.group(1) == name:
                lines[i] = f"{name}={value}"
                break
        else:
            lines.append(f"{name}={value}")
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(path)
    # Names from the constant, not from `updates`: nothing that held a secret reaches the caller.
    return [name for name in GENERATED if name in updates]


def main(argv: list[str] | None = None, environ: Env | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--profile", choices=PROFILES, default="dev")
    parser.add_argument("--write-local-secrets", action="store_true")
    parser.add_argument("--ignore-environment", action="store_true", help="check the file alone")
    args = parser.parse_args(argv)

    if args.write_local_secrets:
        generated = generate_missing_values(args.env_file)
        print(
            f"{args.env_file}: "
            + (", ".join(f"{n} generated" for n in generated) if generated else "nothing to generate")
        )

    if not args.env_file.exists():
        print(f"{args.env_file} doesn't exist — copy .env.example to start", file=sys.stderr)
        return 2
    file_values = parse_env(args.env_file.read_text(encoding="utf-8"))
    env, sources = effective(file_values, {} if args.ignore_environment else dict(environ or os.environ))
    findings = check(env, sources, args.profile)
    print(report(findings, args.profile, args.env_file))
    return 1 if any(f.level == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
