# Nagrywanie lokalnego demo

Uruchamiaj z katalogu głównego repozytorium. Skrypt nie instaluje narzędzi ani zależności i nie zmienia aplikacji.

## Wymagania

- Przygotowany, kompletny `backend/data/demo/`, zgodnie z [docs/demo.md](../../docs/demo.md).
- Istniejące zależności backendu i frontendu, uv oraz Node.js w PATH.
- Microsoft Edge i interpreter Python z już dostępnym pakietem Playwright.
- FFmpeg z `libx264` oraz ffprobe: w PATH, w `demo-video/.work/tools/` albo przekazane flagami `--ffmpeg` / `--ffprobe`.
- Windows z Bahnschrift (fallback: Segoe UI), wolne miejsce na surowe ujęcie i film.

W tej sesji użyto istniejącego Playwright z cache uv oraz przenośnego FFmpeg 9.0.2 z oficjalnie wskazanego [Gyan](https://www.gyan.dev/ffmpeg/builds/), po sprawdzeniu SHA-256 dostawcy. Narzędzia pozostają lokalnie w ignorowanym `.work/tools/`, bez zmiany PATH. Nie są dołączane do repozytorium.

## PowerShell

Wskaż interpreter z istniejącym Playwright (to nie musi być interpreter backendu):

```powershell
$RecordingPython = Read-Host 'Pełna ścieżka do python.exe z Playwright'
& $RecordingPython .\demo-video\recording-script\record.py --preview
& $RecordingPython .\demo-video\recording-script\record.py
```

Zewnętrzne narzędzia, gdy nie ma ich w PATH ani `.work/tools/`:

```powershell
& $RecordingPython .\demo-video\recording-script\record.py --ffmpeg 'C:\tools\ffmpeg.exe' --ffprobe 'C:\tools\ffprobe.exe'
```

Pierwsze polecenie sprawdza trzy przykłady i nagrywa trzysekundową próbę. Drugie nagrywa całość i montuje `demo-video/przesiadka-demo.mp4`. Ponowne uruchomienie zastępuje poprzedni wygenerowany film dopiero po kontroli nowego pliku. Aby ponowić sam montaż bez nagrywania:

```powershell
& $RecordingPython .\demo-video\recording-script\record.py --edit-only
```

Nie wykonuj `--preview` między pełnym nagraniem a `--edit-only`, ponieważ próba zastępuje surowe `.work/capture.mp4`.

## Serwery i bezpieczeństwo

Skrypt korzysta z działających usług na `127.0.0.1:8000` i `127.0.0.1:5173`. Backend musi jawnie udostępniać tryb archiwalnego demo; zwykły backend zostanie odrzucony. Jeżeli usług nie ma, skrypt uruchamia je sam, backend na tymczasowej kopii pakietu demo. Zamyka tylko uruchomione przez siebie procesy. Niczego nie pobiera i nie wywołuje OpenRouteService. Wartość ORS_API_KEY nie jest odczytywana ani logowana.

Przed i po pracy porównuje SHA-256, rozmiar i mtime trzech baz użytkownika i pakietu demo. UI/API są sprawdzane przed nagrywaniem; każdy wymagany wynik jest ponownie potwierdzany w ujęciu. Stare wyniki nie są podstawiane. Rozbieżność przerywa generowanie. Nagranie wykorzystuje prawdziwe klatki Edge przez CDP; sampler CFR zapisuje 30 klatek/s, a licznik duplikatów i liczba klatek źródłowych są jawne w `capture-stats.json`.

## Kontrola wyniku

- `verification/ffprobe.json`: H.264, 1920×1080, 30/1 FPS, 100 s, brak audio.
- `verification/api-checks.json`: wejścia i rzeczywiste odpowiedzi trzech przykładów.
- `verification/recording-checks.json`: wyniki interakcji, wersja Edge i błędy strony.
- `verification/database-check.json`: niezmienność baz.
- PNG: intro, planowanie, zielony, czerwony, zero, szary, oba pozostałe przykłady i outro.

Pełny przebieg wywołuje również `verify_movie.py`: dekoduje wszystkie 3000 klatek, szuka nieoczekiwanych czarnych odcinków i porównuje rzeczywisty ruch trzech wariantów postaci. Raport: `verification/movie-check.json`. Po wygenerowaniu obejrzyj też kluczowe klatki i podpisy. Sam poprawny kontener nie potwierdza poprawności treści. Nie dodawaj MP4, narzędzi ani danych roboczych do Git. Nie wykonuj commita automatycznie.
