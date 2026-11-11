import csv
import hashlib
import io
import socket
import stat
import struct
import tempfile
import time
import zipfile
import zlib
from contextlib import contextmanager
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .sources import CACHE_DIRECTORY, GTFSError, Source

MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 64
MAX_ROWS = 4_000_000
MAX_CSV_LINE_CHARS = 1024 * 1024
TIMEOUT_SECONDS = 30
DOWNLOAD_SECONDS = 180
REQUIRED_FILES = {"agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt"}


def check_directory(path: Path) -> None:
    # Bound central-directory metadata before ZipFile allocates ZipInfo objects.
    with path.open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - 65557))
        tail = stream.read(65557)
    position = tail.rfind(b"PK\x05\x06")
    if position < 0 or len(tail) - position < 22:
        raise GTFSError("Nieprawidłowy katalog ZIP.")
    _, disk, directory_disk, disk_count, count, directory_size, offset, comment_size = struct.unpack_from("<4s4H2LH", tail, position)
    if (disk or directory_disk or disk_count != count or count > MAX_MEMBERS or directory_size > 1024 * 1024
            or offset + directory_size > size or position + 22 + comment_size != len(tail)):
        raise GTFSError("ZIP64, ZIP wieloczęściowy lub zbyt duży katalog ZIP nie jest obsługiwany.")


def archive_manifest(path: Path) -> list[dict]:
    try:
        if path.stat().st_size > MAX_DOWNLOAD_BYTES:
            raise GTFSError("Archiwum przekracza limit 80 MiB.")
        check_directory(path)
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_MEMBERS or sum(item.file_size for item in entries) > MAX_EXPANDED_BYTES:
                raise GTFSError("ZIP przekracza limit liczby plików lub 512 MiB po rozpakowaniu.")
            names = set()
            manifest = []
            for item in entries:
                name = item.filename
                if (not name or PurePosixPath(name).name != name or "\\" in name or ":" in name or name in (".", "..")
                        or name in names or stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1):
                    raise GTFSError("ZIP zawiera niebezpieczną, powtórzoną lub zaszyfrowaną pozycję.")
                if (item.file_size > MAX_MEMBER_BYTES or item.file_size > max(1, item.compress_size) * 200
                        or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise GTFSError("Plik ZIP przekracza limity rozmiaru lub kompresji.")
                names.add(name)
                actual = 0
                # Read bounded chunks to verify CRC even for intentionally unused files.
                with archive.open(item) as stream:
                    while chunk := stream.read(65536):
                        actual += len(chunk)
                        if actual > MAX_MEMBER_BYTES:
                            raise GTFSError("Plik ZIP przekracza limit rozpakowania.")
                manifest.append({"name": name, "bytes": item.file_size, "archive_timestamp": list(item.date_time)})
            missing = REQUIRED_FILES - names
            if not names.intersection({"calendar.txt", "calendar_dates.txt"}):
                missing.add("calendar.txt lub calendar_dates.txt")
            if missing:
                raise GTFSError(f"Brakuje wymaganych plików GTFS lub kalendarza: {', '.join(sorted(missing))}.")
            return manifest
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError, zlib.error, EOFError, UnicodeError) as error:
        raise GTFSError(f"Nie można odczytać poprawnego ZIP: {error}") from error


def download_feed(source: Source, directory: Path = CACHE_DIRECTORY) -> tuple[Path, dict]:
    directory.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    temporary = None
    try:
        with urlopen(Request(source.feed_url, headers={"User-Agent": "PrzesiadkaPlus-GTFS/0.1"}), timeout=TIMEOUT_SECONDS) as response:
            if urlparse(response.geturl()).scheme != "https":
                raise GTFSError("Pobieranie GTFS wymaga HTTPS także po przekierowaniu.")
            length = response.headers.get("Content-Length")
            if length and (not length.isdigit() or int(length) > MAX_DOWNLOAD_BYTES):
                raise GTFSError("Serwer podał nieprawidłowy rozmiar lub archiwum większe niż 80 MiB.")
            with tempfile.NamedTemporaryFile(dir=directory, suffix=".part", delete=False) as output:
                temporary = Path(output.name)
                size = 0
                while chunk := response.read1(65536):
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES or time.monotonic() - started > DOWNLOAD_SECONDS:
                        raise GTFSError("Pobieranie przekroczyło limit 80 MiB lub 180 sekund.")
                    output.write(chunk)
            if length and size != int(length):
                raise GTFSError("Pobieranie niekompletne: rozmiar różni się od Content-Length.")
            provenance = {
                "import_method": "official_download", "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "final_url": response.geturl(), "last_modified": response.headers.get("Last-Modified"),
                "etag": response.headers.get("ETag"),
            }
        archive_manifest(temporary)
        target = directory / f"{source.operator}.zip"
        temporary.replace(target)
        return target, provenance
    except (HTTPError, URLError, socket.timeout, TimeoutError, OSError, HTTPException) as error:
        raise GTFSError(f"Nie udało się pobrać GTFS {source.operator} (timeout {TIMEOUT_SECONDS} s): {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def csv_rows(archive: zipfile.ZipFile, name: str, required_columns: set[str]):
    try:
        with archive.open(name) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
            def lines():
                while line := text.readline(MAX_CSV_LINE_CHARS + 1):
                    if len(line) > MAX_CSV_LINE_CHARS:
                        raise GTFSError(f"{name}: przekroczono limit długości wiersza CSV.")
                    yield line

            reader = csv.DictReader(lines(), strict=True)
            columns = reader.fieldnames or []
            if len(columns) > 128 or len(columns) != len(set(columns)) or not required_columns.issubset(columns):
                raise GTFSError(f"{name}: brak wymaganych kolumn lub powtórzone nagłówki.")

            def checked():
                for number, row in enumerate(reader, 2):
                    if number > MAX_ROWS + 1 or None in row or None in row.values():
                        raise GTFSError(f"{name}, wiersz {number}: limit wierszy lub niezgodna liczba kolumn.")
                    yield row

            yield checked()
    except (UnicodeError, csv.Error, zipfile.BadZipFile) as error:
        raise GTFSError(f"{name}: nieprawidłowy CSV UTF-8 lub uszkodzony ZIP: {error}") from error


def archive_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
