from pathlib import Path


def validate_database_paths(transit: Path, walking: Path) -> None:
    if transit == walking or (transit.exists() and walking.exists() and transit.samefile(walking)):
        raise ValueError("Bazy GTFS i walking muszą mieć osobne pliki. Sprawdź konfigurację ścieżek.")
