# Notatki do nagrania i końcowy przegląd

## Ocena poprzedniej wersji

Zachowano siedem części, otwarcie od opóźnionego pociągu, pierwszą osobę, prawdziwe demo oraz suwak z oryginalnymi postaciami. Poprawki dotyczą wyboru podróży, przejścia do własnego algorytmu, uzasadnienia podziału aplikacji i krótszego zakończenia.

- [P2] Ryzyko mylącej głównej historii: stan wejściowy `docs/video/narration.md:11`. Strzyża przez Główny jest wynikiem ograniczonego rejestru, lecz lokalny GTFS zawiera dużo prostszy odcinek bezpośredni z okolicy Wrzeszcza. Komisja mogłaby oceniać pozorny objazd zamiast implementacji. Wybrano Przegalinę po opisanym niżej porównaniu.
- [P3] Tempo niedopasowane do nowego założenia: stan wejściowy `docs/video/recording-notes.md:9`. Poprzednie 437 słów planowano przy 125 do 140 słowach/min. Przy 115 słowach/min same zdania zajmują około 228 s; z poprzednio przewidzianymi minimum 30 s pauz przekroczyłyby 4 min. Skrócono wyjaśnienia, zachowując ich sens.
- Sformułowania „obie zmiany czasu w Warszawie” i „przeglądarka nie liczy po swojemu” zastąpiono objaśnieniem zmiany czasu i testowalności. Zakończenie ustala kolejność dalszej pracy. Nie zmieniano danych aplikacji pod film.

## Porównanie trzech podróży

Ponowiono prawdziwe żądania FastAPI przez TestClient, bez serwera sieciowego i bez mockowania planera. Odczytano istniejący pakiet `backend/data/demo/`; API otwiera bazy tylko do odczytu. Dodatkowo zablokowano otwieranie żądań ORS w procesie. Data każdego przykładu: 13.11.2026, wyszukiwanie od 17:00, offset +01:00. Ten sam pociąg `skm:284819`: Wrzeszcz 17:02 do Gdańska Głównego 17:09.

| Kryterium | Strzyża PKM | Lawendowe Wzgórze | Przegalina |
|---|---|---|---|
| GTFS i kurs ZTM | Potwierdzone: 6, Dworzec Główny 01, 17:15 do 17:36 | Potwierdzone: 11, Dworzec PKS 02, 17:13 do 17:37 | Potwierdzone: 112, Dworzec Główny 08, 17:16 do 18:21 |
| Od wejścia do SKM / od zapytania 17:00 | 34 / 36 min | 35 / 37 min | 79 / 81 min |
| ORS i minuty do oceny | 153,7 s; 3 min | 102,4 s; 2 min | 82,2 s; 2 min |
| Zapas bez opóźnienia | +3 min | +2 min | +5 min |
| Pokaz zielony / czerwony / zero / szary | opóźnienia 0 / 2 / 3 / 4 | 0 / 1 / 2 / 3 | 0 / 4 / 5 / 6 |
| Logika geograficzna | Przez Główny, potem powrót w rejon bliski Wrzeszczowi; słaby przykład główny | Podróż na inny obszar, ale tramwaj 11 przejeżdża również w pobliżu początku | Dalsza podróż autobusem z Głównego; brak oczywistego powrotu do rejonu Wrzeszcza |
| Pytanie komisji | „Dlaczego nie wsiąść do tramwaju bliżej?” | „Czy ten sam tramwaj nie jest dostępny we Wrzeszczu?” | „Czy 79 minut to najlepsza trasa?”: odpowiadamy wyłącznie za obsługiwany zakres |
| Przydatność filmowa | Krótka, ale ryzyko dyskusji o objazdach | Dobra alternatywa, lecz ma tylko 2 min początkowego zapasu | Czytelny cel dalszej podróży, pięciominutowy zapas i wszystkie stany; długi przejazd pokazujemy godzinami, nie nagrywamy go w całości |

### Screening poza zakresem MVP

W pełnej lokalnej `backend/data/gtfs/transit.db`, otwartej przez `mode=ro`, wybrano 20 konkretnych słupków ZTM w promieniu 500 m Haversine od współrzędnych SKM Wrzeszcz `skm:7534`. Dla każdego celu z manifestu szukano późniejszego postoju tego samego kursu ZTM, z prawem wejścia i wyjścia, aktywnym kalendarzem i wyjątkami. Sprawdzono planowane odjazdy 17:00 do 23:00 dnia 13.11.2026, z zachowaniem service_date i czasu GTFS. To odczyt porównawczy, nie nowy algorytm w aplikacji.

