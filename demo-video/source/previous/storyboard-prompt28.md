# Przesiadka+ — film rekrutacyjny

100 sekund · 1920×1080 · 30 FPS · H.264 / MP4 · bez dźwięku.

## Koncepcja

Prawdziwe ujęcie Edge: archiwalne demo Kinetic Transit, bez zmiany DOM, CSS, SVG ani odpowiedzi API. Z prawdziwego ujęcia obcięto 32 px górnej krawędzi, aby po przewinięciu nie pokazywać fragmentu poprzedniej sekcji. Kadr 1920×1048 jest zmniejszony do 1792×978 i umieszczony na płótnie 1920×1080 z marginesem 64 px po bokach i 16 px od góry. Dolny pas służy podpisom; wynik, postać i suwak pozostają w całości widoczne. Nie zasłaniamy kontrolek ani postaci. Bahnschrift, jasne litery na tle #08080A. Kolory i ruch pochodzą z działającej aplikacji. Bez dodatkowych efektów i muzyki. Przejścia 0,4 s; brak zoomu.

## Sceny

| Czas filmu | Obraz i rzeczywista interakcja | Treść / kontrola |
|---|---|---|
| 00:00–00:10 | Spokojna plansza otwierająca | Przesiadka+; „Czy zdążysz na przesiadkę?”; data archiwalnego rozkładu |
| 00:10–00:35 | Interfejs → „Zobacz przykład” → Wrzeszcz → Strzyża PKM → przewinięcie do analizy | SKM 17:02–17:09; tramwaj 6 o 17:15; cel 17:36; dojście 3 min; +3 min zapasu |
| 00:35–01:05 | Prawdziwy suwak, płynne przeciągnięcia i dłuższe zatrzymania | 0 / 2 / 3 / 4 min opóźnienia → +3 / +1 / 0 / −1 min zapasu; zielona / czerwona / czerwona / szara postać |
| 01:05–01:30 | Wybór Lawendowego Wzgórza, potem Przegaliny | Tramwaj 11, 17:13–17:37, dojście 2 min, zapas +2; autobus 112, 17:16–18:21, dojście 2 min, zapas +5 |
| 01:30–01:40 | Plansza końcowa | Technologie, „Prototyp MVP — demonstracja na archiwalnych danych”, źródła i atrybucja ORS/OSM |

Wszystkie wyjazdy: 13.11.2026, wyszukiwanie od 17:00. Wyniki oblicza istniejące API; skrypt przerywa pracę przy rozbieżności. Postać: ≥2 min zielona, 0–<2 min czerwona, <0 min szara. Każdy stan pozostaje widoczny przez kilka sekund, z oryginalnym ruchem SMIL.

## Ograniczenia prezentacji

To odtworzenie lokalnych archiwalnych danych, nie dane realtime ani globalnie najszybszy routing. Dojście jest zapisanym szacunkiem OpenRouteService, zaokrąglonym w górę do pełnych minut. Nie wykonujemy nowych zapytań ORS. Szczegóły źródeł i ograniczeń opisuje [dokumentacja demo](../docs/demo.md).

## Dowody

Automatyczny przebieg zapisuje lokalnie `verification/api-checks.json`, `recording-checks.json`, `capture-stats.json`, `database-check.json`, `ffprobe.json` i kluczowe klatki PNG. Surowe ujęcie i logi montażu: `.work/`. Film i dane robocze są ignorowane przez Git.

Samokrytyka: czytelność wyniku i autentyczny ruch mają pierwszeństwo przed efektami. Zrezygnowano z dekoracyjnych neonowych plansz, sztucznej animacji kursora i dodatkowego zoomu. Archiwalny charakter danych jest wskazany zarówno w aplikacji, jak i na planszach filmu.
