# Wersja bez narratora

Montaż 3:55 według tego samego storyboardu; główny przykład Wrzeszcz → Przegalina. Krótkie podpisy zastępują głos; nie nakładaj równolegle pełnej narracji. Dla wersji mówionej można wykorzystać wybrane podpisy jako objaśnienia. To nie jest gotowy plik SRT ani nowy film.

Zachowaj rzeczywisty dźwięk ciszy lub brak ścieżki audio. Muzyka nie jest potrzebna. Podczas ujęć UI podpis zajmuje osobny pas poza postacią, suwakami i kartami. Maksymalnie dwa wiersze, około 34 do 40 px przy 1080p, duży kontrast. Podziały `<br>` oznaczają dwa wiersze. Zachowaj stałą małą informację „Dane archiwalne: 13.11.2026” w bezpiecznym marginesie filmu. To nakładka montażowa, nie zmiana aplikacji.

| Początek | Koniec | Podpis |
|---|---|---|
| 0:00 | 0:10 | Sześć minut opóźnienia.<br>W planie było pięć minut zapasu. |
| 0:10 | 0:20 | Przesiadka+<br>Czy nadal zdążę? |
| 0:20 | 0:33 | Wrzeszcz do Przegaliny.<br>Archiwalny rozkład 13.11.2026. |
| 0:33 | 0:47 | SKM: Wrzeszcz 17:02.<br>Gdańsk Główny 17:09. |
| 0:47 | 0:57 | Autobus 112: odjazd 17:16.<br>Przegalina: planowo 18:21. |
| 0:57 | 1:05 | Szacowane dojście: 2 min.<br>Zapas: +5 min. |
| 1:05 | 1:12 | Opóźnienie 0 min.<br>Zapas +5 min, spokojny chód. |
| 1:12 | 1:19 | Opóźnienie 4 min.<br>Zapas +1 min, mały margines. |
| 1:19 | 1:26 | Opóźnienie 5 min.<br>Zapas 0 min, dokładnie na styk. |
| 1:26 | 1:35 | Opóźnienie 6 min.<br>Zapas -1 min, kurs nieosiągalny. |
| 1:35 | 1:46 | Planer sprawdza dalsze postoje<br>konkretnego pociągu SKM. |
| 1:46 | 1:56 | Zatwierdzony słupek ZTM.<br>Cel na tym samym kursie autobusu. |
| 1:56 | 2:11 | React zbiera wybór, FastAPI waliduje.<br>Czystą ocenę testuję bez HTTP i bazy. |
| 2:11 | 2:20 | Starsza odpowiedź nie zastępuje<br>nowszego wyboru. |
| 2:20 | 2:28 | GTFS: przystanki, kursy i kalendarze.<br>Lokalny import do SQLite. |
| 2:28 | 2:35 | Dojście: kierunkowy cache ORS.<br>Suwak nie wysyła zapytań ORS. |
| 2:35 | 2:45 | 82,2 s daje 2 min dojścia.<br>Zaokrąglenie w górę. |
| 2:45 | 2:54 | Nieaktualny szacunek<br>nie bierze udziału w planowaniu. |
| 2:54 | 3:05 | Preferencja: zapas co najmniej 2 min.<br>Potem czas dotarcia do celu. |
| 3:05 | 3:19 | Testy: kalendarz, północ, zmiana czasu.<br>Odizolowane bazy i testy UI. |
| 3:19 | 3:35 | Cztery przejścia w jednym węźle.<br>Dojście od peronu niezweryfikowane. |
| 3:35 | 3:50 | Kolejny etap: walidacja dojścia<br>i następny węzeł. |
| 3:50 | 3:55 | Przesiadka+<br>Lokalny prototyp MVP. |

Podpis o konkretnej wartości opóźnienia włącz dopiero po rzeczywistym wyniku API. Podczas przeciągania zostaw przez chwilę sam interfejs; nie uprzedzaj stanu opisem. Końce przedziałów są wyłączne, żeby nie nakładać dwóch podpisów w tej samej klatce.

Od 3:45 pozostaw czytelne źródła w dolnym obszarze planszy: Zarząd Transportu Miejskiego w Gdańsku; PKP Szybka Kolej Miejska w Trójmieście Sp. z o.o.; „© openrouteservice by HeiGIT | Data from OpenStreetMap”, CC BY-SA 4.0. Nie usuwaj atrybucji już widocznych w UI. Datę pozyskania GTFS i nieustaloną datę wytworzenia podaj zgodnie z manifestem i [dokumentacją demo](../demo.md), nie jako datę realizacji filmu. Realtime pozostaje niezrealizowanym kierunkiem rozwoju.
