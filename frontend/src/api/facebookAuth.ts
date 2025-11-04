import apiClient from '../lib/apiClient'
import type { FbAdAccount, FbAppAuthRecord, FbAppSeedPayload, FbTokenType } from '../types/facebook-auth'

interface SuccessResponse<T> {
  success: boolean
  data: T
  message?: string
}

type RawFbAdAccount = {
  id: string
  name: string
}

type RawFbAppAuthRecord = {
  app_id: string
  user_id: string | null
  user_name: string | null
  type: FbTokenType
  application: string | null
  is_valid: boolean | null
  expires_at: string | null
  data_access_expires_at: string | null
  scopes: string[]
  granular_scopes: Array<Record<string, unknown>>
  accounts: RawFbAdAccount[]
  last_synced_at: string
  last_synced_by: string | null
  access_token_last4: string | null
}

const mapAccount = (account: RawFbAdAccount): FbAdAccount => ({
  id: account.id,
  name: account.name
})

const mapAuthRecord = (record: RawFbAppAuthRecord): FbAppAuthRecord => ({
  appId: record.app_id,
  userId: record.user_id,
  userName: record.user_name,
  type: record.type,
  application: record.application,
  isValid: record.is_valid,
  expiresAt: record.expires_at,
  dataAccessExpiresAt: record.data_access_expires_at,
  scopes: record.scopes ?? [],
  granularScopes: record.granular_scopes ?? [],
  accounts: (record.accounts ?? []).map(mapAccount),
  lastSyncedAt: record.last_synced_at,
  lastSyncedBy: record.last_synced_by,
  accessTokenLast4: record.access_token_last4
})

export const fetchFbAppTokens = async (): Promise<FbAppAuthRecord[]> => {
  const response = await apiClient.get<SuccessResponse<RawFbAppAuthRecord[]>>('/fb/auth/app-tokens')
  return response.data.data.map(mapAuthRecord)
}

export const syncFbAppToken = async (payload: FbAppSeedPayload): Promise<FbAppAuthRecord> => {
  const response = await apiClient.post<SuccessResponse<RawFbAppAuthRecord>>('/fb/auth/app-tokens', {
    app_id: payload.appId.trim(),
    app_secret: payload.appSecret.trim(),
    access_token: payload.accessToken.trim()
  })
  return mapAuthRecord(response.data.data)
}

export const resyncFbAppToken = async (
  appId: string,
  tokenUserId: string
): Promise<FbAppAuthRecord> => {
  const response = await apiClient.post<SuccessResponse<RawFbAppAuthRecord>>(
    `/fb/auth/app-tokens/${encodeURIComponent(appId)}/${encodeURIComponent(tokenUserId)}/sync`
  )
  return mapAuthRecord(response.data.data)
}

export const refreshFbAppToken = async (
  appId: string,
  tokenUserId: string
): Promise<FbAppAuthRecord> => {
  const response = await apiClient.post<SuccessResponse<RawFbAppAuthRecord>>(
    `/fb/auth/app-tokens/${encodeURIComponent(appId)}/${encodeURIComponent(tokenUserId)}/refresh`
  )
  return mapAuthRecord(response.data.data)
}
