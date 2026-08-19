import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from .config import Settings, get_settings
from .reports import inside_city
from .schemas import AddressLookupRequest, AddressLookupResponse
from .security import rate_limiter


router = APIRouter(prefix="/api/v1/geocoding", tags=["geocodificación"])


@router.post("/address", response_model=AddressLookupResponse)
def lookup_address(
    payload: AddressLookupRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    rate_limiter.check(request, settings, scope="address-search", limit=settings.geocoding_rate_limit)
    params = {
        "q": f"{payload.address_reference}, La Rioja Capital, Argentina",
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "ar",
        "viewbox": "-66.98,-29.34,-66.76,-29.53",
        "bounded": 1,
    }
    try:
        with httpx.Client(
            timeout=6,
            headers={"User-Agent": "SIGARD-address-lookup/0.2 (academic public-health project)"},
        ) as client:
            response = client.get("https://nominatim.openstreetmap.org/search", params=params)
            response.raise_for_status()
            matches = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="El buscador de direcciones no está disponible") from None
    if not matches:
        raise HTTPException(status_code=404, detail="No encontramos esa referencia dentro de la Ciudad de La Rioja")
    latitude, longitude = float(matches[0]["lat"]), float(matches[0]["lon"])
    if not inside_city(latitude, longitude):
        raise HTTPException(status_code=404, detail="La referencia encontrada está fuera de la cobertura")
    return AddressLookupResponse(
        latitude=latitude,
        longitude=longitude,
        display_name=matches[0].get("display_name", payload.address_reference),
    )
