"""STORAGE_BACKEND picks where generated files go, independently of FAKE_ADAPTERS."""

import pytest

from adapters.factory import AdapterSettings, build_ports, build_storage
from adapters.storage.local import LocalStorage
from adapters.storage.supabase import SupabaseStorage

SUPABASE = {"supabase_url": "https://example.supabase.co", "supabase_service_key": "service-key"}


def test_local_is_the_default(tmp_path):
    assert isinstance(build_storage(AdapterSettings(storage_root=str(tmp_path))), LocalStorage)


@pytest.mark.parametrize("fake", [True, False])
def test_supabase_backs_storage_in_both_fake_and_live_mode(fake):
    ports = build_ports(AdapterSettings(fake=fake, storage_backend="supabase", storage_bucket="artifacts", **SUPABASE))
    assert isinstance(ports.storage, SupabaseStorage)
    assert ports.storage._bucket == "artifacts"


@pytest.mark.parametrize("missing", ["supabase_url", "supabase_service_key"])
def test_supabase_without_credentials_fails_loudly(missing):
    settings = {**SUPABASE, missing: None}
    with pytest.raises(ValueError, match="SUPABASE_URL and SUPABASE_SERVICE_KEY"):
        build_storage(AdapterSettings(storage_backend="supabase", **settings))


def test_an_unknown_backend_is_refused():
    with pytest.raises(ValueError, match="STORAGE_BACKEND"):
        build_storage(AdapterSettings(storage_backend="s3"))  # type: ignore[arg-type]
