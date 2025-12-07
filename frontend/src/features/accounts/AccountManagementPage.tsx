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
    <div className="p-4">
      <div className="mb-6">
        <button
          type="button"
          className="button button--primary w-full flex items-center justify-center gap-2"
          style={{ background: channelConfig[channel].color }}
          onClick={() => alert(`${channelConfig[channel].label} OAuth 登录功能开发中`)}
        >
          使用 {channelConfig[channel].label} 登录授权
        </button>
        <div className="text-center text-muted-foreground text-sm my-4 flex items-center gap-2">
          <div className="flex-1 h-px bg-border" />
          <span>或手动输入授权信息</span>
          <div className="flex-1 h-px bg-border" />
        </div>
      </div>

      <form onSubmit={handleSubmit} className="grid gap-4">
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

        {errorMessage && <div className="text-destructive font-medium">{errorMessage}</div>}
        {successMessage && <div className="text-success font-medium">{successMessage}</div>}

        <div className="flex justify-end gap-3">
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
      <div className="flex justify-between items-center mb-4">
        <div className="flex gap-2 items-center">
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
          <h4 className="my-4 text-muted-foreground">授权记录 ({records.length})</h4>
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
                        <div className="font-semibold">{record.application ?? '未命名应用'}</div>
                        <div className="text-muted-foreground text-sm">
                          {record.userName ?? record.userId ?? '未知用户'} · ...{record.accessTokenLast4}
                        </div>
                      </td>
                      <td>{getTokenTypeLabel(record.type)}</td>
                      <td><span className={status.className}>{status.label}</span></td>
                      <td>
                        <div>{record.expiresAt ? formatDateTime(record.expiresAt) : '永久'}</div>
                        {record.expiresAt && <div className="text-xs text-muted-foreground">{formatRelativeTime(record.expiresAt)}</div>}
                      </td>
                      <td>{record.accounts.length} 个</td>
                      <td>
                        <div className="flex gap-2">
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

          <h4 className="mt-6 mb-2 text-muted-foreground">广告账户映射 ({accountRows.length})</h4>
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
                      <div className="font-semibold">{account.name}</div>
                      <div className="text-muted-foreground text-sm">{account.id}</div>
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
      <div className="flex justify-between items-center mb-4">
        <div className="text-muted-foreground text-sm">广告账号数据同步状态</div>
        <button className="button button--secondary" onClick={() => overviewQuery.refetch()} disabled={overviewQuery.isFetching}>
          {overviewQuery.isFetching ? '刷新中...' : '刷新'}
        </button>
      </div>

      {overviewQuery.isLoading ? (
        <div className="empty-state">加载中...</div>
      ) : overviewQuery.isError ? (
        <div className="empty-state text-destructive">加载失败</div>
      ) : items.length === 0 ? (
        <div className="empty-state">暂无账号数据</div>
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))' }}>
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
      <div className="border border-border rounded-lg p-4 bg-card">
        <div className="font-semibold mb-3">
          {item.accountName || item.accountId}
          <div className="text-xs text-muted-foreground font-normal">{item.accountId}</div>
        </div>

        <div className="flex flex-col gap-2 text-sm">
          <div className="flex justify-between items-center">
            <span className="text-muted-foreground">MongoDB:</span>
            <div className="flex items-center gap-2">
              <span className={`${statusClassMap[item.mongodbStatus]} text-xs`}>{statusLabelMap[item.mongodbStatus]}</span>
              <span className="text-sm">{item.mongodbCoverageSince && item.mongodbCoverageUntil ? `${item.mongodbCoverageSince} → ${item.mongodbCoverageUntil}` : '—'}</span>
              <button className="button button--ghost p-1 text-xs" onClick={() => setShowHistory('mongodb')}>📋</button>
              <button className="button button--primary px-2 py-1 text-xs" onClick={() => mongodbSyncMutation.mutate()} disabled={mongodbSyncMutation.isPending || item.mongodbIsRunning}>同步</button>
            </div>
          </div>

          <div className="flex justify-between items-center">
            <span className="text-muted-foreground">Redis:</span>
            <div className="flex items-center gap-2">
              <span className={`${statusClassMap[item.redisStatus]} text-xs`}>{statusLabelMap[item.redisStatus]}</span>
              <span className="text-sm">{item.redisCacheSince && item.redisCacheUntil ? `${item.redisCacheSince} → ${item.redisCacheUntil}` : '—'}</span>
              <button className="button button--ghost p-1 text-xs" onClick={() => setShowHistory('redis')}>📋</button>
              <button className="button button--success px-2 py-1 text-xs" onClick={() => redisSyncMutation.mutate()} disabled={redisSyncMutation.isPending || item.redisIsRunning}>同步</button>
            </div>
          </div>
        </div>
      </div>

      <Modal title={`${showHistory === 'mongodb' ? 'MongoDB' : 'Redis'} 同步历史 - ${item.accountName || item.accountId}`} open={!!showHistory} onClose={() => setShowHistory(null)} width={700}>
        {historyQuery.isLoading ? (
          <div>加载中...</div>
        ) : historyQuery.isError ? (
          <div className="text-destructive">加载失败</div>
        ) : !(historyQuery.data?.items?.length) ? (
          <div>暂无历史记录</div>
        ) : (
          <div className="flex flex-col gap-3 max-h-[400px] overflow-auto">
            {historyQuery.data.items.map((record: SyncHistoryRecord) => (
              <div key={record.id} className="p-3 border border-border rounded">
                <div className="flex justify-between mb-2">
                  <span className={statusClassMap[record.status]}>{statusLabelMap[record.status]}</span>
                  <span className="text-sm text-muted-foreground">{formatRelativeTime(record.startedAt)}</span>
                </div>
                <div className="text-sm text-muted-foreground">
                  范围: {record.since} → {record.until} | 记录: {record.recordsCount} | 耗时: {record.durationSeconds ? `${(record.durationSeconds / 60).toFixed(1)}分` : '—'}
                </div>
                {record.errorMessage && <div className="mt-2 text-sm text-destructive">{record.errorMessage}</div>}
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
      <section className="card mb-4">
        <div className="card__header border-b-0 pb-0">
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
