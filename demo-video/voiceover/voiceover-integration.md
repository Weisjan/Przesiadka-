# Dodanie głosu po zatwierdzeniu filmu

TTS nie został wygenerowany. Oba obecne MP4 nie mają ścieżki audio. Czysty master zawiera rzeczywisty tekst interfejsu, opisy diagramów i wymagane atrybucje; nie zawiera napisów narratora.

## 1. Generowanie i odsłuch

Użyj `voiceover-segments.json`, `voiceover-script.md` i `pronunciation-guide.md`. Generuj każdy z 22 segmentów oddzielnie, jednym polskim głosem, w spokojnym tempie. Preferuj bezstratny WAV 48 kHz. Nie przesyłaj kluczy ani lokalnych danych aplikacji. Dobór usługi TTS i jej licencji pozostaje do decyzji autora.

`voiceover-ssml.xml` jest poprawnym składniowo dokumentem SSML 1.0 z akapitami i pauzami 250 ms. Nie testowano go u dostawcy. Przed użyciem sprawdź obsługę danego dialektu; jeśli nie obsługuje SSML, użyj zwykłego tekstu. Cały plik SSML nie wymusza 165 sekund ani bezwzględnych pozycji segmentów.

## 2. Pomiar i synchronizacja

`start_time` i `end_time` to docelowe sekundy od początku filmu, a `pause_after_ms` to wskazówka, nie pomierzony czas audio. Zmierz rzeczywisty czas każdego WAV przez lokalny `ffprobe -show_entries format=duration`. Odsłuchaj wymowę przed montażem.

Umieść segment na jego docelowym początku. Krótsze nagranie uzupełnij ciszą do następnego segmentu. Jeśli nagranie jest dłuższe, skróć tekst albo przedłuż właściwe ujęcie i przesuń późniejsze cięcia. Pozostaw oddech przy zmianach stanu. Nie przyspieszaj agresywnie głosu i nie ucinaj końcówek do długości slotu.

Po zmianie montażu zaktualizuj `scripts/production.json`, segmenty, SRT/VTT i timeline. Podpis stanu musi następować po rzeczywistym wyniku w UI. Aktualny renderer ma montaż 165 s; większa zmiana długości wymaga również zmiany czasów cięć w `scripts/render/render.py` i oczekiwań `verify.py`.

Zatwierdzone segmenty połącz w `voiceover-mix.wav`, z ciszą w przerwach. Tego pliku obecnie nie ma. Nie używaj przykładowego lub pustego audio jako ukończonej narracji.

## 3. Głośność i eksport

Poniższe komendy są instrukcją przyszłego montażu, a nie deklaracją testu nieistniejącego audio. Uruchamiaj z katalogu głównego dopiero po utworzeniu i odsłuchaniu `voiceover-mix.wav`. Dla narracji internetowej przyjmij cel około −16 LUFS i true peak do −1,5 dBTP. Do końcowego masteringu wykonaj dwupassowe `loudnorm`: najpierw pomiar z `print_format=json`, potem drugi przebieg z pomierzonymi wartościami. Poniżej wariant roboczy jednopassowy:

```powershell
$FFmpeg = '.\demo-video\.work\tools\ffmpeg.exe'
& $FFmpeg -n -i '.\demo-video\voiceover\voiceover-mix.wav' -af 'loudnorm=I=-16:TP=-1.5:LRA=11,apad,atrim=duration=165' -ar 48000 -c:a pcm_s24le '.\demo-video\voiceover\voiceover-normalized.wav'
& $FFmpeg -n -i '.\demo-video\final\przesiadka-demo-clean.mp4' -i '.\demo-video\voiceover\voiceover-normalized.wav' -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 192k -t 165 -movflags +faststart '.\demo-video\final\przesiadka-demo-voiceover.mp4'
```

`atrim` wolno zastosować dopiero po sprawdzeniu, że żadne słowo nie wykracza poza 165 s. Jeśli montaż wydłużono, zmień także obie wartości długości. `-n` chroni przed przypadkowym nadpisaniem eksportu. Oryginalny clean master pozostaje osobno.

Aby do nowego MP4 dodać przełączalne napisy, użyj zaktualizowanego SRT jako drugiego wejścia, mapuj istniejące ścieżki i napisy, ustaw `-c copy -c:s mov_text` oraz język napisów `pol`. Do wersji z wypalonymi napisami wyrenderuj osobny master; zachowaj clean i źródłowe SRT/VTT.

## 4. Muzyka i kontrola końcowa

Domyślnie pozostaw film bez muzyki. Jeśli później użyjesz utworu z odpowiednią licencją, zachowaj dowód licencji i atrybucję. Ścisz muzykę pod narracją; sidechaincompress w FFmpeg jest opcją techniczną, nie gotową konfiguracją dla każdego materiału. Ustawienia dobierz po odsłuchu i pomiarze miksu, a nie na podstawie samego limitera. Obecna produkcja nie zawiera muzyki ani duckingu.

Sprawdź eksport przez ffprobe, zdekoduj cały plik, odsłuchaj całość i obejrzyj zmiany 0/4/5/6 minut. Zweryfikuj wymowę, synchronizację napisów, pauzy, brak przesterów i zgodność z realnym API. Nie oznaczaj nagrania jako danych realtime.
