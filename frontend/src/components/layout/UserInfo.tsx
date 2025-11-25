import { useQuery } from '@tanstack/react-query'
import { fetchCurrentUser } from '../../api/user'

const UserInfo = () => {
  const { data: userInfo, isLoading } = useQuery({
    queryKey: ['current-user'],
    queryFn: fetchCurrentUser,
    staleTime: 5 * 60 * 1000, // 5分钟内不重新获取
    retry: false,
  })

  if (isLoading) {
    return (
      <div className="user-info-compact">
        <div className="user-info-compact__avatar">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" opacity="0.3"></circle>
          </svg>
        </div>
        <div className="user-info-compact__name">...</div>
      </div>
    )
  }

  const displayName = userInfo?.name || userInfo?.email?.split('@')[0] || userInfo?.user_id || 'User'

  return (
    <div className="user-info-compact">
      <div className="user-info-compact__avatar">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
          <circle cx="12" cy="7" r="4"></circle>
        </svg>
      </div>
      <div className="user-info-compact__name">{displayName}</div>
    </div>
  )
}

export default UserInfo
