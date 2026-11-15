# Przesiadka+ dla komisji rekrutacyjnej

Tekst do przeczytania własnym głosem. Plan montażu: 3:55, z pauzami na wyniki i diagram. Tytuły i timecode nie są czytane. Zachowano siedem części oraz osobisty charakter poprzedniej wersji. Główny przykład: Wrzeszcz → Przegalina, archiwalne dane 13.11.2026, wyszukiwanie od 17:00. To porównanie obsługiwanych przesiadek, bez deklaracji globalnie najszybszej trasy.

## 0:00 do 0:20: Problem

Pociąg ma sześć minut opóźnienia. W planie było pięć minut zapasu na przesiadkę. Czy nadal zdążę? W Przesiadce+ sprawdzam taką podróż, razem z dojściem na właściwy przystanek.

## 0:20 do 1:05: Podróż użytkownika

Wybieram Gdańsk Wrzeszcz, wyjazd od siedemnastej i Przegalinę jako cel. To archiwalny rozkład z trzynastego listopada dwa tysiące dwudziestego szóstego roku. SKM odjeżdża o siedemnastej zero dwa i dociera do Gdańska Głównego siedem minut później. Aplikacja dobiera przystanek Dworzec Główny zero osiem i autobus sto dwanaście o siedemnastej szesnaście. Planowo docieram o osiemnastej dwadzieścia jeden. Nie wpisuję miejsca przesiadki ani linii. Zostawiam ten wybór aplikacji. Po dwóch minutach szacowanego dojścia zostaje pięć minut zapasu.

## 1:05 do 1:35: Symulacja opóźnienia

Bez opóźnienia zostaje pięć minut zapasu i postać spokojnie idzie. Cztery minuty opóźnienia zostawiają jedną: postać biegnie. Przy pięciu minutach zapas spada do zera. Przy sześciu nie zdążę na wybrany autobus. To symulacja dla tych samych kursów.

## 1:35 do 2:20: Architektura i wyszukiwanie

Żeby znaleźć taką podróż, napisałem planer w Pythonie. Sprawdzam dalsze postoje konkretnego pociągu i dojazd do celu z zatwierdzonych przystanków ZTM. Wybrany autobus musi faktycznie zatrzymywać się przy celu, już po miejscu przesiadki. Sama nazwa kierunku nie wystarczy. React i TypeScript obsługują wybór podróży. FastAPI udostępnia REST API i waliduje dane. Samą ocenę zapasu wydzieliłem do czystej funkcji. Mogę testować ją bez serwera i bazy. Spóźniona odpowiedź API nie zastępuje nowszego wyboru.

## 2:20 do 3:05: Dane i kontrola zasobów

Rozkłady SKM i ZTM importuję z oficjalnych plików GTFS do SQLite. Dzięki lokalnym danym wyszukiwanie nie czeka na zewnętrzną usługę. Dojście pochodzi z osobnego cache OpenRouteService. Korzystam z zapisanego wyniku, więc ruch suwaka nie zużywa limitu tej usługi. Nieaktualny szacunek nie bierze udziału w planowaniu. Szacunek dojścia zaokrąglam w górę do pełnych minut. Preferuję warianty z zapasem co najmniej dwóch minut. W tej samej grupie porównuję czas dotarcia do celu.

## 3:05 do 3:35: Jakość i ograniczenia

Testy obejmują kalendarze, przejazdy przez północ i przejścia między czasem letnim a zimowym. Osobno sprawdzam interfejs w przeglądarce. Bazy testowe są odizolowane. Zakres to cztery zatwierdzone przejścia przy Gdańsku Głównym, bez porównania wszystkich tras w mieście. Rozkład SKM nie wskazuje peronu, dlatego dojście pozostaje szacunkiem, bez terenowej weryfikacji drogi od peronu do słupka.

## 3:35 do 3:55: Dalszy rozwój

Najpierw sprawdziłbym dojście w terenie i dodał kolejny węzeł. Rzeczywiste opóźnienia byłyby osobnym etapem. Każde rozszerzenie chcę oprzeć na potwierdzonych danych i testach.

Liczba słów tekstu mówionego: 356. Tempo 115 do 130 słów/min i próba głosowa: [notatki nagraniowe](recording-notes.md).
