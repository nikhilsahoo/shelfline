from epub_tui.credentials import CredentialStore, MemoryCredentialBackend


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

    assert store.service_name("standard-ebooks") == "epub-tui:standard-ebooks"
