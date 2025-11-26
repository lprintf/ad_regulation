import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchSyncOverview, fetchSyncHistory, triggerMongodbSync, triggerRedisSync } from '../../api/insights'
import { formatRelativeTime } from '../../lib/datetime'
import type {
  InsightSyncStatus,
  SyncOverviewItem,
  SyncHistoryRecord
} from '../../types/insights'

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

const InsightsSyncPage = () => {
  return (
    <div className="page">
      {/* Header */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div className="card__header">
          <div>
            <div className="card__title">洞察数据同步管理</div>
            <div className="card__subtitle">管理 Facebook 广告洞察数据的同步任务</div>
          </div>
        </div>
      </div>

      {/* Account Cards Grid */}
      <OverviewSection />
    </div>
  )
}

// ===== Overview Section =====

const OverviewSection = () => {
  const overviewQuery = useQuery({
    queryKey: ['sync-overview'],
    queryFn: fetchSyncOverview,
    refetchInterval: 30_000
  })

  const items: SyncOverviewItem[] = overviewQuery.data?.items ?? []

  return (
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
  )
}

interface AccountCardProps {
  item: SyncOverviewItem
}

const AccountCard = ({ item }: AccountCardProps) => {
  const queryClient = useQueryClient()
  const [showMongodbHistory, setShowMongodbHistory] = useState(false)
  const [showRedisHistory, setShowRedisHistory] = useState(false)

  const mongodbBadgeClass = statusClassMap[item.mongodbStatus] ?? 'badge'
  const mongodbStatusLabel = statusLabelMap[item.mongodbStatus]
  const redisBadgeClass = statusClassMap[item.redisStatus] ?? 'badge'
  const redisStatusLabel = statusLabelMap[item.redisStatus]

  const isAnyRunning = item.mongodbIsRunning || item.redisIsRunning

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

  // Query MongoDB-specific history
  const mongodbHistoryQuery = useQuery({
    queryKey: ['sync-history', item.accountId, 'mongodb'],
    queryFn: () => fetchSyncHistory({
      accountId: item.accountId,
      dataTarget: 'mongodb',
      page: 1,
      pageSize: 10
    }),
    enabled: showMongodbHistory
  })

  // Query Redis-specific history
  const redisHistoryQuery = useQuery({
    queryKey: ['sync-history', item.accountId, 'redis'],
    queryFn: () => fetchSyncHistory({
      accountId: item.accountId,
      dataTarget: 'redis',
      page: 1,
      pageSize: 10
    }),
    enabled: showRedisHistory
  })

  return (
    <>
      <div
        style={{
          border: '1px solid var(--color-border)',
          borderRadius: '0.5rem',
          padding: '1rem',
          backgroundColor: isAnyRunning ? 'rgba(24, 119, 242, 0.05)' : 'var(--color-bg-elevated)'
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
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.875rem' }}>
          {/* MongoDB 数据覆盖范围和状态 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--color-text-muted)', minWidth: '80px' }}>MongoDB:</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1 }}>
              <span
                className={mongodbBadgeClass}
                style={{ fontSize: '0.75rem', cursor: item.mongodbLastError ? 'help' : 'default' }}
                title={item.mongodbLastError || undefined}
              >
                {mongodbStatusLabel}
              </span>
              <span style={{ color: 'var(--color-primary)', fontWeight: 500, flex: 1, textAlign: 'right' }}>
                {item.mongodbCoverageSince && item.mongodbCoverageUntil
                  ? `${item.mongodbCoverageSince} → ${item.mongodbCoverageUntil}`
                  : '—'}
              </span>
              <button
                className="button button--ghost button--sm"
                onClick={() => setShowMongodbHistory(true)}
                style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                title="查看MongoDB同步历史"
              >
                📋
              </button>
              <button
                className="button button--sm button--primary"
                onClick={() => mongodbSyncMutation.mutate()}
                disabled={mongodbSyncMutation.isPending || item.mongodbIsRunning}
                style={{ whiteSpace: 'nowrap', fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}
              >
                {mongodbSyncMutation.isPending ? '...' : '同步'}
              </button>
            </div>
          </div>

          {/* MongoDB 最后同步时间 */}
          {item.mongodbLastSyncedAt && (
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingLeft: '1rem', fontSize: '0.8rem' }}>
              <span style={{ color: 'var(--color-text-muted)' }}>最后同步:</span>
              <span style={{ color: 'var(--color-text-muted)' }}>
                {formatRelativeTime(item.mongodbLastSyncedAt)}
              </span>
            </div>
          )}

          {/* Redis 缓存范围和状态 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--color-text-muted)', minWidth: '80px' }}>Redis:</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flex: 1 }}>
              <span
                className={redisBadgeClass}
                style={{ fontSize: '0.75rem', cursor: item.redisLastError ? 'help' : 'default' }}
                title={item.redisLastError || undefined}
              >
                {redisStatusLabel}
              </span>
              <span style={{ color: 'var(--color-success)', fontWeight: 500, flex: 1, textAlign: 'right' }}>
                {item.redisCacheSince && item.redisCacheUntil
                  ? `${item.redisCacheSince} → ${item.redisCacheUntil}`
                  : '—'}
              </span>
              <button
                className="button button--ghost button--sm"
                onClick={() => setShowRedisHistory(true)}
                style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                title="查看Redis同步历史"
              >
                📋
              </button>
              <button
                className="button button--sm button--success"
                onClick={() => redisSyncMutation.mutate()}
                disabled={redisSyncMutation.isPending || item.redisIsRunning}
                style={{ whiteSpace: 'nowrap', fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}
              >
                {redisSyncMutation.isPending ? '...' : '同步'}
              </button>
            </div>
          </div>

          {/* Redis 最后同步时间 */}
          {item.redisLastSyncedAt && (
            <div style={{ display: 'flex', justifyContent: 'space-between', paddingLeft: '1rem', fontSize: '0.8rem' }}>
              <span style={{ color: 'var(--color-text-muted)' }}>最后同步:</span>
              <span style={{ color: 'var(--color-text-muted)' }}>
                {formatRelativeTime(item.redisLastSyncedAt)}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* MongoDB History Modal */}
      {showMongodbHistory && (
        <HistoryModal
          title={`MongoDB同步历史 - ${item.accountName || item.accountId}`}
          historyQuery={mongodbHistoryQuery}
          onClose={() => setShowMongodbHistory(false)}
        />
      )}

      {/* Redis History Modal */}
      {showRedisHistory && (
        <HistoryModal
          title={`Redis同步历史 - ${item.accountName || item.accountId}`}
          historyQuery={redisHistoryQuery}
          onClose={() => setShowRedisHistory(false)}
        />
      )}
    </>
  )
}

// ===== History Modal Component =====

interface HistoryModalProps {
  title: string
  historyQuery: ReturnType<typeof useQuery>
  onClose: () => void
}

const HistoryModal = ({ title, historyQuery, onClose }: HistoryModalProps) => {
  return (
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
      onClick={onClose}
    >
      <div
        className="card"
        style={{ maxWidth: '800px', width: '90%', maxHeight: '80vh', overflow: 'auto' }}
        onClick={e => e.stopPropagation()}
      >
        <div className="card__header">
          <div className="card__title">{title}</div>
        </div>
        <div className="card__body">
          {historyQuery.isLoading ? (
            <div>加载中…</div>
          ) : historyQuery.isError ? (
            <div style={{ color: 'var(--color-danger)' }}>加载失败</div>
          ) : !historyQuery.data || historyQuery.data.items.length === 0 ? (
            <div>暂无历史记录</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {historyQuery.data.items.map((record: SyncHistoryRecord) => (
                <div
                  key={record.id}
                  style={{
                    padding: '0.75rem',
                    border: '1px solid var(--color-border)',
                    borderRadius: '0.25rem',
                    backgroundColor: 'var(--color-bg-elevated)'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <span className={statusClassMap[record.status]}>
                        {statusLabelMap[record.status]}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                        {triggerLabelMap[record.triggerType] || record.triggerType}
                      </span>
                      {record.mode === 'async' && (
                        <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                          异步
                        </span>
                      )}
                    </div>
                    <span style={{ fontSize: '0.875rem', color: 'var(--color-text-muted)' }}>
                      {formatRelativeTime(record.startedAt)}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.875rem', color: 'var(--color-text-muted)' }}>
                    范围: {record.since} → {record.until} | 记录: {record.recordsCount.toLocaleString()} |
                    耗时: {record.durationSeconds ? `${(record.durationSeconds / 60).toFixed(1)} 分` : '—'}
                  </div>
                  {/* Show skip reason as info if present */}
                  {record.metadata?.skipped && record.metadata?.skip_reason && (
                    <div style={{
                      marginTop: '0.5rem',
                      fontSize: '0.75rem',
                      color: 'var(--color-info)',
                      padding: '0.5rem',
                      backgroundColor: 'rgba(24, 119, 242, 0.1)',
                      borderRadius: '0.25rem'
                    }}>
                      ℹ️ {record.metadata.skip_reason}
                    </div>
                  )}
                  {/* Show error message only if not skipped */}
                  {record.errorMessage && !record.metadata?.skipped && (
                    <div style={{
                      marginTop: '0.5rem',
                      fontSize: '0.75rem',
                      color: 'var(--color-danger)',
                      padding: '0.5rem',
                      backgroundColor: 'rgba(225, 77, 64, 0.1)',
                      borderRadius: '0.25rem'
                    }}>
                      {record.errorMessage}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="card__footer" style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button className="button button--primary" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}

export default InsightsSyncPage
