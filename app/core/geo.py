import ipaddress
import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeoLocation:
    country: str | None = None
    city: str | None = None
    provider: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.country and not self.city


class GeoProvider(Protocol):
    name: str

    def lookup(self, ip_address: str) -> GeoLocation | None: ...


def is_public_address(ip_address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(ip_address)
    except ValueError:
        return False
    return parsed.is_global


class GeoProviderChain:
    def __init__(self, providers: Sequence[GeoProvider]) -> None:
        self._providers = tuple(providers)

    @property
    def providers(self) -> tuple[GeoProvider, ...]:
        return self._providers

    def lookup(self, ip_address: str) -> GeoLocation | None:
        if not is_public_address(ip_address):
            return None

        for provider in self._providers:
            try:
                location = provider.lookup(ip_address)
            except Exception:
                logger.warning(
                    "geo provider %s failed, advancing chain",
                    provider.name,
                    exc_info=True,
                )
                continue
            if location is not None and not location.is_empty:
                return replace(location, provider=provider.name)
        return None
