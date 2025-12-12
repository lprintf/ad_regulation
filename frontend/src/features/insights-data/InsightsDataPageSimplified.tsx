/**
 * Simplified Insights Data Page
 * Uses new overview/drilldown API instead of n+1 queries
 */
import { useState, useMemo, useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Modal, Spinner, Tabs } from '@/components/ui'
import { fetchAdAccounts } from '../../api/adAccounts'
import {
  fetchInsightsOverview,
  fetchInsightsDrilldown,
  syncEntityNames,
  type InsightsDataSource,
  type EntitySelection,
} from '../../api/insights'
import type { InsightRecord } from '../../types/insights'
import type { RuleEntityType } from '../../types/rule-engine'
import PerformanceTrendChart from './PerformanceTrendChart'
import RuleBindingsList from '../../components/RuleBindingsList'
import RuleBindingModal, { type RuleBindingTarget } from './RuleBindingModal'
import { toast } from 'sonner'

type HierarchyLevel = 'account' | 'campaign' | 'adset' | 'ad'

const LEVEL_LABELS: Record<HierarchyLevel, string> = {
  account: '账号',
  campaign: '广告系列',
  adset: '广告组',
  ad: '广告',
}

const numberFormatter = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const decimalFormatter = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

type MetricKey = keyof InsightRecord['metrics']

const METRIC_COLUMNS: Array<{
  key: MetricKey
  label: string
  formatter: (value: number) => string
}> = [
  { key: 'spend', label: 'Spend', formatter: v => decimalFormatter.format(v) },
  { key: 'impressions', label: 'Impressions', formatter: v => numberFormatter.format(v) },
  { key: 'reach', label: 'Reach', formatter: v => numberFormatter.format(v) },
  { key: 'clicks', label: 'Clicks', formatter: v => numberFormatter.format(v) },
  { key: 'inlineLinkClicks', label: 'Inline Link Clicks', formatter: v => numberFormatter.format(v) },
  { key: 'outboundClicks', label: 'Outbound Clicks', formatter: v => numberFormatter.format(v) },
  { key: 'landingPageView', label: 'Landing Page Views', formatter: v => numberFormatter.format(v) },
  { key: 'onsiteWebAddToCart', label: 'Onsite ATC', formatter: v => numberFormatter.format(v) },
  { key: 'onsiteWebCheckout', label: 'Onsite Checkout', formatter: v => numberFormatter.format(v) },
  { key: 'onsiteWebPurchase', label: 'Onsite Purchase', formatter: v => numberFormatter.format(v) },
  { key: 'onsiteWebPurchaseValue', label: 'Purchase Value', formatter: v => decimalFormatter.format(v) },
]

const safeDivide = (a: number, b: number) => (b === 0 ? 0 : a / b)

type DerivedMetricKey = 'ctr' | 'cpc' | 'cpm' | 'cpa' | 'roas'

const DERIVED_METRICS: Array<{
  key: DerivedMetricKey
  label: string
  formatter: (v: number) => string
  compute: (m: Record<MetricKey, number>) => number
}> = [
  {
    key: 'ctr',
    label: 'CTR',
    formatter: v => `${decimalFormatter.format(v * 100)}%`,
    compute: m => safeDivide(m.clicks, m.impressions),
  },
  {
    key: 'cpc',
    label: 'CPC',
    formatter: v => decimalFormatter.format(v),
    compute: m => safeDivide(m.spend, m.clicks),
  },
  {
    key: 'cpm',
    label: 'CPM',
    formatter: v => decimalFormatter.format(v),
    compute: m => safeDivide(m.spend * 1000, m.impressions),
  },
  {
    key: 'cpa',
    label: 'CPA',
    formatter: v => decimalFormatter.format(v),
    compute: m => safeDivide(m.spend, m.onsiteWebPurchase),
  },
  {
    key: 'roas',
    label: 'ROAS',
    formatter: v => decimalFormatter.format(v),
    compute: m => safeDivide(m.onsiteWebPurchaseValue, m.spend),
  },
]

const getDefaultDateRange = () => {
  const now = new Date()
  const until = now.toISOString().slice(0, 10)
  const since = new Date(now.setDate(now.getDate() - 6)).toISOString().slice(0, 10)
  return { since, until }
}

