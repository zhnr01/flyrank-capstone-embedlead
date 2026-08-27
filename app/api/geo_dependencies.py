from typing import Annotated

from fastapi import Depends

from app.core.config import settings
from app.core.geo import GeoProvider, GeoProviderChain
from app.services.geo_providers import IpapiCoProvider, IpApiProvider


def build_geo_chain() -> GeoProviderChain:
    if not settings.geo_enrichment_enabled:
        return GeoProviderChain([])
    providers: list[GeoProvider] = [
        IpApiProvider(timeout_seconds=settings.geo_provider_timeout_seconds),
        IpapiCoProvider(timeout_seconds=settings.geo_provider_timeout_seconds),
    ]
    return GeoProviderChain(providers)


_chain = build_geo_chain()


def get_geo_chain() -> GeoProviderChain:
    return _chain


GeoChainDep = Annotated[GeoProviderChain, Depends(get_geo_chain)]
