import { useEffect, useId, useRef, type ReactNode } from 'react'
import { X } from 'lucide-react'

interface Props {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  /** Action buttons, right-aligned. */
  footer?: ReactNode
  /** "drawer" slides in from the right; "modal" is centered. */
  kind?: 'modal' | 'drawer'
  /** Extra class for sizing, e.g. "modal-wide". */
  className?: string
}

/**
 * Built on the native <dialog> element, which gives focus trapping, Escape to
 * close and a backdrop for free.
 */
export default function Modal({ open, onClose, title, children, footer, kind = 'modal', className = '' }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      className={`${kind} ${className}`}
      aria-labelledby={titleId}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
      onClick={(e) => {
        // A click on the dialog element itself is a click on the backdrop.
        if (e.target === ref.current) onClose()
      }}
    >
      {open && (
        <div className={`${kind}-inner`}>
          <header className={`${kind}-header`}>
            <h2 id={titleId}>{title}</h2>
            <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
              <X size={20} aria-hidden="true" />
            </button>
          </header>
          <div className={`${kind}-content`}>{children}</div>
          {footer && <footer className={`${kind}-footer`}>{footer}</footer>}
        </div>
      )}
    </dialog>
  )
}
