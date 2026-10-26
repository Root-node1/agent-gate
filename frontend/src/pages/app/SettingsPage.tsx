import { useRef, useState, type KeyboardEvent } from 'react'
import { useSearchParams } from 'react-router'
import { useDemoState } from '../../demo/store'
import PageHeader from '../../ui/PageHeader'
import { useSimulatedLoad } from '../../ui/hooks'
import ApiKeysSection from './settings/ApiKeysSection'
import AppearanceSection from './settings/AppearanceSection'
import DevelopersSection from './settings/DevelopersSection'
import PaypalSection from './settings/PaypalSection'
import TeamSection from './settings/TeamSection'
import WorkspaceSection from './settings/WorkspaceSection'
import { SETTINGS_TABS, defaultWorkspace, isSettingsTab, type SettingsTab } from './settings/settingsData'
import './SettingsPage.css'

export default function SettingsPage() {
  const state = useDemoState()
  const loading = useSimulatedLoad()
  const [params, setParams] = useSearchParams()
  const [workspace, setWorkspace] = useState(defaultWorkspace)
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])

  const param = params.get('tab')
  const active: SettingsTab = isSettingsTab(param) ? param : 'workspace'

  function select(tab: SettingsTab) {
    const next = new URLSearchParams(params)
    if (tab === 'workspace') next.delete('tab')
    else next.set('tab', tab)
    setParams(next, { replace: true, preventScrollReset: true })
  }

  // Arrow keys move between tabs, as in the WAI-ARIA tabs pattern.
  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = SETTINGS_TABS.length - 1
    let target: number | null = null
    if (e.key === 'ArrowRight') target = index === last ? 0 : index + 1
    if (e.key === 'ArrowLeft') target = index === 0 ? last : index - 1
    if (e.key === 'Home') target = 0
    if (e.key === 'End') target = last
    if (target === null) return
    e.preventDefault()
    select(SETTINGS_TABS[target].id)
    tabRefs.current[target]?.focus()
  }

  return (
    <div className="stack-lg">
      <PageHeader
        title="Settings"
        description="Workspace defaults, the PayPal connection, API keys, your team, developer resources and display options."
      />

      <div className="st-tabs-scroll">
        <div className="tabs st-tabs" role="tablist" aria-label="Settings sections">
          {SETTINGS_TABS.map((tab, i) => (
            <button
              key={tab.id}
              ref={(el) => {
                tabRefs.current[i] = el
              }}
              type="button"
              role="tab"
              id={`st-tab-${tab.id}`}
              className="tab"
              aria-selected={active === tab.id}
              aria-controls={`st-panel-${tab.id}`}
              tabIndex={active === tab.id ? 0 : -1}
              onClick={() => select(tab.id)}
              onKeyDown={(e) => onKeyDown(e, i)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <section
        className="card st-panel"
        role="tabpanel"
        id={`st-panel-${active}`}
        aria-labelledby={`st-tab-${active}`}
        tabIndex={0}
      >
        {active === 'workspace' && <WorkspaceSection saved={workspace} onSave={setWorkspace} />}
        {active === 'paypal' && <PaypalSection />}
        {active === 'keys' && <ApiKeysSection state={state} loading={loading} />}
        {active === 'team' && <TeamSection state={state} loading={loading} />}
        {active === 'developers' && <DevelopersSection />}
        {active === 'appearance' && <AppearanceSection />}
      </section>
    </div>
  )
}