Potwierdzone przykłady spoza planera:

- Strzyża: tramwaj 6 `ztm:6202611131633_21_006-07`, Galeria Bałtycka 01 (`ztm:2025`) 17:11 do Strzyża PKM 01 (`ztm:2033`) 17:16. Słupek początkowy leży około 421,6 m w linii prostej od punktu SKM. To istotna alternatywa wobec przyjazdu 17:36 przez Główny.
- Lawendowe: ten sam kurs 11 co w demo, `ztm:11202611131653_11_011-27`, ma wcześniejszy postój Klonowa 02 (`ztm:2022`) o 17:00 i cel 17:37. Nie dowodzi to, że pasażer rozpoczynający na stacji SKM o 17:00 zdąży na ten tramwaj. Wyjaśnia jednak potencjalne pytanie o bezpośrednią jazdę.
- Przegalina: nie znaleziono bezpośredniego kursu ZTM do grupy celu z żadnego z tych 20 słupków w badanym oknie.

Odległość w linii prostej nie jest trasą pieszą ani zweryfikowanym czasem dojścia. Nie zatwierdzano nowych par i nie wykonywano ORS. Nie porównano wyczerpująco tras z wieloma przesiadkami ZTM, innych stacji, przystanków poza 500 m ani transportu nieobecnego w importach. Brak bezpośredniego kursu w screeningu nie dowodzi optymalności Przegaliny.

Ocenę geograficzną wspierają współrzędne z GTFS: Strzyża leży na północny zachód od Wrzeszcza, a Główny w przeciwnym ogólnym kierunku; Przegalina leży znacznie dalej na wschód i południe. To ocena kierunku i rekordów podróży, nie analiza geometrii całej drogi. Przegalinę wybrano jako najmniej mylącą historię spośród trzech dostępnych demonstracji, bez twierdzenia, że jest globalnie najszybsza.

## Jedyny główny przykład i progi

Przegalina: SKM 17:02 do 17:09, autobus 112 od 17:16 do 18:21, Dworzec Główny 08, `skm:7500` do `ztm:1021`. Kurs autobusu: `ztm:112202611131713_201_112-02`, cel `ztm:14926`. Zapis ORS wynosi 82,2 s, więc do oceny używane są 2 min.

Zapas = `17:16 - (17:09 + 2 min + d)` = `5 - d` min. Zielony przy `0 <= d <= 3`, czerwony przy `3 < d <= 5`, szary przy `d > 5`. Dla całkowitego kroku suwaka: zielony 0 do 3, czerwony 4 i 5, szary od 6. Nagranie pokazuje 0/4/5/6, czyli +5/+1/0/−1. W dodatkowej kontroli 3 min opóźnienia dały dokładnie +2 i pozostają zielone. Silnik nadal nazywa dodatni zapas „Zdążysz”, zero „Na styk”, ujemny „Nie zdążysz”; kolor ostrzegawczy zaczyna się wcześniej niż ujemny wynik.

## Czas i własny głos

Tekst po redakcji: 356 słów. Przy 115 do 130 słowach/min sama narracja zajmie około 2:44 do 3:06. Plan montażu ma 235 s, czyli 3:55; pozostałe około 49 do 71 s służy pauzom, załadowaniu wyniku, przesunięciu suwaka i diagramom. Każda sekcja mieści się we własnym przedziale także przy 115 słowach/min. To budżet, nie pomiar własnego głosu autora. Po próbie można skrócić zatrzymania do około 3:35, bez przyspieszania technicznych zdań.

Nagraj próbę godzin i czterech stanów. Wypowiedź o wartości rozpoczynaj po wyniku API, a przerwę zostaw przed kolejną zmianą suwaka. Przy zerze zapasu postać nadal biegnie; nie dopisuj gwarancji zdążenia. Oryginalny SVG pozostaje w ruchu, również przy szarej postaci. Końcowe plany wypowiadaj jako proponowaną kolejność pracy.

Nagrywaj siedem części własnym głosem, w cichym pomieszczeniu i ze stałą odległością od mikrofonu. Zachowaj zapas ciszy na początku i końcu, sprawdź przesterowanie oraz wyrazistość godzin. WAV mono, np. 48 kHz, wystarczy do montażu. Nie przyspieszaj nagrania, żeby zmieścić tekst. Próba autora pozostaje do wykonania.

