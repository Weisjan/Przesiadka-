# Synchronizacja istniejących nagrań TTSMaker

Wejście: pięć oryginalnych `generated/scene-01.wav`–`scene-05.wav`, nie MP3. PCM 16-bit, mono, 24 kHz. Piąte nagranie zostało poprawione przez autora po wykryciu duplikatu. Nie generowano ponownie głosu i nie wysyłano plików do zewnętrznej usługi.

## Wynik

- `../final/przesiadka-demo-ai-voice.mp4`: nowy eksport H.264, 1920×1080, 30 FPS, polskie AAC i wypalone napisy.
- `generated/final-voiceover.wav`: osobny miks PCM 24-bit, 48 kHz, mono.
- `../subtitles/captions-ai.srt`, `.vtt`, `.ass`: nowa wersja napisów; poprzednich napisów ani filmów nie nadpisano.
- `../qa/voiceover-sync.json`: parametry, pomiary głośności, szczegółowa mapa wszystkich zdań i kontrola oryginałów.

Film nadal trwa 165 sekund. Bez zmiany tempa głosu, długości scen i treści narracji. Nie zmieniono backendu ani frontendu. Nie wykonywano zapytań ORS ani importów GTFS.

## Metoda i granice weryfikacji

Kolejność scen pochodzi z nazw plików 01–05. W każdej scenie wykryto pauzy dłuższe niż 0,7 s poniżej −40 dB. Liczby oddzielonych wypowiedzi wynoszą 8/7/8/9/5 i zgadzają się z 37 zdaniami narracji. To potwierdzenie struktury, nie automatyczna transkrypcja. Nie ma lokalnie polskiego ASR; treść i wymowa NIE zostały semantycznie potwierdzone odsłuchem przez agenta.

Każda wypowiedź zachowuje 80 ms przed początkiem po pauzie i 120 ms po wykrytym końcu mowy. Cięcia są w ciszy; zachowano także krótkie pauzy wewnętrzne. Zastosowano 15/25 ms łagodne wygaszenia przy cięciach, korektę poziomu scen z ograniczeniem true peak i dwupassową normalizację miksu do około −16 LUFS. Bez przyspieszania, odszumiania i agresywnej kompresji. Dłuższe pauzy umieszczono według rzeczywistych ujęć i wyników API.

Nie zastąpiono pierwotnego JSON slotów pliku bez głosu; rzeczywiste pozycje audio są w raporcie `voiceover-sync.json`, a napisy w osobnych `captions-ai.*`. Tekst napisów pozostaje identyczny, więc nie wykonywano redakcji Humanizer.

## Odsłuch przed wysyłką

Obejrzyj i odsłuchaj cały film. Szczególnie sprawdź:

- 0:00–0:40: Wrzeszcz, Przegalina, data, godziny 17:02/17:09/17:16/18:21 i nazwy miejsc;
- 0:40–1:10: poprawność zdań o opóźnieniu 4/5/6 min oraz ich zgodność ze stanem postaci;
- 1:10–1:45: planer, kolejność postojów i ranking;
- 1:45–2:20: wymowa React, TypeScript, FastAPI, REST API, GTFS, SQLite i OpenRouteService;
- 2:20–2:45: właściwa, odrębna narracja finału, brak ucięcia ostatniego słowa.

Do obejrzenia: tak, po zaliczeniu technicznego raportu QA. Do wysłania komisji: po powyższym odsłuchu, którego kontrola parametrów i pauz nie zastępuje.

## Odtworzenie

Z katalogu głównego: `& .\backend\.venv\Scripts\python.exe -B .\demo-video\scripts\render\voiceover.py`.

Skrypt korzysta wyłącznie z biblioteki standardowej i już lokalnie dostępnych FFmpeg/ffprobe. Odmawia zastąpienia istniejącego `final-voiceover.wav` lub MP4 z lektorem. Przed kolejnym eksportem zachowaj je samodzielnie w innym lokalnym katalogu. Nagrania wejściowe i wcześniejsze mastery są chronione porównaniem SHA-256, rozmiaru i mtime. Skrypt nie usuwa ich ani nie zastępuje.
