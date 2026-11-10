# Przesiadka+

Demo aplikacji analizującej ryzyko przesiadek w Gdańsku.

- Backend: Python 3.13, FastAPI, Pydantic, SQLModel, SQLite; zarządzanie zależnościami przez uv.
- Frontend: React, TypeScript, Vite, CSS Modules.
- Wszystkie teksty UI pisz po polsku, kod i identyfikatory po angielsku.
- Backend odpowiada za obliczenia. Logikę domenową implementuj jako czystą funkcję, niezależną od HTTP, bazy danych i innych efektów ubocznych.
- MVP obejmuje pełny CRUD scenariuszy, analizę marginesu przesiadki, próg opóźnienia i plan B.
- Nie używaj zewnętrznych API, kont ani sekretów.
- Wprowadzaj małe, testowalne zmiany, bez nadmiarowych zależności. Zachowuj zmiany użytkownika.
- Nie przedstawiaj fikcyjnych komend ani nieukończonych funkcji jako działających.
- Nie wykonuj commitów ani publikacji bez zgody użytkownika.

## Skill usage

- `frontend-design`: stosuj przy planowaniu i implementacji istotnych zmian wizualnych; najpierw koncepcja, potem kod, potem ocena zrzutów ekranu.

- `ponytail`: stosuj przy implementacji, gdy pomaga uprościć rozwiązanie i wykorzystać istniejący kod; nie rezygnuj z testów, walidacji ani czytelności.
- `caveman`: używaj do zwięzłego raportowania, bez pomijania wyników testów, błędów i decyzji.
- `i-have-adhd`: używaj przy planowaniu pracy i prowadzeniu małych etapów; podawaj jasny status i następny krok.
- `review-mvp`: stosuj po istotnych zmianach i przed końcową recenzją; raportuj problemy według istotności, z plikami i liniami.
- `verify-demo`: stosuj po przygotowaniu działającego scenariusza i przed nagraniem filmu; raportuj PASS/FAIL/NOT TESTED wraz z dowodami.

Codex wykrywa lokalne skille w `.agents/skills`. Sam wpis w AGENTS.md nie uruchamia skilla: przy odpowiednim etapie wczytaj jego SKILL.md i wykonaj instrukcje. Użytkownik może wywołać skill jawnie przez `$nazwa-skilla` w promptcie; Codex może też dobrać go na podstawie opisu, jeśli polityka na to pozwala. `i-have-adhd` ma `allow_implicit_invocation: false` w `agents/openai.yaml`, więc wymaga jawnego wywołania `$i-have-adhd`; bez niego zachowuj opisane wyżej zasady małych etapów. Gdy skill lub narzędzia są niedostępne, zgłoś ograniczenie zamiast deklarować wykonanie.

Priorytety: poprawność i bezpieczeństwo są ważniejsze od skracania kodu; wyniki testów i wymagane informacje są ważniejsze od zwięzłości; wymagania produktu są ważniejsze od preferencji stylistycznych. Ograniczenia długości wypowiedzi i list nie mogą usuwać ustaleń ani dowodów. Skille nie rozszerzają zakresu polecenia ani uprawnień; `review-mvp` i `verify-demo` nie upoważniają do samodzielnych poprawek kodu.
