---
name: verify-demo
description: "Weryfikacja działającego demo Przesiadka+: API, obliczenia, plan B, CRUD, trwałość i interfejs. Używaj przy testowaniu aplikacji; raportuj PASS/FAIL/NOT TESTED, bez implementacji i code review."
---

# Weryfikacja demo

## Uruchomienie i warunki

Wywołanie: `$verify-demo Sprawdź lokalne demo` lub `$verify-demo Sprawdź demo pod wskazanymi adresami API i UI`.
Stosuj także przy prośbie o przetestowanie działającej aplikacji.

- Przeczytaj AGENTS.md i sprawdź `git status --short`. Ustal z repozytorium dostępne funkcje, dane demo, kontrakt API, adresy, komendy uruchomienia i testów. Nie zakładaj istnienia endpointu `/health` ani konkretnej komendy.
- Sprawdź działające usługi. Jeśli wymagają uruchomienia, użyj istniejących instrukcji i dostępnych zależności; nie instaluj niczego i nie twórz zastępczej aplikacji. Zapisz przeszkody. Gdy brak implementacji lub środowiska, oznacz zależne kontrole NOT TESTED i przedstaw checklistę do późniejszego wykonania.
- Nie zmieniaj kodu, konfiguracji ani testów, nie wykonuj commitów i nie publikuj. CRUD wykonuj na własnych, jednoznacznie oznaczonych danych testowych w lokalnej bazie demo. Nie usuwaj ani nie nadpisuj danych użytkownika; jeśli nie można odizolować danych, oznacz kontrolę NOT TESTED z powodem.

## Sposób wykonania

Jeśli repozytorium ma testy Playwright, sprawdź ich konfigurację i wykorzystaj je zgodnie z istniejącymi komendami. Nie pobieraj pakietów ani przeglądarek przy okazji uruchomienia. Zachowaj wynik procesu i dostępne raporty, logi lub zrzuty jako dowody. Sprawdź rzeczywisty zakres testów: zielony zestaw nie potwierdza funkcji, których nie obejmuje.

Brakujące kontrole wykonaj ręcznie w dostępnej przeglądarce lub przez API. Jeśli Playwright nie istnieje lub nie można go uruchomić, podaj poniższą ręczną checklistę z krokami i oczekiwanymi rezultatami; wykonaj dostępne kroki. Sama checklista bez wykonania ma status NOT TESTED. Nie twórz nowych skryptów ani testów w ramach tej weryfikacji.

## Checklista funkcjonalna i ręczna

1. **Health API:** wywołaj faktycznie zaimplementowany endpoint diagnostyczny, zapisz URL, status HTTP i treść odpowiedzi; porównaj z kontraktem. Brak endpointu oznacz NOT TESTED jako brak implementacji, nie zastępuj go odpowiedzią strony UI.
2. **Scenariusze demo:** otwórz dostępne przykłady i zanotuj ich dane. Porównaj wynik API i UI z oczekiwaniem obliczonym niezależnie według specyfikacji, nie przez ponowne wywołanie tej samej funkcji. Sprawdź scenariusz bezpieczny, graniczny i nieudaną przesiadkę, o ile model je umożliwia.
3. **Opóźnienie i próg:** dla tych samych danych zmień opóźnienie na zero, wartość poniżej, równą i powyżej progu. Zapisz konkretne wejście, oczekiwany i otrzymany margines oraz ocenę ryzyka; sprawdź jednostki i czas przejścia. Jeżeli reguła graniczna nie jest określona, zaznacz niepewność i NOT TESTED zamiast zgadywać oczekiwanie.
4. **Plan B:** sprawdź przypadek z dostępną alternatywą oraz bez alternatywy; porównaj zalecaną opcję i czasy z danymi i regułami projektu. UI powinien jasno komunikować brak planu B.
5. **Pełny CRUD:** utwórz własny scenariusz, odczytaj go na liście i w szczegółach, zmień dane i potwierdź nowy wynik analizy, usuń i potwierdź brak w API i UI. Sprawdź nieistniejący identyfikator i nieprawidłowe dane wejściowe bez uszkodzenia istniejących rekordów.
6. **Trwałość SQLite:** po utworzeniu i po aktualizacji sprawdź dane po odświeżeniu UI oraz restarcie lokalnego backendu używającego tej samej bazy. Po usunięciu potwierdź, że rekord nie wraca po restarcie. Restartuj tylko instancję testową, którą możesz bezpiecznie kontrolować. Jeśli restart nie jest dostępny, trwałość po restarcie ma status NOT TESTED; samo odświeżenie nie wystarcza. Posprzątaj wyłącznie własne dane i podaj wynik sprzątania.
7. **Widok 390 px i 1440 px:** ustaw obie szerokości viewportu w pikselach CSS, zapisz także wysokość. Na każdej sprawdź listę, formularz, analizę i plan B: brak niezamierzonego poziomego przewijania, uciętych treści i niedostępnych przycisków. Zapisz zrzuty lub konkretne obserwacje.
8. **Klawiatura:** przejdź przepływ przez Tab/Shift+Tab, aktywuj przyciski Enter/Space, sprawdź widoczny fokus, etykiety pól, kolejność i brak pułapki fokusu; jeśli są dialogi, sprawdź ich zamknięcie i powrót fokusu.
9. **Błędy:** wyślij pusty lub nieprawidłowy formularz i sprawdź obsługę błędu API lub utraty połączenia w kontrolowanym środowisku. Komunikaty muszą być zrozumiałe i po polsku, dane formularza zachowane, a ponowienie możliwe. Niewywołane stany błędów oznacz NOT TESTED.

## Raportowanie

Raport pisz po polsku. Podaj środowisko (adresy API/UI, wersję lub commit i lokalne zmiany, przeglądarkę, viewporty, bazę testową), faktycznie wykonane komendy i ich wyniki. Nie ujawniaj sekretów.

Użyj tabeli: `Kontrola | PASS/FAIL/NOT TESTED | Oczekiwane | Zaobserwowane | Dowód lub powód braku testu`.

- **PASS:** kontrola została wykonana, a obserwacja potwierdza oczekiwane zachowanie.
- **FAIL:** wykonana kontrola wykazała rozbieżność; podaj kroki odtworzenia i konkretne dane.
- **NOT TESTED:** kontrola niewykonana lub bez wystarczającego dowodu, także dla brakującej implementacji, narzędzia lub nieokreślonego oczekiwania. Podaj przyczynę i krok potrzebny do weryfikacji.

Dowodem może być status i odpowiedź API, dane wejścia/wyjścia, wynik testu z nazwą przypadku, log, ścieżka do istniejącego raportu lub zrzut ekranu. Przy kontroli ręcznej zapisz kroki i obserwację. Nie przedstawiaj samego istnienia kodu, mocka, pominiętego testu ani checklisty jako PASS. Rozbij częściowo sprawdzone obszary na osobne wiersze.

Na końcu podaj liczbę kontroli w każdym statusie, blokery, pozostałą checklistę i wynik sprzątania danych. Nie deklaruj pełnego sukcesu demo, jeśli wymagane kontrole mają FAIL lub NOT TESTED.
