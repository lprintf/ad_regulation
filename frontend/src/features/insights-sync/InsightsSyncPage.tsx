import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchSyncOverview, fetchSyncHistory, triggerSync } from '../../api/insights'
import { formatDateTime, formatRelativeTime } from '../../lib/datetime'
import type {
  InsightSyncStatus,
  SyncOverviewItem,
  SyncHistoryRecord,
  InsightSyncTriggerResult
} from '../../types/insights'

type TabId = 'overview' | 'history'

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

const triggerLabelMap: Record<string, string> = {
  manual: '手动触发',
  auto: '自动调度',
  retry: '重试'
}

const dataTargetLabelMap: Record<string, string> = {
  mongodb: 'MongoDB',
  redis: 'Redis',
  hybrid: 'MongoDB + Redis'
}

const dataTargetColorMap: Record<string, string> = {
  mongodb: 'var(--color-primary)',
  redis: 'var(--color-success)',
  hybrid: 'var(--color-warning)'
}

const InsightsSyncPage = () => {
  const [activeTab, setActiveTab] = useState<TabId>('overview')

  return (
    <div className="page">
      {/* Tab Navigation */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card__header">
          <div>
            <div className="card__title">洞察数据同步管理</div>
            <div className="card__subtitle">管理 Facebook 广告洞察数据的同步任务</div>
          </div>
        </div>
        <div
          className="card__body"
          style={{
            borderTop: '1px solid var(--color-border)',
            padding: 0,
            display: 'flex',
            gap: 0
          }}
        >
          <button
            className={`tab-button ${activeTab === 'overview' ? 'tab-button--active' : ''}`}
            onClick={() => setActiveTab('overview')}
            style={{
              flex: 1,
              padding: '1rem',
              border: 'none',
              background: activeTab === 'overview' ? 'var(--color-bg-elevated)' : 'transparent',
              borderBottom: activeTab === 'overview' ? '2px solid var(--color-primary)' : '2px solid transparent',
              cursor: 'pointer',
              fontWeight: activeTab === 'overview' ? 600 : 400,
              transition: 'all 0.2s'
            }}
          >
            概览
          </button>
          <button
            className={`tab-button ${activeTab === 'history' ? 'tab-button--active' : ''}`}
            onClick={() => setActiveTab('history')}
            style={{
              flex: 1,
              padding: '1rem',
              border: 'none',
              background: activeTab === 'history' ? 'var(--color-bg-elevated)' : 'transparent',
              borderBottom: activeTab === 'history' ? '2px solid var(--color-primary)' : '2px solid transparent',
              cursor: 'pointer',
              fontWeight: activeTab === 'history' ? 600 : 400,
              transition: 'all 0.2s'
            }}
          >
            同步历史
          </button>
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && <OverviewTab />}
      {activeTab === 'history' && <HistoryTab />}
    </div>
  )
}

// ===== Overview Tab =====

