import httpx

from app.core.geo import GeoLocation


class IpApiProvider:
    name = "ip-api"

    def __init__(self, timeout_seconds: float) -> None:
        self._timeout = timeout_seconds

    def lookup(self, ip_address: str) -> GeoLocation | None:
        response = httpx.get(
            f"http://ip-api.com/json/{ip_address}",
            params={"fields": "status,countryCode,city"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "success":
            return None
        return GeoLocation(
            country=payload.get("countryCode"),
            city=payload.get("city"),
        )


class IpapiCoProvider:
    name = "ipapi-co"

    def __init__(self, timeout_seconds: float) -> None:
        self._timeout = timeout_seconds

    def lookup(self, ip_address: str) -> GeoLocation | None:
        response = httpx.get(
            f"https://ipapi.co/{ip_address}/json/",
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            return None
        return GeoLocation(
            country=payload.get("country_code"),
            city=payload.get("city"),
        )
