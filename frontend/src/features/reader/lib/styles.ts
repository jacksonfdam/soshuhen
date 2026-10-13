import type { ReaderBackground, ReaderScale } from '../../../lib/api'

// Static maps rather than `bg-reader-${name}`: the Tailwind scanner never
// sees an interpolated class, and the build silently drops it.
export const BACKGROUND: Record<ReaderBackground, string> = {
  black: 'bg-reader-black',
  gray: 'bg-reader-gray',
  white: 'bg-reader-white',
}

export const PAGED_FIT: Record<ReaderScale, string> = {
  fit_width: 'h-auto w-full',
  fit_height: 'h-screen w-auto max-w-none',
  fit_screen: 'max-h-screen max-w-full object-contain',
}

// Fit height has no meaning down a strip, so it reads as a comfortable column
// the same as fit screen.
export const STRIP_FIT: Record<ReaderScale, string> = {
  fit_width: 'w-full',
  fit_height: 'w-full max-w-3xl',
  fit_screen: 'w-full max-w-3xl',
}
