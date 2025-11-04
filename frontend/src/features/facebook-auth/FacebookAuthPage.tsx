import { useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  fetchFbAppTokens,
  refreshFbAppToken,
  resyncFbAppToken,
  syncFbAppToken
} from '../../api/facebookAuth'
import type {
  FbAdAccount,
  FbAppAuthRecord,
  FbAppSeedPayload,
  FbTokenType
} from '../../types/facebook-auth'
import { formatDateTime, formatRelativeTime } from '../../lib/datetime'

const tokenTypeLabel: Record<FbTokenType, string> = {
  USER: '用户令牌',
  SYSTEM_USER: '系统用户令牌',
  null: '未知类型'
}

type TokenStatus = {
  className: string
  label: string
  description: string
}

const resolveTokenStatus = (record: FbAppAuthRecord): TokenStatus => {
  if (record.isValid === false) {
    return {
      className: 'badge badge--failure',
      label: '失效',
      description: 'Facebook 判定令牌无效（is_valid = false）'
    }
  }

  if (record.isValid === null) {
    const expiresAt = record.expiresAt ? new Date(record.expiresAt) : null
    const expiredNote =
      expiresAt && expiresAt.getTime() < Date.now()
        ? '，过期时间已过，请关注'
        : ''
    return {
      className: 'badge badge--success',
      label: '有效',
      description: `Facebook 未返回 is_valid，默认视为有效${expiredNote}`
    }
  }

  const expiresAt = record.expiresAt ? new Date(record.expiresAt) : null
  const expiredNote =
    expiresAt && expiresAt.getTime() < Date.now()
      ? '，过期时间已过，请关注'
      : ''

  return {
    className: 'badge badge--success',
    label: '有效',
    description: `Facebook 判定令牌有效${expiredNote}`
  }
}

const initialFormValues: FbAppSeedPayload = {
  appId: '',
  appSecret: '',
  accessToken: ''
}

