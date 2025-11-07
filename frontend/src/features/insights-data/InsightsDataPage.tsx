import { useMemo, useState, useEffect, useRef, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Modal, message } from 'antd'
import {
  fetchInsightsData,
  syncEntityNames,
  type InsightsDataQuery
} from '../../api/insights'
import type { InsightRecord } from '../../types/insights'
import AdAccountSelect from '../../components/AdAccountSelect'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts'

const numberFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 0
})

const decimalFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
})

const METRIC_COLUMNS: Array<{
  key: keyof InsightRecord['metrics']
  label: string
  formatter: (value: number) => string
}> = [
  { key: 'spend', label: 'Spend', formatter: value => decimalFormatter.format(value) },
  { key: 'impressions', label: 'Impressions', formatter: value => numberFormatter.format(value) },
  { key: 'reach', label: 'Reach', formatter: value => numberFormatter.format(value) },
  { key: 'clicks', label: 'Clicks', formatter: value => numberFormatter.format(value) },
  {
    key: 'inlineLinkClicks',
    label: 'Inline Link Clicks',
    formatter: value => numberFormatter.format(value)
  },
  { key: 'outboundClicks', label: 'Outbound Clicks', formatter: value => numberFormatter.format(value) },
  { key: 'landingPageView', label: 'Landing Page Views', formatter: value => numberFormatter.format(value) },
  { key: 'onsiteWebAddToCart', label: 'Onsite ATC', formatter: value => numberFormatter.format(value) },
  { key: 'onsiteWebCheckout', label: 'Onsite Checkout', formatter: value => numberFormatter.format(value) },
  { key: 'onsiteWebPurchase', label: 'Onsite Purchase', formatter: value => numberFormatter.format(value) },
  {
    key: 'onsiteWebPurchaseValue',
    label: 'Onsite Purchase Value',
    formatter: value => decimalFormatter.format(value)
  }
]

const getDefaultDateRange = () => {
  const today = new Date()
  const until = new Date(today.getTime() - 3 * 24 * 60 * 60 * 1000)
  const since = new Date(until)
  since.setDate(since.getDate() - 6)
  const format = (value: Date) => value.toISOString().slice(0, 10)
  return { since: format(since), until: format(until) }
}

const normalizeAccountId = (value: string): string => {
  const trimmed = value.trim()
  if (!trimmed) {
    return ''
  }
  return trimmed.startsWith('act_') ? trimmed : `act_${trimmed.replace(/^act_/i, '')}`
}

