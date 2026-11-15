# Demo rekrutacyjne Przesiadka+

Przesiadka+ pomaga sprawdzić zaplanowaną podróż SKM → dojście → ZTM i zobaczyć, jak symulowane opóźnienie wpływa na możliwość przesiadki.

To działające lokalnie MVP, nie pełny planer Trójmiasta ani źródło informacji live. Interfejs Kinetic Transit wykorzystuje oryginalne SVG/SMIL, a obliczenia wykonuje backend.

## Technologie i zakres

Python 3.13, FastAPI, Pydantic, SQLite i uv; React, TypeScript, Vite i CSS Modules. Importowane GTFS zawierają rzeczywiste kursy SKM/ZTM. Dojście pochodzi wyłącznie z zapisanych szacunków OpenRouteService. Nie ma kont, kluczy w przeglądarce ani żądań ORS podczas prezentacji.

Użytkownik podaje skąd, kiedy i dokąd. Backend porównuje dalsze postoje konkretnych kursów SKM i zatwierdzone przejścia do ZTM, sprawdza dojazd do celu oraz proponuje do trzech wariantów. Ranking preferuje zapas co najmniej 2 min, następnie dotarcie do celu, czas podróży, oczekiwanie i stabilne ID. Suwak zachowuje wybrane kursy; nie wyszukuje automatycznie innego odjazdu.

## Uruchomienie

Wymagane: Python 3.13, uv, Node.js 24/npm i zainstalowane zależności projektu. Pierwszą instalację opisuje [README](../README.md). Poniższe komendy PowerShell wykonuj z katalogu głównego repozytorium.

Przygotuj zestaw **raz, przed prezentacją**, z posiadanych oficjalnych importów zawierających 13.11.2026 i czterech zapisanych pomiarów ORS:

```powershell
uv run --no-sync --directory backend python -m app.demo prepare
```

Komenda odczytuje lokalne źródła; niczego nie pobiera. Tworzy osobny, ignorowany przez Git `backend/data/demo/`: `transit.db`, `walking.db`, `manifest.json`. Aktualny zestaw ma około 2,9 MB. Gdy katalog już istnieje, komenda odmawia nadpisania. Nie przygotowuj go ponownie przed każdą prezentacją.

Uruchom backend demo w pierwszym terminalu:

```powershell
uv run --no-sync --directory backend python -m app.demo serve
```

Uruchom frontend w drugim terminalu:

```powershell
npm.cmd run dev --prefix frontend
```

Otwórz <http://127.0.0.1:5173>. API działa pod <http://127.0.0.1:8000>; `/api/health` zwraca stan serwera. Przed uruchomieniem zatrzymaj poprzedni backend na porcie 8000. Zatrzymanie: Ctrl+C w obu terminalach.

Na ekranie musi być widoczny komunikat **„Archiwalne demo · 13 listopada 2026 · to nie jest aktualny rozkład”**. Jeśli go nie ma, uruchomiono zwykły backend, a nie tryb demo. Kliknij „Zobacz przykład” i wybierz podróż. Ten jeden wybór uzupełnia formularz i wywołuje normalny endpoint planera.

Nie wskazuj wycinka zmiennymi ścieżek zwykłego backendu: aplikacja odmawia uruchomienia archiwalnego wycinka bez jawnego trybu `app.demo serve`.

Parametry lokalnego przygotowania, gdy importy są w innym miejscu:

```powershell
uv run --no-sync --directory backend python -m app.demo prepare --transit .\data\gtfs\transit.db --walking .\data\walking.db --output .\data\demo-kopia
uv run --no-sync --directory backend python -m app.demo serve --directory .\data\demo-kopia
```

Ścieżki względne w tych dwóch komendach są liczone od `backend`, ponieważ uv otrzymuje `--directory backend`. Własny katalog wyjściowy również zachowaj poza Git. Serwer przyjmuje `--port`, ale frontend domyślnie łączy się z 8000.

## Przypadki i oczekiwane wyniki

Wszystkie przykłady: **13.11.2026, wyjazd nie wcześniej niż 17:00**, SKM `skm:284819`, Wrzeszcz 17:02 → Gdańsk Główny 17:09. To dane archiwalne, nie rekomendacja podróży na inną datę.

| Przykład | Dokładny słupek wejścia ZTM | Kurs ZTM / dotarcie | ORS / minuty użyte | Zapas przy 0 min |
|---|---|---|---|---:|
| Wrzeszcz → Strzyża PKM | Dworzec Główny 01, `ztm:2001` | 6 kier. Jelitkowo, 17:15 → Strzyża PKM 01, 17:36 | 153,7 s / 3 min | +3 min |
| Wrzeszcz → Lawendowe Wzgórze | Dworzec PKS 02, `ztm:2136` | 11 kier. Lawendowe Wzgórze, 17:13 → Lawendowe Wzgórze 01, 17:37 | 102,4 s / 2 min | +2 min |
| Wrzeszcz → Przegalina | Dworzec Główny 08, `ztm:1021` | 112 kier. Przegalina, 17:16 → Przegalina 02, 18:21 | 82,2 s / 2 min | +5 min |

