const RESERVED_METADATA_KEYS = [
  'ad_account_id',
  'account_id',
  'accountId',
  'notes',
  'note',
  'remark'
] as const

type ReservedKey = (typeof RESERVED_METADATA_KEYS)[number]

export const mergeBindingMetadata = (
  metadata: Record<string, unknown> | undefined,
  accountId?: string,
  notes?: string
): Record<string, unknown> | undefined => {
  const base: Record<string, unknown> = metadata ? { ...metadata } : {}

  // Normalize reserved keys to avoid duplication
  RESERVED_METADATA_KEYS.forEach(key => {
    if (key in base && key !== 'ad_account_id' && key !== 'notes') {
      delete base[key as ReservedKey]
    }
  })

  if (accountId !== undefined) {
    if (accountId) {
      base.ad_account_id = accountId
    } else {
      delete base.ad_account_id
    }
  }

  if (notes !== undefined) {
    if (notes) {
      base.notes = notes
    } else {
      delete base.notes
    }
  }

  return Object.keys(base).length === 0 ? undefined : base
}

export const stripReservedMetadata = (
  metadata: Record<string, unknown> | undefined
): Record<string, unknown> | undefined => {
  if (!metadata) return undefined
  const result: Record<string, unknown> = { ...metadata }
  RESERVED_METADATA_KEYS.forEach(key => {
    if (key in result) {
      delete result[key as ReservedKey]
    }
  })
  return Object.keys(result).length === 0 ? undefined : result
}