const OverviewTab = () => {
  const queryClient = useQueryClient()
  const [accountInput, setAccountInput] = useState('')
  const [sinceDate, setSinceDate] = useState('')
  const [untilDate, setUntilDate] = useState('')
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(
    null
  )
  const [lastResult, setLastResult] = useState<InsightSyncTriggerResult | null>(null)

  const overviewQuery = useQuery({
    queryKey: ['sync-overview'],
    queryFn: fetchSyncOverview,
    refetchInterval: 30_000
  })

  const syncMutation = useMutation({
    mutationFn: triggerSync,
    onSuccess: (result: InsightSyncTriggerResult) => {
      queryClient.invalidateQueries({ queryKey: ['sync-overview'] })
      queryClient.invalidateQueries({ queryKey: ['sync-history'] })
      const processedCount = Object.keys(result.processedAccounts ?? {}).length
      const failedCount = Object.keys(result.failedAccounts ?? {}).length
      setLastResult(result)
      setFeedback({
        type: failedCount > 0 ? 'error' : 'success',
        message: `同步已触发：${result.totalAccounts} 个账号，成功 ${processedCount} 个，失败 ${failedCount} 个`
      })
    },
    onError: error => {
      const message = error instanceof Error ? error.message : '触发同步失败'
      setFeedback({ type: 'error', message })
      setLastResult(null)
    }
  })

  const parseAccountIds = (raw: string): string[] => {
    const normalized = raw
      .split(/[\s,]+/)
      .map(segment => segment.trim())
      .filter(Boolean)
      .map(value => {
        const stripped = value.replace(/^act_/i, '')
        return stripped ? `act_${stripped}` : ''
      })
      .filter(Boolean)
    return Array.from(new Set(normalized))
  }

  const handleTriggerSync = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!sinceDate || !untilDate) {
      setFeedback({ type: 'error', message: '请选择起始和结束日期' })
      return
    }
    if (sinceDate > untilDate) {
      setFeedback({ type: 'error', message: '起始日期需不晚于结束日期' })
      return
    }
    const accountIds = parseAccountIds(accountInput)
    setFeedback(null)
    syncMutation.mutate({
      accountIds: accountIds.length > 0 ? accountIds : undefined,
      since: sinceDate,
      until: untilDate
    })
  }

  const items: SyncOverviewItem[] = overviewQuery.data?.items ?? []

  return (
    <>
      {/* Trigger Form */}
      <section className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card__header">
          <div className="card__title">手动触发同步</div>
        </div>
        <form onSubmit={handleTriggerSync} className="card__body">
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(220px, 2fr) repeat(2, minmax(140px, 1fr)) auto',
              gap: '1rem',
              alignItems: 'end'
            }}
          >
            <label className="form-label" style={{ display: 'flex', flexDirection: 'column' }}>
              <span>广告账号（可选，多值用逗号或换行分隔）</span>
              <textarea
                className="textarea"
                rows={2}
                value={accountInput}
                onChange={event => setAccountInput(event.target.value)}
                placeholder="act_123, act_456 (留空表示全部账号)"
                spellCheck={false}
              />
            </label>
            <label className="form-label">
              <span>起始日期</span>
              <input
                className="input"
                type="date"
                value={sinceDate}
                onChange={event => setSinceDate(event.target.value)}
              />
            </label>
            <label className="form-label">
              <span>结束日期</span>
              <input
                className="input"
                type="date"
                value={untilDate}
                onChange={event => setUntilDate(event.target.value)}
              />
            </label>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button
                className="button button--primary"
                type="submit"
                disabled={syncMutation.isPending}
              >
                {syncMutation.isPending ? '触发中…' : '触发同步'}
              </button>
              <button
                className="button button--ghost"
                type="button"
                onClick={() => {
                  setAccountInput('')
                  setSinceDate('')
                  setUntilDate('')
                  setFeedback(null)
                  setLastResult(null)
                }}
                disabled={syncMutation.isPending}
              >
                清空
              </button>
            </div>
          </div>

          {feedback && (
            <div
              style={{
                marginTop: '1rem',
                padding: '0.75rem 1rem',
                borderRadius: '0.5rem',
                backgroundColor:
                  feedback.type === 'success' ? 'rgba(38, 176, 108, 0.1)' : 'rgba(225, 77, 64, 0.1)',
                color: feedback.type === 'success' ? 'var(--color-success)' : 'var(--color-danger)'
              }}
            >
              {feedback.message}
            </div>
          )}
        </form>
      </section>

      {/* Account Cards Grid */}
      <section className="card">
        <div className="card__header">
          <div>
            <div className="card__title">账号同步状态</div>
            <div className="card__subtitle">所有广告账号的当前同步状态</div>
          </div>
          <button
            className="button button--ghost"
            onClick={() => overviewQuery.refetch()}
            disabled={overviewQuery.isFetching}
          >
            {overviewQuery.isFetching ? '刷新中…' : '刷新'}
          </button>
        </div>

        {overviewQuery.isLoading ? (
          <div className="card__body">加载中…</div>
        ) : overviewQuery.isError ? (
          <div className="card__body" style={{ color: 'var(--color-danger)' }}>
            数据加载失败，请刷新重试
          </div>
        ) : items.length === 0 ? (
          <div className="card__body">暂无账号数据</div>
        ) : (
          <div
            className="card__body"
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))',
              gap: '1rem'
            }}
          >
            {items.map(item => (
              <AccountCard key={item.accountId} item={item} />
            ))}
          </div>
        )}
      </section>
    </>
  )
}

interface AccountCardProps {
  item: SyncOverviewItem
}

