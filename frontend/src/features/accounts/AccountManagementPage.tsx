import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Modal, Tabs } from '@/components/ui'
import {
  fetchFbAppTokens,
  refreshFbAppToken,
  resyncFbAppToken,
  syncFbAppToken
} from '../../api/facebookAuth'
import { fetchSyncOverview, fetchSyncHistory, triggerMongodbSync, triggerRedisSync } from '../../api/insights'
import type { FbAdAccount, FbAppAuthRecord, FbAppSeedPayload, FbTokenType } from '../../types/facebook-auth'
import type { InsightSyncStatus, SyncOverviewItem, SyncHistoryRecord } from '../../types/insights'
import { formatDateTime, formatRelativeTime } from '../../lib/datetime'

type AdChannel = 'facebook' | 'google' | 'pinterest'

const channelConfig: Record<AdChannel, { label: string; color: string; icon: string }> = {
  facebook: { label: 'Facebook', color: '#1877f2', icon: 'f' },
  google: { label: 'Google Ads', color: '#4285f4', icon: 'G' },
  pinterest: { label: 'Pinterest', color: '#e60023', icon: 'P' }
}

// ===== Authorization Panel =====
const AuthorizationPanel = ({ channel, onClose }: { channel: AdChannel; onClose: () => void }) => {
  const queryClient = useQueryClient()
  const [formValues, setFormValues] = useState<FbAppSeedPayload>({ appId: '', appSecret: '', accessToken: '' })
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const syncMutation = useMutation({
    mutationFn: syncFbAppToken,
    onSuccess: () => {
      setErrorMessage(null)
      setSuccessMessage('授权同步成功')
      setFormValues({ appId: '', appSecret: '', accessToken: '' })
      queryClient.invalidateQueries({ queryKey: ['fb-app-tokens'] })
      setTimeout(onClose, 1500)
    },
    onError: (error: any) => {
      setSuccessMessage(null)
      setErrorMessage(error?.response?.data?.detail?.message ?? error?.message ?? '同步失败')
    }
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (channel !== 'facebook') {
      setErrorMessage(`${channelConfig[channel].label} 授权功能开发中`)
      return
    }
    if (!formValues.appId || !formValues.appSecret || !formValues.accessToken) {
      setErrorMessage('请完整填写所有字段')
      return
    }
    syncMutation.mutate(formValues)
  }

  return (
    <div style={{ padding: '1rem' }}>
      <div style={{ marginBottom: '1.5rem' }}>
        <button
          type="button"
          className="button button--primary"
          style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', background: channelConfig[channel].color }}
          onClick={() => alert(`${channelConfig[channel].label} OAuth 登录功能开发中`)}
        >
          使用 {channelConfig[channel].label} 登录授权
        </button>
        <div style={{ textAlign: 'center', color: 'var(--color-text-muted)', fontSize: '0.875rem', margin: '1rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div style={{ flex: 1, height: '1px', background: 'var(--color-border)' }} />
          <span>或手动输入授权信息</span>
          <div style={{ flex: 1, height: '1px', background: 'var(--color-border)' }} />
        </div>
      </div>

      <form onSubmit={handleSubmit} style={{ display: 'grid', gap: '1rem' }}>
        <label className="form-label">
          <span>App ID</span>
          <input className="input" value={formValues.appId} onChange={e => setFormValues(prev => ({ ...prev, appId: e.target.value }))} placeholder="应用 ID" />
        </label>
        <label className="form-label">
          <span>App Secret</span>
          <input className="input" type="password" value={formValues.appSecret} onChange={e => setFormValues(prev => ({ ...prev, appSecret: e.target.value }))} placeholder="应用密钥" />
        </label>
        <label className="form-label">
          <span>Access Token</span>
          <textarea className="textarea" rows={3} value={formValues.accessToken} onChange={e => setFormValues(prev => ({ ...prev, accessToken: e.target.value }))} placeholder="访问令牌" />
        </label>

        {errorMessage && <div style={{ color: 'var(--color-danger)', fontWeight: 500 }}>{errorMessage}</div>}
        {successMessage && <div style={{ color: 'var(--color-success)', fontWeight: 500 }}>{successMessage}</div>}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
          <button type="button" className="button button--ghost" onClick={onClose}>取消</button>
          <button type="submit" className="button button--primary" disabled={syncMutation.isPending}>
            {syncMutation.isPending ? '同步中...' : '同步授权'}
          </button>
        </div>
      </form>
    </div>
  )
}

// ===== Auth Records Tab =====
const AuthRecordsTab = () => {
  const queryClient = useQueryClient()
  const [authModalOpen, setAuthModalOpen] = useState(false)
  const [selectedChannel, setSelectedChannel] = useState<AdChannel>('facebook')

  const { data: records, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['fb-app-tokens'],
    queryFn: fetchFbAppTokens,
    staleTime: 30_000
  })

  const resyncMutation = useMutation({
    mutationFn: ({ appId, userId }: { appId: string; userId: string }) => resyncFbAppToken(appId, userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['fb-app-tokens'] })
  })

  const refreshMutation = useMutation({
    mutationFn: ({ appId, userId }: { appId: string; userId: string }) => refreshFbAppToken(appId, userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['fb-app-tokens'] })
  })

  const getTokenTypeLabel = (type: FbTokenType) => type === 'USER' ? '用户令牌' : type === 'SYSTEM_USER' ? '系统用户' : '未知'

  const resolveStatus = (record: FbAppAuthRecord) => {
    if (record.isValid === false) return { className: 'badge badge--failure', label: '失效' }
    return { className: 'badge badge--success', label: '有效' }
  }

  const accountRows = useMemo(() => {
    const rows: { account: FbAdAccount; app: Pick<FbAppAuthRecord, 'appId' | 'application' | 'accessTokenLast4'> }[] = []
    for (const record of records ?? []) {
      for (const account of record.accounts) {
        rows.push({ account, app: { appId: record.appId, application: record.application, accessTokenLast4: record.accessTokenLast4 } })
      }
    }
    return rows
  }, [records])

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <select className="select" value={selectedChannel} onChange={e => setSelectedChannel(e.target.value as AdChannel)}>
            {Object.entries(channelConfig).map(([key, cfg]) => (
              <option key={key} value={key}>{cfg.label}</option>
            ))}
          </select>
          <button className="button button--primary" onClick={() => setAuthModalOpen(true)}>
            添加授权
          </button>
        </div>
        <button className="button button--secondary" onClick={() => refetch()} disabled={isFetching}>
          {isFetching ? '刷新中...' : '刷新状态'}
        </button>
      </div>

      {isLoading ? (
        <div className="empty-state">加载中...</div>
      ) : !records?.length ? (
        <div className="empty-state">暂无授权记录，请先添加授权</div>
      ) : (
        <>
          <h4 style={{ margin: '1rem 0 0.5rem', color: 'var(--color-text-muted)' }}>授权记录 ({records.length})</h4>
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>应用</th>
                  <th>令牌类型</th>
                  <th>状态</th>
                  <th>过期时间</th>
                  <th>广告账户</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {records.map(record => {
                  const status = resolveStatus(record)
                  const rowKey = `${record.appId}-${record.userId ?? 'unknown'}`
                  return (
                    <tr key={rowKey}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{record.application ?? '未命名应用'}</div>
                        <div style={{ color: 'var(--color-text-muted)', fontSize: '0.8rem' }}>
                          {record.userName ?? record.userId ?? '未知用户'} · ...{record.accessTokenLast4}
                        </div>
                      </td>
                      <td>{getTokenTypeLabel(record.type)}</td>
                      <td><span className={status.className}>{status.label}</span></td>
                      <td>
                        <div>{record.expiresAt ? formatDateTime(record.expiresAt) : '永久'}</div>
                        {record.expiresAt && <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>{formatRelativeTime(record.expiresAt)}</div>}
                      </td>
                      <td>{record.accounts.length} 个</td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <button className="button button--ghost" onClick={() => record.userId && refreshMutation.mutate({ appId: record.appId, userId: record.userId })} disabled={!record.userId || refreshMutation.isPending}>
                            刷新Token
                          </button>
                          <button className="button button--ghost" onClick={() => record.userId && resyncMutation.mutate({ appId: record.appId, userId: record.userId })} disabled={!record.userId || resyncMutation.isPending}>
                            更新账户
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <h4 style={{ margin: '1.5rem 0 0.5rem', color: 'var(--color-text-muted)' }}>广告账户映射 ({accountRows.length})</h4>
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>广告账户</th>
                  <th>关联应用</th>
                  <th>Access Token</th>
                </tr>
              </thead>
              <tbody>
                {accountRows.map(({ account, app }) => (
                  <tr key={`${account.id}-${app.appId}`}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{account.name}</div>
                      <div style={{ color: 'var(--color-text-muted)', fontSize: '0.8rem' }}>{account.id}</div>
                    </td>
                    <td>{app.application ?? '未命名'}</td>
                    <td>...{app.accessTokenLast4}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <Modal title={`添加 ${channelConfig[selectedChannel].label} 授权`} open={authModalOpen} onClose={() => setAuthModalOpen(false)} width={500}>
        <AuthorizationPanel channel={selectedChannel} onClose={() => setAuthModalOpen(false)} />
      </Modal>
    </div>
  )
}

// ===== Sync Status Tab =====
const statusClassMap: Record<InsightSyncStatus, string> = {
  pending: 'badge badge--warning',
  running: 'badge badge--info',
  success: 'badge badge--success',
  failed: 'badge badge--failure'
}

const statusLabelMap: Record<InsightSyncStatus, string> = {
  pending: '待同步',
  running: '同步中',
  success: '已完成',
  failed: '失败'
}

const SyncStatusTab = () => {
  const overviewQuery = useQuery({
    queryKey: ['sync-overview'],
    queryFn: fetchSyncOverview,
    refetchInterval: 30_000
  })

  const items: SyncOverviewItem[] = overviewQuery.data?.items ?? []

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>广告账号数据同步状态</div>
        <button className="button button--secondary" onClick={() => overviewQuery.refetch()} disabled={overviewQuery.isFetching}>
          {overviewQuery.isFetching ? '刷新中...' : '刷新'}
        </button>
      </div>

      {overviewQuery.isLoading ? (
        <div className="empty-state">加载中...</div>
      ) : overviewQuery.isError ? (
        <div className="empty-state" style={{ color: 'var(--color-danger)' }}>加载失败</div>
      ) : items.length === 0 ? (
        <div className="empty-state">暂无账号数据</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '1rem' }}>
          {items.map(item => <SyncAccountCard key={item.accountId} item={item} />)}
        </div>
      )}
    </div>
  )
}

const SyncAccountCard = ({ item }: { item: SyncOverviewItem }) => {
  const queryClient = useQueryClient()
  const [showHistory, setShowHistory] = useState<'mongodb' | 'redis' | null>(null)

  const mongodbSyncMutation = useMutation({
    mutationFn: () => triggerMongodbSync(item.accountId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sync-overview'] })
      queryClient.invalidateQueries({ queryKey: ['sync-history'] })
    }
  })

  const redisSyncMutation = useMutation({
    mutationFn: () => triggerRedisSync(item.accountId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sync-overview'] })
      queryClient.invalidateQueries({ queryKey: ['sync-history'] })
    }
  })

  const historyQuery = useQuery({
    queryKey: ['sync-history', item.accountId, showHistory],
    queryFn: () => fetchSyncHistory({ accountId: item.accountId, dataTarget: showHistory!, page: 1, pageSize: 10 }),
    enabled: !!showHistory
  })

  return (
    <>
      <div style={{ border: '1px solid var(--color-border)', borderRadius: '0.5rem', padding: '1rem', backgroundColor: 'var(--color-bg-elevated)' }}>
        <div style={{ fontWeight: 600, marginBottom: '0.75rem' }}>
          {item.accountName || item.accountId}
          <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', fontWeight: 400 }}>{item.accountId}</div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.875rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--color-text-muted)' }}>MongoDB:</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span className={statusClassMap[item.mongodbStatus]} style={{ fontSize: '0.75rem' }}>{statusLabelMap[item.mongodbStatus]}</span>
              <span style={{ fontSize: '0.8rem' }}>{item.mongodbCoverageSince && item.mongodbCoverageUntil ? `${item.mongodbCoverageSince} → ${item.mongodbCoverageUntil}` : '—'}</span>
              <button className="button button--ghost" style={{ padding: '0.25rem', fontSize: '0.75rem' }} onClick={() => setShowHistory('mongodb')}>📋</button>
              <button className="button button--primary" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }} onClick={() => mongodbSyncMutation.mutate()} disabled={mongodbSyncMutation.isPending || item.mongodbIsRunning}>同步</button>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--color-text-muted)' }}>Redis:</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span className={statusClassMap[item.redisStatus]} style={{ fontSize: '0.75rem' }}>{statusLabelMap[item.redisStatus]}</span>
              <span style={{ fontSize: '0.8rem' }}>{item.redisCacheSince && item.redisCacheUntil ? `${item.redisCacheSince} → ${item.redisCacheUntil}` : '—'}</span>
              <button className="button button--ghost" style={{ padding: '0.25rem', fontSize: '0.75rem' }} onClick={() => setShowHistory('redis')}>📋</button>
              <button className="button button--success" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }} onClick={() => redisSyncMutation.mutate()} disabled={redisSyncMutation.isPending || item.redisIsRunning}>同步</button>
            </div>
          </div>
        </div>
      </div>

      <Modal title={`${showHistory === 'mongodb' ? 'MongoDB' : 'Redis'} 同步历史 - ${item.accountName || item.accountId}`} open={!!showHistory} onClose={() => setShowHistory(null)} width={700}>
        {historyQuery.isLoading ? (
          <div>加载中...</div>
        ) : historyQuery.isError ? (
          <div style={{ color: 'var(--color-danger)' }}>加载失败</div>
        ) : !(historyQuery.data?.items?.length) ? (
          <div>暂无历史记录</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', maxHeight: '400px', overflow: 'auto' }}>
            {historyQuery.data.items.map((record: SyncHistoryRecord) => (
              <div key={record.id} style={{ padding: '0.75rem', border: '1px solid var(--color-border)', borderRadius: '0.25rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                  <span className={statusClassMap[record.status]}>{statusLabelMap[record.status]}</span>
                  <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>{formatRelativeTime(record.startedAt)}</span>
                </div>
                <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
                  范围: {record.since} → {record.until} | 记录: {record.recordsCount} | 耗时: {record.durationSeconds ? `${(record.durationSeconds / 60).toFixed(1)}分` : '—'}
                </div>
                {record.errorMessage && <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: 'var(--color-danger)' }}>{record.errorMessage}</div>}
              </div>
            ))}
          </div>
        )}
      </Modal>
    </>
  )
}

// ===== Main Page =====
const AccountManagementPage = () => {
  return (
    <div className="page">
      <section className="card" style={{ marginBottom: '1rem' }}>
        <div className="card__header" style={{ borderBottom: 'none', paddingBottom: 0 }}>
          <div>
            <div className="card__title">账号管理</div>
            <div className="card__subtitle">管理广告账号授权和数据同步</div>
          </div>
        </div>
      </section>

      <Tabs
        defaultActiveKey="auth"
        items={[
          { key: 'auth', label: '账号授权', children: <AuthRecordsTab /> },
          { key: 'sync', label: '数据同步', children: <SyncStatusTab /> }
        ]}
      />
    </div>
  )
}

export default AccountManagementPage
