# Ujęcia prawdziwej aplikacji

Plan realizacji filmu 3:55 z Przegaliną jako jedynym przykładem użytkowym. Ten etap nie generuje nagrania ani screenshotów. Istniejący film Promptu 28 trwa 100 sekund i nie zawiera całej części technicznej. Ujęcia użytkowe nagrywaj w prawdziwym Edge z prawdziwym lokalnym API, bez mocków z testów przeglądarkowych.

## Przygotowanie Playwright

1. Zachowaj istniejący pakiet `backend/data/demo/`. Nie uruchamiaj ponownie `prepare`, importu GTFS ani ORS. Instrukcja: [demo](../demo.md).
2. Sprawdź porty 8000 i 5173 oraz `/api/health` i `/api/transit/sources`. Działającego demo nie uruchamiaj ponownie. Zwykły backend wymaga świadomego zatrzymania przed demo; nie zabijaj nieznanego procesu.
3. Ustaw viewport 1920×1080, `device_scale_factor=1`, `locale="pl-PL"`, `timezone_id="Europe/Warsaw"`, `reduced_motion="no-preference"`. Nagrywaj viewport bez paska przeglądarki, terminala i powiadomień. Nie zmieniaj DOM ani stylów aplikacji.
4. Oczekuj na prawdziwy wynik POST, poprawną treść oraz stabilny kadr; sam `networkidle` nie wystarczy. Zapisz po kilka sekund zapasu przed i po ujęciu. API musi działać w jawnym trybie demo.

| Element | Selektor Playwright Python | Warunek gotowości |
|---|---|---|
| Przykłady | `page.get_by_role("button", name="Zobacz przykład", exact=True)` | Aktywny, etykieta „Archiwalne demo” widoczna. |
| Lista | `page.get_by_role("group", name="Przykłady archiwalnego demo")` | Widoczna po kliknięciu. |
| Pierwszy przykład | `page.get_by_role("button", name="Wrzeszcz → Przegalina", exact=False)` | Obejmij kliknięcie `page.expect_response` dla POST `/api/transit/journeys/plan`; status 200 i zgodny pierwszy wynik. |
| Pola | `page.get_by_label("Skąd jedziesz?", exact=True)`; odpowiednio „Dokąd jedziesz?”, „Data wyjazdu”, „Godzina wyjazdu” | Wrzeszcz, Przegalina, `2026-11-13`, `17:00`; wybór przykładu uzupełnia pola sam. |
| Karty | `page.get_by_role("region", name="Twój przejazd SKM", exact=True)`; analogicznie „Twój przejazd ZTM” | Czasy i przystanki zgodne z tabelą poniżej. |
| Zapas | `page.locator('output[aria-label="Zapas czasu: 5 minut"]')` | Widoczny; następnie wartości 1, 0 i -1, dla opóźnień 4, 5 i 6. |
| Postać | `page.locator("[data-figure-state]")` | `success`, `edge`, `edge`, `missed`. |
| Opóźnienie | `page.get_by_role("slider")` | Aktywny, zakres 0 do 30; w ujęciu przeciągaj prawdziwą myszą. |
| Wyjaśnienie | `page.get_by_text("Dlaczego ta podróż?", exact=True)` | Aktywuj istniejący `summary`; sprawdź kryteria i powiązania. |

Pozycję myszki oblicz z bieżącego `bounding_box()` suwaka, wartości i zakresu, nie ze stałych współrzędnych ekranu. Dla każdego ustawienia oczekuj na `/api/transit/transfers/search` oraz zgodny wynik DOM. Dopiero wtedy licz zatrzymanie. Nie używaj `setContent`, `route.fulfill`, `margin_override` ani ręcznie wstawionych wyników.

## Lista ujęć

