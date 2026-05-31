from __future__ import annotations

from typing import Protocol
from urllib.parse import quote


class CredentialError(RuntimeError):
    """Raised when a credential operation cannot be completed safely."""


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

    def __init__(
        self,
        backend: CredentialBackend | None = None,
        *,
        namespace: str | None = None,
        config_scope: str | None = None,
    ) -> None:
        self.backend = backend or KeyringCredentialBackend()
        self.namespace = namespace if namespace is not None else config_scope

    def service_name(self, catalog_name: str) -> str:
        catalog_component = self._service_component(catalog_name)
        if self.namespace:
            namespace_component = self._service_component(self.namespace)
            return f"{self.SERVICE_PREFIX}:{namespace_component}:{catalog_component}"
        return f"{self.SERVICE_PREFIX}:{catalog_component}"

    def _service_component(self, value: str) -> str:
        return quote(value, safe="")

    def save_password(self, catalog_name: str, username: str, password: str) -> None:
        try:
            self.backend.set_password(self.service_name(catalog_name), username, password)
        except Exception:
            failed = True
        else:
            failed = False

        if failed:
            raise CredentialError("Failed to save credential") from None

    def get_password(self, catalog_name: str, username: str) -> str | None:
        try:
            return self.backend.get_password(self.service_name(catalog_name), username)
        except Exception:
            return None

    def delete_password(self, catalog_name: str, username: str) -> None:
        try:
            self.backend.delete_password(self.service_name(catalog_name), username)
        except Exception:
            return None