## Uruchomienie do właściwego nagrania

Z katalogu repozytorium, jeśli usługi jeszcze nie działają, w dwóch terminalach PowerShell:

```powershell
uv run --no-sync --directory backend python -m app.demo serve
```

```powershell
npm.cmd run dev --prefix frontend
```

Otwórz `http://127.0.0.1:5173`. Sprawdź etykietę archiwalnego demo. Aby serwer odczytywał osobną, już skopiowaną paczkę zamiast oryginału, użyj istniejącego `serve --directory`; skopiuj razem `transit.db`, `walking.db` i `manifest.json`. Przy `--directory backend` względna ścieżka paczki jest liczona od backendu. Zachowaj kopię poza Git. Nie pokazuj terminali z prywatnymi ścieżkami ani klucza ORS. Nie uruchamiaj importów dla potrzeb filmu.

[shot-list.md](shot-list.md) podaje ustawienia Playwright, selektory, warunki gotowości i 20 ujęć. Obecny skrypt nagrania pozostaje wersją 100-sekundową. Rozszerzenie automatycznego montażu do 3:55 i nagranie głosu nie były przedmiotem tego etapu.


## Humanizer 4.0.0

Sprawdzono zainstalowany `humanizer/SKILL.md` w katalogu skilli Codexa użytkownika, metadata.version 4.0.0. Zastosowano jego instrukcje wyłącznie do poprawionej narracji, we wszystkich siedmiu częściach. Nie poddawano Humanizerowi dokumentacji technicznej ani danych.

Osobny przebieg redakcyjny zachował pierwszą osobę, usuwał mechaniczny rytm i upraszczał zdania. Poprawiono składnię wyjaśnienia REST API oraz precyzję opisu izolacji baz. Ponownie porównano godziny, kierunek, zapas, progi, ranking i podział odpowiedzialności z kodem. Zmiana podróży na Przegalinę wynika z audytu przed humanizacją; redakcja językowa nie zmieniała jej danych. Nie dodano fikcyjnych doświadczeń autora.

## Weryfikacja Promptu 30

| Kontrola | Wynik | Zakres i dowód |
|---|---|---|
| Trzy rzeczywiste przykłady | PASS | Trzy POST planera przez TestClient, z istniejących baz demo otwieranych tylko do odczytu. Potwierdzone dane w tabeli porównawczej. |
| Opóźnienia i granice | PASS | 13 ocen API: po cztery dla Strzyży i Lawendowego, pięć dla Przegaliny. Przegalina: 0/3/4/5/6 dają +5/+2/+1/0/−1. |
| Geograficzne ryzyko i bezpośrednie alternatywy | PASS w ograniczonym zakresie | Screening GTFS opisany wyżej; nie jest pełnym porównaniem transportowym. |
| Wyszukiwanie, ranking i architektura | PASS przeglądu kodu | Planer śledzi konkretne kursy i dalsze postoje, używa zatwierdzonych linków, czystej oceny i pasma ≥2 min przed czasem celu. [Dowody](architecture-visuals.md). |
| ORS i cache | PASS przeglądu kodu | Odczyt lokalnego wpisu 82,2 s; ceil 2 min; brak wywołania ORS przez UI, planer i ocenę. Nie odczytywano wartości klucza. |
| Animacje | PASS przeglądu kodu | Kolory z dokładnego marginesu; lokalny SVG/SMIL, crossfade 250 ms i reduced motion pozostają w kodzie. Nie nagrywano nowych ujęć. |
| Bieżący pełny pytest, Node, Edge i build | NOT TESTED | Zmiany wyłącznie redakcyjne. Nie ponawiano pełnej regresji ani builda; nie przedstawia się wyników historycznych jako nowego uruchomienia. |
| Głos i finalne MP4 | NOT TESTED | Zgodnie z zakresem nie nagrywano filmu. Tempo i naturalność głośnego czytania wymagają próby autora. |

W Prompcie 29 wykonano 222 testy backendu, 25 Node i 15 Edge z wynikiem PASS; pierwszy start pytest wymagał poprawy katalogu tymczasowego, pozostało ostrzeżenie deprecacji TestClient/httpx. To historyczne wyniki tego samego kodu, nie uruchomienie w Prompcie 30. Nie przytaczamy liczb w głosie ani nie deklarujemy pełnego pokrycia.

