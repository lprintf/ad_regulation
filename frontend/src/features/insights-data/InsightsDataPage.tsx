import { useMemo, useState, useEffect, useRef, useCallback, useContext } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Modal, message, ConfigProvider, Spin } from 'antd'
import {
  fetchInsightsData,
  syncEntityNames,
  type InsightsDataQuery,
  type SyncedEntityName
} from '../../api/insights'
import type { InsightRecord, InsightsDataResponse } from '../../types/insights'
import AdAccountSelect from '../../components/AdAccountSelect'

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

const METRIC_COLUMN_MAP = METRIC_COLUMNS.reduce<Record<MetricKey, (typeof METRIC_COLUMNS)[number]>>(
  (acc, column) => {
    acc[column.key] = column
    return acc
  },
  {} as Record<MetricKey, (typeof METRIC_COLUMNS)[number]>
)

const MAX_TOOLTIP_POINTS = 14

type MetricKey = (typeof METRIC_COLUMNS)[number]['key']

const DEFAULT_VISIBLE_METRICS: MetricKey[] = [
  'spend',
  'impressions',
  'reach',
  'clicks',
  'onsiteWebPurchase',
  'onsiteWebPurchaseValue'
]

const clampWidth = (value: number, min = 80, max = 400) => Math.min(max, Math.max(min, value))
const DEFAULT_COLUMN_ORDER: MetricKey[] = METRIC_COLUMNS.map(column => column.key)
const DEFAULT_COLUMN_WIDTHS: Record<MetricKey, number> = {
  spend: 140,
  impressions: 140,
  reach: 140,
  clicks: 120,
  inlineLinkClicks: 160,
  outboundClicks: 150,
  landingPageView: 160,
  onsiteWebCheckout: 150,
  onsiteWebAddToCart: 160,
  onsiteWebPurchase: 150,
  onsiteWebCheckoutValue: 180,
  onsiteWebAddToCartValue: 200,
  onsiteWebPurchaseValue: 200
}

const isMetricKey = (value: string): value is MetricKey =>
  METRIC_COLUMNS.some(column => column.key === value)

const sanitizeColumnOrder = (order: unknown): MetricKey[] => {
  if (!Array.isArray(order)) {
    return [...DEFAULT_COLUMN_ORDER]
  }
  const normalized: MetricKey[] = []
  for (const item of order) {
    if (typeof item !== 'string') {
      continue
    }
    if (isMetricKey(item) && !normalized.includes(item)) {
      normalized.push(item)
    }
  }
  for (const key of DEFAULT_COLUMN_ORDER) {
    if (!normalized.includes(key)) {
      normalized.push(key)
    }
  }
  return normalized
}

const sanitizeColumnWidths = (source: unknown): Record<MetricKey, number> => {
  const widths: Record<MetricKey, number> = { ...DEFAULT_COLUMN_WIDTHS }
  if (typeof source !== 'object' || source === null) {
    return widths
  }
  for (const key of Object.keys(source)) {
    if (!isMetricKey(key)) {
      continue
    }
    const value = Number((source as Record<string, unknown>)[key])
    if (Number.isFinite(value)) {
      widths[key] = clampWidth(value)
    }
  }
  return widths
}

const sanitizeVisibleMetrics = (keys: unknown, fallback: MetricKey[]): MetricKey[] => {
  if (!Array.isArray(keys)) {
    return [...fallback]
  }
  const normalized: MetricKey[] = []
  for (const item of keys) {
    if (typeof item !== 'string') {
      continue
    }
    if (isMetricKey(item) && !normalized.includes(item)) {
      normalized.push(item)
    }
  }
  return normalized.length > 0 ? normalized : [...fallback]
}

type HierarchyLevel = 'account' | 'campaign' | 'adset' | 'ad'

const HIERARCHY_LEVELS: HierarchyLevel[] = ['account', 'campaign', 'adset', 'ad']

const LEVEL_LABELS: Record<HierarchyLevel, string> = {
  account: '广告账号',
  campaign: '广告系列',
  adset: '广告组',
  ad: '广告'
}

const LEVEL_PARENT_CHAIN: Record<HierarchyLevel, HierarchyLevel[]> = {
  account: [],
  campaign: ['account'],
  adset: ['campaign', 'account'],
  ad: ['adset', 'campaign', 'account']
}

const REALTIME_ENTITY_FIELDS = [
  'ad_name',
  'adset_name',
  'campaign_name',
  'adset_id',
  'campaign_id',
  'configured_status',
  'effective_status'
] as const

type DerivedMetricKey = 'ctr' | 'cpc' | 'cpm' | 'cpa' | 'roas'

const safeDivide = (numerator: number, denominator: number) =>
  denominator === 0 ? 0 : numerator / denominator

const DERIVED_METRICS: Array<{
  key: DerivedMetricKey
  label: string
  formatter: (value: number) => string
  compute: (metrics: Record<MetricKey, number>) => number
}> = [
  {
    key: 'ctr',
    label: 'CTR',
    formatter: value => `${decimalFormatter.format(value * 100)}%`,
    compute: metrics => safeDivide(metrics.clicks, metrics.impressions)
  },
  {
    key: 'cpc',
    label: 'CPC',
    formatter: value => decimalFormatter.format(value),
    compute: metrics => safeDivide(metrics.spend, metrics.clicks)
  },
  {
    key: 'cpm',
    label: 'CPM',
    formatter: value => decimalFormatter.format(value),
    compute: metrics => metrics.impressions === 0 ? 0 : (metrics.spend / metrics.impressions) * 1000
  },
  {
    key: 'cpa',
    label: '每次购买成本',
    formatter: value => decimalFormatter.format(value),
    compute: metrics => safeDivide(metrics.spend, metrics.onsiteWebPurchase)
  },
  {
    key: 'roas',
    label: 'ROAS',
    formatter: value => `${decimalFormatter.format(value)}x`,
    compute: metrics => safeDivide(metrics.onsiteWebPurchaseValue, metrics.spend)
  }
]

const getStatusColor = (status: string | null) => {
  if (!status) {
    return '#d9d9d9'
  }
  const normalized = status.toLowerCase()
  if (normalized.includes('active') || normalized.includes('run')) {
    return '#52c41a'
  }
  if (normalized.includes('pause') || normalized.includes('suspend') || normalized.includes('limited')) {
    return '#faad14'
  }
  if (normalized.includes('disable') || normalized.includes('delete') || normalized.includes('stop')) {
    return '#ff4d4f'
  }
  return '#d9d9d9'
}

interface SubmittedParams {
  accountId: string
  since: string
  until: string
  source: InsightsDataQuery['source']
  timeIncrement: number | null
  breakdowns?: string
}

const createEmptySelectionMap = (): Record<HierarchyLevel, Set<string>> => ({
  account: new Set<string>(),
  campaign: new Set<string>(),
  adset: new Set<string>(),
  ad: new Set<string>()
})

interface AggregatedEntityRow {
  entityId: string
  entityName: string | null
  dateCount: number
  metrics: Record<MetricKey, number>
  startDate: string
  endDate: string
  configuredStatus: string | null
  effectiveStatus: string | null
}

const DATA_SOURCE_LABEL: Record<InsightsDataQuery['source'], string> = {
  database: '数据库',
  realtime: '实时数据',
  hybrid: '数据库 + 实时数据'
}

