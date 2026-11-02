import {
  DEFAULT_PREFERENCES,
  FONT_SIZE_OPTIONS,
  THEME_OPTIONS,
  resetPreferences,
  setPreferences,
  usePreferences,
} from '../../../a11y/preferences'

// Changes apply immediately and are saved in this browser, so there is no
// save button: the preview is the page itself.
export default function AppearanceSection() {
  const prefs = usePreferences()
  const isDefault =
    prefs.theme === DEFAULT_PREFERENCES.theme &&
    prefs.highContrast === DEFAULT_PREFERENCES.highContrast &&
    prefs.fontSize === DEFAULT_PREFERENCES.fontSize

  return (
    <div>
      <div className="form-section">
        <div>
          <h2 className="form-section-title">Theme</h2>
          <p className="form-section-text">Dark mode is easier on the eyes in low light.</p>
        </div>
        <fieldset className="st-role-picker">
          <legend className="visually-hidden">Theme</legend>
          {THEME_OPTIONS.map((o) => (
            <label key={o.value} className="st-role-option">
              <input
                type="radio"
                name="st-theme"
                value={o.value}
                checked={prefs.theme === o.value}
                onChange={() => setPreferences({ theme: o.value })}
              />
              <span>
                <strong>{o.label}</strong>
              </span>
            </label>
          ))}
        </fieldset>
      </div>

      <div className="form-section">
        <div>
          <h2 className="form-section-title">Contrast</h2>
          <p className="form-section-text">Stronger text, borders and focus outlines. Works with light and dark.</p>
        </div>
        <div>
          <label className="st-role-option">
            <input
              type="checkbox"
              checked={prefs.highContrast}
              onChange={(e) => setPreferences({ highContrast: e.target.checked })}
              aria-describedby="st-contrast-hint"
            />
            <span>
              <strong>High contrast</strong>
              <span id="st-contrast-hint" className="hint">
                Pure black and white surfaces with text that meets WCAG AAA.
              </span>
            </span>
          </label>
        </div>
      </div>

      <div className="form-section">
        <div>
          <h2 className="form-section-title">Text size</h2>
          <p className="form-section-text">Scales all text in AgentGate. Your browser zoom still works on top.</p>
        </div>
        <fieldset className="st-role-picker">
          <legend className="visually-hidden">Text size</legend>
          {FONT_SIZE_OPTIONS.map((o) => (
            <label key={o.value} className="st-role-option">
              <input
                type="radio"
                name="st-font-size"
                value={o.value}
                checked={prefs.fontSize === o.value}
                onChange={() => setPreferences({ fontSize: o.value })}
              />
              <span>
                <strong style={{ fontSize: `${o.percent / 100}em` }}>{o.label}</strong>
                <span className="hint">{o.percent}%</span>
              </span>
            </label>
          ))}
        </fieldset>
      </div>

      <div className="form-actions st-form-actions">
        <p className="hint st-demo-note">Saved in this browser and applied on every page.</p>
        <button type="button" className="btn btn-ghost" onClick={resetPreferences} disabled={isDefault}>
          Reset to defaults
        </button>
      </div>
    </div>
  )
}