const AccountCard = ({ item }: AccountCardProps) => {
  const badgeClass = statusClassMap[item.status] ?? 'badge'
  const statusLabel = statusLabelMap[item.status]

  return (
    <div
      style={{
        border: '1px solid var(--color-border)',
        borderRadius: '0.5rem',
        padding: '1rem',
        backgroundColor: item.isRunning ? 'rgba(24, 119, 242, 0.05)' : 'var(--color-bg-elevated)'
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '0.75rem' }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: '1rem' }}>
            {item.accountName || item.accountId}
          </div>
          <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem', marginTop: '0.25rem' }}>
            {item.accountId}
          </div>
        </div>
        <span className={badgeClass}>{statusLabel}</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.875rem' }}>
        {/* MongoDB 数据覆盖范围 */}
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--color-text-muted)' }}>MongoDB:</span>
          <span style={{ color: 'var(--color-primary)', fontWeight: 500 }}>
            {item.mongodbCoverageSince && item.mongodbCoverageUntil
              ? `${item.mongodbCoverageSince} → ${item.mongodbCoverageUntil}`
              : '—'}
          </span>
        </div>

        {/* Redis 缓存范围 */}
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--color-text-muted)' }}>Redis缓存:</span>
          <span style={{ color: 'var(--color-success)', fontWeight: 500 }}>
            {item.redisCacheSince && item.redisCacheUntil
              ? `${item.redisCacheSince} → ${item.redisCacheUntil}`
              : '—'}
          </span>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--color-text-muted)' }}>最近同步:</span>
          <span>
            {item.lastSyncedAt
              ? formatRelativeTime(item.lastSyncedAt)
              : '—'}
          </span>
        </div>

        {item.lastError && (
          <div
            style={{
              marginTop: '0.5rem',
              padding: '0.5rem',
              borderRadius: '0.25rem',
              backgroundColor: 'rgba(225, 77, 64, 0.1)',
              color: 'var(--color-danger)',
              fontSize: '0.75rem'
            }}
          >
            {item.lastError}
          </div>
        )}
      </div>
    </div>
  )
}

// ===== History Tab =====

