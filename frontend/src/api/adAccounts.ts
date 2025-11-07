import apiClient from '../lib/apiClient'
import type { AdAccount } from '../types/ad-accounts'

interface SuccessResponse<T> {
  success: boolean
  data: T
  message?: string
}

type RawAdAccount = {
  id: string
  name: string
  has_auth: boolean
}

type RawAdAccountListResponse = {
  accounts: RawAdAccount[]
  total: number
}

const mapAdAccount = (account: RawAdAccount): AdAccount => ({
  id: account.id,
  name: account.name,
  hasAuth: Boolean(account.has_auth)
})

export const fetchAdAccounts = async (): Promise<AdAccount[]> => {
  const response = await apiClient.get<SuccessResponse<RawAdAccountListResponse>>('/ad-accounts')
  const payload = response.data?.data ?? response.data ?? { accounts: [] }
  const accounts = Array.isArray(payload.accounts) ? payload.accounts : []
  return accounts.map(mapAdAccount)
}