const ENTITY_NAME_SYNC_BATCH_SIZE = 50
const TABLE_PAGE_SIZE = 20

const chunkArray = <T,>(items: T[], chunkSize: number): T[][] => {
  if (chunkSize <= 0) {
    return [items]
  }
  const chunks: T[][] = []
  for (let i = 0; i < items.length; i += chunkSize) {
    chunks.push(items.slice(i, i + chunkSize))
  }
  return chunks
}

const areQueriesEqual = (a: InsightsDataQuery, b: InsightsDataQuery) => {
  const normalizeList = (items?: string[]) => (items ? [...items].sort().join('|') : '')
  return (
    a.accountId === b.accountId &&
    a.since === b.since &&
    a.until === b.until &&
    (a.level ?? 'ad') === (b.level ?? 'ad') &&
    (a.timeIncrement ?? null) === (b.timeIncrement ?? null) &&
    (a.breakdowns ?? '') === (b.breakdowns ?? '') &&
    a.source === b.source &&
    normalizeList(a.fields) === normalizeList(b.fields) &&
    (a.objectLevel ?? null) === (b.objectLevel ?? null) &&
    normalizeList(a.objectIds) === normalizeList(b.objectIds)
  )
}

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
  const [timeIncrement, setTimeIncrement] = useState<'daily' | 'aggregate'>('daily')
  const [breakdowns, setBreakdowns] = useState('')
  const [useDatabaseSource, setUseDatabaseSource] = useState(true)
  const [useRealtimeSource, setUseRealtimeSource] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [selectedAccountName, setSelectedAccountName] = useState<string | null>(null)
  const [submittedAccountName, setSubmittedAccountName] = useState<string | null>(null)
  const [activeLevel, setActiveLevel] = useState<HierarchyLevel>('campaign')
  const [lastSubmittedParams, setLastSubmittedParams] = useState<SubmittedParams | null>(null)
  const [activeQuery, setActiveQuery] = useState<InsightsDataQuery | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [detailEntityId, setDetailEntityId] = useState<string | null>(null)
  const [detailEntityName, setDetailEntityName] = useState<string | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [visibleMetricKeys, setVisibleMetricKeys] = useState<MetricKey[]>(DEFAULT_VISIBLE_METRICS)
  const [columnOrder, setColumnOrder] = useState<MetricKey[]>(() => [...DEFAULT_COLUMN_ORDER])
  const [columnWidths, setColumnWidths] = useState<Record<MetricKey, number>>({ ...DEFAULT_COLUMN_WIDTHS })
  const [isColumnPickerOpen, setIsColumnPickerOpen] = useState(false)
  const [selectedEntityIds, setSelectedEntityIds] = useState<Record<HierarchyLevel, Set<string>>>(() => createEmptySelectionMap())
  const [drillSelection, setDrillSelection] = useState<Record<HierarchyLevel, string | null>>({
    account: null,
    campaign: null,
    adset: null,
    ad: null
  })
  const [drillOptions, setDrillOptions] = useState<Record<Exclude<HierarchyLevel, 'account'>, string[]>>({
    campaign: [],
    adset: [],
    ad: []
  })
  const [openDropdownLevel, setOpenDropdownLevel] = useState<Exclude<HierarchyLevel, 'account'> | null>(null)
  const dropdownRefs = useRef<Record<Exclude<HierarchyLevel, 'account'>, HTMLDivElement | null>>({
    campaign: null,
    adset: null,
    ad: null
  })
  const [syncingEntityIds, setSyncingEntityIds] = useState<Set<string>>(() => new Set())
  const configContext = useContext(ConfigProvider.ConfigContext)
  const columnModalPrefix = useMemo(
    () => (configContext?.getPrefixCls ? configContext.getPrefixCls('insights-column-picker') : 'insights-column-picker'),
    [configContext]
  )

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }
    try {
      const storedOrderRaw = window.localStorage.getItem('insights-column-order')
      if (storedOrderRaw) {
        const parsed = JSON.parse(storedOrderRaw)
        setColumnOrder(sanitizeColumnOrder(parsed))
      }
      const storedVisibleRaw = window.localStorage.getItem('insights-visible-metrics')
      if (storedVisibleRaw) {
        const parsedVisible = JSON.parse(storedVisibleRaw)
        setVisibleMetricKeys(sanitizeVisibleMetrics(parsedVisible, DEFAULT_VISIBLE_METRICS))
      }
      const storedWidthRaw = window.localStorage.getItem('insights-column-widths')
      if (storedWidthRaw) {
        const parsedWidths = JSON.parse(storedWidthRaw)
        setColumnWidths(sanitizeColumnWidths(parsedWidths))
      }
    } catch (error) {
      console.warn('[Insights] Failed to load saved column preferences', error)
    }
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }
    try {
      window.localStorage.setItem('insights-column-order', JSON.stringify(columnOrder))
    } catch {
      /* noop */
    }
  }, [columnOrder])

  const updateSyncingEntities = useCallback((ids: string[], action: 'add' | 'remove') => {
    if (!ids.length) {
      return
    }
    setSyncingEntityIds(prev => {
      const next = new Set(prev)
      for (const id of ids) {
        if (!id) {
          continue
        }
        if (action === 'add') {
          next.add(id)
        } else {
          next.delete(id)
        }
      }
      return next
    })
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }
    try {
      window.localStorage.setItem('insights-visible-metrics', JSON.stringify(visibleMetricKeys))
    } catch {
      /* noop */
    }
  }, [visibleMetricKeys])

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }
    try {
      window.localStorage.setItem('insights-column-widths', JSON.stringify(columnWidths))
    } catch {
      /* noop */
    }
  }, [columnWidths])

  useEffect(() => {
    setVisibleMetricKeys(prev => {
      const filtered = prev.filter(key => columnOrder.includes(key))
      if (filtered.length === prev.length) {
        return prev
      }
      if (filtered.length === 0 && columnOrder.length > 0) {
        return [columnOrder[0]]
      }
      return filtered
    })
  }, [columnOrder])

  const resolveObjectFilter = useCallback(
    (targetLevel: HierarchyLevel) => {
      const parents = LEVEL_PARENT_CHAIN[targetLevel]
      for (const parent of parents) {
        if (parent === 'account') {
          return null
        }
        const multiSelected = selectedEntityIds[parent]
        if (multiSelected && multiSelected.size > 0) {
          return {
            level: parent as Exclude<HierarchyLevel, 'account'>,
            ids: Array.from(multiSelected)
          }
        }
      }
      return null
    },
    [selectedEntityIds]
  )

  const buildQueryForLevel = useCallback(
    (
      targetLevel: HierarchyLevel,
      baseOverride?: SubmittedParams | null,
      forcedFilter?: { level: Exclude<HierarchyLevel, 'account'>; ids: string[] } | null
    ): InsightsDataQuery | null => {
      const base = baseOverride ?? lastSubmittedParams
      if (!base) {
        return null
      }
      const filter =
        forcedFilter === undefined ? resolveObjectFilter(targetLevel) : forcedFilter
      const shouldRequestRealtimeFields = base.source !== 'database'
      return {
        accountId: base.accountId,
        since: base.since,
        until: base.until,
        level: targetLevel,
        timeIncrement: base.timeIncrement,
        breakdowns: base.breakdowns,
        source: base.source,
        fields: shouldRequestRealtimeFields ? [...REALTIME_ENTITY_FIELDS] : undefined,
        objectLevel: filter?.level,
        objectIds: filter?.ids
      }
    },
    [lastSubmittedParams, resolveObjectFilter]
  )

  // The level of the currently displayed dataset.
  const resultLevel = (activeQuery?.level ?? activeLevel) as HierarchyLevel

  // Track which queries have had their entity names synced to prevent duplicate syncing
  const syncedQueriesRef = useRef<Set<string>>(new Set())
  const headerCheckboxRef = useRef<HTMLInputElement | null>(null)

  // Derive the ID column name based on level
  const idColumnName = useMemo(() => {
    switch (resultLevel) {
      case 'account':
        return 'Account ID'
      case 'adset':
        return 'AdSet ID'
      case 'campaign':
        return 'Campaign ID'
      default:
        return 'Ad ID'
    }
  }, [resultLevel])

  // Function to get the correct ID and name from a record based on level
  const normalizedSubmittedAccountId = useMemo(() => {
    if (!activeQuery?.accountId) {
      return null
    }
    return activeQuery.accountId.replace(/^act_/, '')
  }, [activeQuery?.accountId])

  const getEntityId = useCallback(
    (record: InsightRecord) => {
      if (record.adId) {
        return record.adId
      }
      if (record.adsetId) {
        return record.adsetId
      }
      if (record.campaignId) {
        return record.campaignId
      }
      if (record.adAccountId) {
        return record.adAccountId
      }
      return activeQuery?.accountId ?? ''
    },
    [activeQuery?.accountId]
  )

  const getEntityName = useCallback(
    (record: InsightRecord): string | null => {
      if (record.adName) {
        return record.adName
      }
      if (record.adsetName) {
        return record.adsetName
      }
      if (record.campaignName) {
        return record.campaignName
      }
      if (resultLevel === 'account') {
        const accountIdentifier = record.adAccountId ?? record.adId ?? ''
        const recordAccountId = accountIdentifier.replace(/^act_/, '')
        if (
          normalizedSubmittedAccountId &&
          recordAccountId === normalizedSubmittedAccountId &&
          submittedAccountName
        ) {
          return submittedAccountName
        }
        return submittedAccountName ?? record.adName ?? null
      }
      return null
    },
    [resultLevel, normalizedSubmittedAccountId, submittedAccountName]
  )

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
  const aggregatedInsights = useMemo<AggregatedEntityRow[]>(() => {
    if (insights.length === 0) {
      return []
    }

    const createMetricBucket = () =>
      METRIC_COLUMNS.reduce<Record<MetricKey, number>>((acc, col) => {
        acc[col.key] = 0
        return acc
      }, {} as Record<MetricKey, number>)

    const grouped = new Map<string, AggregatedEntityRow>()

    for (const record of insights) {
      const entityId = getEntityId(record)
      if (!entityId) {
        continue
      }

      if (!grouped.has(entityId)) {
        grouped.set(entityId, {
          entityId,
          entityName: getEntityName(record),
          dateCount: 0,
          metrics: createMetricBucket(),
          startDate: record.date,
          endDate: record.date,
          configuredStatus: record.configuredStatus ?? null,
          effectiveStatus: record.effectiveStatus ?? null
        })
      }

      const entity = grouped.get(entityId)!
      entity.dateCount += 1
      for (const column of METRIC_COLUMNS) {
        entity.metrics[column.key] += record.metrics[column.key] ?? 0
      }
      if (!entity.entityName) {
        const maybeName = getEntityName(record)
        if (maybeName) {
          entity.entityName = maybeName
        }
      }
      if (!entity.configuredStatus && record.configuredStatus) {
        entity.configuredStatus = record.configuredStatus
      }
      if (!entity.effectiveStatus && record.effectiveStatus) {
        entity.effectiveStatus = record.effectiveStatus
      }
      if (record.date < entity.startDate) {
        entity.startDate = record.date
      }
      if (record.date > entity.endDate) {
        entity.endDate = record.date
      }
    }

    return Array.from(grouped.values()).sort((a, b) => a.entityId.localeCompare(b.entityId))
  }, [insights, getEntityId, getEntityName])

  useEffect(() => {
    if (resultLevel === 'account' || aggregatedInsights.length === 0) {
      return
    }
    const optionLevel = resultLevel as Exclude<HierarchyLevel, 'account'>
    const nextOptions = Array.from(new Set(aggregatedInsights.map(entity => entity.entityId)))
    setDrillOptions(prev => {
      const updated = { ...prev }
      updated[optionLevel] = nextOptions
      return updated
    })
  }, [aggregatedInsights, resultLevel])

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!openDropdownLevel) {
        return
      }
      const container = dropdownRefs.current[openDropdownLevel]
      if (container && container.contains(event.target as Node)) {
        return
      }
      setOpenDropdownLevel(null)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [openDropdownLevel])

  const metricTimeline = useMemo(() => {
    const map = new Map<string, Record<MetricKey, Array<{ date: string; value: number }>>>()
    for (const record of insights) {
      const entityId = getEntityId(record)
      if (!entityId) {
        continue
      }
      let entityTimeline = map.get(entityId)
      if (!entityTimeline) {
        entityTimeline = {} as Record<MetricKey, Array<{ date: string; value: number }>>
        for (const column of METRIC_COLUMNS) {
          entityTimeline[column.key] = []
        }
        map.set(entityId, entityTimeline)
      }
      for (const column of METRIC_COLUMNS) {
        entityTimeline[column.key].push({
          date: record.date,
          value: record.metrics[column.key] ?? 0
        })
      }
    }
    for (const entityTimeline of map.values()) {
      for (const column of METRIC_COLUMNS) {
        entityTimeline[column.key].sort((a, b) => a.date.localeCompare(b.date))
      }
    }
    return map
  }, [insights, getEntityId])

  const formatMetricTooltip = useCallback(
    (entityId: string, metricKey: MetricKey) => {
      const entityTimeline = metricTimeline.get(entityId)
      if (!entityTimeline) {
        return ''
      }
      const metricSeries = entityTimeline[metricKey]
      if (!metricSeries?.length) {
        return ''
      }
      const segment = metricSeries.slice(-MAX_TOOLTIP_POINTS)
      const formatter = METRIC_COLUMN_MAP[metricKey]?.formatter ?? (value => String(value))
      return segment.map(entry => `${entry.date}: ${formatter(entry.value ?? 0)}`).join('\n')
    },
    [metricTimeline]
  )

  const orderedColumns = useMemo(
    () =>
      columnOrder
        .map(key => METRIC_COLUMNS.find(column => column.key === key))
        .filter((column): column is (typeof METRIC_COLUMNS)[number] => Boolean(column)),
    [columnOrder]
  )

  const visibleMetricColumns = useMemo(
    () => orderedColumns.filter(column => visibleMetricKeys.includes(column.key)),
    [orderedColumns, visibleMetricKeys]
  )

  useEffect(() => {
    setCurrentPage(1)
  }, [aggregatedInsights])

  const totalPages = Math.max(1, Math.ceil(aggregatedInsights.length / TABLE_PAGE_SIZE) || 1)

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages)
    }
  }, [currentPage, totalPages])

  const paginatedAggregatedInsights = useMemo(() => {
    const startIndex = (currentPage - 1) * TABLE_PAGE_SIZE
    return aggregatedInsights.slice(startIndex, startIndex + TABLE_PAGE_SIZE)
  }, [aggregatedInsights, currentPage])

  const currentLevelSelection = selectedEntityIds[resultLevel] ?? new Set<string>()
  const isAllCurrentPageSelected =
    paginatedAggregatedInsights.length > 0 &&
    paginatedAggregatedInsights.every(entity => currentLevelSelection.has(entity.entityId))
  const hasAnyCurrentPageSelected = paginatedAggregatedInsights.some(entity =>
    currentLevelSelection.has(entity.entityId)
  )

  const handleSelectAllChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { checked } = event.target
    setSelectedEntityIds(prev => {
      const updated: Record<HierarchyLevel, Set<string>> = {
        account: new Set(prev.account),
        campaign: new Set(prev.campaign),
        adset: new Set(prev.adset),
        ad: new Set(prev.ad)
      }
      updated[resultLevel] = checked
        ? new Set(paginatedAggregatedInsights.map(entity => entity.entityId))
        : new Set<string>()
      return updated
    })
  }

  useEffect(() => {
    if (headerCheckboxRef.current) {
      headerCheckboxRef.current.indeterminate =
        !isAllCurrentPageSelected && hasAnyCurrentPageSelected
    }
  }, [isAllCurrentPageSelected, hasAnyCurrentPageSelected])

  const applySyncedNamesToCache = useCallback(
    (entities: SyncedEntityName[]) => {
      if (!entities.length || !activeQuery) {
        return
      }

      const currentQuery = activeQuery
      const queryKey = ['insights-data', currentQuery] as const
      const detailMap = new Map<
        string,
        { name: string | null; configuredStatus: string | null; effectiveStatus: string | null }
      >(
        entities.map(item => [
          item.entityId,
          {
            name: item.entityName ?? null,
            configuredStatus: item.configuredStatus ?? null,
            effectiveStatus: item.effectiveStatus ?? null
          }
        ])
      )

      queryClient.setQueryData<InsightsDataResponse | undefined>(queryKey, previous => {
        if (!previous?.insights?.length) {
          return previous
        }

        const updatedInsights = previous.insights.map(record => {
          const entityId = getEntityId(record)
          if (!entityId || !detailMap.has(entityId)) {
            return record
          }

          const details = detailMap.get(entityId)!

          if (currentQuery.level === 'adset') {
            return {
              ...record,
              adsetName: details.name ?? record.adsetName,
              configuredStatus: details.configuredStatus ?? record.configuredStatus,
              effectiveStatus: details.effectiveStatus ?? record.effectiveStatus
            }
          }
          if (currentQuery.level === 'campaign') {
            return {
              ...record,
              campaignName: details.name ?? record.campaignName,
              configuredStatus: details.configuredStatus ?? record.configuredStatus,
              effectiveStatus: details.effectiveStatus ?? record.effectiveStatus
            }
          }
          return {
            ...record,
            adName: details.name ?? record.adName,
            configuredStatus: details.configuredStatus ?? record.configuredStatus,
            effectiveStatus: details.effectiveStatus ?? record.effectiveStatus
          }
        })

        return {
          ...previous,
          insights: updatedInsights
        }
      })
    },
    [activeQuery, queryClient, getEntityId]
  )

  // Auto-sync entity names when insights data loads
  useEffect(() => {
    console.log('[Entity Sync] useEffect triggered', {
      insightsLength: insights.length,
      activeQuery,
      level: activeQuery?.level ?? activeLevel
    })

    // Only run when we have insights data and an active query
    if (!insights.length || !activeQuery || activeQuery.level === 'account') {
      console.log('[Entity Sync] Skipping - missing insights/query or unsupported level')
      return
    }

    // Create a unique key for this query to track if we've already synced it
    const queryKey = `${activeQuery.accountId}-${activeQuery.level}-${activeQuery.since}-${activeQuery.until}-${activeQuery.source}-${activeQuery.objectLevel ?? 'none'}-${(activeQuery.objectIds ?? []).join(',')}`
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

      const pendingIds = Array.from(unnamedEntityIds)
      updateSyncingEntities(pendingIds, 'add')

      const syncNames = async () => {
        const entityIdBatches = chunkArray(pendingIds, ENTITY_NAME_SYNC_BATCH_SIZE)
        const aggregateResult = {
          synced: 0,
          failed: 0,
          rateLimited: 0,
          entities: [] as SyncedEntityName[]
        }
        const requestedEntityType =
          activeQuery.level === 'campaign'
            ? 'campaign'
            : activeQuery.level === 'adset'
              ? 'adset'
              : 'ad'

        try {
          for (let idx = 0; idx < entityIdBatches.length; idx += 1) {
            const batchIds = entityIdBatches[idx]
            message.loading({
              content: `正在获取名称 ${idx + 1}/${entityIdBatches.length}（${batchIds.length} 个实体）...`,
              key: 'sync'
            })

            const result = await syncEntityNames({
              adAccountId: activeQuery.accountId,
              entityIds: batchIds,
              entityType: requestedEntityType
            })

            console.log(`[Entity Sync] Batch ${idx + 1} result:`, result)

            aggregateResult.synced += result.synced
            aggregateResult.failed += result.failed
            aggregateResult.rateLimited += result.rateLimited
            if (result.entities.length > 0) {
              aggregateResult.entities.push(...result.entities)
              applySyncedNamesToCache(result.entities)
            }

            if (result.rateLimited > 0) {
              break
            }
          }

          if (aggregateResult.rateLimited > 0) {
            message.warning({
              content: `同步受到速率限制 (成功: ${aggregateResult.synced}, 失败: ${aggregateResult.failed}, 限制: ${aggregateResult.rateLimited})。请稍后再试。`,
              key: 'sync',
              duration: 5
            })
            // Allow retry later
            syncedQueriesRef.current.delete(queryKey)
            updateSyncingEntities(pendingIds, 'remove')
            return
          }

          if (aggregateResult.failed > 0 && aggregateResult.synced === 0) {
            message.error({
              content: `同步失败。所有 ${aggregateResult.failed} 个请求都失败了。请检查网络连接或稍后再试。`,
              key: 'sync',
              duration: 5
            })
            // Remove from synced set on complete failure so it can be retried
            syncedQueriesRef.current.delete(queryKey)
            updateSyncingEntities(pendingIds, 'remove')
            return
          }

          if (aggregateResult.synced > 0) {
            const successMsg = aggregateResult.failed > 0
              ? `部分同步成功 (成功: ${aggregateResult.synced}, 失败: ${aggregateResult.failed})`
              : `实体名称同步完成 (成功: ${aggregateResult.synced})`

            message.success({
              content: successMsg,
              key: 'sync',
              duration: 3
            })

            // If some entities failed, remove from synced set to allow retry
            if (aggregateResult.failed > 0) {
              syncedQueriesRef.current.delete(queryKey)
            }

            // Invalidate cache and refetch insights to get updated names
            await queryClient.invalidateQueries({ queryKey: ['insights-data', activeQuery] })
            queryResult.refetch()
            updateSyncingEntities(pendingIds, 'remove')
          }
          if (aggregateResult.synced === 0 && aggregateResult.failed === 0 && aggregateResult.rateLimited === 0) {
            updateSyncingEntities(pendingIds, 'remove')
          }
        } catch (error) {
          console.error('[Entity Sync] Sync failed:', error)
          message.error({ content: '同步实体名称失败', key: 'sync', duration: 3 })
          // Remove from synced set on error so it can be retried
          syncedQueriesRef.current.delete(queryKey)
          updateSyncingEntities(pendingIds, 'remove')
        }
      }

      syncNames()
    } else {
      console.log('[Entity Sync] No unnamed entities found')
    }
  }, [insights, activeQuery, activeLevel, getEntityId, getEntityName, queryClient, queryResult, applySyncedNamesToCache, updateSyncingEntities])

  // Get historical data for selected entity
  const selectedEntityData = useMemo(() => {
    if (!detailEntityId) {
      return []
    }
    return insights
      .filter(record => getEntityId(record) === detailEntityId)
      .sort((a, b) => a.date.localeCompare(b.date))
  }, [insights, detailEntityId, getEntityId])

  const selectedEntityTotals = useMemo(() => {
    if (!selectedEntityData.length) {
      return null
    }
    const totals = METRIC_COLUMNS.reduce<Record<MetricKey, number>>((acc, column) => {
      acc[column.key] = 0
      return acc
    }, {} as Record<MetricKey, number>)

    for (const record of selectedEntityData) {
      for (const column of METRIC_COLUMNS) {
        totals[column.key] += record.metrics[column.key] ?? 0
      }
    }
    return totals
  }, [selectedEntityData])

  const selectedEntityDerivedSummary = useMemo(() => {
    if (!selectedEntityTotals) {
      return null
    }
    return DERIVED_METRICS.map(metric => ({
      key: metric.key,
      label: metric.label,
      value: metric.compute(selectedEntityTotals),
      formatter: metric.formatter
    }))
  }, [selectedEntityTotals])

  const selectedEntityDailyRows = useMemo(() => {
    if (!selectedEntityData.length) {
      return []
    }
    return selectedEntityData.map(record => ({
      date: record.date,
      metrics: record.metrics,
      derived: DERIVED_METRICS.map(metric => ({
        key: metric.key,
        value: metric.compute(record.metrics as Record<MetricKey, number>),
        formatter: metric.formatter
      }))
    }))
  }, [selectedEntityData])

  const accountBreadcrumbLabel = useMemo(
    () => submittedAccountName ?? lastSubmittedParams?.accountId ?? '—',
    [submittedAccountName, lastSubmittedParams]
  )

  const hasActiveSelection = useMemo(() => {
    const levelKeys: HierarchyLevel[] = ['campaign', 'adset', 'ad']
    return levelKeys.some(level => selectedEntityIds[level]?.size > 0)
  }, [selectedEntityIds])

  const handleClearSelectionFilters = useCallback(() => {
    setSelectedEntityIds(createEmptySelectionMap())
    setDrillSelection(prev => ({
      account: prev.account,
      campaign: null,
      adset: null,
      ad: null
    }))
    setOpenDropdownLevel(null)
    if (!lastSubmittedParams) {
      return
    }
    const nextQuery = buildQueryForLevel(resultLevel, lastSubmittedParams, null)
    if (!nextQuery) {
      return
    }
    const shouldRefetchSameQuery = activeQuery ? areQueriesEqual(activeQuery, nextQuery) : false
    setActiveQuery(nextQuery)
    if (shouldRefetchSameQuery) {
      void queryResult.refetch()
    }
  }, [buildQueryForLevel, lastSubmittedParams, resultLevel, activeQuery, queryResult])

  const handleDropdownItemToggle = useCallback(
    (level: Exclude<HierarchyLevel, 'account'>, optionId: string, checked: boolean) => {
      setSelectedEntityIds(prev => {
        const updated: Record<HierarchyLevel, Set<string>> = {
          account: new Set(prev.account),
          campaign: new Set(prev.campaign),
          adset: new Set(prev.adset),
          ad: new Set(prev.ad)
        }
        const nextSet = new Set(updated[level])
        if (checked) {
          nextSet.add(optionId)
        } else {
          nextSet.delete(optionId)
        }
        const totalOptions = drillOptions[level].length
        if (totalOptions > 0 && nextSet.size === totalOptions) {
          nextSet.clear()
        }
        updated[level] = nextSet
        return updated
      })
    },
    [drillOptions]
  )

  const handleDropdownClearLevel = useCallback((level: Exclude<HierarchyLevel, 'account'>) => {
    setSelectedEntityIds(prev => {
      const updated: Record<HierarchyLevel, Set<string>> = {
        account: new Set(prev.account),
        campaign: new Set(prev.campaign),
        adset: new Set(prev.adset),
        ad: new Set(prev.ad)
      }
      updated[level] = new Set<string>()
      return updated
    })
  }, [])

  const toggleDropdownLevel = useCallback((level: Exclude<HierarchyLevel, 'account'>) => {
    setOpenDropdownLevel(prev => (prev === level ? null : level))
  }, [])

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
    if (!useDatabaseSource && !useRealtimeSource) {
      setFormError('请至少选择一个数据源（数据库或实时数据）')
      return
    }
    const normalizedAccount = normalizeAccountId(accountInput)
    if (!normalizedAccount) {
      setFormError('请输入广告账号 ID，例如 act_123456789')
      return
    }
    const dataSourceMode: InsightsDataQuery['source'] =
      useDatabaseSource && useRealtimeSource
        ? 'hybrid'
        : useRealtimeSource
          ? 'realtime'
          : 'database'
    const submittedParams: SubmittedParams = {
      accountId: normalizedAccount,
      since: sinceDate,
      until: untilDate,
      source: dataSourceMode,
      timeIncrement: timeIncrement === 'daily' ? 1 : null,
      breakdowns: breakdowns.trim() || undefined
    }
    setFormError(null)
    setSubmittedAccountName(selectedAccountName ?? null)
    setSyncingEntityIds(new Set())
    setLastSubmittedParams(submittedParams)
    setSelectedEntityIds(createEmptySelectionMap())
    setDrillSelection({
      account: normalizedAccount,
      campaign: null,
      adset: null,
      ad: null
    })
    setDetailEntityId(null)
    setDetailEntityName(null)
    setIsModalOpen(false)

    const nextQuery = buildQueryForLevel(activeLevel, submittedParams)
    if (!nextQuery) {
      return
    }
    const shouldRefetchSameQuery = activeQuery ? areQueriesEqual(activeQuery, nextQuery) : false
    setActiveQuery(nextQuery)

    if (shouldRefetchSameQuery) {
      void queryResult.refetch()
    }
  }

  const handleLevelChange = (nextLevel: HierarchyLevel) => {
    setActiveLevel(nextLevel)
    if (!lastSubmittedParams) {
      return
    }
    const nextQuery = buildQueryForLevel(nextLevel)
    if (!nextQuery) {
      return
    }
    const shouldRefetchSameQuery = activeQuery ? areQueriesEqual(activeQuery, nextQuery) : false
    setActiveQuery(nextQuery)
    if (shouldRefetchSameQuery) {
      void queryResult.refetch()
    }
  }

  const handleRowFocus = (entityId: string) => {
    const currentIndex = HIERARCHY_LEVELS.indexOf(resultLevel)
    const isSameEntity = drillSelection[resultLevel] === entityId

    setDrillSelection(prev => {
      const updated: Record<HierarchyLevel, string | null> = { ...prev }
      updated[resultLevel] = isSameEntity ? null : entityId
      for (let idx = currentIndex + 1; idx < HIERARCHY_LEVELS.length; idx += 1) {
        updated[HIERARCHY_LEVELS[idx]] = null
      }
      return updated
    })
    setSelectedEntityIds(prev => {
      const updated: Record<HierarchyLevel, Set<string>> = {
        account: new Set(prev.account),
        campaign: new Set(prev.campaign),
        adset: new Set(prev.adset),
        ad: new Set(prev.ad)
      }
      for (let idx = currentIndex + 1; idx < HIERARCHY_LEVELS.length; idx += 1) {
        updated[HIERARCHY_LEVELS[idx]] = new Set<string>()
      }
      return updated
    })
  }

  const handleDetailOpen = (entityId: string, entityName: string | null) => {
    setDetailEntityId(entityId)
    setDetailEntityName(entityName ?? null)
    setIsModalOpen(true)
  }

  const handleModalClose = () => {
    setIsModalOpen(false)
    setDetailEntityId(null)
    setDetailEntityName(null)
  }

  const toggleRowSelection = (entityId: string, checked: boolean) => {
    setSelectedEntityIds(prev => {
      const updated: Record<HierarchyLevel, Set<string>> = {
        account: new Set(prev.account),
        campaign: new Set(prev.campaign),
        adset: new Set(prev.adset),
        ad: new Set(prev.ad)
      }
      if (checked) {
        updated[resultLevel].add(entityId)
      } else {
        updated[resultLevel].delete(entityId)
      }
      return updated
    })
  }

  const handleMetricToggle = (metricKey: MetricKey, checked: boolean) => {
    setVisibleMetricKeys(prev => {
      if (checked) {
        if (prev.includes(metricKey)) {
          return prev
        }
        return [...prev, metricKey]
      }
      if (prev.length === 1) {
        message.warning('至少选择一个指标列')
        return prev
      }
      return prev.filter(key => key !== metricKey)
    })
  }

  const moveColumn = useCallback((metricKey: MetricKey, direction: 'up' | 'down') => {
    setColumnOrder(order => {
      const currentIndex = order.indexOf(metricKey)
      if (currentIndex === -1) {
        return order
      }
      const nextIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1
      if (nextIndex < 0 || nextIndex >= order.length) {
        return order
      }
      const next = [...order]
      const [removed] = next.splice(currentIndex, 1)
      next.splice(nextIndex, 0, removed)
      return next
    })
  }, [])

  const handleColumnWidthChange = useCallback((metricKey: MetricKey, rawValue: number) => {
    setColumnWidths(prev => ({
      ...prev,
      [metricKey]: clampWidth(rawValue)
    }))
  }, [])

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
              选择广告账号与时间区间，查询后可在结果区域切换账号 / 广告系列 / 广告组 / 广告四级数据，并查看日级表现。
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
              onChange={value => {
                setAccountInput(value)
                if (!value) {
                  setSelectedAccountName(null)
                }
              }}
              placeholder="act_123456789"
              inputClassName="input"
              required
              helperText="可输入或从下拉列表选择 act_ 开头的账号 ID。"
              onAccountDetailsChange={details => {
                setSelectedAccountName(details?.name ?? null)
              }}
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
          <div className="form-label" style={{ flex: '2 1 320px' }}>
            <span>数据源</span>
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
              <label
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 500 }}
              >
                <input
                  type="checkbox"
                  checked={useDatabaseSource}
                  onChange={event => setUseDatabaseSource(event.target.checked)}
                />
                <span>数据库</span>
              </label>
              <label
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 500 }}
              >
                <input
                  type="checkbox"
                  checked={useRealtimeSource}
                  onChange={event => setUseRealtimeSource(event.target.checked)}
                />
                <span>实时数据</span>
              </label>
            </div>
            <div className="form-hint">
              至少勾选一个选项。勾选“实时数据”时会直接从 Facebook 拉取最新数据；同时勾选两个选项时自动调用混合接口，用数据库 + 最新实时数据拼接结果。
            </div>
          </div>

          {formError && (
            <div style={{ flexBasis: '100%', color: 'var(--color-danger)' }}>{formError}</div>
          )}
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button className="button button--primary" type="submit" disabled={isLoading}>
              {isLoading ? '查询中…' : '查询 / 刷新数据'}
            </button>
          </div>
        </form>
      </section>

      <section className="card" style={{ marginTop: '1.5rem' }}>
        <div className="card__header">
          <div>
            <div className="card__title">洞察结果</div>
            <div className="card__subtitle">
              {activeQuery
                ? `账号 ${activeQuery.accountId} · ${activeQuery.since} → ${activeQuery.until} · 数据源：${
                    DATA_SOURCE_LABEL[activeQuery.source]
                  }`
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
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '1rem',
                flexWrap: 'wrap',
                marginBottom: '1rem'
              }}
            >
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {HIERARCHY_LEVELS.map(levelKey => {
                  const isActiveTab = resultLevel === levelKey
                  return (
                    <button
                      type="button"
                      key={levelKey}
                      className="button button--ghost"
                      style={{
                        padding: '0.35rem 0.9rem',
                        borderRadius: '999px',
                        border: isActiveTab
                          ? '1px solid var(--color-primary, #1677ff)'
                          : '1px solid var(--color-border, #d9d9d9)',
                        backgroundColor: isActiveTab ? 'var(--color-primary, #1677ff)' : 'transparent',
                        color: isActiveTab ? '#fff' : 'inherit',
                        cursor: !lastSubmittedParams ? 'not-allowed' : 'pointer',
                        opacity: !lastSubmittedParams && !isActiveTab ? 0.5 : 1
                      }}
                      onClick={() => handleLevelChange(levelKey)}
                      disabled={!lastSubmittedParams}
                    >
                      {LEVEL_LABELS[levelKey]}
                    </button>
                  )
                })}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className="button button--ghost"
                  onClick={() => setIsColumnPickerOpen(true)}
                  disabled={!lastSubmittedParams}
                >
                  自定义列
                </button>
                <span style={{ color: 'var(--color-text-muted)' }}>
                  当前层级选中 {currentLevelSelection.size} 个
                </span>
              </div>
            </div>

            <div
              style={{
                marginBottom: '1rem',
                fontSize: '0.85rem',
                color: 'var(--color-text-muted)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                flexWrap: 'wrap'
              }}
            >
              <span>广告账号：{accountBreadcrumbLabel}</span>
              {(['campaign', 'adset', 'ad'] as Array<Exclude<HierarchyLevel, 'account'>>).map(levelKey => {
                const selectedSet = selectedEntityIds[levelKey] ?? new Set<string>()
                const options = drillOptions[levelKey]
                const summaryLabel =
                  selectedSet.size === 0 ? `全部${LEVEL_LABELS[levelKey]}` : `已选 ${selectedSet.size}`
                return (
                  <div
                    key={levelKey}
                    ref={node => {
                      dropdownRefs.current[levelKey] = node
                    }}
                    style={{ position: 'relative', display: 'inline-flex', flexDirection: 'column', gap: '0.4rem' }}
                  >
                    <button
                      type="button"
                      className="button button--ghost"
                      onClick={() => toggleDropdownLevel(levelKey)}
                      style={{ minWidth: '200px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                    >
                      <span>{LEVEL_LABELS[levelKey]}：{summaryLabel}</span>
                      <span style={{ fontSize: '0.75rem' }}>{openDropdownLevel === levelKey ? '▲' : '▼'}</span>
                    </button>
                    {openDropdownLevel === levelKey && (
                      <div
                        style={{
                          position: 'absolute',
                          top: '110%',
                          left: 0,
                          minWidth: '220px',
                          background: '#fff',
                          border: '1px solid var(--color-border, #d9d9d9)',
                          borderRadius: '8px',
                          boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
                          maxHeight: '240px',
                          overflow: 'auto',
                          zIndex: 5,
                          padding: '8px 12px'
                        }}
                      >
                        <div style={{ marginBottom: '8px', fontWeight: 500 }}>{LEVEL_LABELS[levelKey]}筛选</div>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
                          <input
                            type="checkbox"
                            checked={selectedSet.size === 0}
                            onChange={() => handleDropdownClearLevel(levelKey)}
                          />
                          <span>全部{LEVEL_LABELS[levelKey]}</span>
                        </label>
                        {options.length === 0 ? (
                          <div style={{ color: 'var(--color-text-muted)' }}>暂无可选项</div>
                        ) : (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                            {options.map(optionId => (
                              <label
                                key={`${levelKey}-${optionId}`}
                                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                              >
                                <input
                                  type="checkbox"
                                  checked={selectedSet.has(optionId)}
                                  onChange={event => handleDropdownItemToggle(levelKey, optionId, event.target.checked)}
                                />
                                <span style={{ wordBreak: 'break-all' }}>{optionId}</span>
                              </label>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
              <button
                type="button"
                className="button button--ghost"
                onClick={handleClearSelectionFilters}
                disabled={!hasActiveSelection || !lastSubmittedParams}
              >
                清空筛选
              </button>
            </div>

            <div className="card__body" style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
              <div>
                <div style={{ fontSize: '2rem', fontWeight: 600 }}>{aggregatedInsights.length}</div>
                <div style={{ color: 'var(--color-text-muted)' }}>
                  {idColumnName} 数量
                </div>
              </div>
              {totals && (
                <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>
                  {orderedColumns.slice(0, 4).map(column => (
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
                    <th
                      style={{
                        width: '56px',
                        position: 'sticky',
                        left: 0,
                        zIndex: 2,
                        background: '#fff'
                      }}
                    >
                      <input
                        ref={headerCheckboxRef}
                        type="checkbox"
                        checked={isAllCurrentPageSelected && paginatedAggregatedInsights.length > 0}
                        onChange={handleSelectAllChange}
                        disabled={!paginatedAggregatedInsights.length}
                      />
                    </th>
                    <th
                      style={{
                        minWidth: '320px',
                        position: 'sticky',
                        left: 56,
                        zIndex: 1,
                        background: '#fff'
                      }}
                    >
                      {idColumnName}
                    </th>
                    <th style={{ width: '180px' }}>状态</th>
                    <th style={{ width: '180px' }}>操作</th>
                    {visibleMetricColumns.map(column => (
                      <th
                        key={column.key}
                        style={{
                          width: columnWidths[column.key],
                          minWidth: columnWidths[column.key]
                        }}
                      >
                        {column.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {paginatedAggregatedInsights.map(entity => {
                    const isActiveRow = drillSelection[resultLevel] === entity.entityId
                    const checkboxChecked = currentLevelSelection.has(entity.entityId)
                    const currentIndex = HIERARCHY_LEVELS.indexOf(resultLevel)
                    const statusColor = getStatusColor(entity.configuredStatus)
                    const isSyncingName = syncingEntityIds.has(entity.entityId)
                    const displayNameText = entity.entityName ?? (isSyncingName ? '同步中' : '名称未同步')
                    const nameCell = entity.entityName ? (
                      entity.entityName
                    ) : isSyncingName ? (
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px',
                          color: 'var(--color-text-muted)'
                        }}
                      >
                        <Spin size="small" />
                        <span>同步中…</span>
                      </span>
                    ) : (
                      <span style={{ color: 'var(--color-text-muted)' }}>名称未同步</span>
                    )
                    const showAvatar = resultLevel === 'ad'

                    return (
                      <tr
                        key={entity.entityId}
                        onClick={() => handleRowFocus(entity.entityId)}
                        style={{
                          cursor: 'pointer',
                          transition: 'background-color 0.2s',
                          backgroundColor: isActiveRow ? 'rgba(22,119,255,0.08)' : 'transparent'
                        }}
                      >
                        <td
                          style={{
                            width: '56px',
                            position: 'sticky',
                            left: 0,
                            zIndex: 2,
                            background: '#fff'
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={checkboxChecked}
                            onChange={event => {
                              event.stopPropagation()
                              toggleRowSelection(entity.entityId, event.target.checked)
                            }}
                          />
                        </td>
                        <td
                          style={{
                            minWidth: '320px',
                            position: 'sticky',
                            left: 56,
                            zIndex: 1,
                            background: '#fff'
                          }}
                          title={entity.entityId}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            {showAvatar && (
                              <div
                                style={{
                                  width: 40,
                                  height: 40,
                                  borderRadius: 6,
                                  background: '#f5f5f5',
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  fontWeight: 600
                                }}
                              >
                                {(displayNameText && displayNameText.charAt(0)) || entity.entityId.slice(-2)}
                              </div>
                            )}
                            <div>
                              <div
                                style={{
                                  fontWeight: entity.entityName ? 600 : 400,
                                  color: entity.entityName ? 'inherit' : 'var(--color-text-muted)'
                                }}
                              >
                                {nameCell}
                              </div>
                              <div style={{ fontFamily: 'monospace', fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
                                {entity.entityId}
                              </div>
                              <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                                覆盖 {entity.dateCount} 天（{entity.startDate} ~ {entity.endDate}）
                              </div>
                            </div>
                          </div>
                        </td>
                        <td
                          title={`数据范围：${entity.startDate} ~ ${entity.endDate}`}
                          style={{ width: '180px' }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                            <span
                              style={{
                                width: 10,
                                height: 10,
                                borderRadius: '50%',
                                backgroundColor: statusColor,
                                display: 'inline-block'
                              }}
                            />
                            <span>{entity.configuredStatus ?? '—'}</span>
                          </div>
                          {entity.effectiveStatus && entity.effectiveStatus !== entity.configuredStatus && (
                            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                              有效：{entity.effectiveStatus}
                            </div>
                          )}
                        </td>
                        <td style={{ width: '180px' }}>
                          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                            <button
                              type="button"
                              className="button button--ghost"
                              onClick={event => {
                                event.stopPropagation()
                                handleDetailOpen(entity.entityId, entity.entityName)
                              }}
                            >
                              详情
                            </button>
                          </div>
                        </td>
                        {visibleMetricColumns.map(column => (
                          <td
                            key={`${entity.entityId}-${column.key}`}
                            style={{
                              width: columnWidths[column.key],
                              minWidth: columnWidths[column.key]
                            }}
                          >
                            <span
                              title={formatMetricTooltip(entity.entityId, column.key) || '暂无日度数据'}
                              style={{ cursor: 'help' }}
                            >
                              {column.formatter(entity.metrics[column.key] ?? 0)}
                            </span>
                          </td>
                        ))}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {aggregatedInsights.length > 0 && (
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginTop: '12px',
                  flexWrap: 'wrap',
                  gap: '12px'
                }}
              >
                <div style={{ color: 'var(--color-text-secondary, #666)' }}>
                  共 {aggregatedInsights.length} 条记录，每页显示 {TABLE_PAGE_SIZE} 条
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <button
                    type="button"
                    onClick={() => setCurrentPage(page => Math.max(1, page - 1))}
                    disabled={currentPage === 1}
                    style={{
                      padding: '6px 12px',
                      borderRadius: '4px',
                      border: '1px solid var(--color-border, #d9d9d9)',
                      backgroundColor: currentPage === 1 ? '#f5f5f5' : 'white',
                      cursor: currentPage === 1 ? 'not-allowed' : 'pointer'
                    }}
                  >
                    上一页
                  </button>
                  <span style={{ minWidth: '90px', textAlign: 'center' }}>
                    第 {currentPage} / {totalPages} 页
                  </span>
                  <button
                    type="button"
                    onClick={() => setCurrentPage(page => Math.min(totalPages, page + 1))}
                    disabled={currentPage === totalPages}
                    style={{
                      padding: '6px 12px',
                      borderRadius: '4px',
                      border: '1px solid var(--color-border, #d9d9d9)',
                      backgroundColor: currentPage === totalPages ? '#f5f5f5' : 'white',
                      cursor: currentPage === totalPages ? 'not-allowed' : 'pointer'
                    }}
                  >
                    下一页
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </section>

      <Modal
        title="自定义指标列"
        open={isColumnPickerOpen}
        onCancel={() => setIsColumnPickerOpen(false)}
        footer={null}
        destroyOnClose
      >
        <div
          className={`${columnModalPrefix}__list`}
          style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}
        >
          {columnOrder.map(metricKey => {
            const column = METRIC_COLUMNS.find(item => item.key === metricKey)
            if (!column) {
              return null
            }
            const checked = visibleMetricKeys.includes(column.key)
            return (
              <div
                key={column.key}
                className={`${columnModalPrefix}__item`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '0.5rem',
                  padding: '0.4rem 0.2rem',
                  borderBottom: '1px solid var(--color-border, #f0f0f0)'
                }}
              >
                <label
                  style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 500 }}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={event => handleMetricToggle(column.key, event.target.checked)}
                  />
                  <span>{column.label}</span>
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                  <button
                    type="button"
                    className="button button--ghost"
                    onClick={() => moveColumn(column.key, 'up')}
                    disabled={columnOrder[0] === column.key}
                    style={{ padding: '0.15rem 0.5rem' }}
                  >
                    上移
                  </button>
                  <button
                    type="button"
                    className="button button--ghost"
                    onClick={() => moveColumn(column.key, 'down')}
                    disabled={columnOrder[columnOrder.length - 1] === column.key}
                    style={{ padding: '0.15rem 0.5rem' }}
                  >
                    下移
                  </button>
                </div>
                <div style={{ width: '100px', textAlign: 'right' }}>
                  <input
                    type="number"
                    min={80}
                    max={400}
                    value={columnWidths[column.key] ?? DEFAULT_COLUMN_WIDTHS[column.key]}
                    onChange={event => handleColumnWidthChange(column.key, Number(event.target.value))}
                    style={{ width: '100%', padding: '0.15rem', fontSize: '0.85rem' }}
                  />
                </div>
              </div>
            )
          })}
        </div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: '1rem',
            flexWrap: 'wrap',
            gap: '0.5rem'
          }}
        >
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              type="button"
              className="button button--ghost"
              onClick={() => setVisibleMetricKeys([...columnOrder])}
            >
              全部显示
            </button>
            <button
              type="button"
              className="button button--ghost"
              onClick={() => {
                setColumnOrder([...DEFAULT_COLUMN_ORDER])
                setVisibleMetricKeys(DEFAULT_VISIBLE_METRICS)
                setColumnWidths({ ...DEFAULT_COLUMN_WIDTHS })
              }}
            >
              恢复默认
            </button>
          </div>
          <button
            type="button"
            className="button button--primary"
            onClick={() => setIsColumnPickerOpen(false)}
          >
            完成
          </button>
        </div>
      </Modal>

      <Modal
        title={
          detailEntityName
            ? `${detailEntityName} (${detailEntityId ?? ''})`
            : `${idColumnName} 历史数据: ${detailEntityId ?? ''}`
        }
        open={isModalOpen}
        onCancel={handleModalClose}
        width={1100}
        footer={null}
      >
        {selectedEntityData.length === 0 ? (
          <div style={{ color: 'var(--color-text-muted)' }}>请选择一个实体查看明细数据。</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', padding: '8px 0' }}>
            {selectedEntityTotals && (
              <section>
                <h3 style={{ marginBottom: '12px' }}>基础指标汇总</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
                  {METRIC_COLUMNS.map(column => (
                    <div
                      key={column.key}
                      style={{
                        padding: '12px',
                        borderRadius: '8px',
                        background: 'var(--color-bg-muted, #fafafa)',
                        border: '1px solid var(--color-border, #f0f0f0)'
                      }}
                    >
                      <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>
                        {column.formatter(selectedEntityTotals[column.key])}
                      </div>
                      <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>{column.label}</div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {selectedEntityDerivedSummary && (
              <section>
                <h3 style={{ marginBottom: '12px' }}>扩展指标汇总</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
                  {selectedEntityDerivedSummary.map(item => (
                    <div
                      key={item.key}
                      style={{
                        padding: '12px',
                        borderRadius: '8px',
                        background: 'var(--color-bg-muted, #fafafa)',
                        border: '1px solid var(--color-border, #f0f0f0)'
                      }}
                    >
                      <div style={{ fontSize: '1.1rem', fontWeight: 600 }}>{item.formatter(item.value)}</div>
                      <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>{item.label}</div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            <section>
              <h3 style={{ marginBottom: '12px' }}>每日表现</h3>
              <div className="table-wrapper" style={{ maxHeight: '420px', overflow: 'auto' }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th style={{ width: '120px' }}>日期</th>
                      {METRIC_COLUMNS.map(column => (
                        <th key={`base-${column.key}`}>{column.label}</th>
                      ))}
                      {DERIVED_METRICS.map(metric => (
                        <th key={`derived-${metric.key}`}>{metric.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {selectedEntityDailyRows.map(row => (
                      <tr key={row.date}>
                        <td>{row.date}</td>
                        {METRIC_COLUMNS.map(column => (
                          <td key={`${row.date}-${column.key}`}>
                            {column.formatter(row.metrics[column.key] ?? 0)}
                          </td>
                        ))}
                        {row.derived.map(metric => (
                          <td key={`${row.date}-${metric.key}`}>{metric.formatter(metric.value)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        )}
      </Modal>
    </div>
  )
}

export default InsightsDataPage

