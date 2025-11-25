import apiClient from '../lib/apiClient'

interface UserInfo {
  user_id: string
  email: string | null
  name: string | null
}

interface SuccessResponse<T> {
  success: boolean
  data: T
  message?: string
}

export const fetchCurrentUser = async (): Promise<UserInfo> => {
  const response = await apiClient.get<SuccessResponse<UserInfo>>('/user/me')
  return response.data.data
}
