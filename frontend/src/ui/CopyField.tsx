import { useState } from 'react'
import { Check, Copy } from 'lucide-react'

/** Read-only value with a copy button, e.g. an API key shown once. */
export default function CopyField({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard can be blocked (e.g. non-secure context); the value is still selectable.
    }
  }

  return (
    <div className="copy-field">
      <code aria-label={label}>{value}</code>
      <button type="button" className="btn btn-secondary btn-sm" onClick={copy}>
        {copied ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}