| ID | Czas montażu | Kadr i działanie | Kontrola |
|---|---|---|---|
| S01 | 0:00 do 0:08 | Poza kadrem wybierz Przegalinę i ustaw opóźnienie 6. Pokaż rzeczywisty wynik. | −1 min, szara postać, stałe kursy; podpis o archiwalnych danych. |
| S02 | 0:08 do 0:20 | Cięcie do tytułu i formularza po odświeżeniu. | Neutralny wynik i etykieta demo. |
| S03 | 0:20 do 0:33 | Kliknij przykład Przegalina, pokaż wypełnione pola. | 13.11.2026, od 17:00; przesiadka i linia dobrane przez aplikację. |
| S04 | 0:33 do 0:47 | Pokaż kartę SKM. | Wrzeszcz 17:02, Gdańsk Główny 17:09, ten sam kurs skm:284819. |
| S05 | 0:47 do 0:57 | Pokaż kartę ZTM. | Autobus 112, kierunek Przegalina; Dworzec Główny 08 o 17:16, Przegalina 02 o 18:21. |
| S06 | 0:57 do 1:05 | Pokaż analizę i szacowane dojście. | 2 min dojścia, +5 min zapasu, zielona postać. |
| S07 | 1:05 do 1:12 | Suwak 0; nie zmieniaj kadru. | +5, zielony chód; kilka cykli po 1,2 s. |
| S08 | 1:12 do 1:19 | Płynnie przeciągnij do 4 i zatrzymaj. | +1, czerwony bieg po prawdziwej odpowiedzi API. |
| S09 | 1:19 do 1:26 | Przeciągnij do 5 i zatrzymaj. | 0 i czerwony bieg. Nie podpisuj tego jako gwarancji przesiadki. |
| S10 | 1:26 do 1:35 | Przeciągnij do 6 i zatrzymaj. | −1 i szara postać z ruchem 2,4 s. Kurs i planowana godzina celu pozostają te same. |
| S11 | 1:35 do 1:56 | G1: planer, dalsze postoje tego samego pociągu i przystanek celu na tym samym autobusie. | Dokładny kurs SKM, zatwierdzony słupek i późniejszy postój 112; żadnego fikcyjnego węzła. |
| S12 | 1:56 do 2:11 | G2: UI, walidacja FastAPI i rzeczywisty fragment czystej funkcji. | Obliczenia po stronie backendu, w UTC; kod bez prywatnych ścieżek. |
| S13 | 2:11 do 2:20 | G3: odpowiedź musi odpowiadać bieżącemu wyborowi. | Prosty schemat A/B, bez wymyślonych czasów sieci. Pod koniec można wrócić do prawdziwego SVG. |
| S14 | 2:20 do 2:35 | G4: jawny import i odczyt lokalnego GTFS oraz cache. | Nie uruchamiaj importu ani ORS do nagrania; rozdziel wcześniejsze przygotowanie od pracy UI. |
| S15 | 2:35 do 2:45 | G5: 82,2 s i zaokrąglenie do 2 min. | Zapis skm:7500 do ztm:1021; szacunek ORS, bez pomiaru terenowego. |
| S16 | 2:45 do 3:05 | Przywróć 0 poza kadrem, rozwiń „Dlaczego ta podróż?”. | +0 opóźnienia widoczne; aktualność cache i ranking bazowy. Wynik tylko w obsługiwanym zakresie. |
| S17 | 3:05 do 3:19 | Prawdziwy świeży raport testów i podpis o kalendarzach oraz zmianie czasu. | Nagrywaj rzeczywiste podsumowanie, bez ścieżek użytkownika; nie kopiuj historycznych liczb jako nowych. |
| S18 | 3:19 do 3:35 | Pokaż ograniczenia MVP i dojścia. | Cztery przejścia w jednym węźle, brak określonego peronu, estymacja. |
| S19 | 3:35 do 3:50 | Szeroki kadr aplikacji przy +0. | Przegalina, +5; rozwój przedstawiony jako plan. |
| S20 | 3:50 do 3:55 | Plansza końcowa i źródła. | MVP, archiwalne dane i zachowane atrybucje. |

Podczas S07 do S10 zachowaj ciągłe nagranie, natywne SVG/SMIL i crossfade aplikacji. Przy przewinięciach nie kadruj formularza w połowie kontrolki. Zostaw osobny pas na podpisy. Plansze G1 do G5 opisuje [plan grafik](architecture-visuals.md).

## Wybrany przypadek i kontrola progów

Dane wejściowe: `przegalina` z manifestu demo. Wynik: SKM `skm:284819` i ZTM `ztm:112202611131713_201_112-02`, kierunkowy link `skm:7500` do `ztm:1021`, cel `ztm:14926`. Zapas = `17:16 - (17:09 + 2 min + opóźnienie)` = `5 - opóźnienie` min. Dla całych minut suwaka zielony jest przy 0 do 3, czerwony przy 4 i 5, szary od 6. Dodatkowa kontrola granicy: opóźnienie 3 daje dokładnie +2 i nadal zielony.

Przed kliknięciem przykładu obejmij akcję oczekiwaniem na POST planera; potem sprawdź wszystkie cztery godziny, `walking_minutes=2`, +5 i `success`. Przy suwaku czekaj równocześnie na właściwą odpowiedź `/transfers/search` i DOM. Odpowiedź musi dotyczyć tego samego kursu oraz stop sequence. Dla +1 i 0 oczekuj `edge`, dla −1 `missed`. Zapisane 82,2 s są estymacją, nie rzeczywistym czasem od peronu.

## Istniejące narzędzia

[record.py](../../demo-video/recording-script/record.py) i [instrukcja](../../demo-video/recording-script/README.md) potwierdzają nagrywanie realnego Edge. Obecny skrypt ma choreografię Strzyży, progi 0/2/3/4 i montaż 100 sekund. Nie realizuje nowego scenariusza Przegaliny. Nie uruchamiaj go z oczekiwaniem gotowego filmu 3:55. Realizacja tej listy wymaga osobnego rozszerzenia choreografii lub montażu prawdziwych surowych ujęć; ten etap nie zmienia skryptu.

Nie montuj syntetycznych fixture'ów Edge jako przejazdu demo. Kontrole automatyczne z mockami są dowodem działania testów i muszą być tak podpisane, jeśli trafią do części o jakości.
