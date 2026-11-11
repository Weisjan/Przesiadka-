import type { ScenarioInput } from './types'

export interface DemoExample {
  key: string
  description: string
  scenario: ScenarioInput
}

export const demoExamples: DemoExample[] = [
  {
    key: 'calm',
    description: '6 min zapasu. Przy 8 min opóźnienia sprawdź kurs o 18:03.',
    scenario: {
      name: 'Spokojna przesiadka',
      interchange: 'Gdańsk Główny',
      arrival_line: 'SKM',
      departure_line: '8',
      direction: 'Jelitkowo',
      arrival_at: '2026-11-10T17:42:00+01:00',
      departure_at: '2026-11-10T17:51:00+01:00',
      walking_minutes: 3,
      next_departures: ['2026-11-10T18:03:00+01:00'],
    },
  },
  {
    key: 'edge',
    description: 'Tylko minuta zapasu. Porównaj opóźnienie 0, 1 i 2 min.',
    scenario: {
      name: 'Przesiadka na styk',
      interchange: 'Gdańsk Wrzeszcz',
      arrival_line: 'SKM',
      departure_line: '6',
      direction: 'Oliwa',
      arrival_at: '2026-11-10T17:48:00+01:00',
      departure_at: '2026-11-10T17:52:00+01:00',
      walking_minutes: 3,
      next_departures: ['2026-11-10T18:04:00+01:00'],
    },
  },
  {
    key: 'last',
    description: 'Przez północ. Przy 4 min opóźnienia nie ma już planu B.',
    scenario: {
      name: 'Ostatni kurs',
      interchange: 'Gdańsk Główny',
      arrival_line: 'SKM',
      departure_line: 'N8',
      direction: 'Przymorze',
      arrival_at: '2026-11-10T23:58:00+01:00',
      departure_at: '2026-11-11T00:04:00+01:00',
      walking_minutes: 3,
      next_departures: [],
    },
  },
]
