import { useState } from 'react'
import { Accessibility } from 'lucide-react'
import Modal from '../ui/Modal'
import {
  DEFAULT_PREFERENCES,
  FONT_SIZE_OPTIONS,
  THEME_OPTIONS,
  resetPreferences,
  setPreferences,
  usePreferences,
} from './preferences'

interface Props {
  /** Button class, so the trigger matches the header it sits in. */
  className?: string
}

/**
 * Accessibility button that opens the display settings (theme, contrast, text
 * size) in a dialog. Used in both headers so it is reachable from every page.
 */
export default function DisplayButton({ className = 'icon-button' }: Props) {
  const [open, setOpen] = useState(false)
  const prefs = usePreferences()
  const isDefault =
    prefs.theme === DEFAULT_PREFERENCES.theme &&
    prefs.highContrast === DEFAULT_PREFERENCES.highContrast &&
    prefs.fontSize === DEFAULT_PREFERENCES.fontSize

  return (
    <>
      <button
        type="button"
        className={className}
        onClick={() => setOpen(true)}
        aria-label="Display settings: theme, contrast and text size"
        aria-haspopup="dialog"
        title="Display settings"
      >
        <Accessibility size={20} aria-hidden="true" />
      </button>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Display settings"
        footer={
          <>
            <button type="button" className="btn btn-ghost" onClick={resetPreferences} disabled={isDefault}>
              Reset to defaults
            </button>
            <button type="button" className="btn btn-primary" onClick={() => setOpen(false)}>
              Done
            </button>
          </>
        }
      >
        <div className="display-settings">
          <fieldset className="display-group">
            <legend className="field-label">Theme</legend>
            <div className="display-choices display-choices-3">
              {THEME_OPTIONS.map((o) => (
                <label key={o.value} className="display-choice">
                  <input
                    type="radio"
                    name="display-theme"
                    value={o.value}
                    checked={prefs.theme === o.value}
                    onChange={() => setPreferences({ theme: o.value })}
                  />
                  <span>{o.label}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="display-group">
            <legend className="field-label">Contrast</legend>
            <label className="display-choice display-choice-row">
              <input
                type="checkbox"
                checked={prefs.highContrast}
                onChange={(e) => setPreferences({ highContrast: e.target.checked })}
                aria-describedby="display-contrast-hint"
              />
              <span>
                High contrast
                <span id="display-contrast-hint" className="hint">
                  Stronger text, borders and focus outlines.
                </span>
              </span>
            </label>
          </fieldset>

          <fieldset className="display-group">
            <legend className="field-label">Text size</legend>
            <div className="display-choices display-choices-4">
              {FONT_SIZE_OPTIONS.map((o) => (
                <label key={o.value} className="display-choice">
                  <input
                    type="radio"
                    name="display-font-size"
                    value={o.value}
                    checked={prefs.fontSize === o.value}
                    onChange={() => setPreferences({ fontSize: o.value })}
                  />
                  <span>
                    <span className="display-sample" style={{ fontSize: `${o.percent / 100}em` }} aria-hidden="true">
                      Aa
                    </span>
                    {o.label}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <p className="hint">Changes apply right away and are saved in this browser.</p>
        </div>
      </Modal>
    </>
  )
}
