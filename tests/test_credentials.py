import builtins
import traceback

import pytest

from shelfline.credentials import (
    CredentialError,
    CredentialStore,
    KeyringCredentialBackend,
    MemoryCredentialBackend,
)


def test_memory_backend_round_trips_saved_password() -> None:
    store = CredentialStore(MemoryCredentialBackend())

    store.save_password("standard-ebooks", "reader", "secret")

    assert store.get_password("standard-ebooks", "reader") == "secret"


def test_missing_password_returns_none() -> None:
    store = CredentialStore(MemoryCredentialBackend())

    assert store.get_password("standard-ebooks", "reader") is None


def test_delete_removes_password() -> None:
    store = CredentialStore(MemoryCredentialBackend())
    store.save_password("standard-ebooks", "reader", "secret")

    store.delete_password("standard-ebooks", "reader")

    assert store.get_password("standard-ebooks", "reader") is None


def test_service_name_includes_prefix_and_catalog() -> None:
    store = CredentialStore(MemoryCredentialBackend())

    assert store.service_name("standard-ebooks") == "shelfline:standard-ebooks"


def test_service_name_preserves_default_private_spec_behavior() -> None:
    store = CredentialStore(MemoryCredentialBackend())

    assert store.service_name("Private") == "shelfline:Private"


def test_service_name_can_include_namespace() -> None:
    store = CredentialStore(MemoryCredentialBackend(), namespace="config-a")

    assert store.service_name("Private") == "shelfline:config-a:Private"


def test_service_name_disambiguates_delimiter_characters() -> None:
    store_a = CredentialStore(MemoryCredentialBackend(), namespace="a")
    store_b = CredentialStore(MemoryCredentialBackend(), namespace="a:b")

    assert store_a.service_name("b:c") != store_b.service_name("c")


class FailingCredentialBackend:
    def get_password(self, service: str, username: str) -> str | None:
        raise RuntimeError("keyring is unavailable")

    def set_password(self, service: str, username: str, password: str) -> None:
        raise RuntimeError(f"failed to save {password}")

    def delete_password(self, service: str, username: str) -> None:
        raise RuntimeError("password not found")


def test_get_password_returns_none_when_backend_lookup_fails() -> None:
    store = CredentialStore(FailingCredentialBackend())

    assert store.get_password("standard-ebooks", "reader") is None


def test_delete_password_is_idempotent_when_backend_delete_fails() -> None:
    store = CredentialStore(FailingCredentialBackend())

    store.delete_password("standard-ebooks", "reader")


def test_save_password_wraps_backend_failure_without_exposing_secret() -> None:
    store = CredentialStore(FailingCredentialBackend())

    with pytest.raises(CredentialError) as excinfo:
        store.save_password("standard-ebooks", "reader", "super-secret")

    assert "super-secret" not in str(excinfo.value)
    assert "standard-ebooks" not in str(excinfo.value)


def test_save_password_traceback_does_not_expose_backend_secret() -> None:
    store = CredentialStore(FailingCredentialBackend())
    secret = "traceback" + "-secret"

    with pytest.raises(CredentialError) as excinfo:
        store.save_password("standard-ebooks", "reader", secret)

    formatted = "".join(
        traceback.format_exception(
            type(excinfo.value),
            excinfo.value,
            excinfo.value.__traceback__,
        )
    )

    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None
    assert secret not in formatted


def test_keyring_backend_imports_keyring_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__
    imported_modules: list[str] = []

    def tracking_import(name: str, *args: object, **kwargs: object) -> object:
        imported_modules.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", tracking_import)

    KeyringCredentialBackend()

    assert "keyring" not in imported_modules