const getStatusColor = (status: string | null | undefined): string => {
  switch (status?.toUpperCase()) {
    case 'ACTIVE': return '#22c55e'
    case 'PAUSED': return '#f59e0b'
    case 'DELETED': case 'ARCHIVED': return '#ef4444'
    default: return '#9ca3af'
  }
}

interface AggregatedEntity {
  entityId: string
  entityName: string | null
  accountId: string
  campaignId: string | null
  adsetId: string | null
  configuredStatus: string | null
  effectiveStatus: string | null
  metrics: InsightRecord['metrics']
  dateCount: number
  startDate: string | null
  endDate: string | null
}

const InsightsDataPageSimplified = () => {
  const defaultRange = useMemo(getDefaultDateRange, [])

  // Form state
  const [sinceDate, setSinceDate] = useState(defaultRange.since)
  const [untilDate, setUntilDate] = useState(defaultRange.until)
  const [source, setSource] = useState<InsightsDataSource>('mongo_redis')
  const [submittedParams, setSubmittedParams] = useState<{
    since: string
    until: string
    source: InsightsDataSource
  } | null>(null)

  // Navigation state
  const [level, setLevel] = useState<HierarchyLevel>('account')
  const [selections, setSelections] = useState<EntitySelection[]>([])

  // Selection state (checkboxes) - stored per level to preserve selections when switching
  const [selectedIdsByLevel, setSelectedIdsByLevel] = useState<Map<HierarchyLevel, Set<string>>>(new Map())
  const selectedIds = selectedIdsByLevel.get(level) ?? new Set<string>()
  const setSelectedIds = useCallback((ids: Set<string>) => {
    setSelectedIdsByLevel(prev => new Map(prev).set(level, ids))
  }, [level])

  // Detail modal state
  const [detailEntity, setDetailEntity] = useState<AggregatedEntity | null>(null)
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false)
  const [selectedTrendDate, setSelectedTrendDate] = useState<string | null>(null)

  // Rule binding modal state
  const [ruleBindingTarget, setRuleBindingTarget] = useState<RuleBindingTarget | null>(null)
  const [isRuleBindingModalOpen, setIsRuleBindingModalOpen] = useState(false)

  // Fetch ad accounts
  const { data: adAccounts = [], isLoading: isLoadingAccounts } = useQuery({
    queryKey: ['insights', 'ad-accounts'],
    queryFn: fetchAdAccounts,
    staleTime: 5 * 60_000,
  })

  const accountIds = useMemo(() => adAccounts.map(a => a.id), [adAccounts])
  const accountNameMap = useMemo(() => {
    const map = new Map<string, string>()
    adAccounts.forEach(a => map.set(a.id, a.name ?? a.id))
    return map
  }, [adAccounts])

  // Auto-submit on mount
  useEffect(() => {
    if (accountIds.length > 0 && !submittedParams) {
      setSubmittedParams({ since: sinceDate, until: untilDate, source })
    }
  }, [accountIds, submittedParams, sinceDate, untilDate, source])

  // Overview query (account level)
  const overviewQuery = useQuery({
    queryKey: ['insights', 'overview', { accountIds, ...submittedParams }],
    queryFn: () => fetchInsightsOverview({
      accountIds,
      since: submittedParams!.since,
      until: submittedParams!.until,
      source: submittedParams!.source,
    }),
    enabled: !!submittedParams && level === 'account' && accountIds.length > 0,
    staleTime: 30_000,
  })

  // Drilldown query
  const drilldownQuery = useQuery({
    queryKey: ['insights', 'drilldown', { selections, level, ...submittedParams }],
    queryFn: () => fetchInsightsDrilldown({
      selections,
      level: level as 'campaign' | 'adset' | 'ad',
      since: submittedParams!.since,
      until: submittedParams!.until,
      source: submittedParams!.source,
    }),
    enabled: !!submittedParams && level !== 'account' && selections.length > 0,
    staleTime: 30_000,
  })

  // Detail query for modal (fetches daily data for selected entity at account level)
  const detailQuery = useQuery({
    queryKey: ['insights', 'detail', { detailEntityId: detailEntity?.entityId, level, ...submittedParams }],
    queryFn: async () => {
      if (!detailEntity || !submittedParams || level !== 'account') {
        return { insights: [], totalRecords: 0, dateRange: { since: '', until: '' } }
      }
      // For account level, query campaigns to get daily data
      return fetchInsightsDrilldown({
        selections: [{ accountId: detailEntity.accountId, campaignId: null, adsetId: null, adId: null }],
        level: 'campaign',
        since: submittedParams.since,
        until: submittedParams.until,
        source: submittedParams.source,
      })
    },
    enabled: !!detailEntity && !!submittedParams && isDetailModalOpen && level === 'account',
    staleTime: 30_000,
  })

  // Entity name sync mutation
  const queryClient = useQueryClient()
  const [syncingEntityIds, setSyncingEntityIds] = useState<Set<string>>(new Set())

  const syncMutation = useMutation({
    mutationFn: async ({ entityIds, accountId }: { entityIds: string[], accountId: string }) => {
      const entityType = level as 'campaign' | 'adset' | 'ad'
      return syncEntityNames({
        adAccountId: accountId,
        entityIds,
        entityType,
      })
    },
    onSuccess: (result, variables) => {
      // Mark syncing complete
      setSyncingEntityIds(prev => {
        const next = new Set(prev)
        variables.entityIds.forEach(id => next.delete(id))
        return next
      })

      // Invalidate queries to refetch with updated names
      queryClient.invalidateQueries({ queryKey: ['insights', 'drilldown'] })
      queryClient.invalidateQueries({ queryKey: ['insights', 'overview'] })

      // Show success toast
      toast.success(`已同步 ${result.synced} 个实体名称`)

      if (result.failed > 0) {
        toast.warning(`${result.failed} 个实体同步失败`)
      }
      if (result.rateLimited > 0) {
        toast.warning(`${result.rateLimited} 个实体被速率限制`)
      }
    },
    onError: (error, variables) => {
      // Mark syncing complete
      setSyncingEntityIds(prev => {
        const next = new Set(prev)
        variables.entityIds.forEach(id => next.delete(id))
        return next
      })
      toast.error(`同步失败: ${error instanceof Error ? error.message : String(error)}`)
    },
  })

  const handleSyncEntity = useCallback((entityId: string, accountId: string) => {
    setSyncingEntityIds(prev => new Set(prev).add(entityId))
    syncMutation.mutate({ entityIds: [entityId], accountId })
  }, [syncMutation])

  // Aggregate drilldown data by entity
  const aggregatedEntities = useMemo<AggregatedEntity[]>(() => {
    if (level === 'account') {
      return (overviewQuery.data?.items ?? []).map(item => ({
        entityId: item.accountId,
        entityName: item.accountName ?? accountNameMap.get(item.accountId) ?? null,
        accountId: item.accountId,
        campaignId: null,
        adsetId: null,
        configuredStatus: null,
        effectiveStatus: null,
        metrics: item.metrics,
        dateCount: item.dateCount,
        startDate: item.startDate,
        endDate: item.endDate,
      }))
    }

    const insights = drilldownQuery.data?.insights ?? []
    const aggregated = new Map<string, AggregatedEntity>()

    for (const record of insights) {
      const entityId = level === 'ad' ? record.adId
        : level === 'adset' ? record.adsetId
        : record.campaignId
      if (!entityId) continue

      const entityName = (level === 'ad' ? record.adName
        : level === 'adset' ? record.adsetName
        : record.campaignName) ?? null

      if (!aggregated.has(entityId)) {
        aggregated.set(entityId, {
          entityId,
          entityName,
          accountId: record.adAccountId,
          campaignId: record.campaignId ?? null,
          adsetId: record.adsetId ?? null,
          configuredStatus: record.configuredStatus ?? null,
          effectiveStatus: record.effectiveStatus ?? null,
          metrics: { ...record.metrics },
          dateCount: 1,
          startDate: record.date,
          endDate: record.date,
        })
      } else {
        const existing = aggregated.get(entityId)!
        existing.dateCount += 1
        if (!existing.startDate || record.date < existing.startDate) existing.startDate = record.date
        if (!existing.endDate || record.date > existing.endDate) existing.endDate = record.date
        for (const key of Object.keys(record.metrics) as MetricKey[]) {
          existing.metrics[key] += record.metrics[key]
        }
        if (!existing.entityName && entityName) existing.entityName = entityName
        if (!existing.configuredStatus) existing.configuredStatus = record.configuredStatus ?? null
        if (!existing.effectiveStatus) existing.effectiveStatus = record.effectiveStatus ?? null
      }
    }

    return Array.from(aggregated.values())
  }, [level, overviewQuery.data, drilldownQuery.data, accountNameMap])

  const handleBatchSync = useCallback(() => {
    if (selectedIds.size === 0) {
      toast.warning('请先选择要同步的实体')
      return
    }

    const MAX_BATCH_SIZE = 50  // 后端限制每次最多50个

    // Group by account ID
    const entityIdsByAccount = new Map<string, string[]>()
    aggregatedEntities.forEach(entity => {
      if (selectedIds.has(entity.entityId)) {
        const list = entityIdsByAccount.get(entity.accountId) ?? []
        list.push(entity.entityId)
        entityIdsByAccount.set(entity.accountId, list)
      }
    })

    // Mark all as syncing
    setSyncingEntityIds(prev => new Set([...prev, ...selectedIds]))

    // 自动分批：将每个账号的实体ID列表分成每批最多50个
    let totalBatches = 0
    entityIdsByAccount.forEach((entityIds, accountId) => {
      // 分批处理
      for (let i = 0; i < entityIds.length; i += MAX_BATCH_SIZE) {
        const batch = entityIds.slice(i, i + MAX_BATCH_SIZE)
        totalBatches++

        // 每批之间延迟100ms，避免并发过多
        setTimeout(() => {
          syncMutation.mutate({ entityIds: batch, accountId })
        }, totalBatches * 100)
      }
    })

    if (totalBatches > 1) {
      toast.info(`已分成 ${totalBatches} 批次同步，请稍候...`)
    }
  }, [selectedIds, aggregatedEntities, syncMutation])


  // Get entity insights for detail modal
  const detailEntityInsights = useMemo<InsightRecord[]>(() => {
    if (!detailEntity) return []

    // For account level, use detailQuery data and aggregate by date
    if (level === 'account') {
      const insights = detailQuery.data?.insights ?? []
      // Aggregate all campaigns by date for this account
      const dateMap = new Map<string, InsightRecord['metrics']>()
      for (const record of insights) {
        if (!dateMap.has(record.date)) {
          dateMap.set(record.date, { ...record.metrics })
        } else {
          const existing = dateMap.get(record.date)!
          for (const key of Object.keys(record.metrics) as MetricKey[]) {
            existing[key] += record.metrics[key]
          }
        }
      }
      return Array.from(dateMap.entries())
        .map(([date, metrics]) => ({
          adAccountId: detailEntity.accountId,
          adId: null,
          adsetId: null,
          campaignId: null,
          adName: null,
          adsetName: null,
          campaignName: null,
          configuredStatus: null,
          effectiveStatus: null,
          date,
          metrics,
        }))
        .sort((a, b) => a.date.localeCompare(b.date))
    }

    // For other levels, filter from drilldown data
    return (drilldownQuery.data?.insights ?? [])
      .filter(r => {
        const id = level === 'ad' ? r.adId : level === 'adset' ? r.adsetId : r.campaignId
        return id === detailEntity.entityId
      })
      .sort((a, b) => a.date.localeCompare(b.date))
  }, [detailEntity, level, drilldownQuery.data, detailQuery.data])

  // Computed metrics for detail modal
  const detailEntityTotals = useMemo(() => {
    if (!detailEntity) return null
    return detailEntity.metrics
  }, [detailEntity])

  const detailEntityDerivedSummary = useMemo(() => {
    if (!detailEntityTotals) return null
    return DERIVED_METRICS.map(metric => ({
      key: metric.key,
      label: metric.label,
      value: metric.compute(detailEntityTotals as Record<MetricKey, number>),
      formatter: metric.formatter,
    }))
  }, [detailEntityTotals])

  const detailEntityDailyRows = useMemo(() => {
    if (!detailEntityInsights.length) return []
    return detailEntityInsights.map(record => ({
      date: record.date,
      metrics: record.metrics,
      derived: DERIVED_METRICS.map(metric => ({
        key: metric.key,
        value: metric.compute(record.metrics as Record<MetricKey, number>),
        formatter: metric.formatter,
      })),
    }))
  }, [detailEntityInsights])

  // Handlers
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setSubmittedParams({ since: sinceDate, until: untilDate, source })
    setLevel('account')
    setSelections([])
    setSelectedIdsByLevel(new Map())
  }

  const handleLevelChange = useCallback((newLevel: HierarchyLevel) => {
    // Going back to account level - clear selections filter
    if (newLevel === 'account') {
      setSelections([])
      setLevel('account')
      return
    }

    // Build selections from the highest level with selections above newLevel
    // For level L, we need selections from levels < L (parent levels)
    const levelHierarchy: HierarchyLevel[] = ['account', 'campaign', 'adset', 'ad']
    const newLevelIndex = levelHierarchy.indexOf(newLevel)
    
    // Find the highest parent level that has selections
    let newSelections: EntitySelection[] = []
    
    for (let i = newLevelIndex - 1; i >= 0; i--) {
      const parentLevel = levelHierarchy[i]
      const parentSelectedIds = selectedIdsByLevel.get(parentLevel)
      
      if (parentSelectedIds && parentSelectedIds.size > 0) {
        // Build selections based on this parent level's selections
        // We need the data from this level to build proper selections
        if (parentLevel === 'account') {
          // Use account selections
          const accountData = overviewQuery.data?.items ?? []
          newSelections = accountData
            .filter(item => parentSelectedIds.has(item.accountId))
            .map(item => ({
              accountId: item.accountId,
              campaignId: null,
              adsetId: null,
              adId: null,
            }))
        } else {
          // Use drilldown data from the current view if available
          const drilldownData = drilldownQuery.data?.insights ?? []
          newSelections = drilldownData
            .filter(item => {
              const entityId = parentLevel === 'campaign' ? item.campaignId
                : parentLevel === 'adset' ? item.adsetId
                : item.adId
              return entityId && parentSelectedIds.has(entityId)
            })
            .map(item => ({
              accountId: item.adAccountId,
              campaignId: parentLevel === 'campaign' ? (item.campaignId ?? null)
                : parentLevel === 'adset' || parentLevel === 'ad' ? (item.campaignId ?? null)
                : null,
              adsetId: parentLevel === 'adset' ? (item.adsetId ?? null)
                : parentLevel === 'ad' ? (item.adsetId ?? null)
                : null,
              adId: null,
            }))
        }
        break
      }
    }
    
    // If no parent level has selections, use all accounts
    if (newSelections.length === 0) {
      const accountData = overviewQuery.data?.items ?? []
      newSelections = accountData.map(item => ({
        accountId: item.accountId,
        campaignId: null,
        adsetId: null,
        adId: null,
      }))
    }

    setSelections(newSelections)
    setLevel(newLevel)
  }, [selectedIdsByLevel, overviewQuery.data, drilldownQuery.data])

  const handleDetailOpen = (entity: AggregatedEntity) => {
    setDetailEntity(entity)
    setSelectedTrendDate(null)
    setIsDetailModalOpen(true)
  }

  const handleManageRules = useCallback((entity: AggregatedEntity) => {
    const entityType = level as RuleEntityType
    setRuleBindingTarget({
      entityId: entity.entityId,
      entityName: entity.entityName,
      entityType,
      adAccountId: entity.accountId,
      campaignId: entity.campaignId,
      adsetId: entity.adsetId,
      adId: level === 'ad' ? entity.entityId : null,
    })
    setIsRuleBindingModalOpen(true)
  }, [level])

  const toggleSelection = (entityId: string) => {
    const next = new Set(selectedIds)
    if (next.has(entityId)) next.delete(entityId)
    else next.add(entityId)
    setSelectedIds(next)
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === aggregatedEntities.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(aggregatedEntities.map(e => e.entityId)))
    }
  }

  const isLoading = isLoadingAccounts || (level === 'account' ? overviewQuery.isLoading : drilldownQuery.isLoading)
  const isError = level === 'account' ? overviewQuery.isError : drilldownQuery.isError
  const isAllSelected = selectedIds.size > 0 && selectedIds.size === aggregatedEntities.length

  // Render table
  const renderTable = () => {
    if (aggregatedEntities.length === 0) {
      return <div className="empty-state py-8">暂无数据</div>
    }

    return (
      <div className="table-wrapper">
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: 56 }}>
                <input
                  type="checkbox"
                  checked={isAllSelected}
                  onChange={toggleSelectAll}
                  disabled={aggregatedEntities.length === 0}
                />
              </th>
              <th style={{ minWidth: 260 }}>{LEVEL_LABELS[level]}</th>
              {level !== 'account' && <th style={{ width: 140 }}>状态</th>}
              <th style={{ width: 160 }}>操作</th>
              <th className="text-right" style={{ width: 120 }}>Spend</th>
              <th className="text-right" style={{ width: 120 }}>Impressions</th>
              <th className="text-right" style={{ width: 100 }}>Clicks</th>
              <th className="text-right" style={{ width: 100 }}>Purchase</th>
              <th className="text-right" style={{ width: 140 }}>Purchase Value</th>
            </tr>
          </thead>
          <tbody>
            {aggregatedEntities.map(entity => {
              const isChecked = selectedIds.has(entity.entityId)
              const statusColor = getStatusColor(entity.configuredStatus)
              const displayName = entity.entityName ?? entity.entityId

              return (
                <tr
                  key={entity.entityId}
                  className={`hover:bg-muted/50 ${isChecked ? 'bg-primary/5' : ''}`}
                >
                  <td style={{ width: 56 }}>
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleSelection(entity.entityId)}
                    />
                  </td>
                  <td style={{ minWidth: 260 }}>
                    <div className="flex items-center gap-3">
                      {level === 'ad' && (
                        <div className="w-10 h-10 rounded-md bg-muted flex items-center justify-center font-semibold text-sm">
                          {displayName.charAt(0).toUpperCase()}
                        </div>
                      )}
                      <div className="min-w-0">
                        <div
                          className={`font-semibold truncate ${entity.entityName ? '' : 'text-muted-foreground'}`}
                          title={displayName}
                        >
                          {entity.entityName ?? '名称未同步'}
                        </div>
                        <div className="text-xs text-muted-foreground font-mono truncate" title={entity.entityId}>
                          {entity.entityId}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          覆盖 {entity.dateCount} 天
                          {entity.startDate && entity.endDate && ` (${entity.startDate} ~ ${entity.endDate})`}
                        </div>
                      </div>
                    </div>
                  </td>
                  {level !== 'account' && (
                    <td style={{ width: 140 }}>
                      <div className="flex items-center gap-2">
                        <div className="flex items-center gap-2 flex-1">
                          <span
                            className="w-2.5 h-2.5 rounded-full inline-block"
                            style={{ backgroundColor: statusColor }}
                          />
                          <span>{entity.configuredStatus ?? '—'}</span>
                        </div>
                        <button
                          className="button button--ghost p-1 hover:bg-accent rounded"
                          onClick={(e) => {
                            e.stopPropagation()
                            handleSyncEntity(entity.entityId, entity.accountId)
                          }}
                          disabled={syncingEntityIds.has(entity.entityId)}
                          title="刷新实体名称和状态"
                        >
                          {syncingEntityIds.has(entity.entityId) ? (
                            <Spinner className="w-4 h-4" />
                          ) : (
                            <svg
                              className="w-4 h-4"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                              />
                            </svg>
                          )}
                        </button>
                      </div>
                      {entity.effectiveStatus && entity.effectiveStatus !== entity.configuredStatus && (
                        <div className="text-xs text-muted-foreground">有效：{entity.effectiveStatus}</div>
                      )}
                    </td>
                  )}
                  <td style={{ width: 160 }}>
                    <div className="flex gap-2 flex-wrap">
                      <button
                        className="button button--ghost text-xs px-2 py-1"
                        onClick={() => handleDetailOpen(entity)}
                      >
                        详情
                      </button>
                      <button
                        className="button button--ghost text-xs px-2 py-1"
                        onClick={() => handleManageRules(entity)}
                      >
                        托管
                      </button>
                    </div>
                  </td>
                  <td className="text-right">{decimalFormatter.format(entity.metrics.spend)}</td>
                  <td className="text-right">{numberFormatter.format(entity.metrics.impressions)}</td>
                  <td className="text-right">{numberFormatter.format(entity.metrics.clicks)}</td>
                  <td className="text-right">{numberFormatter.format(entity.metrics.onsiteWebPurchase)}</td>
                  <td className="text-right">{decimalFormatter.format(entity.metrics.onsiteWebPurchaseValue)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    )
  }

  // Render detail modal tabs
  const renderDetailModalContent = () => {
    if (!detailEntity) return null

    const isAccountLevel = level === 'account'
    const isLoadingDetail = isAccountLevel && detailQuery.isLoading

    // Daily data loading state
    const renderDailyContent = () => {
      if (isLoadingDetail) {
        return (
          <div className="flex items-center justify-center gap-2 py-8">
            <Spinner size="sm" />
            <span className="text-muted-foreground">加载每日数据...</span>
          </div>
        )
      }
      if (detailEntityDailyRows.length > 0) {
        return (
          <div className="table-wrapper max-h-96 overflow-auto py-4">
            <table className="table text-sm">
              <thead>
                <tr>
                  <th style={{ width: 100 }}>日期</th>
                  {METRIC_COLUMNS.slice(0, 6).map(col => (
                    <th key={col.key} className="text-right">{col.label}</th>
                  ))}
                  {DERIVED_METRICS.map(m => (
                    <th key={m.key} className="text-right">{m.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {detailEntityDailyRows.map(row => (
                  <tr key={row.date}>
                    <td>{row.date}</td>
                    {METRIC_COLUMNS.slice(0, 6).map(col => (
                      <td key={col.key} className="text-right">
                        {col.formatter(row.metrics[col.key] ?? 0)}
                      </td>
                    ))}
                    {row.derived.map(d => (
                      <td key={d.key} className="text-right">{d.formatter(d.value)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      }
      return <div className="text-muted-foreground py-8 text-center">暂无每日数据</div>
    }

    // Trend chart loading state
    const renderTrendContent = () => {
      if (isLoadingDetail) {
        return (
          <div className="flex items-center justify-center gap-2 py-8">
            <Spinner size="sm" />
            <span className="text-muted-foreground">加载趋势数据...</span>
          </div>
        )
      }
      return (
        <div className="py-4">
          <PerformanceTrendChart
            data={detailEntityInsights}
            onDateSelect={setSelectedTrendDate}
            selectedDate={selectedTrendDate}
          />
          {selectedTrendDate && (
            <div className="mt-4 p-4 bg-blue-50 border border-blue-500 rounded-lg flex justify-between items-center">
              <div>
                <div className="font-semibold text-blue-800">已选择测试日期: {selectedTrendDate}</div>
                <div className="text-sm text-slate-500">
                  点击右侧按钮，使用此日期作为 evaluation_date 参数进行规则测试
                </div>
              </div>
              <button
                className="button button--primary whitespace-nowrap"
                onClick={() => {
                  setIsDetailModalOpen(false)
                  handleManageRules(detailEntity)
                }}
              >
                测试规则
              </button>
            </div>
          )}
        </div>
      )
    }

    return (
      <Tabs
        defaultActiveKey="basic"
        items={[
          {
            key: 'basic',
            label: '基础指标汇总',
            children: detailEntityTotals ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 py-4">
                {METRIC_COLUMNS.map(col => (
                  <div
                    key={col.key}
                    className="p-3 rounded-lg bg-muted/50 border border-border"
                  >
                    <div className="text-lg font-semibold">
                      {col.formatter(detailEntityTotals[col.key])}
                    </div>
                    <div className="text-sm text-muted-foreground">{col.label}</div>
                  </div>
                ))}
              </div>
            ) : null,
          },
          {
            key: 'extended',
            label: '扩展指标汇总',
            children: detailEntityDerivedSummary ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 py-4">
                {detailEntityDerivedSummary.map(item => (
                  <div
                    key={item.key}
                    className="p-3 rounded-lg bg-muted/50 border border-border"
                  >
                    <div className="text-lg font-semibold">{item.formatter(item.value)}</div>
                    <div className="text-sm text-muted-foreground">{item.label}</div>
                  </div>
                ))}
              </div>
            ) : null,
          },
          {
            key: 'daily',
            label: '每日表现',
            children: renderDailyContent(),
          },
          {
            key: 'trend',
            label: '趋势图表',
            children: renderTrendContent(),
          },
          {
            key: 'bindings',
            label: '已绑定规则',
            children: (
              <div className="py-4">
                <div className="mb-4 text-sm text-muted-foreground">
                  此实体已绑定以下规则，规则会按计划自动执行
                </div>
                <RuleBindingsList
                  entityId={detailEntity.entityId}
                  showRuleName
                  showEntityId={false}
                  allowDelete
                  allowToggle
                />
              </div>
            ),
          },
        ]}
      />
    )
  }

  return (
    <div className="page">
      {/* Header */}
      <header className="page__header responsive-container">
        <h1 className="page__title">洞察数据浏览</h1>
        <p className="page__subtitle">
          基于 MongoDB + Redis 的广告洞察数据，支持按账号和日期范围查询。
        </p>
      </header>

      {/* Filter Form */}
      <section className="card responsive-container">
        <div className="card__header">
          <div className="card__title">筛选条件</div>
        </div>
        <form onSubmit={handleSubmit} className="card__body flex flex-wrap gap-4">
          <label className="form-label flex-[0_1_140px]">
            <span>起始日期</span>
            <input
              type="date"
              className="input"
              value={sinceDate}
              onChange={e => setSinceDate(e.target.value)}
            />
          </label>
          <label className="form-label flex-[0_1_140px]">
            <span>结束日期</span>
            <input
              type="date"
              className="input"
              value={untilDate}
              onChange={e => setUntilDate(e.target.value)}
            />
          </label>
          <label className="form-label flex-[0_1_180px]">
            <span>数据源</span>
            <select
              className="input"
              value={source}
              onChange={e => setSource(e.target.value as InsightsDataSource)}
            >
              <option value="mongo_redis">MongoDB + Redis</option>
              <option value="mongo">MongoDB</option>
              <option value="redis">Redis</option>
            </select>
          </label>
          <div className="flex gap-3 items-end">
            <button className="button button--primary" type="submit" disabled={isLoading}>
              {isLoading ? '查询中…' : '查询'}
            </button>
          </div>
        </form>
      </section>

      {/* Results */}
      <section className="card responsive-container mt-6">
        <div className="card__header">
          <div>
            <div className="card__title">洞察结果</div>
            <div className="card__subtitle">
              {submittedParams
                ? `${submittedParams.since} → ${submittedParams.until}`
                : '请先查询数据'}
            </div>
          </div>
        </div>

        {/* Level tabs and selection actions */}
        {submittedParams && (
          <div className="flex items-center justify-between gap-4 mb-4 px-6 flex-wrap">
            <div className="flex gap-2">
              {(['account', 'campaign', 'adset', 'ad'] as HierarchyLevel[]).map(l => (
                <button
                  key={l}
                  className={`px-4 py-1.5 rounded-full text-sm border transition-colors ${
                    level === l
                      ? 'bg-primary text-primary-foreground border-primary'
                      : 'bg-transparent border-border hover:bg-muted'
                  }`}
                  onClick={() => handleLevelChange(l)}
                >
                  {LEVEL_LABELS[l]}
                </button>
              ))}
              {selections.length > 0 && (
                <button
                  className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
                  onClick={() => { setLevel('account'); setSelections([]); setSelectedIdsByLevel(new Map()) }}
                >
                  清除选择
                </button>
              )}
            </div>

            {/* Selection actions */}
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <span>已选 {selectedIds.size} 个</span>
              {selectedIds.size > 0 && level !== 'ad' && (
                <span className="text-xs">（勾选的实体将用于下钻筛选）</span>
              )}
              {selectedIds.size > 0 && level !== 'account' && (
                <button
                  className="button button--primary text-xs px-3 py-1"
                  onClick={handleBatchSync}
                  disabled={syncMutation.isPending}
                >
                  {syncMutation.isPending ? '同步中...' : '批量刷新实体名称'}
                </button>
              )}
            </div>
          </div>
        )}

        {/* Data table */}
        <div className="card__body">
          {isLoading ? (
            <div className="flex items-center justify-center gap-2 py-8">
              <Spinner size="sm" />
              <span className="text-muted-foreground">加载中...</span>
            </div>
          ) : isError ? (
            <div className="text-destructive py-4">加载失败，请重试</div>
          ) : !submittedParams ? (
            <div className="text-muted-foreground py-4">请先选择日期范围并查询</div>
          ) : (
            renderTable()
          )}
        </div>

        {/* Summary */}
        {aggregatedEntities.length > 0 && (
          <div className="card__footer border-t border-border">
            <div className="text-sm text-muted-foreground">
              共 {aggregatedEntities.length} 条记录
            </div>
          </div>
        )}
      </section>

      {/* Detail Modal */}
      <Modal
        title={
          detailEntity?.entityName
            ? `${detailEntity.entityName} (${detailEntity.entityId})`
            : `${LEVEL_LABELS[level]} 历史数据: ${detailEntity?.entityId ?? ''}`
        }
        open={isDetailModalOpen}
        onClose={() => { setIsDetailModalOpen(false); setDetailEntity(null); setSelectedTrendDate(null) }}
        width={1100}
      >
        {renderDetailModalContent()}
      </Modal>

      {/* Rule Binding Modal */}
      <RuleBindingModal
        target={ruleBindingTarget}
        open={isRuleBindingModalOpen}
        onClose={() => { setIsRuleBindingModalOpen(false); setRuleBindingTarget(null) }}
      />
    </div>
  )
}

export default InsightsDataPageSimplified
