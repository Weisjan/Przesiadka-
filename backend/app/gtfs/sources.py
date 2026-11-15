import os
from dataclasses import asdict, dataclass
from pathlib import Path


CACHE_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "gtfs"
DEFAULT_DATABASE = CACHE_DIRECTORY / "transit.db"


def configured_path() -> Path:
    return Path(os.environ.get("PRZESIADKA_TRANSIT_PATH", str(DEFAULT_DATABASE))).resolve()


@dataclass(frozen=True)
class Source:
    operator: str
    name: str
    feed_url: str
    documentation_url: str
    terms_url: str
    attribution: str
    license: str

    def metadata(self) -> dict:
        return asdict(self)


SOURCES = {
    "ztm": Source(
        "ztm", "Zarząd Transportu Miejskiego w Gdańsku",
        "https://ckan.multimediagdansk.pl/dataset/c24aa637-3619-4dc2-a171-a23eec8f2172/resource/30e783e4-2bec-4a7d-bb22-ee3e3b26ca96/download/gtfsgoogle.zip",
        "https://ckan.multimediagdansk.pl/pl/dataset/tristar",
        "https://ckan.multimediagdansk.pl/dataset/c24aa637-3619-4dc2-a171-a23eec8f2172/resource/09cafa1b-604b-4408-ac48-5720319b72b7/download/regulamin-korzystania-z-danych.pdf",
        "Źródło: Zarząd Transportu Miejskiego w Gdańsku, Otwarte dane ZTM w Gdańsku. Dane rozkładowe, nie realtime.",
        "CKAN: Creative Commons Attribution (wersja nieokreślona); regulamin ponownego wykorzystywania dostawcy.",
    ),
    "skm": Source(
        "skm", "PKP Szybka Kolej Miejska w Trójmieście Sp. z o.o.",
        "https://www.skm.pkp.pl/gtfs-mi-kpd.zip",
        "https://bip.skm.pkp.pl/c60/rozklad-jazdy",
        "https://bip.skm.pkp.pl/otwarte-dane",
        "Źródło: PKP Szybka Kolej Miejska w Trójmieście Sp. z o.o., repozytorium Otwarte dane PKP SKM. Dane rozkładowe, nie realtime.",
        "Ponowne wykorzystywanie informacji sektora publicznego na warunkach regulaminu dostawcy.",
    ),
}


class GTFSError(ValueError):
    """A rejected feed, failed download or unavailable local transit database."""


def source_for(operator: str) -> Source:
    try:
        return SOURCES[operator]
    except KeyError as error:
        raise GTFSError("Nieznany operator. Wybierz ztm lub skm.") from error


def namespaced(operator: str, value: str) -> str:
    if not value or len(value) > 256:
        raise GTFSError("Identyfikator GTFS musi mieć od 1 do 256 znaków.")
    return f"{operator}:{value}"