const HistoryTab = () => {
  const [page, setPage] = useState(1)
  const [selectedRecord, setSelectedRecord] = useState<SyncHistoryRecord | null>(null)

  const historyQuery = useQuery({
    queryKey: ['sync-history', page],
    queryFn: () => fetchSyncHistory({ page, pageSize: 20 }),
    refetchInterval: 60_000
  })

  const items: SyncHistoryRecord[] = historyQuery.data?.items ?? []
  const total = historyQuery.data?.total ?? 0
  const totalPages = Math.ceil(total / 20)

  return (
    <>
      <section className="card">
        <div className="card__header">
          <div>
            <div className="card__title">同步历史记录</div>
            <div className="card__subtitle">
              共 {total} 条记录，第 {page} / {totalPages} 页
            </div>
          </div>
          <button
            className="button button--ghost"
            onClick={() => historyQuery.refetch()}
            disabled={historyQuery.isFetching}
          >
            {historyQuery.isFetching ? '刷新中…' : '刷新'}
          </button>
        </div>

        {historyQuery.isLoading ? (
          <div className="card__body">加载中…</div>
        ) : historyQuery.isError ? (
          <div className="card__body" style={{ color: 'var(--color-danger)' }}>
            数据加载失败
          </div>
        ) : items.length === 0 ? (
          <div className="card__body">暂无历史记录</div>
        ) : (
          <>
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th style={{ width: '180px' }}>账号</th>
                    <th style={{ width: '80px' }}>状态</th>
                    <th style={{ width: '90px' }}>触发方式</th>
                    <th style={{ width: '110px' }}>数据目标</th>
                    <th style={{ width: '120px' }}>同步范围</th>
                    <th style={{ width: '80px' }}>记录数</th>
                    <th style={{ width: '80px' }}>进度</th>
                    <th style={{ width: '140px' }}>开始时间</th>
                    <th style={{ width: '80px' }}>耗时</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map(record => (
                    <tr key={record.id}>
                      <td>
                        <div style={{ fontWeight: 600 }}>
                          {record.accountName || record.accountId}
                        </div>
                        {record.accountName && (
                          <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                            {record.accountId}
                          </div>
                        )}
                      </td>
                      <td>
                        <span className={statusClassMap[record.status]}>
                          {statusLabelMap[record.status]}
                        </span>
                      </td>
                      <td>{triggerLabelMap[record.triggerType] || record.triggerType}</td>
                      <td>
                        <span style={{
                          color: dataTargetColorMap[record.dataTarget],
                          fontWeight: 500,
                          fontSize: '0.875rem'
                        }}>
                          {dataTargetLabelMap[record.dataTarget] || record.dataTarget}
                        </span>
                      </td>
                      <td>
                        <div style={{ fontSize: '0.875rem' }}>
                          {record.since}
                        </div>
                        <div style={{ fontSize: '0.875rem' }}>
                          {record.until}
                        </div>
                      </td>
                      <td>{record.recordsCount.toLocaleString()}</td>
                      <td>
                        <div>{record.percentComplete}%</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                          {record.processedDays}/{record.totalDays} 天
                        </div>
                      </td>
                      <td>
                        <div>{formatDateTime(record.startedAt)}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                          {formatRelativeTime(record.startedAt)}
                        </div>
                      </td>
                      <td>
                        {record.durationSeconds
                          ? `${(record.durationSeconds / 60).toFixed(1)} 分`
                          : '—'}
                      </td>
                      <td>
                        <button
                          className="button button--ghost button--sm"
                          onClick={() => setSelectedRecord(record)}
                        >
                          详情
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div
              className="card__footer"
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}
            >
              <button
                className="button button--ghost"
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1 || historyQuery.isFetching}
              >
                上一页
              </button>
              <span>
                第 {page} / {totalPages} 页
              </span>
              <button
                className="button button--ghost"
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages || historyQuery.isFetching}
              >
                下一页
              </button>
            </div>
          </>
        )}
      </section>

      {/* Detail Modal */}
      {selectedRecord && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000
          }}
          onClick={() => setSelectedRecord(null)}
        >
          <div
            className="card"
            style={{ maxWidth: '600px', width: '90%', maxHeight: '80vh', overflow: 'auto' }}
            onClick={e => e.stopPropagation()}
          >
            <div className="card__header">
              <div className="card__title">同步记录详情</div>
            </div>
            <div className="card__body">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div>
                  <strong>账号:</strong> {selectedRecord.accountName || selectedRecord.accountId}
                </div>
                <div>
                  <strong>状态:</strong>{' '}
                  <span className={statusClassMap[selectedRecord.status]}>
                    {statusLabelMap[selectedRecord.status]}
                  </span>
                </div>
                <div>
                  <strong>同步范围:</strong> {selectedRecord.since} → {selectedRecord.until}
                </div>
                <div>
                  <strong>触发方式:</strong>{' '}
                  {triggerLabelMap[selectedRecord.triggerType] || selectedRecord.triggerType}
                </div>
                <div>
                  <strong>数据目标:</strong>{' '}
                  <span style={{
                    color: dataTargetColorMap[selectedRecord.dataTarget],
                    fontWeight: 500
                  }}>
                    {dataTargetLabelMap[selectedRecord.dataTarget] || selectedRecord.dataTarget}
                  </span>
                </div>
                {selectedRecord.triggeredBy && (
                  <div>
                    <strong>触发人:</strong> {selectedRecord.triggeredBy}
                  </div>
                )}
                <div>
                  <strong>记录数:</strong> {selectedRecord.recordsCount.toLocaleString()}
                </div>
                <div>
                  <strong>进度:</strong> {selectedRecord.percentComplete}% ({selectedRecord.processedDays}/{selectedRecord.totalDays} 天)
                </div>
                <div>
                  <strong>开始时间:</strong> {formatDateTime(selectedRecord.startedAt)}
                </div>
                {selectedRecord.completedAt && (
                  <div>
                    <strong>完成时间:</strong> {formatDateTime(selectedRecord.completedAt)}
                  </div>
                )}
                {selectedRecord.durationSeconds && (
                  <div>
                    <strong>耗时:</strong> {(selectedRecord.durationSeconds / 60).toFixed(2)} 分钟
                  </div>
                )}
                {selectedRecord.errorMessage && (
                  <div
                    style={{
                      padding: '0.75rem',
                      borderRadius: '0.25rem',
                      backgroundColor: 'rgba(225, 77, 64, 0.1)',
                      color: 'var(--color-danger)'
                    }}
                  >
                    <strong>错误信息:</strong>
                    <div style={{ marginTop: '0.5rem' }}>{selectedRecord.errorMessage}</div>
                  </div>
                )}
              </div>
            </div>
            <div className="card__footer" style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button className="button button--primary" onClick={() => setSelectedRecord(null)}>
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default InsightsSyncPage
