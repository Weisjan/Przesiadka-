import json
import math
import os
import socket
import ssl
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ENDPOINT = "https://api.heigit.org/openrouteservice/v2/directions/foot-walking/json"
PROFILE = "foot-walking"
ATTRIBUTION = "© openrouteservice by HeiGIT | Data from OpenStreetMap"
TERMS_URL = "https://account.heigit.org/info/tos"
LICENSE = "CC-BY-SA-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
TERMS_CHECKED_ON = "2026-11-12"
TIMEOUT_SECONDS = 10
MAX_RESPONSE_BYTES = 65536
TRANSIENT_STATUS = {408, 500, 502, 503, 504}


class WalkingError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise WalkingError("redirect", "ORS przekierował żądanie. Nie przekazano klucza do innego adresu.")


open_request = build_opener(NoRedirect()).open


def coordinates(longitude, latitude) -> tuple[float, float]:
    if (any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in (longitude, latitude)) or not -180 <= longitude <= 180 or not -90 <= latitude <= 90):
        raise WalkingError("invalid_coordinates", "Przystanek ma brakujące lub nieprawidłowe współrzędne.")
    return float(longitude), float(latitude)


def read_json(data: bytes):
    if len(data) > MAX_RESPONSE_BYTES:
        raise WalkingError("invalid_response", "Odpowiedź ORS przekracza limit 64 KiB.")
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        raise WalkingError("invalid_response", "ORS zwrócił nieprawidłowy JSON.") from None


def no_route(value) -> bool:
    return isinstance(value, dict) and isinstance(value.get("error"), dict) and value["error"].get("code") in (2009, 2010)


def parse_response(value) -> dict:
    if no_route(value) or (isinstance(value, dict) and "error" not in value and value.get("routes") == []):
        return {"status": "no_route", "distance_m": None, "walking_seconds": None}
    if not isinstance(value, dict) or not isinstance(value.get("routes"), list) or len(value["routes"]) != 1:
        raise WalkingError("invalid_response", "ORS nie zwrócił jednej jednoznacznej trasy.")
    route = value["routes"][0]
    summary = route.get("summary") if isinstance(route, dict) else None
    if not isinstance(summary, dict):
        raise WalkingError("invalid_response", "Brak podsumowania odległości i czasu w odpowiedzi ORS.")
    distance, duration = summary.get("distance"), summary.get("duration")
    if (any(isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number <= 0
            for number in (distance, duration)) or distance > 20000 or duration > 180 * 60):
        raise WalkingError("invalid_response", "ORS zwrócił nieprawidłowy wynik lub trasę poza zakresem lokalnej przesiadki (20 km / 180 min).")
    return {"status": "available", "distance_m": float(distance), "walking_seconds": float(duration)}


def fetch_walking(start: tuple[float, float], end: tuple[float, float], max_requests: int = 2, *, before_request=None) -> dict:
    start, end = coordinates(*start), coordinates(*end)
    if isinstance(max_requests, bool) or not isinstance(max_requests, int) or not 1 <= max_requests <= 3:
        raise WalkingError("request_limit", "Limit żądań musi wynosić od 1 do 3, łącznie z ponowieniami.")
    api_key = os.environ.get("ORS_API_KEY", "").strip()
    if not api_key:
        raise WalkingError("missing_key", "Brak ORS_API_KEY w środowisku procesu. Ustaw klucz lokalnie przed jawnym importem; nie wklejaj go do rozmowy.")
    # Keys are opaque, including JWT-style keys; enforce header safety, not an undocumented length/shape.
    if any(not 33 <= ord(character) <= 126 for character in api_key):
        raise WalkingError("invalid_key", "ORS_API_KEY zawiera spacje, znaki sterujące lub znaki spoza ASCII niedozwolone w kluczu nagłówka HTTP. Wartość klucza nie jest wyświetlana.")
    body = json.dumps({"coordinates": [start, end], "geometry": False, "instructions": False, "units": "m"}).encode()
    request = Request(ENDPOINT, data=body, headers={"Authorization": api_key, "Content-Type": "application/json",
                                                "Accept": "application/json", "User-Agent": "PrzesiadkaPlus-Walking/0.1"})
    for attempt in range(max_requests):
        retry = False
        if before_request is not None:
            before_request()
        try:
            with open_request(request, timeout=TIMEOUT_SECONDS) as response:
                return parse_response(read_json(response.read(MAX_RESPONSE_BYTES + 1)))
        except HTTPError as error:
            with error:
                status = error.code
                if status in (400, 404):
                    value = read_json(error.read(MAX_RESPONSE_BYTES + 1))
                    if no_route(value):
                        return {"status": "no_route", "distance_m": None, "walking_seconds": None}
                retry = status in TRANSIENT_STATUS
                if status == 401:
                    failure = WalkingError("unauthorized", "ORS: HTTP 401. Sprawdź ORS_API_KEY w środowisku procesu.")
                elif status == 403:
                    failure = WalkingError("forbidden", "ORS: HTTP 403. Brak uprawnień do profilu lub wyczerpany limit dzienny; sprawdź panel HeiGIT.")
                elif status == 429:
                    failure = WalkingError("rate_limited", "ORS: HTTP 429. Przekroczono limit żądań; odczekaj zgodnie z panelem HeiGIT / Retry-After. Nie ponowiono automatycznie.")
                else:
                    failure = WalkingError("http_error", f"ORS: HTTP {status}. Nie zapisano nowego wyniku; poprzedni zapis pozostaje bez zmian.")
                if retry and error.headers and error.headers.get("Retry-After") is not None:
                    retry = False
                    failure = WalkingError("retry_after", f"ORS: HTTP {status}. Serwer wymaga odczekania (Retry-After); nie ponowiono żądania przedwcześnie.")
        except (socket.timeout, TimeoutError):
            retry = True
            failure = WalkingError("timeout", "Przekroczono limit czasu połączenia z ORS. Nie zapisano nowego wyniku.")
        except (URLError, OSError, HTTPException) as error:
            retry = not isinstance(error, ssl.SSLError) and not isinstance(getattr(error, "reason", None), ssl.SSLError)
            failure = WalkingError("network", "Nie udało się połączyć z ORS. Sprawdź sieć i spróbuj później.")
        if not retry or attempt + 1 == max_requests:
            raise failure from None
        time.sleep(attempt + 1)
    raise AssertionError("Unreachable request budget")
