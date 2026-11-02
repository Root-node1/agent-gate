// Display preferences: colour theme, high contrast and text size. Saved in
// localStorage and applied as attributes on <html>, which tokens.css reads.
// index.html applies the saved values before first paint to avoid a flash;
// keep its inline script in step with apply() below.

import { useSyncExternalStore } from 'react'

export type ThemePreference = 'system' | 'light' | 'dark'
export type FontSize = 'small' | 'default' | 'large' | 'x-large'

export interface DisplayPreferences {
  theme: ThemePreference
  highContrast: boolean
  fontSize: FontSize
}

export const THEME_OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'Match my device' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]

export const FONT_SIZE_OPTIONS: { value: FontSize; label: string; percent: number }[] = [
  { value: 'small', label: 'Small', percent: 87.5 },
  { value: 'default', label: 'Default', percent: 100 },
  { value: 'large', label: 'Large', percent: 112.5 },
  { value: 'x-large', label: 'Extra large', percent: 125 },
]

export const DEFAULT_PREFERENCES: DisplayPreferences = {
  theme: 'system',
  highContrast: false,
  fontSize: 'default',
}

const STORAGE_KEY = 'agentgate:display'

const darkQuery = window.matchMedia('(prefers-color-scheme: dark)')
const contrastQuery = window.matchMedia('(prefers-contrast: more)')

let prefs = load()
const listeners = new Set<() => void>()

function load(): DisplayPreferences {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null') as Partial<DisplayPreferences> | null
    if (saved) return { ...DEFAULT_PREFERENCES, ...saved }
  } catch {
    // Unreadable or blocked storage: fall back to defaults.
  }
  // First visit: follow the device's contrast setting.
  return { ...DEFAULT_PREFERENCES, highContrast: contrastQuery.matches }
}

function apply() {
  const root = document.documentElement
  const dark = prefs.theme === 'dark' || (prefs.theme === 'system' && darkQuery.matches)
  root.dataset.theme = dark ? 'dark' : 'light'
  if (prefs.highContrast) root.dataset.contrast = 'high'
  else delete root.dataset.contrast
  if (prefs.fontSize === 'default') delete root.dataset.fontSize
  else root.dataset.fontSize = prefs.fontSize
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getPreferences(): DisplayPreferences {
  return prefs
}

export function usePreferences(): DisplayPreferences {
  return useSyncExternalStore(subscribe, getPreferences)
}

export function setPreferences(update: Partial<DisplayPreferences>) {
  prefs = { ...prefs, ...update }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
  } catch {
    // Storage full or blocked: the change still applies for this session.
  }
  apply()
  listeners.forEach((listener) => listener())
}

export function resetPreferences() {
  setPreferences(DEFAULT_PREFERENCES)
}

/** Apply saved preferences and follow device theme changes. Call once at startup. */
export function initPreferences() {
  apply()
  darkQuery.addEventListener('change', () => {
    if (prefs.theme === 'system') apply()
  })
}
