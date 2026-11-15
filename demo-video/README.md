# Przesiadka+ — film rekrutacyjny

Gotowy montaż: **2:45 · 1920×1080 · 30 FPS · H.264 / MP4**, bez muzyki i bez wygenerowanego głosu. Nagranie rzeczywistej aplikacji w Edge, uzupełnione autorskimi diagramami objaśniającymi istniejący kod.

- [Film z polskimi napisami](final/przesiadka-demo-subtitled.mp4)
- [Czysty master do późniejszego lektora](final/przesiadka-demo-clean.mp4)
- [Storyboard](storyboard.md)
- [Pełny tekst narracji](voiceover/voiceover-script.md)

Clean master zawiera tekst aplikacji, diagramy i atrybucje. Nie ma napisów narratora ani ścieżki audio. Napisy w drugim masterze są wypalone; niezależne SRT/VTT pozostają edytowalne.

## Co pokazuje film

Pierwsza klatka to aplikacja, bez intro. Ręczne wyszukiwanie Wrzeszcz → Przegalina na 13.11.2026, 17:00; SKM 17:02–17:09, Dworzec Główny 08, szacowane dojście 2 min, autobus 112 o 17:16, cel 18:21. Suwak pokazuje 0/4/5/6 minut symulowanego opóźnienia i zapas +5/+1/0/−1. Kursy pozostają te same.

Następnie film objaśnia planer i architekturę, pokazuje wyniki rzeczywistych testów i wraca do aplikacji. Diagramy pochodzą z implementacji, nie są makietami UI. Dane są archiwalne; wynik dotyczy czterech zatwierdzonych przejść przy Gdańsku Głównym. Brak realtime i pełnego routingu po Trójmieście.

## Pliki produkcji

| Katalog / plik | Zawartość |
|---|---|
| `source/recordings/` | 18-sekundowa próbka i 100-sekundowe oryginalne nagranie aplikacji |
| `source/graphics/` | 11 źródłowych SVG diagramów i wygenerowane PNG |
| `scripts/production.json` | Sceny, finalny tekst i parametry danych |
| `scripts/capture/capture.py` | Nagranie Edge, asercje API/UI i testy |
| `scripts/render/assets.py` | Diagramy, SSML, segmenty i napisy |
| `scripts/render/render.py` | Montaż i dwa mastery |
| `scripts/render/verify.py` | Parametry, pełne dekodowanie, ruch, spójność warstw |
| `qa/` | Lokalne raporty, logi i 28 kluczowych kadrów |
| `.production-work/` | Tymczasowe kopie demo, fonty, render i robocze klipy |

Nagranie używa istniejących helperów z `recording-script/record.py`; ten plik pozostał bez zmian. Poprzedni film `przesiadka-demo.mp4` zachowano. Poprzedni storyboard ma kopię w `source/previous/`.

Duże MP4, nagrania, PNG, QA i katalogi robocze są ignorowane przez Git. Skrypty, SVG, tekst, SRT/VTT i dokumentację można wersjonować oddzielnie. Nie wykonano commita ani pusha.

## Ponowne wygenerowanie — Windows PowerShell

Uruchamiaj z katalogu głównego repozytorium. Wymagane są już dostępne: Python z Playwright, przeglądarka Edge, uv, Node/npm, zsynchronizowane środowisko backendu i `frontend/node_modules`. Skrypt nie instaluje zależności ani przeglądarki.

Potrzebne lokalne pliki:

- `backend/data/demo/transit.db`, `walking.db`, `manifest.json` — istniejąca przygotowana paczka archiwalna; nie uruchamiaj ponownego pobierania GTFS ani ORS na potrzeby filmu;
- `demo-video/.work/tools/ffmpeg.exe` i `ffprobe.exe` z obsługą libx264, drawtext i libass;
- fonty Windows Bahnschrift i Segoe UI.

Binariów, fontów ani baz nie dołączono do skryptów. W tym środowisku wszystkie były już dostępne. Przeniesienie samych plików tekstowych na inny komputer nie dostarcza tych zasobów.

```powershell
$RecordingPython = Read-Host 'Pełna ścieżka do istniejącego python.exe z Playwright'
& $RecordingPython -B .\demo-video\scripts\produce.py
```

