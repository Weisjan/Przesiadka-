# Mapa narracji

Czas w sekundach od początku filmu. Sloty docelowe, nie pomierzone audio. TTS nie został wygenerowany. Niewielkie korekty początku segmentów wynikają z rzeczywistych odpowiedzi UI.

| Segment | Scena | Od | Do | Tekst |
|---|---|---:|---:|---|
| seg-01 | scene-1 | 0 | 8 | Wybieram Wrzeszcz, godzinę i Przegalinę. Aplikacja dobiera kursy, miejsce przesiadki i dojście. |
| seg-02 | scene-1 | 8 | 16 | To archiwalny rozkład z trzynastego listopada dwa tysiące dwudziestego szóstego roku. |
| seg-03 | scene-1 | 16 | 24 | SKM odjeżdża o siedemnastej zero dwa i dociera do Gdańska Głównego siedem minut później. |
| seg-04 | scene-1 | 24 | 32 | Dalej jest autobus sto dwanaście o siedemnastej szesnaście. Do Przegaliny docieram planowo o osiemnastej dwadzieścia jeden. |
| seg-05 | scene-1 | 32 | 40 | Po dwóch minutach szacowanego dojścia zostaje pięć minut zapasu. Nie wybieram ręcznie słupka. |
| seg-06 | scene-2 | 40 | 47 | Bez opóźnienia postać spokojnie idzie. Suwak ocenia te same kursy, bez zmiany planu. |
| seg-07 | scene-2 | 47.41 | 55 | Cztery minuty opóźnienia zostawiają jedną minutę zapasu. Postać zaczyna biec. |
| seg-08 | scene-2 | 55.26 | 60 | Przy pięciu minutach zapas wynosi zero. |
| seg-09 | scene-2 | 63 | 70 | Sześć minut oznacza spóźnienie na ten autobus. Opóźnienie jest wyłącznie symulowane. |
| seg-10 | scene-3 | 70 | 78 | Napisałem własny planer w Pythonie. Sprawdza dalsze postoje konkretnego pociągu. |
| seg-11 | scene-3 | 78 | 85 | Porównuje zatwierdzone przejścia i dokładne słupki ZTM. Potem sprawdza dalszą trasę wybranego autobusu. |
| seg-12 | scene-3 | 85 | 92 | Cel musi występować na tym samym kursie, po przystanku wejścia. |
| seg-13 | scene-3 | 92 | 99 | Planer uwzględnia dojście i oblicza zapas. Preferuje warianty z zapasem co najmniej dwóch minut. |
| seg-14 | scene-3 | 99 | 105 | W tej grupie liczy się czas dotarcia do celu. |
| seg-15 | scene-4 | 105 | 112 | React i TypeScript odpowiadają za interfejs. FastAPI udostępnia REST API i waliduje dane. |
| seg-16 | scene-4 | 112 | 119 | Samą ocenę zapasu wydzieliłem do czystej funkcji. Mogę testować ją bez serwera i bazy. |
| seg-17 | scene-4 | 119 | 126 | Rozkłady SKM i ZTM importuję z oficjalnych plików GTFS do lokalnego SQLite. |
| seg-18 | scene-4 | 126 | 133 | Dojście pochodzi z cache OpenRouteService. Suwak nie odpytuje tej usługi. |
| seg-19 | scene-4 | 133 | 140 | Szacunek zaokrąglam w górę do minut. Nieaktualny wpis wyklucza przejście. |
| seg-20 | scene-5 | 140 | 148 | Testuję backend, frontend i przeglądarkę, także kalendarze, północ i zmianę czasu. |
| seg-21 | scene-5 | 148 | 157 | MVP porównuje cztery zatwierdzone przejścia przy Gdańsku Głównym. Nie jest pełnym planerem Trójmiasta. |
| seg-22 | scene-5 | 157 | 165 | To dane archiwalne, bez rzeczywistych opóźnień. Dojście pozostaje szacunkiem, a nie zweryfikowanym czasem od peronu. |