Do powtórzenia testów przed właściwym nagrywaniem, z katalogu repozytorium:

```powershell
$VideoTestRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('przesiadka-video-' + [guid]::NewGuid().ToString('N'))
uv run --no-sync --directory backend python -m pytest -q --basetemp $VideoTestRoot
npm.cmd test --prefix frontend
```

Zestaw Edge wymaga istniejącego Playwright i działającego Vite. Używa syntetycznych odpowiedzi API, więc nie służy jako nagranie prawdziwych kursów:

```powershell
$BrowserPython = Read-Host 'Ścieżka do python.exe z istniejącym Playwright'
& $BrowserPython ./frontend/tests/stop_selection_browser.py
```

## Końcowy przegląd review-mvp

Zakres: sześć materiałów filmu i potwierdzenie ich tez w aktualnym kodzie. Nie jest to pełny audyt ani poprawka aplikacji. Wskazane na początku problemy scenariusza rozwiązano w granicach zadania; nie ma pozostawionych blokujących sprzeczności technicznych w wersji do nagrania.

- Pierwsze 10 do 15 s zawiera konkretny konflikt: sześć minut opóźnienia i pięć minut początkowego zapasu. Dane oraz wynik −1 są prawdziwe.
- Pokaz obsługi, suwak i osobisty ton pozostały. Część techniczna zaczyna od własnego wyszukiwania, a nie listy bibliotek.
- Dalszy postój tego samego autobusu tłumaczy, dlaczego nazwa kierunku nie zastępuje sprawdzenia celu. Podział API i czystej funkcji wyjaśnia możliwość testowania bez serwera.
- Lokalny import i cache pokazują konkretną kontrolę zasobów, bez niezmierzonych obietnic szybkości ani nowych żądań ORS.
- Mniejsze ryzyko geograficzne nie staje się obietnicą globalnej optymalności. Cztery powiązania, archiwalne dane i niezweryfikowane dojście od peronu są jawne.
- Godziny, 2 min dojścia, sekwencja 0/4/5/6 oraz +5/+1/0/−1 obowiązują w narracji, ujęciach, wzorze i napisach. Stare przykłady występują wyłącznie w audycie porównawczym.
- Próba własnego głosu i gotowy montaż nie zostały sprawdzone. Diagramy są możliwe do wykonania, ale nie deklarujemy nowych renderów.

## Gotowość i decyzje autora

Scenariusz jest gotowy technicznie i redakcyjnie do próby głosowej oraz realizacji opisanych ujęć. Przed nagraniem potwierdź brzmienie pierwszej osoby, przeczytaj godziny i zachowaj pauzy przy czterech wynikach. Kolejność rozwoju jest propozycją: terenowa walidacja, kolejny węzeł, później realtime. Nowy montaż wymaga realizacji listy ujęć; stary 100-sekundowy skrypt nie jest nowym automatycznym filmem.

Źródła oraz atrybucje zachowaj zgodnie z [docs/demo.md](../demo.md). Nie wykonywano nowych pobrań ani internetowego sprawdzenia regulaminów. To lokalny przegląd archiwum i dokumentów; nie publikowano materiałów.

## Końcowa kontrola spójności

Potwierdzono 356 słów narracji, siedem zgodnych sekcji w narration.md i storyboard.md oraz montaż 235 s (3:55). Storyboard ma 7 ciągłych przedziałów, lista ujęć 20, wersja napisowa 23; bez luk i nakładania czasu. Wszystkie sekcje mieszczą się w swoich slotach przy 115 słowach/min. Sprawdzono 44 linki lokalne i 27 odnośników do linii kodu, ogrodzenia bloków kodu, końcowe spacje oraz brak prywatnych ścieżek i znaków sterujących. `git diff --check` przeszedł.

Porównanie SHA-256, rozmiaru i mtime wykazało zmiany wyłącznie w sześciu materiałach docs/video/. Pozostałe 104 sprawdzone pliki zachowano bez zmian, w tym trzy lokalne bazy użytkownika, cały trzyplikowy pakiet demo i MP4 Promptu 28. Nie nagrywano nowych ujęć, nie instalowano zależności, nie wykonywano ORS, commita ani pusha. Stan Git nadal zawiera wcześniejsze zmiany użytkownika; ich obecność nie oznacza edycji w tym zadaniu.
