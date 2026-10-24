import type { ProseTheme } from '../../lib/api'

// Whole class names, never built by interpolation: Tailwind only generates
// the classes it can read in the source.
export const PAGE: Record<ProseTheme, string> = {
  light: 'bg-prose-light text-on-prose-light',
  sepia: 'bg-prose-sepia text-on-prose-sepia',
  dark: 'bg-prose-dark text-on-prose-dark',
}

export const SIZE: Record<number, string> = {
  1: 'text-prose-1',
  2: 'text-prose-2',
  3: 'text-prose-3',
  4: 'text-prose-4',
  5: 'text-prose-5',
  6: 'text-prose-6',
  7: 'text-prose-7',
}

export const SMALLEST = 1
export const LARGEST = 7

export const THEMES: { value: ProseTheme; label: string }[] = [
  { value: 'light', label: 'Light' },
  { value: 'sepia', label: 'Sepia' },
  { value: 'dark', label: 'Dark' },
]