Runner usuwa `ORS_API_KEY` ze środowiska procesu przez nazwę, bez odczytu wartości. Wykonuje kolejno próbkę z testami, kontrolę próbki, główne nagranie, render i końcową weryfikację. Nie generuje TTS. Komponenty tego przebiegu wykonano rzeczywiście; zbiorczy runner dodano po wykonaniu produkcji i sprawdzono statycznie, bez ponownego nagrywania całej sekwencji.

Nagrywanie weryfikuje działające demo na portach 8000 i 5173. Zwykły backend na porcie 8000 powoduje przerwanie. Jeśli porty są wolne, uruchamia własne procesy na tymczasowej kopii paczki demo, a po nagraniu je zamyka. Nie zamyka wcześniej działających serwerów użytkownika. Nie zmienia zwykłych baz ani oryginalnej paczki.

Przed nadpisaniem istniejącego nagrania lub mastera powstaje kopia w lokalnym `archive/`. Przerwanie nagrania nie zastępuje poprzedniego mastera. Sam ponowny render, bez nowych testów i nagrania:

```powershell
& $RecordingPython -B .\demo-video\scripts\render\render.py
& $RecordingPython -B .\demo-video\scripts\render\verify.py
```

Wymaga wcześniejszych raportów `qa/tests.json`, `qa/main-capture.json` i `source/recordings/main.mp4`. Zmiana liczby testów w grafice wynika z odczytu raportu, nie z ręcznie wpisanej liczby w SVG.

## Warstwy przyszłego TTS

1. [Finalny tekst](voiceover/voiceover-script.md) — 260 słów, bez technicznych nagłówków.
2. [22 segmenty JSON](voiceover/voiceover-segments.json) — tekst, scena, slot czasowy, pauza i uwagi.
3. [SSML](voiceover/voiceover-ssml.xml) — poprawny XML; dialekt dostawcy wymaga sprawdzenia.
4. [Wymowa](voiceover/pronunciation-guide.md).
5. [SRT](subtitles/captions.srt) — 37 czytelnych cue.
6. [WebVTT](subtitles/captions.vtt).
7. [Mapa narracji](voiceover/narration-timeline.md).
8. [Instrukcja dodania głosu](voiceover/voiceover-integration.md).

Sloty czasowe nie są pomiarem audio. Po wygenerowaniu TTS trzeba zmierzyć rzeczywistą długość, odsłuchać i dopasować montaż; nie przyspieszać agresywnie narracji. Nie wybrano dostawcy i nie wysłano tekstu do usługi TTS.

## Sprawdzenie i ograniczenia

Zobacz lokalne [QA](qa/final-check.json), [testy](qa/tests.json), [ochronę baz](qa/databases.json) i [raport przeglądu](qa/review.md). Backend: 222 PASS; frontend: 25 PASS; Edge z syntetycznym API: 15 PASS. Nagranie korzystało z prawdziwego API lokalnego demo. Trzy przykłady sprawdzono także przez HTTP przed nagraniem.

Oba mastery: 4950 klatek, 165 s, H.264, 1920×1080, 30/1, bez audio; pełne dekodowanie i kontrola czarnych klatek. Potwierdzono ruch postaci i tła na kolejnych klatkach, zgodność napisów z narracją i oddzielenie napisów od clean mastera. Maksymalna szybkość napisów: 15,75 znaku/s. Obejrzano kluczowe kadry, nie deklarowano ręcznego obejrzenia całego filmu.

Nagranie CDP kodowano jako stałe 30 FPS: 129 z 3000 klatek źródłowych korzystało z powtórzonej ostatniej klatki (4,3%). Nie jest to deklaracja 30 unikalnych klatek każdej sekundy. Kontrolowane próbki trzech animacji i tła miały po 30 różnych klatek na sekundę. Brak testu wygenerowanego lektora, bo nie powstał.

Narrację, napisy i podpisy techniczne zredagowano według zainstalowanego skilla Humanizer 4.0.0, a nazwy, liczby i reguły porównano z aktualnym kodem. Zachowano atrybucje ZTM Gdańsk, PKP SKM Trójmiasto i © openrouteservice by HeiGIT / OpenStreetMap (CC BY-SA 4.0). Szczegóły pochodzenia danych: [demo](../docs/demo.md), [GTFS](../docs/gtfs.md), [walking](../docs/walking.md). Nie wykonano nowych zapytań ORS ani nie odczytano kluczy.
