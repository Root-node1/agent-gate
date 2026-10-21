const moneyFormats = new Map<string, Intl.NumberFormat>()

/** "$1,234.50" for USD; falls back to "1,234.50 XYZ" for unknown codes. */
export function formatMoney(amount: number, currency = 'USD'): string {
  let format = moneyFormats.get(currency)
  if (!format) {
    try {
      format = new Intl.NumberFormat('en-US', { style: 'currency', currency })
    } catch {
      return `${amount.toFixed(2)} ${currency}`
    }
    moneyFormats.set(currency, format)
  }
  return format.format(amount)
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

/** Full timestamp with seconds, for audit logs. */
export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const relative = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

/** "just now", "4 minutes ago", "yesterday", "in 3 hours". */
export function timeAgo(iso: string, now = Date.now()): string {
  const minutes = Math.round((new Date(iso).getTime() - now) / 60_000)
  if (minutes === 0) return 'just now'
  if (Math.abs(minutes) < 60) return relative.format(minutes, 'minute')
  const hours = Math.round(minutes / 60)
  if (Math.abs(hours) < 24) return relative.format(hours, 'hour')
  return relative.format(Math.round(hours / 24), 'day')
}

/** Short request id for tables: first 8 characters. */
export function shortId(id: string): string {
  return id.slice(0, 8)
}

export function percent(part: number, whole: number): number {
  return whole <= 0 ? 0 : Math.min(100, Math.round((part / whole) * 100))
}