| Przykład | Zielona postać | Czerwona postać | Dokładnie 0 zapasu | Szara postać |
|---|---|---|---|---|
| Strzyża | opóźnienie 0–1 min | 2–3 min | +3 min opóźnienia | od +4 min |
| Lawendowe | 0 min | 1–2 min | +2 min opóźnienia | od +3 min |
| Przegalina | 0–3 min | 4–5 min | +5 min opóźnienia | od +6 min |

Kolory postaci korzystają z dokładnego zapasu zwróconego przez API: ≥2 min zielony, 0–<2 czerwony, <0 szary. Słowny status silnika jest dodatni/zero/ujemny; próg 2 min jest pasmem prezentacji ryzyka. Sekundy ORS są zaokrąglane w górę, a oryginalne wartości pozostają w bazie.

Identyfikatory kursów ZTM do sprawdzenia w danych:

- 6: `ztm:6202611131653_21_006-08`, cel `ztm:2033`;
- 11: `ztm:11202611131653_11_011-27`, cel `ztm:14825`;
- 112: `ztm:112202611131713_201_112-02`, cel `ztm:14926`.

Te oczekiwane wyniki są dokumentacją sprawdzonego zestawu. Frontend ani manifest nie przechowują odpowiedzi analizy; wszystkie są obliczane przez backend. Po zmianie źródeł lub kodu ponownie sprawdź tabelę zamiast zakładać niezmienność wyniku.

## Prezentacja w 4 minuty

1. **0:00–0:30 — problem i granice.** „Porównuję jedną podróż SKM → ZTM na rozkładach archiwalnych. Dojście jest szacunkowe. To nie jest realtime ani pełny routing miasta”.
2. **0:30–1:30 — Strzyża.** Kliknij „Zobacz przykład” → Strzyża PKM. Pokaż SKM 17:02, wybrane miejsce przesiadki, dojście 3 min, tramwaj 17:15 i cel 17:36. Ustaw kolejno +2, +3, +4 min: zapas +1, 0, −1; postać biegnie, następnie stoi. Powiedz, że API ocenia stałe kursy.
3. **1:30–2:20 — alternatywy.** Zostaw +4 min, otwórz „Inne podróże” i wybierz tramwaj 9 o 17:17. Suwak nadal pokazuje +4, a nowy zapas wynosi +1. Przywróć +0, aby wrócić do oceny bez opóźnienia.
4. **2:20–3:10 — inne miejsce przesiadki.** Wybierz Lawendowe Wzgórze. System sam wskazuje Dworzec PKS 02 i tramwaj 11. Ustaw +1/+2/+3: zapas +1/0/−1. Opcjonalnie pokaż Przegalinę: inny słupek, autobus i +5 min zapasu.
5. **3:10–4:00 — jakość i kod.** Na telefonie pokaż duży wynik i suwak oraz „Zmień podróż”. W „Dlaczego ta podróż?” wskaż ranking i ograniczenie zasięgu. Wyjaśnij czystą funkcję obliczeń, UTC/DST, ochronę przed starymi odpowiedziami, izolowane testy i brak wywołań ORS w czasie prezentacji.

Jeśli komisja pyta o brak połączenia: zmień cel na Port Lotniczy i wyszukaj w tym wycinku. Komunikat oznacza brak wyniku w obsługiwanym zakresie, nie brak dowolnej trasy w mieście. Wróć do działającego przykładu jednym kliknięciem. Nie wywołuj awarii API podczas głównej prezentacji; obsługę błędów pokrywają testy.

## Dlaczego dane nie wygaszą prezentacji

Przygotowanie kopiuje oryginalne SQLite do nowego katalogu, zachowuje wszystkie postoje wybranych kursów oraz ich routes/services/calendars, a usuwa niepotrzebne kursy wyłącznie z kopii. Wycinek obejmuje pociągi dla wszystkich stacji SKM i cztery zatwierdzone słupki ZTM między 16:00 a północą. Wyjazdy demo są ograniczone do 16:00–18:00, aby ich pełne sześciogodzinne okna mieściły się w danych. Można zmieniać początek, cel, godzinę i alternatywy wewnątrz tego zakresu.

