export interface FbAdAccount {
  id: string
  name: string
}

export type FbTokenType = 'SYSTEM_USER' | 'USER' | null

export interface FbAppAuthRecord {
  appId: string
  userId: string | null
  userName: string | null
  type: FbTokenType
  application: string | null
  isValid: boolean | null
  expiresAt: string | null
  dataAccessExpiresAt: string | null
  scopes: string[]
  granularScopes: Array<Record<string, unknown>>
  accounts: FbAdAccount[]
  lastSyncedAt: string
  lastSyncedBy: string | null
  accessTokenLast4: string | null
}

export interface FbAppSeedPayload {
  appId: string
  appSecret: string
  accessToken: string
}
