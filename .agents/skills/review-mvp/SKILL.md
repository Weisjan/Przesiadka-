---
name: review-mvp
description: "Przegląd zmian w Przesiadka+: logika przesiadek, walidacja, regresje i złożoność w FastAPI, React i TypeScript. Używaj przy code review, nie do testowania działającego demo ani implementacji."
---

# Przegląd MVP

## Uruchomienie i zakres

Wywołanie: `$review-mvp Przejrzyj lokalne zmiany` albo `$review-mvp Przejrzyj zmiany względem wskazanej gałęzi`.
Stosuj także przy prośbie o przegląd zmian w tym projekcie.

- Przeczytaj obowiązujące AGENTS.md i sprawdź `git status --short`. Zbadaj diff oraz nowe pliki; dla porównania gałęzi użyj bazy podanej przez użytkownika. Jeśli zakres jest niejasny, zacznij od zmian lokalnych i zaznacz ten zakres w raporcie.
- Przeczytaj kontekst zmienianych funkcji, wywołań i testów. Oceniaj rzeczywiste zachowanie względem wymagań, nie tylko sam diff.
- Nie modyfikuj kodu ani innych plików bez wyraźnego polecenia. Nie instaluj zależności, nie wykonuj commitów i nie publikuj. Uruchamiaj tylko istniejące, adekwatne testy bez zmiany danych użytkownika; komendy ustal z repozytorium, nie wymyślaj ich.

## Co sprawdzać

- Logika domenowa: obliczenia na backendzie, czysta funkcja bez HTTP, bazy i efektów ubocznych; deterministyczny wynik dla tych samych danych. Frontend nie powinien duplikować obliczeń.
- Przesiadki: zgodność jednostek czasu, znak marginesu, czas przejścia i bufor według przyjętej specyfikacji, wpływ opóźnienia, próg graniczny i plan B. Sprawdź zero oraz wartości tuż poniżej, równe i tuż powyżej progu, ujemny margines i brak alternatywy. Przejście przez północ sprawdzaj, gdy model obsługuje godziny lub daty. Nie narzucaj nieopisanej reguły biznesowej; brak reguły zgłoś jako pytanie.
- FastAPI/Pydantic: walidacja wymaganych pól, zakresów i typów po stronie API, odrzucanie nieprawidłowych czasów i wartości niefinitywnych, jeśli przyjmowane są liczby zmiennoprzecinkowe; spójne odpowiedzi i błędy dla nieistniejących zasobów. Typy TypeScript nie zastępują walidacji API.
- SQLModel/SQLite i CRUD: tworzenie, lista i odczyt, aktualizacja, usuwanie, identyfikatory, transakcje i trwałość; rozróżnienie pominiętego pola od jawnego null przy aktualizacji. Szukaj utraty danych i niezamierzonych zmian innych scenariuszy.
- React/TypeScript: zgodność typów z kontraktem API, stany ładowania, pustych danych i błędów, kontrolowane formularze, nieaktualne odpowiedzi asynchroniczne i odświeżanie widoku po CRUD. Teksty UI mają być po polsku, kod i identyfikatory po angielsku.
- Regresje: wpływ zmian na istniejące przepływy, brakujące testy istotnych zachowań i przypadki brzegowe. Zgłaszaj nadmierne zależności, duplikację i abstrakcje tylko z konkretnym kosztem dla MVP; unikaj uwag wyłącznie stylistycznych.
- MVP nie wymaga zewnętrznych API, kont ani sekretów. Odróżniaj niezaimplementowany zakres od regresji w istniejącym zachowaniu.

## Raportowanie

Raport pisz po polsku. Najpierw problemy, od najistotniejszych:

- P0: krytyczny problem blokujący użycie lub powodujący poważną utratę danych.
- P1: istotnie błędne obliczenia, uszkodzenie danych lub niedziałający podstawowy przepływ MVP.
- P2: błąd dla ograniczonego przypadku lub istotne ryzyko regresji.
- P3: drobny problem z konkretnym skutkiem dla użytkownika lub utrzymania.

Dla każdego problemu podaj `[P1] Krótki tytuł`, `ścieżka:linia` (możliwie mały zakres), warunki wystąpienia, oczekiwany i rzeczywisty skutek oraz dowód z kodu lub testu. Odwołuj się do aktualnych linii pliku, najlepiej objętych zmianą. Oddziel potwierdzone błędy od pytań i założeń; nie wymyślaj numerów linii ani wyników.

Zakończ zakresem przeglądu, uruchomionymi testami i ich wynikami oraz nieweryfikowanymi obszarami. Jeśli nie znaleziono problemów, powiedz to wprost z ograniczeniami przeglądu. Brak uruchomionych testów nie oznacza potwierdzenia działania aplikacji.
