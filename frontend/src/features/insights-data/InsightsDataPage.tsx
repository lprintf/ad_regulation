import { useMemo, useState, useEffect, useRef, useCallback, useContext } from 'react'
import { useQuery, useQueries, useQueryClient } from '@tanstack/react-query'
import { Modal, message, ConfigProvider, Spin } from 'antd'
import {
  fetchInsightsData,
  syncEntityNames,
  type InsightsDataQuery,
  type SyncedEntityName
} from '../../api/insights'
import { fetchAdAccounts } from '../../api/adAccounts'
import type { InsightRecord, InsightsDataResponse } from '../../types/insights'

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
const MAX_SELECTED_ACCOUNTS = 9

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
  'campaign_id'
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
  accountId: string | null
  dateCount: number
  metrics: Record<MetricKey, number>
  startDate: string
  endDate: string
  configuredStatus: string | null
  effectiveStatus: string | null
}

const DATA_SOURCE_LABEL: Record<InsightsDataQuery['source'], string> = {
  'frontend-hybrid': '混合（前端拼接）',
  database: '数据库',
  realtime: '实时数据',
  hybrid: '混合（后端）'
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

const areSetsEqual = (a: Set<string>, b: Set<string>) => {
  if (a.size !== b.size) {
    return false
  }
  for (const value of a) {
    if (!b.has(value)) {
      return false
    }
  }
  return true
}

const getDefaultDateRange = () => {
  const today = new Date()
  const until = new Date(today.getTime() - 3 * 24 * 60 * 60 * 1000)
  const since = new Date(until)
  since.setDate(since.getDate() - 6)
  const format = (value: Date) => value.toISOString().slice(0, 10)
  return { since: format(since), until: format(until) }
}

const InsightsDataPage = () => {
  const queryClient = useQueryClient()
  const defaultRange = useMemo(getDefaultDateRange, [])
  const [sinceDate, setSinceDate] = useState(defaultRange.since)
  const [untilDate, setUntilDate] = useState(defaultRange.until)
  const [timeIncrement, setTimeIncrement] = useState<'daily' | 'aggregate'>('daily')
  const [breakdowns, setBreakdowns] = useState('')
  const [selectedDataSource, setSelectedDataSource] =
    useState<InsightsDataQuery['source']>('frontend-hybrid')
  const [formError, setFormError] = useState<string | null>(null)
  const [activeLevel, setActiveLevel] = useState<HierarchyLevel>('account')
  const [lastSubmittedParams, setLastSubmittedParams] = useState<SubmittedParams | null>(null)
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
  const [selectedAccountIds, setSelectedAccountIds] = useState<Set<string>>(() => new Set())
  const [activeAccountIds, setActiveAccountIds] = useState<Set<string>>(() => new Set())
  const {
    data: adAccounts = [],
    isLoading: isLoadingAccounts,
    isError: isAdAccountError
  } = useQuery({
    queryKey: ['insights', 'ad-accounts'],
    queryFn: fetchAdAccounts,
    staleTime: 5 * 60_000
  })
  const adAccountNameMap = useMemo(() => {
    const map = new Map<string, string>()
    for (const account of adAccounts) {
      map.set(account.id, account.name ?? account.id)
    }
    return map
  }, [adAccounts])
  useEffect(() => {
    if (!adAccounts.length) {
      return
    }
    setSelectedAccountIds(prev => {
      if (prev.size > 0) {
        return prev
      }
      const initialIds = adAccounts.slice(0, MAX_SELECTED_ACCOUNTS).map(account => account.id)
      const initialSet = new Set(initialIds)
      setActiveAccountIds(current => (current.size > 0 ? current : initialSet))
      return initialSet
    })
  }, [adAccounts])

  useEffect(() => {
    if (lastSubmittedParams || selectedAccountIds.size === 0) {
      return
    }
    setLastSubmittedParams({
      since: defaultRange.since,
      until: defaultRange.until,
      source: selectedDataSource,
      timeIncrement: timeIncrement === 'daily' ? 1 : null,
      breakdowns: breakdowns.trim() || undefined
    })
  }, [
    breakdowns,
    defaultRange.since,
    defaultRange.until,
    lastSubmittedParams,
    selectedAccountIds.size,
    selectedDataSource,
    timeIncrement
  ])

  useEffect(() => {
    if (selectedAccountIds.size === 0) {
      return
    }
    setActiveAccountIds(new Set(selectedAccountIds))
  }, [selectedAccountIds])

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
      accountId: string,
      targetLevel: HierarchyLevel,
      forcedFilter?: { level: Exclude<HierarchyLevel, 'account'>; ids: string[] } | null
    ): InsightsDataQuery | null => {
      if (!lastSubmittedParams) {
        return null
      }
      const baseFilter =
        forcedFilter === undefined ? resolveObjectFilter(targetLevel) : forcedFilter
      let filter = baseFilter ?? null
      if (filter) {
        const filteredIds = filter.ids.filter(
          id => entityAccountMapRef.current.get(id) === accountId
        )
        if (filteredIds.length === 0) {
          filter = null
        } else {
          filter = {
            level: filter.level,
            ids: filteredIds
          }
        }
      }
      const shouldRequestRealtimeFields = lastSubmittedParams.source !== 'database'
      return {
        accountId,
        since: lastSubmittedParams.since,
        until: lastSubmittedParams.until,
        level: targetLevel,
        timeIncrement: lastSubmittedParams.timeIncrement,
        breakdowns: lastSubmittedParams.breakdowns,
        source: lastSubmittedParams.source,
        fields: shouldRequestRealtimeFields ? [...REALTIME_ENTITY_FIELDS] : undefined,
        objectLevel: filter?.level,
        objectIds: filter?.ids
      }
    },
    [lastSubmittedParams, resolveObjectFilter]
  )

  // The level of the currently displayed dataset.
  const resultLevel = activeLevel

  // Track which queries have had their entity names synced to prevent duplicate syncing
  const syncedQueriesRef = useRef<Set<string>>(new Set())
  const entityAccountMapRef = useRef<Map<string, string>>(new Map())
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
  const getEntityId = useCallback((record: InsightRecord) => {
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
    return ''
  }, [])

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
        const accountId = record.adAccountId ?? ''
        return adAccountNameMap.get(accountId) ?? accountId ?? null
      }
      return null
    },
    [adAccountNameMap, resultLevel]
  )

  const objectFilterKey = useMemo(() => {
    const parentLevels: Array<Exclude<HierarchyLevel, 'account'>> = ['campaign', 'adset', 'ad']
    const entries = parentLevels
      .map(level => `${level}:${Array.from(selectedEntityIds[level]).sort().join('|')}`)
      .join(';')
    return entries
  }, [selectedEntityIds])

  const accountsToQuery = useMemo(() => {
    if (activeLevel === 'account') {
      return adAccounts.map(account => account.id)
    }
    const source =
      activeAccountIds.size > 0
        ? activeAccountIds
        : selectedAccountIds.size > 0
          ? selectedAccountIds
          : new Set(adAccounts.slice(0, MAX_SELECTED_ACCOUNTS).map(account => account.id))
    return Array.from(source)
  }, [activeAccountIds, activeLevel, adAccounts, selectedAccountIds])

  const accountSelectionKey = useMemo(
    () => accountsToQuery.join(','),
    [accountsToQuery]
  )

  const accountQueries = useQueries({
    queries: accountsToQuery.map(accountId => ({
      queryKey: [
        'insights-data',
        accountId,
        activeLevel,
        lastSubmittedParams?.since ?? '',
        lastSubmittedParams?.until ?? '',
        lastSubmittedParams?.source ?? 'database',
        lastSubmittedParams?.timeIncrement ?? 'null',
        lastSubmittedParams?.breakdowns ?? '',
        objectFilterKey
      ],
      enabled: Boolean(lastSubmittedParams),
      queryFn: async () => {
        const query = buildQueryForLevel(accountId, activeLevel)
        if (!query) {
          return {
            insights: [],
            totalRecords: 0,
            dateRange: {
              since: lastSubmittedParams?.since ?? '',
              until: lastSubmittedParams?.until ?? ''
            }
          } satisfies InsightsDataResponse
        }
        return fetchInsightsData(query)
      }
    }))
  })

  const accountQueryEntries = useMemo(
    () =>
      accountsToQuery.map((accountId, index) => ({
        accountId,
        query: accountQueries[index]
      })),
    [accountQueries, accountsToQuery]
  )

  const refetchInsights = useCallback(() => {
    accountQueryEntries.forEach(entry => {
      if (entry.query?.refetch) {
        void entry.query.refetch()
      }
    })
  }, [accountQueryEntries])

  const insights: InsightRecord[] = useMemo(() => {
    if (!accountQueryEntries.length) {
      return []
    }
    const merged = accountQueryEntries.flatMap(entry => entry.query.data?.insights ?? [])
    return merged.sort((a, b) => a.date.localeCompare(b.date))
  }, [accountQueryEntries])

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
      entityAccountMapRef.current.clear()
      return []
    }

    entityAccountMapRef.current.clear()

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
          accountId: record.adAccountId ?? null,
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
      if (!entity.accountId && record.adAccountId) {
        entity.accountId = record.adAccountId
      }
      if (record.date < entity.startDate) {
        entity.startDate = record.date
      }
      if (record.date > entity.endDate) {
        entity.endDate = record.date
      }
      if (entity.accountId) {
        entityAccountMapRef.current.set(entityId, entity.accountId)
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

  useEffect(() => {
    if (!selectedAccountIds.size) {
      return
    }
    setSelectedEntityIds(prev => {
      if (areSetsEqual(prev.account, selectedAccountIds)) {
        return prev
      }
      return {
        account: new Set(selectedAccountIds),
        campaign: new Set(prev.campaign),
        adset: new Set(prev.adset),
        ad: new Set(prev.ad)
      }
    })
  }, [selectedAccountIds])

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

    if (resultLevel === 'account') {
      setSelectedAccountIds(prev => {
        const next = new Set(prev)
        let changed = false
        if (checked) {
          for (const entity of paginatedAggregatedInsights) {
            if (next.has(entity.entityId)) {
              continue
            }
            if (next.size >= MAX_SELECTED_ACCOUNTS) {
              message.warning(`最多只能选择 ${MAX_SELECTED_ACCOUNTS} 个广告账号`)
              break
            }
            next.add(entity.entityId)
            changed = true
          }
        } else {
          paginatedAggregatedInsights.forEach(entity => {
            if (next.size > 1) {
              next.delete(entity.entityId)
              changed = true
            }
          })
          if (next.size === 0 && paginatedAggregatedInsights.length > 0) {
            next.add(paginatedAggregatedInsights[0].entityId)
            message.warning('至少保留一个广告账号以便继续查询')
          }
        }
        if (!changed) {
          return prev
        }
        setSelectedEntityIds(prevIds => ({
          account: new Set(next),
          campaign: new Set(prevIds.campaign),
          adset: new Set(prevIds.adset),
          ad: new Set(prevIds.ad)
        }))
        return next
      })
      return
    }

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
    (accountId: string, entities: SyncedEntityName[]) => {
      if (!entities.length || !lastSubmittedParams) {
        return
      }

      const queryKey = [
        'insights-data',
        accountId,
        resultLevel,
        lastSubmittedParams.since,
        lastSubmittedParams.until,
        lastSubmittedParams.source,
        lastSubmittedParams.timeIncrement ?? 'null',
        lastSubmittedParams.breakdowns ?? '',
        objectFilterKey
      ] as const

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

          if (resultLevel === 'adset') {
            return {
              ...record,
              adsetName: details.name ?? record.adsetName,
              configuredStatus: details.configuredStatus ?? record.configuredStatus,
              effectiveStatus: details.effectiveStatus ?? record.effectiveStatus
            }
          }
          if (resultLevel === 'campaign') {
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
    [getEntityId, lastSubmittedParams, objectFilterKey, queryClient, resultLevel]
  )

  useEffect(() => {
    if (!lastSubmittedParams || resultLevel === 'account') {
      return
    }

    accountQueryEntries.forEach(entry => {
      const accountId = entry.accountId
      const queryData = entry.query?.data
      if (!queryData?.insights?.length) {
        return
      }

      const queryKey = `${accountId}-${resultLevel}-${lastSubmittedParams.since}-${lastSubmittedParams.until}-${lastSubmittedParams.source}-${objectFilterKey}`
      if (syncedQueriesRef.current.has(queryKey)) {
        return
      }

      const unnamedEntityIds = new Set<string>()
      for (const record of queryData.insights) {
        const entityId = getEntityId(record)
        const entityName = getEntityName(record)
        if (!entityName && entityId) {
          unnamedEntityIds.add(entityId)
        }
      }

      if (unnamedEntityIds.size === 0) {
        return
      }

      syncedQueriesRef.current.add(queryKey)
      const pendingIds = Array.from(unnamedEntityIds)
      updateSyncingEntities(pendingIds, 'add')

      const requestedEntityType =
        resultLevel === 'campaign'
          ? 'campaign'
          : resultLevel === 'adset'
            ? 'adset'
            : 'ad'

      const syncNames = async () => {
        const entityIdBatches = chunkArray(pendingIds, ENTITY_NAME_SYNC_BATCH_SIZE)
        const aggregateResult = {
          synced: 0,
          failed: 0,
          rateLimited: 0,
          entities: [] as SyncedEntityName[]
        }

        try {
          for (let idx = 0; idx < entityIdBatches.length; idx += 1) {
            const batchIds = entityIdBatches[idx]
            message.loading({
              content: `正在获取名称 ${idx + 1}/${entityIdBatches.length}（${batchIds.length} 个实体）...`,
              key: `sync-${accountId}`
            })

            const result = await syncEntityNames({
              adAccountId: accountId,
              entityIds: batchIds,
              entityType: requestedEntityType
            })

            aggregateResult.synced += result.synced
            aggregateResult.failed += result.failed
            aggregateResult.rateLimited += result.rateLimited
            if (result.entities.length > 0) {
              aggregateResult.entities.push(...result.entities)
              applySyncedNamesToCache(accountId, result.entities)
            }

            if (result.rateLimited > 0) {
              break
            }
          }

          if (aggregateResult.rateLimited > 0) {
            message.warning({
              content: `同步受到速率限制 (成功: ${aggregateResult.synced}, 失败: ${aggregateResult.failed}, 限制: ${aggregateResult.rateLimited})。请稍后再试。`,
              key: `sync-${accountId}`,
              duration: 5
            })
            return
          }

          if (aggregateResult.failed > 0 && aggregateResult.synced === 0) {
            message.error({
              content: `同步失败。所有 ${aggregateResult.failed} 个请求都失败了。请稍后再试。`,
              key: `sync-${accountId}`,
              duration: 5
            })
            return
          }

          if (aggregateResult.synced > 0) {
            const successMsg =
              aggregateResult.failed > 0
                ? `部分同步成功 (成功: ${aggregateResult.synced}, 失败: ${aggregateResult.failed})`
                : `实体名称同步完成 (成功: ${aggregateResult.synced})`

            message.success({
              content: successMsg,
              key: `sync-${accountId}`,
              duration: 3
            })
          }
        } catch (error) {
          console.error('[Entity Sync] Sync failed:', error)
          message.error({ content: '同步实体名称失败', key: `sync-${accountId}`, duration: 3 })
        } finally {
          syncedQueriesRef.current.delete(queryKey)
          updateSyncingEntities(pendingIds, 'remove')
        }
      }

      syncNames()
    })
  }, [
    accountQueryEntries,
    applySyncedNamesToCache,
    getEntityId,
    getEntityName,
    lastSubmittedParams,
    objectFilterKey,
    resultLevel,
    updateSyncingEntities
  ])

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

  const accountBreadcrumbLabel = useMemo(() => {
    if (activeAccountIds.size === 0) {
      return '未选择账号'
    }
    if (activeAccountIds.size === 1) {
      const accountId = Array.from(activeAccountIds)[0]
      return adAccountNameMap.get(accountId) ?? accountId
    }
    return `已选 ${activeAccountIds.size} 个账号`
  }, [activeAccountIds, adAccountNameMap])

  const hasActiveSelection = useMemo(() => {
    const levelKeys: HierarchyLevel[] = ['campaign', 'adset', 'ad']
    return levelKeys.some(level => selectedEntityIds[level]?.size > 0)
  }, [selectedEntityIds])

  const handleClearSelectionFilters = useCallback(() => {
    setSelectedEntityIds(prev => ({
      account: new Set(prev.account),
      campaign: new Set<string>(),
      adset: new Set<string>(),
      ad: new Set<string>()
    }))
    setDrillSelection(prev => ({
      account: prev.account,
      campaign: null,
      adset: null,
      ad: null
    }))
    setOpenDropdownLevel(null)
  }, [])

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
    if (selectedAccountIds.size === 0) {
      setFormError('请至少选择一个广告账号')
      return
    }
    const submittedParams: SubmittedParams = {
      since: sinceDate,
      until: untilDate,
      source: selectedDataSource,
      timeIncrement: timeIncrement === 'daily' ? 1 : null,
      breakdowns: breakdowns.trim() || undefined
    }
    setFormError(null)
    setSyncingEntityIds(new Set())
    setLastSubmittedParams(submittedParams)
    setActiveAccountIds(new Set(selectedAccountIds))
    setCurrentPage(1)
    setSelectedEntityIds(prev => ({
      account: new Set(selectedAccountIds),
      campaign: new Set(prev.campaign),
      adset: new Set(prev.adset),
      ad: new Set(prev.ad)
    }))
    setDrillSelection({
      account: null,
      campaign: null,
      adset: null,
      ad: null
    })
    setDetailEntityId(null)
    setDetailEntityName(null)
    setIsModalOpen(false)
  }

  const handleLevelChange = (nextLevel: HierarchyLevel) => {
    setActiveLevel(nextLevel)
    setCurrentPage(1)
    setDrillSelection(prev => {
      const updated: Record<HierarchyLevel, string | null> = { ...prev }
      if (nextLevel === 'account') {
        updated.campaign = null
        updated.adset = null
        updated.ad = null
      } else if (nextLevel === 'campaign') {
        updated.adset = null
        updated.ad = null
      } else if (nextLevel === 'adset') {
        updated.ad = null
      }
      return updated
    })
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
    if (resultLevel === 'account') {
      setSelectedAccountIds(prev => {
        const next = new Set(prev)
        let changed = false
        if (checked) {
          if (!next.has(entityId)) {
            if (next.size >= MAX_SELECTED_ACCOUNTS) {
              message.warning(`最多只能选择 ${MAX_SELECTED_ACCOUNTS} 个广告账号`)
              return prev
            }
            next.add(entityId)
            changed = true
          }
        } else if (next.has(entityId)) {
          if (next.size <= 1) {
            message.warning('至少保留一个广告账号以便继续查询')
            return prev
          }
          next.delete(entityId)
          changed = true
        }
        if (!changed) {
          return prev
        }
        setSelectedEntityIds(prevIds => ({
          account: new Set(next),
          campaign: new Set(prevIds.campaign),
          adset: new Set(prevIds.adset),
          ad: new Set(prevIds.ad)
        }))
        return next
      })
      return
    }

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

  const isLoading =
    (Boolean(lastSubmittedParams) &&
      accountQueryEntries.some(entry => entry.query.isLoading && !entry.query.data)) ||
    isLoadingAccounts

  const isRefetching = accountQueryEntries.some(
    entry => entry.query.isFetching && Boolean(entry.query.data)
  )

  const errorMessage = useMemo(() => {
    if (isAdAccountError) {
      return '广告账号列表加载失败，请稍后重试。'
    }
    const errored = accountQueryEntries.find(entry => entry.query.isError)
    if (!errored) {
      return null
    }
    if (errored.query.error instanceof Error) {
      return errored.query.error.message
    }
    return '洞察数据获取失败，请稍后再试'
  }, [accountQueryEntries, isAdAccountError])

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
          <div className="form-label" style={{ flex: '1 1 260px' }}>
            <span>广告账号</span>
            <div className="form-hint">
              账号默认在下方列表中勾选，最多 9 个，至少选择 1 个账号才能查看下级数据。
            </div>
          </div>
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
            <select
              className="input"
              value={selectedDataSource}
              onChange={event => setSelectedDataSource(event.target.value as InsightsDataQuery['source'])}
            >
              <option value="frontend-hybrid">混合（前端：数据库 + from-last）</option>
              <option value="database">仅数据库</option>
              <option value="realtime">仅实时</option>
              <option value="hybrid">混合（后端接口）</option>
            </select>
            <div className="form-hint">
              默认混合模式：前端先请求数据库数据，再调用 from-last 实时补齐并在浏览器端合并；末项“混合（后端）”才会走新的 `/insights/query/hybrid`。
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
              {lastSubmittedParams
                ? `日期 ${lastSubmittedParams.since} → ${lastSubmittedParams.until} · 数据源：${
                    DATA_SOURCE_LABEL[lastSubmittedParams.source]
                  }`
                : '正在加载默认数据…'}
            </div>
          </div>
          {isRefetching && <div style={{ color: 'var(--color-text-muted)' }}>刷新中…</div>}
        </div>

        {errorMessage ? (
          <div className="card__body" style={{ color: 'var(--color-danger)' }}>{errorMessage}</div>
        ) : isLoading ? (
          <div className="card__body">数据加载中…</div>
        ) : !lastSubmittedParams ? (
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
        destroyOnHidden
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

