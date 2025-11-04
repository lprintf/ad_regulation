export const formatDateTime = (isoString?: string) => {
  if (!isoString) return '—'
  try {
    const date = new Date(isoString)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return isoString
  }
}

export const formatRelativeTime = (isoString?: string) => {
  if (!isoString) return '—'
  try {
    const formatter = new Intl.RelativeTimeFormat('zh-CN', { numeric: 'auto' })
    const date = new Date(isoString)
    const now = new Date()
    const diffMs = date.getTime() - now.getTime()
    const diffMinutes = Math.round(diffMs / (1000 * 60))

    if (Math.abs(diffMinutes) < 60) {
      return formatter.format(diffMinutes, 'minute')
    }

    const diffHours = Math.round(diffMinutes / 60)
    if (Math.abs(diffHours) < 24) {
      return formatter.format(diffHours, 'hour')
    }

    const diffDays = Math.round(diffHours / 24)
    return formatter.format(diffDays, 'day')
  } catch {
    return isoString
  }
}