Manifest zawiera wejścia przykładów, SHA-256 plików, oryginalne pochodzenie obu feedów i zapisane pomiary ORS z calculated_at/expires_at. Serwer sprawdza integralność plików przy uruchomieniu. Nie podmienia dat rozkładu, identyfikatorów, metryk ani terminów cache.

Tylko w wyraźnie oznaczonym trybie demo aktualność cache jest oceniana według utrwalonego `walking_reference_at`, kiedy wszystkie zachowane pomiary były poprawne. To odtworzenie stanu archiwalnego, nie przedłużenie ich rzeczywistej ważności. Zwykły backend nadal używa aktualnego czasu i odrzuca wygasły cache. Test obejmuje zegar w 2035 roku. Starsze endpointy list całego dnia/sugestii wybranego pociągu są wyłączone w wycinku, aby nie udawać pełnego rozkładu.

Zachowaj cały `backend/data/demo/` razem z wersją aplikacji używaną do prezentacji. Jest ignorowany przez Git; sam klon repozytorium go nie zawiera. Aktualne publiczne feedy mogą w przyszłości nie udostępniać historycznego 13.11.2026, więc ponowne pobranie nie zastępuje zachowania zestawu. Brak lub uszkodzenie pliku daje błąd startu, nie fikcyjne wyniki. Nie edytuj plików zestawu ręcznie.

## Pochodzenie i warunki danych

Sprawdzono 14.11.2026:

- GTFS ZTM: [oficjalny zbiór](https://ckan.multimediagdansk.pl/pl/dataset/tristar), [regulamin](https://ckan.multimediagdansk.pl/dataset/c24aa637-3619-4dc2-a171-a23eec8f2172/resource/09cafa1b-604b-4408-ac48-5720319b72b7/download/regulamin-korzystania-z-danych.pdf). Źródło: Zarząd Transportu Miejskiego w Gdańsku. CKAN oznacza CC Attribution bez numeru wersji; stosujemy również warunki dostawcy.
- GTFS SKM: [oficjalny BIP i zasady ponownego wykorzystania](https://bip.skm.pkp.pl/otwarte-dane). Źródło: PKP Szybka Kolej Miejska w Trójmieście Sp. z o.o.
- ORS: [aktualne warunki HeiGIT](https://account.heigit.org/info/tos), odczytane również w przeglądarce. Wyniki są CC BY-SA 4.0; zachowano kredyt „© openrouteservice by HeiGIT | Data from OpenStreetMap”, [link licencji](https://creativecommons.org/licenses/by-sa/4.0/) i informację o zaokrągleniu.

Regulaminy GTFS wymagają podania źródła oraz dat wytworzenia i pozyskania. Import zachowuje dostępne daty pozyskania/modyfikacji, ale **data wytworzenia nie została potwierdzona**. Nie zastępuj jej datą ZIP ani datą przygotowania demo. Dlatego nie dodajemy rzeczywistych rekordów i pomiarów do Git ani nie oferujemy publicznego pakietu. Dostarczamy lokalny proces odtworzenia z oficjalnych importów. Przed publiczną redystrybucją archiwum trzeba uzupełnić wymagane pochodzenie i sprawdzić warunki. Zachowano atrybucje i licencję ORS; nie przenosimy automatycznie jej licencji na kod aplikacji.

## Ograniczenia i dalsze kroki

Tylko jedna przesiadka i cztery zatwierdzone pary przy Gdańsku Głównym. Trasa przez ten węzeł może być objazdem względem nieobsługiwanej alternatywy. Zapas nie gwarantuje zdążenia: feed SKM nie podaje peronu, a czas ORS nie jest pomiarem terenowym ani potwierdzeniem dostępności. Dane są statyczne. Tryb archiwalny nie służy do planowania dzisiejszej podróży.

Dalsze rozszerzenia: terenowa walidacja dojścia, jawne zatwierdzenie kolejnego węzła, lepsze podpowiedzi nazw oraz badanie z pasażerem. Wymagają osobnych etapów; demo nie rozszerza rejestru i nie wykonuje masowych importów.

## Recruitment film

The current 2:45 production, narrated export, subtitles and reproduction commands are documented in [demo-video/README.md](../demo-video/README.md). The earlier 3:55 draft is superseded by the current [storyboard](../demo-video/storyboard.md) and [final narration](../demo-video/voiceover/voiceover-script.md).

Przegalina is the main film example because it clearly demonstrates all margin states. Routing through Gdańsk Główny can be a detour for other destinations: inspected archival GTFS included a direct tram 6 from Galeria Bałtycka 01 at 17:11 to Strzyża PKM 01 at 17:16, outside this planner's approved links. This comparison does not validate walking access or establish a globally optimal route. The film must retain its limited-coverage notice and GTFS/ORS attribution. Local data archives must not be redistributed without resolving the production-date and provider-terms requirements above.
