from __future__ import annotations

from typing import Protocol


class CredentialBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None:
        ...

    def set_password(self, service: str, username: str, password: str) -> None:
        ...

    def delete_password(self, service: str, username: str) -> None:
        ...


class MemoryCredentialBackend:
    def __init__(self) -> None:
        self._passwords: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._passwords.pop((service, username), None)


class KeyringCredentialBackend:
    def get_password(self, service: str, username: str) -> str | None:
        import keyring

        return keyring.get_password(service, username)

    def set_password(self, service: str, username: str, password: str) -> None:
        import keyring

        keyring.set_password(service, username, password)

    def delete_password(self, service: str, username: str) -> None:
        import keyring

        keyring.delete_password(service, username)


class CredentialStore:
    SERVICE_PREFIX = "epub-tui"

    def __init__(self, backend: CredentialBackend | None = None) -> None:
        self.backend = backend or KeyringCredentialBackend()

    def service_name(self, catalog_name: str) -> str:
        return f"{self.SERVICE_PREFIX}:{catalog_name}"

    def save_password(self, catalog_name: str, username: str, password: str) -> None:
        self.backend.set_password(self.service_name(catalog_name), username, password)

    def get_password(self, catalog_name: str, username: str) -> str | None:
        return self.backend.get_password(self.service_name(catalog_name), username)

    def delete_password(self, catalog_name: str, username: str) -> None:
        self.backend.delete_password(self.service_name(catalog_name), username)