const InsightsDataPage = () => {
  const queryClient = useQueryClient()
  const defaultRange = useMemo(getDefaultDateRange, [])
  const [accountInput, setAccountInput] = useState('')
  const [sinceDate, setSinceDate] = useState(defaultRange.since)
  const [untilDate, setUntilDate] = useState(defaultRange.until)
  const [level, setLevel] = useState<'ad' | 'adset' | 'campaign'>('ad')
  const [timeIncrement, setTimeIncrement] = useState<'daily' | 'aggregate'>('daily')
  const [breakdowns, setBreakdowns] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [activeQuery, setActiveQuery] = useState<InsightsDataQuery | null>(null)
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)

  // The level of the currently displayed dataset.
  const resultLevel = activeQuery?.level ?? level

  // Track which queries have had their entity names synced to prevent duplicate syncing
  const syncedQueriesRef = useRef<Set<string>>(new Set())

  // Derive the ID column name based on level
  const idColumnName = useMemo(() => {
    switch (resultLevel) {
      case 'adset':
        return 'AdSet ID'
      case 'campaign':
        return 'Campaign ID'
      default:
        return 'Ad ID'
    }
  }, [resultLevel])

  // Function to get the correct ID and name from a record based on level
  const getEntityId = useCallback((record: InsightRecord) => {
    if (resultLevel === 'adset' && record.adsetId) {
      return record.adsetId
    }
    if (resultLevel === 'campaign' && record.campaignId) {
      return record.campaignId
    }
    return record.adId
  }, [resultLevel])

  const getEntityName = useCallback((record: InsightRecord): string | null => {
    if (resultLevel === 'adset') {
      return record.adsetName
    }
    if (resultLevel === 'campaign') {
      return record.campaignName
    }
    return record.adName
  }, [resultLevel])

  const queryResult = useQuery({
    queryKey: ['insights-data', activeQuery],
    queryFn: () => {
      if (!activeQuery) {
        throw new Error('Missing query parameters')
      }
      return fetchInsightsData(activeQuery)
    },
    enabled: Boolean(activeQuery)
  })

  const insights: InsightRecord[] = useMemo(() => {
    if (!queryResult.data?.insights) {
      return []
    }
    return [...queryResult.data.insights].sort((a, b) => a.date.localeCompare(b.date))
  }, [queryResult.data?.insights])

  const totals = useMemo(() => {
    if (insights.length === 0) {
      return null
    }
    const initial = METRIC_COLUMNS.reduce<Record<string, number>>((acc, col) => {
      acc[col.key] = 0
      return acc
    }, {})

    const result = insights.reduce((acc, record) => {
      for (const column of METRIC_COLUMNS) {
        acc[column.key] += record.metrics[column.key] ?? 0
      }
      return acc
    }, initial)
    return result
  }, [insights])

  // Aggregate insights by entity ID (one row per ID)
  const aggregatedInsights = useMemo(() => {
    if (insights.length === 0) {
      return []
    }

    const grouped = new Map<string, {
      entityId: string
      dateCount: number
      metrics: Record<string, number>
    }>()

    for (const record of insights) {
      const entityId = getEntityId(record)

      if (!grouped.has(entityId)) {
        const initialMetrics = METRIC_COLUMNS.reduce<Record<string, number>>((acc, col) => {
          acc[col.key] = 0
          return acc
        }, {})
        grouped.set(entityId, {
          entityId,
          dateCount: 0,
          metrics: initialMetrics
        })
      }

      const entity = grouped.get(entityId)!
      entity.dateCount += 1
      for (const column of METRIC_COLUMNS) {
        entity.metrics[column.key] += record.metrics[column.key] ?? 0
      }
    }

    return Array.from(grouped.values()).sort((a, b) => a.entityId.localeCompare(b.entityId))
  }, [insights, getEntityId])

  // Auto-sync entity names when insights data loads
  useEffect(() => {
    console.log('[Entity Sync] useEffect triggered', {
      insightsLength: insights.length,
      activeQuery,
      level
    })

    // Only run when we have insights data and an active query
    if (!insights.length || !activeQuery) {
      console.log('[Entity Sync] Skipping - no insights or no active query')
      return
    }

    // Create a unique key for this query to track if we've already synced it
    const queryKey = `${activeQuery.accountId}-${activeQuery.level}-${activeQuery.since}-${activeQuery.until}`
    console.log('[Entity Sync] Query key:', queryKey)

    // Skip if we've already synced this query
    if (syncedQueriesRef.current.has(queryKey)) {
      console.log('[Entity Sync] Skipping - already synced this query')
      return
    }

    // Find entities without names
    const unnamedEntityIds = new Set<string>()
    for (const record of insights) {
      const entityId = getEntityId(record)
      const entityName = getEntityName(record)
      if (!entityName && entityId) {
        unnamedEntityIds.add(entityId)
      }
    }

    console.log('[Entity Sync] Found unnamed entities:', unnamedEntityIds.size, Array.from(unnamedEntityIds))

    // If there are unnamed entities, sync them
    if (unnamedEntityIds.size > 0) {
      // Mark this query as synced immediately to prevent duplicate requests
      syncedQueriesRef.current.add(queryKey)
      console.log('[Entity Sync] Starting sync...')

      const syncNames = async () => {
        try {
          message.loading({ content: `正在获取 ${unnamedEntityIds.size} 个实体的名称...`, key: 'sync' })

          const result = await syncEntityNames({
            adAccountId: activeQuery.accountId,
            entityIds: Array.from(unnamedEntityIds),
            entityType: activeQuery.level
          })

          console.log('[Entity Sync] Sync result:', result)

          // Check if rate limiting occurred
          if (result.rate_limited > 0) {
            message.warning({
              content: `同步受到速率限制 (成功: ${result.synced}, 失败: ${result.failed}, 限制: ${result.rate_limited})。请稍后再试。`,
              key: 'sync',
              duration: 5
            })
            // Don't refetch if rate limited, keep the query key marked to prevent continuous retries
            return
          }

          if (result.failed > 0 && result.synced === 0) {
            message.error({
              content: `同步失败。所有 ${result.failed} 个请求都失败了。请检查网络连接或稍后再试。`,
              key: 'sync',
              duration: 5
            })
            // Remove from synced set on complete failure so it can be retried
            syncedQueriesRef.current.delete(queryKey)
            return
          }

          if (result.synced > 0) {
            const successMsg = result.failed > 0
              ? `部分同步成功 (成功: ${result.synced}, 失败: ${result.failed})`
              : `实体名称同步完成 (成功: ${result.synced})`

            message.success({
              content: successMsg,
              key: 'sync',
              duration: 3
            })

            // If some entities failed, remove from synced set to allow retry
            if (result.failed > 0) {
              syncedQueriesRef.current.delete(queryKey)
            }

            // Invalidate cache and refetch insights to get updated names
            await queryClient.invalidateQueries({ queryKey: ['insights-data', activeQuery] })
            queryResult.refetch()
          }
        } catch (error) {
          console.error('[Entity Sync] Sync failed:', error)
          message.error({ content: '同步实体名称失败', key: 'sync', duration: 3 })
          // Remove from synced set on error so it can be retried
          syncedQueriesRef.current.delete(queryKey)
        }
      }

      syncNames()
    } else {
      console.log('[Entity Sync] No unnamed entities found')
    }
  }, [insights, activeQuery, getEntityId, getEntityName, queryResult])

  // Get historical data for selected entity
  const selectedEntityData = useMemo(() => {
    if (!selectedEntityId) {
      return []
    }
    return insights
      .filter(record => getEntityId(record) === selectedEntityId)
      .sort((a, b) => a.date.localeCompare(b.date))
  }, [insights, selectedEntityId, getEntityId])

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!sinceDate || !untilDate) {
      setFormError('请选择起始和结束日期')
      return
    }
    if (sinceDate > untilDate) {
      setFormError('起始日期不能晚于结束日期')
      return
    }
    const normalizedAccount = normalizeAccountId(accountInput)
    if (!normalizedAccount) {
      setFormError('请输入广告账号 ID，例如 act_123456789')
      return
    }
    setFormError(null)
    setActiveQuery({
      accountId: normalizedAccount,
      since: sinceDate,
      until: untilDate,
      level,
      timeIncrement: timeIncrement === 'daily' ? 1 : null,
      breakdowns: breakdowns.trim() || undefined
    })
  }

  const handleRowClick = (entityId: string) => {
    setSelectedEntityId(entityId)
    setIsModalOpen(true)
  }

  const handleModalClose = () => {
    setIsModalOpen(false)
    setSelectedEntityId(null)
  }

  const isLoading = queryResult.isFetching && !queryResult.data
  const isRefetching = queryResult.isFetching && Boolean(queryResult.data)
  const errorMessage =
    queryResult.isError && queryResult.error instanceof Error
      ? queryResult.error.message
      : queryResult.isError
        ? '洞察数据获取失败，请稍后再试'
        : null

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <h1 className="page__title">洞察数据浏览</h1>
          <p className="page__subtitle">
            基于 MongoDB 中已入库的 Facebook Ads Insights 数据，可按账号与日期范围查询并查看关键指标。
          </p>
        </div>
      </header>

      <section className="card">
        <div className="card__header">
          <div>
            <div className="card__title">筛选条件</div>
            <div className="card__subtitle">
              选择广告账号与时间区间，可选维度级别（ad/adset/campaign）以及按日聚合。
            </div>
          </div>
        </div>
        <form
          onSubmit={handleSubmit}
          className="card__body"
          style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem' }}
        >
          <label className="form-label" style={{ flex: '1 1 260px' }}>
            <span>广告账号</span>
            <AdAccountSelect
              value={accountInput}
              onChange={setAccountInput}
              placeholder="act_123456789"
              inputClassName="input"
              required
              helperText="可输入或从下拉列表选择 act_ 开头的账号 ID。"
            />
          </label>
          <label className="form-label" style={{ flex: '1 1 160px' }}>
            <span>起始日期</span>
            <input
              type="date"
              className="input"
              value={sinceDate}
              onChange={event => setSinceDate(event.target.value)}
            />
          </label>
          <label className="form-label" style={{ flex: '1 1 160px' }}>
            <span>结束日期</span>
            <input
              type="date"
              className="input"
              value={untilDate}
              onChange={event => setUntilDate(event.target.value)}
            />
          </label>
          <label className="form-label" style={{ flex: '1 1 160px' }}>
            <span>维度级别</span>
            <select
              className="input"
              value={level}
              onChange={event => setLevel(event.target.value as typeof level)}
            >
              <option value="ad">Ad</option>
              <option value="adset">Ad Set</option>
              <option value="campaign">Campaign</option>
            </select>
          </label>
          <label className="form-label" style={{ flex: '1 1 180px' }}>
            <span>时间粒度</span>
            <select
              className="input"
              value={timeIncrement}
              onChange={event => setTimeIncrement(event.target.value as typeof timeIncrement)}
            >
              <option value="daily">按日汇总（time_increment=1）</option>
              <option value="aggregate">整体汇总（不分日）</option>
            </select>
          </label>
          <label className="form-label" style={{ flex: '2 1 240px' }}>
            <span>Breakdowns（可选）</span>
            <input
              className="input"
              value={breakdowns}
              onChange={event => setBreakdowns(event.target.value)}
              placeholder="country, device_platform"
              spellCheck={false}
            />
            <div className="form-hint">多个维度以逗号分隔，留空表示不拆分。</div>
          </label>

          {formError && (
            <div style={{ flexBasis: '100%', color: 'var(--color-danger)' }}>{formError}</div>
          )}
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button className="button button--primary" type="submit" disabled={isLoading}>
              {isLoading ? '查询中…' : '查询洞察数据'}
            </button>
            {activeQuery && (
              <>
                <button
                  className="button button--ghost"
                  type="button"
                  onClick={() => setActiveQuery({ ...activeQuery })}
                  disabled={isLoading}
                >
                  刷新数据
                </button>
                <button
                  className="button button--ghost"
                  type="button"
                  onClick={async () => {
                    // Clear the synced queries cache to force re-sync
                    const queryKey = `${activeQuery.accountId}-${activeQuery.level}-${activeQuery.since}-${activeQuery.until}`
                    syncedQueriesRef.current.delete(queryKey)
                    // Invalidate cache and refetch to trigger auto-sync
                    await queryClient.invalidateQueries({ queryKey: ['insights-data', activeQuery] })
                    queryResult.refetch()
                  }}
                  disabled={isLoading}
                >
                  刷新实体名称
                </button>
              </>
            )}
          </div>
        </form>
      </section>

      <section className="card" style={{ marginTop: '1.5rem' }}>
        <div className="card__header">
          <div>
            <div className="card__title">洞察结果</div>
            <div className="card__subtitle">
              {activeQuery
                ? `账号 ${activeQuery.accountId} · ${activeQuery.since} → ${activeQuery.until}`
                : '提交查询后将展示结果。'}
            </div>
          </div>
          {isRefetching && <div style={{ color: 'var(--color-text-muted)' }}>刷新中…</div>}
        </div>

        {errorMessage ? (
          <div className="card__body" style={{ color: 'var(--color-danger)' }}>{errorMessage}</div>
        ) : isLoading ? (
          <div className="card__body">数据加载中…</div>
        ) : !queryResult.data ? (
          <div className="card__body">尚未查询洞察数据。</div>
        ) : insights.length === 0 ? (
          <div className="card__body">未检索到符合条件的洞察记录。</div>
        ) : (
          <>
            <div className="card__body" style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
              <div>
                <div style={{ fontSize: '2rem', fontWeight: 600 }}>{aggregatedInsights.length}</div>
                <div style={{ color: 'var(--color-text-muted)' }}>
                  {idColumnName} 数量
                </div>
              </div>
              {totals && (
                <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>
                  {METRIC_COLUMNS.slice(0, 4).map(column => (
                    <div key={column.key}>
                      <div style={{ fontSize: '1.4rem', fontWeight: 600 }}>
                        {column.formatter(totals[column.key])}
                      </div>
                      <div style={{ color: 'var(--color-text-muted)' }}>{column.label} 汇总</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th style={{ width: '220px' }}>{idColumnName}</th>
                    <th style={{ width: '300px' }}>名称</th>
                    <th style={{ width: '100px' }}>天数</th>
                    {METRIC_COLUMNS.map(column => (
                      <th key={column.key}>{column.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {aggregatedInsights.map(entity => {
                    // Find a sample record to get the name
                    const sampleRecord = insights.find(r => getEntityId(r) === entity.entityId)
                    const entityName = sampleRecord ? getEntityName(sampleRecord) : null

                    return (
                      <tr
                        key={entity.entityId}
                        onClick={() => handleRowClick(entity.entityId)}
                        style={{
                          cursor: 'pointer',
                          transition: 'background-color 0.2s'
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.backgroundColor = 'var(--color-bg-hover, #f5f5f5)'
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.backgroundColor = 'transparent'
                        }}
                      >
                        <td style={{ fontFamily: 'monospace', fontSize: '0.9em' }}>
                          {entity.entityId}
                        </td>
                        <td style={{ fontWeight: entityName ? 500 : 400, color: entityName ? 'inherit' : 'var(--color-text-muted)' }}>
                          {entityName || '(未获取名称)'}
                        </td>
                        <td>{entity.dateCount}</td>
                        {METRIC_COLUMNS.map(column => (
                          <td key={column.key}>
                            {column.formatter(entity.metrics[column.key] ?? 0)}
                          </td>
                        ))}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <Modal
        title={`${idColumnName} 历史数据: ${selectedEntityId || ''}`}
        open={isModalOpen}
        onCancel={handleModalClose}
        width={1200}
        footer={null}
      >
        {selectedEntityData.length > 0 && (
          <div style={{ padding: '20px 0' }}>
            {/* Spend Trend */}
            <div style={{ marginBottom: '40px' }}>
              <h3 style={{ marginBottom: '16px' }}>花费趋势 (Spend)</h3>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={selectedEntityData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip formatter={(value: number) => decimalFormatter.format(value)} />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="metrics.spend"
                    stroke="#8884d8"
                    name="Spend"
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Impressions & Clicks Trend */}
            <div style={{ marginBottom: '40px' }}>
              <h3 style={{ marginBottom: '16px' }}>展示次数与点击量 (Impressions & Clicks)</h3>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={selectedEntityData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip formatter={(value: number) => numberFormatter.format(value)} />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="metrics.impressions"
                    stroke="#82ca9d"
                    name="Impressions"
                    strokeWidth={2}
                  />
                  <Line
                    type="monotone"
                    dataKey="metrics.clicks"
                    stroke="#ffc658"
                    name="Clicks"
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Conversion Metrics Trend */}
            <div style={{ marginBottom: '40px' }}>
              <h3 style={{ marginBottom: '16px' }}>转化指标 (Conversions)</h3>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={selectedEntityData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip formatter={(value: number) => numberFormatter.format(value)} />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="metrics.onsiteWebAddToCart"
                    stroke="#ff7300"
                    name="Add to Cart"
                    strokeWidth={2}
                  />
                  <Line
                    type="monotone"
                    dataKey="metrics.onsiteWebCheckout"
                    stroke="#d84a4a"
                    name="Checkout"
                    strokeWidth={2}
                  />
                  <Line
                    type="monotone"
                    dataKey="metrics.onsiteWebPurchase"
                    stroke="#387908"
                    name="Purchase"
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Purchase Value Trend */}
            <div style={{ marginBottom: '20px' }}>
              <h3 style={{ marginBottom: '16px' }}>购买价值 (Purchase Value)</h3>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={selectedEntityData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip formatter={(value: number) => decimalFormatter.format(value)} />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="metrics.onsiteWebPurchaseValue"
                    stroke="#8b4789"
                    name="Purchase Value"
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Historical Data Table */}
            <div style={{ marginTop: '40px' }}>
              <h3 style={{ marginBottom: '16px' }}>历史明细数据</h3>
              <div className="table-wrapper" style={{ maxHeight: '400px', overflow: 'auto' }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ width: '120px' }}>日期</th>
                      {METRIC_COLUMNS.map(column => (
                        <th key={column.key}>{column.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {selectedEntityData.map(record => (
                      <tr key={record.date}>
                        <td>{record.date}</td>
                        {METRIC_COLUMNS.map(column => (
                          <td key={column.key}>
                            {column.formatter(record.metrics[column.key] ?? 0)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}

export default InsightsDataPage