const FacebookAuthPage = () => {
  const queryClient = useQueryClient()
  const [formValues, setFormValues] = useState(initialFormValues)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [isAppTableCollapsed, setIsAppTableCollapsed] = useState(false)
  const [isAccountTableCollapsed, setIsAccountTableCollapsed] = useState(false)
  const [recordPage, setRecordPage] = useState(1)
  const recordsPerPage = 5
  const [accountPage, setAccountPage] = useState(1)
  const accountsPerPage = 10

  const {
    data: records,
    isLoading,
    isFetching,
    refetch
  } = useQuery({
    queryKey: ['fb-app-tokens'],
    queryFn: fetchFbAppTokens,
    staleTime: 30_000
  })

  const syncMutation = useMutation({
    mutationFn: syncFbAppToken,
    onSuccess: () => {
      setErrorMessage(null)
      setSuccessMessage('授权同步成功')
      setFormValues(initialFormValues)
      queryClient.invalidateQueries({ queryKey: ['fb-app-tokens'] })
    },
    onError: error => {
      setSuccessMessage(null)
      if (axios.isAxiosError(error)) {
        const detail = (error.response?.data as { detail?: { message?: string } })?.detail
        setErrorMessage(detail?.message ?? error.message ?? '同步失败，请稍后重试')
      } else {
        setErrorMessage('同步失败，请稍后重试')
      }
    }
  })

  const isSubmitting = syncMutation.isPending

  const hasRecords = useMemo(() => (records?.length ?? 0) > 0, [records])

  const resyncMutation = useMutation<FbAppAuthRecord, unknown, { appId: string; userId: string }>({
    mutationFn: ({ appId, userId }: { appId: string; userId: string }) =>
      resyncFbAppToken(appId, userId),
    onSuccess: () => {
      setErrorMessage(null)
      setSuccessMessage('广告账户更新成功')
      queryClient.invalidateQueries({ queryKey: ['fb-app-tokens'] })
    },
    onError: error => {
      setSuccessMessage(null)
      if (axios.isAxiosError(error)) {
        const detail = (error.response?.data as { detail?: { message?: string } })?.detail
        setErrorMessage(detail?.message ?? error.message ?? '更新失败，请稍后重试')
      } else {
        setErrorMessage('更新失败，请稍后重试')
      }
    }
  })

  const refreshMutation = useMutation<
    FbAppAuthRecord,
    unknown,
    { appId: string; userId: string }
  >({
    mutationFn: ({ appId, userId }) => refreshFbAppToken(appId, userId),
    onSuccess: () => {
      setErrorMessage(null)
      setSuccessMessage('Token 刷新成功')
      queryClient.invalidateQueries({ queryKey: ['fb-app-tokens'] })
    },
    onError: error => {
      setSuccessMessage(null)
      if (axios.isAxiosError(error)) {
        const detail = (error.response?.data as { detail?: { message?: string } })?.detail
        setErrorMessage(detail?.message ?? error.message ?? '刷新失败，请稍后重试')
      } else {
        setErrorMessage('刷新失败，请稍后重试')
      }
    }
  })

  const accountRows = useMemo(() => {
    const rows: Array<{
      account: FbAdAccount
      app: Pick<FbAppAuthRecord, 'appId' | 'application' | 'accessTokenLast4' | 'lastSyncedAt' | 'userName' | 'userId'>
    }> = []
    if (!records) return rows
    for (const record of records) {
      for (const account of record.accounts) {
        rows.push({
          account,
          app: {
            appId: record.appId,
            application: record.application,
            accessTokenLast4: record.accessTokenLast4,
            lastSyncedAt: record.lastSyncedAt,
            userName: record.userName,
            userId: record.userId
          }
        })
      }
    }
    return rows
  }, [records])

  useEffect(() => {
    setRecordPage(1)
    setAccountPage(1)
  }, [records])

  const recordTotalPages = useMemo(() => {
    const total = Math.ceil((records?.length ?? 0) / recordsPerPage)
    return total > 0 ? total : 0
  }, [records, recordsPerPage])

  const accountTotalPages = useMemo(() => {
    const total = Math.ceil(accountRows.length / accountsPerPage)
    return total > 0 ? total : 0
  }, [accountRows, accountsPerPage])

  useEffect(() => {
    if (recordTotalPages > 0 && recordPage > recordTotalPages) {
      setRecordPage(recordTotalPages)
    }
  }, [recordPage, recordTotalPages])

  useEffect(() => {
    if (accountTotalPages > 0 && accountPage > accountTotalPages) {
      setAccountPage(accountTotalPages)
    }
  }, [accountPage, accountTotalPages])

  const paginatedRecords = useMemo(() => {
    if (!records || recordTotalPages === 0) return []
    const start = (recordPage - 1) * recordsPerPage
    return records.slice(start, start + recordsPerPage)
  }, [records, recordPage, recordsPerPage, recordTotalPages])

  const paginatedAccountRows = useMemo(() => {
    if (accountTotalPages === 0) return []
    const start = (accountPage - 1) * accountsPerPage
    return accountRows.slice(start, start + accountsPerPage)
  }, [accountRows, accountPage, accountsPerPage, accountTotalPages])

  const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000

  const handleRefreshToken = (record: FbAppAuthRecord) => {
    if (!record.userId) {
      setSuccessMessage(null)
      setErrorMessage('当前记录缺少 userId，无法刷新 Token。')
      return
    }

    const expiresAtMs = record.expiresAt ? new Date(record.expiresAt).getTime() : null
    const expiresAtValid = expiresAtMs !== null && !Number.isNaN(expiresAtMs)
    let needsConfirmation = !expiresAtValid
    if (!needsConfirmation && expiresAtMs !== null) {
      needsConfirmation = expiresAtMs - Date.now() > THIRTY_DAYS_MS
    }

    if (needsConfirmation) {
      const message = expiresAtValid
        ? '当前 Token 距离过期超过一个月，确认要刷新有效期吗？'
        : '当前 Token 没有过期时间（视为永久），确认要刷新有效期吗？'
      const confirmed = window.confirm(message)
      if (!confirmed) {
        return
      }
    }


    setErrorMessage(null)
    setSuccessMessage(null)
    refreshMutation.mutate({
      appId: record.appId,
      userId: record.userId
    })
  }


  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setErrorMessage(null)
    setSuccessMessage(null)

    if (!formValues.appId || !formValues.appSecret || !formValues.accessToken) {
      setErrorMessage('请完整填写 App ID、App Secret 与 Access Token。')
      return
    }

    syncMutation.mutate(formValues)
  }

  const handleChange =
    (field: keyof FbAppSeedPayload) => (event: React.ChangeEvent<HTMLInputElement>) => {
      const { value } = event.target
      setFormValues(current => ({ ...current, [field]: value }))
    }

  return (
    <div className="page">
      <section className="card">
        <div className="card__header">
          <div>
            <div className="card__title">Facebook 广告账户授权</div>
            <div className="card__subtitle">
              手动录入 App Token，并查看该令牌能够访问的广告账户。Graph API 仅支持有效令牌。
            </div>
          </div>
          <div className="toolbar__group">
            <button
              className="button button--secondary"
              type="button"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              {isFetching ? '刷新中...' : '刷新状态'}
            </button>
          </div>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'grid', gap: '1rem' }}>
          <div style={{ display: 'grid', gap: '1rem' }}>
            <label className="form-label">
              <span>App ID</span>
              <input
                className="input"
                value={formValues.appId}
                onChange={handleChange('appId')}
                placeholder="597335810122604"
                autoComplete="off"
                required
              />
            </label>

            <label className="form-label">
              <span>App Secret</span>
              <input
                className="input"
                value={formValues.appSecret}
                onChange={handleChange('appSecret')}
                placeholder="App Secret"
                autoComplete="off"
                required
              />
            </label>

            <label className="form-label">
              <span>Access Token</span>
              <textarea
                className="textarea"
                rows={3}
                value={formValues.accessToken}
                onChange={event =>
                  setFormValues(current => ({ ...current, accessToken: event.target.value }))
                }
                placeholder="长字符串，通常以 EAA 开头"
                required
              />
            </label>
          </div>

          {errorMessage && (
            <div style={{ color: 'var(--color-danger, #dc2626)', fontWeight: 500 }}>
              {errorMessage}
            </div>
          )}

          {successMessage && (
            <div style={{ color: 'var(--color-success, #16a34a)', fontWeight: 500 }}>
              {successMessage}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
            <button
              type="button"
              className="button button--ghost"
              onClick={() => {
                setFormValues(initialFormValues)
                setErrorMessage(null)
                setSuccessMessage(null)
              }}
              disabled={isSubmitting}
            >
              重置
            </button>
            <button type="submit" className="button button--primary" disabled={isSubmitting}>
              {isSubmitting ? '同步中...' : '同步授权'}
            </button>
          </div>
        </form>
      </section>

      <section className="card">
        <div className="card__header">
          <div>
            <div className="card__title">授权记录</div>
            <div className="card__subtitle">
              展示已保存的 App Token 状态、到期时间与关联的广告账户。
            </div>
          </div>
          <div className="toolbar__group">
            <span style={{ color: 'var(--color-text-muted)' }}>
              共 {records?.length ?? 0} 条
            </span>
            <button
              type="button"
              className="button button--ghost"
              onClick={() => setIsAppTableCollapsed(current => !current)}
            >
              {isAppTableCollapsed ? '展开' : '收起'}
            </button>
          </div>
        </div>

        {isAppTableCollapsed ? (
          <div className="empty-state">已收起，点击“展开”查看授权记录。</div>
        ) : isLoading ? (
        <div className="empty-state">加载中...</div>
      ) : !hasRecords ? (
        <div className="empty-state">暂无授权记录，请先提交 App Token。</div>
      ) : (
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>应用</th>
                  <th>令牌类型</th>
                  <th>状态</th>
                  <th>最后同步</th>
                  <th>过期时间</th>
                  <th>授权范围</th>
                  <th>广告账户</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {paginatedRecords.map(record => {
                  const status = resolveTokenStatus(record)
                  const appName = record.application ?? '未命名应用'
                  const ownerLabel = record.userName ?? record.userId ?? '未知用户'
                  const displayTitle =
                    record.userName || record.userId ? `${appName} · ${ownerLabel}` : appName
                  const rowKey = `${record.appId}-${record.userId ?? 'unknown'}`
                  const isResyncing =
                    resyncMutation.isPending &&
                    resyncMutation.variables?.appId === record.appId &&
                    resyncMutation.variables?.userId === record.userId
                  const isRefreshing =
                    refreshMutation.isPending &&
                    refreshMutation.variables?.appId === record.appId &&
                    refreshMutation.variables?.userId === record.userId

                  return (
                    <tr key={rowKey}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{displayTitle}</div>
                        <div style={{ color: 'var(--color-text-muted)', fontSize: '0.8rem' }}>
                          App ID: {record.appId}
                        </div>
                        <div style={{ color: 'var(--color-text-muted)', fontSize: '0.8rem' }}>
                          授权用户: {ownerLabel}
                        </div>
                        <div style={{ color: 'var(--color-text-muted)', fontSize: '0.8rem' }}>
                          Access Token: ...{record.accessTokenLast4 ?? '****'}
                        </div>
                      </td>
                      <td>{tokenTypeLabel[record.type]}</td>
                      <td>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                          <span className={status.className}>{status.label}</span>
                          <span style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                            {status.description}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div>{formatDateTime(record.lastSyncedAt)}</div>
                        <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                          {formatRelativeTime(record.lastSyncedAt)} ·{' '}
                          {record.lastSyncedBy ?? '未知操作人'}
                        </div>
                      </td>
                      <td>
                        <div>
                          Token: {formatDateTime(record.expiresAt)}{' '}
                          {record.expiresAt ? (
                            <span style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                              （{formatRelativeTime(record.expiresAt)}）
                            </span>
                          ) : (
                            <span style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                              （无过期时间视为有效）
                            </span>
                          )}
                        </div>
                        <div>Data Access: {formatDateTime(record.dataAccessExpiresAt)}</div>
                      </td>
                      <td>
                        {record.scopes.length ? (
                          <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                            {record.scopes.map(scope => (
                              <span key={scope} className="chip chip--muted">
                                {scope}
                              </span>
                            ))}
                          </div>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td>
                        {record.accounts.length ? (
                          <div
                            style={{ display: 'flex', gap: '0.35rem', flexDirection: 'column' }}
                          >
                            {record.accounts.map(account => (
                              <div key={account.id} className="chip">
                                {account.name} ({account.id})
                              </div>
                            ))}
                          </div>
                        ) : (
                          '暂无'
                        )}
                      </td>
                      <td>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                          <button
                            type="button"
                            className="button button--secondary"
                            disabled={!record.userId || isRefreshing}
                            onClick={() => handleRefreshToken(record)}
                          >
                            {isRefreshing ? '刷新中...' : '刷新 Token'}
                          </button>
                          <button
                            type="button"
                            className="button button--secondary"
                            disabled={!record.userId || isResyncing}
                            onClick={() => {
                              if (!record.userId) {
                                setErrorMessage('当前记录缺少 userId，无法更新广告账户。')
                                return
                              }
                              setErrorMessage(null)
                              setSuccessMessage(null)
                              resyncMutation.mutate({
                                appId: record.appId,
                                userId: record.userId
                              })
                            }}
                          >
                            {isResyncing ? '更新中...' : '更新广告账户'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>

            {recordTotalPages > 1 && (
              <div className="table__pagination">
                <button
                  type="button"
                  className="button button--ghost"
                  onClick={() => setRecordPage(current => Math.max(1, current - 1))}
                  disabled={recordPage === 1}
                >
                  上一页
                </button>
                <span style={{ padding: '0 0.5rem' }}>
                  第 {recordPage} / {recordTotalPages} 页
                </span>
                <button
                  type="button"
                  className="button button--ghost"
                  onClick={() => setRecordPage(current => Math.min(recordTotalPages, current + 1))}
                  disabled={recordPage === recordTotalPages}
                >
                  下一页
                </button>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="card">
        <div className="card__header">
          <div>
            <div className="card__title">广告账户 - 授权映射</div>
            <div className="card__subtitle">展示每个广告账户当前绑定的 App Token。</div>
          </div>
          <div className="toolbar__group">
            <span style={{ color: 'var(--color-text-muted)' }}>
              共 {accountRows.length} 条记录
            </span>
            <button
              type="button"
              className="button button--ghost"
              onClick={() => setIsAccountTableCollapsed(current => !current)}
            >
              {isAccountTableCollapsed ? '展开' : '收起'}
            </button>
          </div>
        </div>

        {isAccountTableCollapsed ? (
          <div className="empty-state">已收起，点击“展开”查看映射关系。</div>
        ) : accountRows.length === 0 ? (
          <div className="empty-state">暂无广告账户授权关系。</div>
        ) : (
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>广告账户</th>
                  <th>App 名称</th>
                  <th>授权用户</th>
                  <th>App ID</th>
                  <th>Access Token</th>
                  <th>最后同步</th>
                </tr>
              </thead>
              <tbody>
                {paginatedAccountRows.map(({ account, app }) => (
                  <tr key={`${account.id}-${app.appId}`}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{account.name}</div>
                      <div style={{ color: 'var(--color-text-muted)', fontSize: '0.8rem' }}>
                        {account.id}
                      </div>
                    </td>
                    <td>{app.application ?? '未命名应用'}</td>
                    <td>{app.userName ?? app.userId ?? '未知用户'}</td>
                    <td>{app.appId}</td>
                    <td>...{app.accessTokenLast4 ?? '****'}</td>
                    <td>
                      {formatDateTime(app.lastSyncedAt)}
                      <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                        {formatRelativeTime(app.lastSyncedAt)}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {accountTotalPages > 1 && (
              <div className="table__pagination">
                <button
                  type="button"
                  className="button button--ghost"
                  onClick={() => setAccountPage(current => Math.max(1, current - 1))}
                  disabled={accountPage === 1}
                >
                  上一页
                </button>
                <span style={{ padding: '0 0.5rem' }}>
                  第 {accountPage} / {accountTotalPages} 页
                </span>
                <button
                  type="button"
                  className="button button--ghost"
                  onClick={() =>
                    setAccountPage(current => Math.min(accountTotalPages, current + 1))
                  }
                  disabled={accountPage === accountTotalPages}
                >
                  下一页
                </button>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  )
}

export default FacebookAuthPage
