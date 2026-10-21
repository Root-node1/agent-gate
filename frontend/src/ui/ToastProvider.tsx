import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { CircleAlert, CircleCheck, Info } from 'lucide-react'
import { ToastContext, type ToastTone } from './toast-context'

interface Toast {
  id: number
  message: string
  tone: ToastTone
}

const ICONS = { success: CircleCheck, error: CircleAlert, info: Info }
const DURATION_MS = 4000

let nextId = 1

export default function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const show = useCallback((message: string, tone: ToastTone = 'success') => {
    const id = nextId++
    setToasts((prev) => [...prev, { id, message, tone }])
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), DURATION_MS)
  }, [])

  const api = useMemo(() => ({ show }), [show])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((toast) => {
          const Icon = ICONS[toast.tone]
          return (
            <div key={toast.id} className={`toast toast-${toast.tone}`}>
              <Icon size={18} aria-hidden="true" />
              {toast.message}
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}
