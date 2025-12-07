import apiClient from '../lib/apiClient'
import type {
  InsightAccountSyncStatus,
  InsightRecord,
  InsightsDataResponse,
  InsightSyncStatus,
  InsightSyncTriggerResult,
  SyncOverviewResponse,
  SyncOverviewItem,
  SyncHistoryListResponse,
  SyncHistoryRecord
} from '../types/insights'

// ===== New Sync Management API =====

const mapSyncOverviewItemFromApi = (item: any): SyncOverviewItem => {
  return {
    accountId: item?.account_id ?? item?.accountId ?? '',
    accountName: item?.account_name ?? item?.accountName ?? null,

    // MongoDB 同步状态
    mongodbStatus: (item?.mongodb_status ?? item?.mongodbStatus ?? 'pending') as InsightSyncStatus,
    mongodbIsRunning: Boolean(item?.mongodb_is_running ?? item?.mongodbIsRunning ?? false),
    mongodbLastSyncedAt: item?.mongodb_last_synced_at ?? item?.mongodbLastSyncedAt ?? null,
    // MongoDB 数据覆盖范围
    mongodbCoverageSince: item?.mongodb_coverage_since ?? item?.mongodbCoverageSince ?? null,
    mongodbCoverageUntil: item?.mongodb_coverage_until ?? item?.mongodbCoverageUntil ?? null,
    mongodbLastError: item?.mongodb_last_error ?? item?.mongodbLastError ?? null,
    mongodbLastHistoryId: item?.mongodb_last_history_id ?? item?.mongodbLastHistoryId ?? null,

    // Redis 同步状态
    redisStatus: (item?.redis_status ?? item?.redisStatus ?? 'pending') as InsightSyncStatus,
    redisIsRunning: Boolean(item?.redis_is_running ?? item?.redisIsRunning ?? false),
    redisLastSyncedAt: item?.redis_last_synced_at ?? item?.redisLastSyncedAt ?? null,
    // Redis 缓存覆盖范围
    redisCacheSince: item?.redis_cache_since ?? item?.redisCacheSince ?? null,
    redisCacheUntil: item?.redis_cache_until ?? item?.redisCacheUntil ?? null,
    redisLastError: item?.redis_last_error ?? item?.redisLastError ?? null,
    redisLastHistoryId: item?.redis_last_history_id ?? item?.redisLastHistoryId ?? null,
  }
}

const mapSyncHistoryRecordFromApi = (item: any): SyncHistoryRecord => {
  return {
    id: item?.id ?? '',
    accountId: item?.account_id ?? item?.accountId ?? '',
    accountName: item?.account_name ?? item?.accountName ?? null,
    triggerType: (item?.trigger_type ?? item?.triggerType ?? 'manual') as 'manual' | 'auto' | 'retry',
    triggeredBy: item?.triggered_by ?? item?.triggeredBy ?? null,
    since: item?.since ?? '',
    until: item?.until ?? '',
    mode: (item?.mode ?? 'sync') as 'sync' | 'async',
    dataTarget: (item?.data_target ?? item?.dataTarget ?? 'mongodb') as 'mongodb' | 'redis' | 'hybrid',
    status: (item?.status ?? 'pending') as InsightSyncStatus,
    startedAt: item?.started_at ?? item?.startedAt ?? '',
    completedAt: item?.completed_at ?? item?.completedAt ?? null,
    recordsCount: Number(item?.records_count ?? item?.recordsCount ?? 0),
    errorMessage: item?.error_message ?? item?.errorMessage ?? null,
    durationSeconds: item?.duration_seconds ?? item?.durationSeconds ?? null,
    percentComplete: Number(item?.percent_complete ?? item?.percentComplete ?? 0),
    totalDays: Number(item?.total_days ?? item?.totalDays ?? 0),
    processedDays: Number(item?.processed_days ?? item?.processedDays ?? 0),
    metadata: item?.metadata ?? null
  }
}

export const fetchSyncOverview = async (): Promise<SyncOverviewResponse> => {
  const { data } = await apiClient.get('/insights/sync/overview')
  const payload = data?.data ?? data ?? {}
  const items = Array.isArray(payload?.items) ? payload.items : []
  return {
    items: items.map(mapSyncOverviewItemFromApi),
    totalAccounts: Number(payload?.total_accounts ?? payload?.totalAccounts ?? items.length)
  }
}

export interface SyncHistoryQueryParams {
  accountId?: string
  status?: InsightSyncStatus
  triggerType?: 'manual' | 'auto' | 'retry'
  dataTarget?: 'mongodb' | 'redis' | 'hybrid'
  page?: number
  pageSize?: number
}

export const fetchSyncHistory = async (params: SyncHistoryQueryParams = {}): Promise<SyncHistoryListResponse> => {
  const queryParams: Record<string, any> = {}
  if (params.accountId) queryParams.account_id = params.accountId
  if (params.status) queryParams.status = params.status
  if (params.triggerType) queryParams.trigger_type = params.triggerType
  if (params.dataTarget) queryParams.data_target = params.dataTarget
  if (params.page) queryParams.page = params.page
  if (params.pageSize) queryParams.page_size = params.pageSize

  const { data } = await apiClient.get('/insights/sync/history', { params: queryParams })
  const payload = data?.data ?? data ?? {}
  const items = Array.isArray(payload?.items) ? payload.items : []

  return {
    items: items.map(mapSyncHistoryRecordFromApi),
    total: Number(payload?.total ?? 0),
    page: Number(payload?.page ?? 1),
    pageSize: Number(payload?.page_size ?? payload?.pageSize ?? 50)
  }
}

export const fetchSyncHistoryDetail = async (historyId: string): Promise<SyncHistoryRecord> => {
  const { data } = await apiClient.get(`/insights/sync/history/${historyId}`)
  const payload = data?.data ?? data ?? {}
  return mapSyncHistoryRecordFromApi(payload)
}

export const triggerSync = async (payload: {
  accountIds?: string[]
  since: string
  until: string
}): Promise<InsightSyncTriggerResult> => {
  const requestBody = {
    account_ids: payload.accountIds,
    since: payload.since,
    until: payload.until
  }

  const { data } = await apiClient.post('/insights/sync/trigger', requestBody)
  const body = data?.data ?? data ?? {}
  const total =
    body?.total_accounts ??
    body?.totalAccounts ??
    Object.keys(body?.processed_accounts ?? body?.processedAccounts ?? {}).length

  const processedSource =
    body?.processed_accounts ?? body?.processedAccounts ?? ({} as Record<string, any>)
  const processedEntries = Object.entries(processedSource).map(([accountId, summary]) => {
    const normalized = (summary ?? {}) as Record<string, any>
    return [
      accountId,
      {
        mode: normalized.mode ?? 'unknown',
        since: normalized.since ?? '',
        until: normalized.until ?? '',
        records: Number(normalized.records ?? 0),
        trigger: normalized.trigger ?? null,
        triggeredBy: normalized.triggered_by ?? normalized.triggeredBy ?? null
      }
    ]
  })

  const failedSource =
    body?.failed_accounts ?? body?.failedAccounts ?? ({} as Record<string, string>)

  return {
    totalAccounts: Number(total ?? 0),
    processedAccounts: Object.fromEntries(processedEntries),
    failedAccounts: failedSource as Record<string, string>
  }
}

export const triggerAccountSync = async (accountId: string): Promise<void> => {
  await apiClient.post(`/insights/sync/trigger-account/${accountId}`)
}

export const triggerMongodbSync = async (accountId: string): Promise<void> => {
  await apiClient.post(`/insights/sync/trigger-mongodb/${accountId}`)
}

export const triggerRedisSync = async (accountId: string): Promise<void> => {
  await apiClient.post(`/insights/sync/trigger-redis/${accountId}`)
}

// ===== Legacy/Deprecated Sync API =====

const mapAccountStatusFromApi = (item: any): InsightAccountSyncStatus => {
  const status = (item?.status ?? 'pending') as InsightSyncStatus
  return {
    accountId: item?.account_id ?? item?.accountId ?? '',
    accountName: item?.account_name ?? item?.accountName ?? null,
    since: item?.since ?? item?.data_since ?? item?.initial_requested_since ?? null,
    status,
    until: item?.until ?? item?.data_until ?? item?.last_synced_date ?? null,
    obsSince: item?.obs_since ?? item?.obsSince ?? null,
    obsUntil: item?.obs_until ?? item?.obsUntil ?? null,
    lastSyncedAt: item?.last_synced_at ?? item?.lastSyncedAt ?? null,
    rangeSince: item?.range_since ?? item?.rangeSince ?? null,
    rangeUntil: item?.range_until ?? item?.rangeUntil ?? null,
    mode: item?.mode ?? null,
    trigger: item?.trigger ?? item?.triggerSource ?? null,
    triggeredBy: item?.triggered_by ?? item?.triggeredBy ?? null,
    lastError: item?.last_error ?? item?.lastError ?? null,
    updatedAt: item?.updated_at ?? item?.updatedAt ?? null
  }
}

export const fetchInsightsSyncRuns = async (): Promise<InsightAccountSyncStatus[]> => {
  const { data } = await apiClient.get('/insights/sync/runs')
  const payload = data?.data ?? data ?? {}
  const items: any[] = Array.isArray(payload?.items) ? payload.items : []
  return items.map(mapAccountStatusFromApi)
}

const mapInsightRecordFromApi = (item: any): InsightRecord => {
  const metrics = item?.metrics ?? {}
  const normalizeId = (value: any): string | null => {
    if (value === undefined || value === null) {
      return null
    }
    const text = String(value).trim()
    return text ? text : null
  }
  const adAccountId =
    normalizeId(item?.ad_account_id ?? item?.adAccountId) ??
    normalizeId(item?.account_id ?? item?.accountId) ??
    ''
  return {
    adAccountId,
    adId: normalizeId(item?.ad_id ?? item?.adId),
    adsetId: item?.adset_id ?? item?.adsetId ?? null,
    campaignId: item?.campaign_id ?? item?.campaignId ?? null,
    adName: item?.ad_name ?? item?.adName ?? null,
    adsetName: item?.adset_name ?? item?.adsetName ?? null,
    campaignName: item?.campaign_name ?? item?.campaignName ?? null,
    configuredStatus: item?.configured_status ?? item?.configuredStatus ?? null,
    effectiveStatus: item?.effective_status ?? item?.effectiveStatus ?? null,
    date: item?.date ?? item?.date_start ?? item?.dateStart ?? '',
    metrics: {
      spend: Number(metrics?.spend ?? item?.spend ?? 0),
      impressions: Number(metrics?.impressions ?? item?.impressions ?? 0),
      reach: Number(metrics?.reach ?? item?.reach ?? 0),
      clicks: Number(metrics?.clicks ?? item?.clicks ?? 0),
      inlineLinkClicks: Number(
        metrics?.inline_link_clicks ?? item?.inline_link_clicks ?? metrics?.inlineLinkClicks ?? 0
      ),
      outboundClicks: Number(
        metrics?.outbound_clicks ?? item?.outbound_clicks ?? metrics?.outboundClicks ?? 0
      ),
      landingPageView: Number(
        metrics?.landing_page_view ?? item?.landing_page_view ?? metrics?.landingPageView ?? 0
      ),
      onsiteWebCheckout: Number(
        metrics?.onsite_web_checkout ?? item?.onsite_web_checkout ?? metrics?.onsiteWebCheckout ?? 0
      ),
      onsiteWebAddToCart: Number(
        metrics?.onsite_web_add_to_cart ??
          item?.onsite_web_add_to_cart ??
          metrics?.onsiteWebAddToCart ??
          0
      ),
      onsiteWebPurchase: Number(
        metrics?.onsite_web_purchase ??
          item?.onsite_web_purchase ??
          metrics?.onsiteWebPurchase ??
          0
      ),
      onsiteWebCheckoutValue: Number(
        metrics?.onsite_web_checkout_value ??
          item?.onsite_web_checkout_value ??
          metrics?.onsiteWebCheckoutValue ??
          0
      ),
      onsiteWebAddToCartValue: Number(
        metrics?.onsite_web_add_to_cart_value ??
          item?.onsite_web_add_to_cart_value ??
          metrics?.onsiteWebAddToCartValue ??
          0
      ),
      onsiteWebPurchaseValue: Number(
        metrics?.onsite_web_purchase_value ??
          item?.onsite_web_purchase_value ??
          metrics?.onsiteWebPurchaseValue ??
          0
      )
    }
  }
}

// Old data source type - kept for backward compatibility
// New simplified API uses InsightsDataSource defined at the end of this file
export type LegacyInsightsDataSource = 'mongo' | 'mongo_redis' | 'realtime' | 'mongo_from_last'

export interface InsightsDataQuery {
  accountId: string
  since: string
  until: string
  level?: 'account' | 'campaign' | 'adset' | 'ad'
  timeIncrement?: number | null
  breakdowns?: string
  source: LegacyInsightsDataSource
  fields?: string[]
  objectLevel?: 'ad' | 'adset' | 'campaign'
  objectIds?: string[]
}

const mapApiResponse = (
  raw: any,
  fallbackSince: string,
  fallbackUntil: string
): InsightsDataResponse => {
  const payload = raw?.data ?? raw ?? {}
  const insights = Array.isArray(payload?.insights) ? payload.insights.map(mapInsightRecordFromApi) : []
  const totalRecords = Number(payload?.total_records ?? payload?.totalRecords ?? insights.length)
  const dateRange = payload?.date_range ?? payload?.dateRange ?? {
    since: fallbackSince,
    until: fallbackUntil
  }
  return {
    insights,
    totalRecords,
    dateRange: {
      since: dateRange?.since ?? fallbackSince,
      until: dateRange?.until ?? fallbackUntil
    }
  }
}

const filterInsightsByObjectSelection = (
  records: InsightRecord[],
  params: InsightsDataQuery
): InsightRecord[] => {
  const { objectLevel, objectIds } = params
  if (!objectLevel || !objectIds || objectIds.length === 0) {
    return records
  }
  const normalized = new Set(
    objectIds
      .map(id => String(id ?? '').trim())
      .filter(id => id.length > 0)
  )
  if (normalized.size === 0) {
    return records
  }

  const matchesFilter = (record: InsightRecord): boolean => {
    switch (objectLevel) {
      case 'ad':
        return record.adId ? normalized.has(record.adId) : false
      case 'adset':
        return record.adsetId ? normalized.has(record.adsetId) : false
      case 'campaign':
        return record.campaignId ? normalized.has(record.campaignId) : false
      default:
        return false
    }
  }

  return records.filter(matchesFilter)
}

const applyObjectFilterToResponse = (
  response: InsightsDataResponse,
  params: InsightsDataQuery
): InsightsDataResponse => {
  const filtered = filterInsightsByObjectSelection(response.insights, params)
  if (filtered.length === response.insights.length) {
    return response
  }
  return {
    ...response,
    insights: filtered,
    totalRecords: filtered.length
  }
}

const buildCommonParams = (params: InsightsDataQuery) => ({
  level: params.level ?? 'ad'
})

const padTwoDigits = (value: number) => value.toString().padStart(2, '0')

// Produce a deterministic dd:hh:mm bucket (UTC) so gateway caches can key per minute.
const buildCacheWindowHint = () => {
  const now = new Date()
  return `${padTwoDigits(now.getUTCDate())}:${padTwoDigits(now.getUTCHours())}:${padTwoDigits(
    now.getUTCMinutes()
  )}`
}

const buildDbParams = (params: InsightsDataQuery) => {
  const queryParams: Record<string, unknown> = {
    ad_account_id: params.accountId,
    since: params.since,
    until: params.until,
    ...buildCommonParams(params)
  }
  if (params.timeIncrement !== undefined) {
    queryParams.time_increment = params.timeIncrement
  }
  if (params.breakdowns) {
    queryParams.breakdowns = params.breakdowns
  }
  if (params.objectIds?.length) {
    queryParams.object_ids = params.objectIds
  }
  if (params.objectLevel) {
    queryParams.obj_level = params.objectLevel
  }
  return queryParams
}

const buildRealtimePayload = (params: InsightsDataQuery) => {
  const payload: Record<string, unknown> = {
    ad_account_id: params.accountId,
    since: params.since,
    until: params.until,
    ...buildCommonParams(params)
  }
  if (params.timeIncrement !== undefined) {
    payload.time_increment = params.timeIncrement
  }
  if (params.breakdowns) {
    payload.breakdowns = params.breakdowns
  }
  if (params.fields?.length) {
    payload.fields = params.fields
  }
  if (params.objectIds?.length) {
    payload.object_ids = params.objectIds
  }
  if (params.objectLevel) {
    payload.obj_level = params.objectLevel
  }
  return payload
}

const buildHybridPayload = (params: InsightsDataQuery) => ({
  ...buildRealtimePayload(params),
  cache_window_hint: buildCacheWindowHint()
})

export const fetchInsightsData = async (params: InsightsDataQuery): Promise<InsightsDataResponse> => {
  if (params.source === 'mongo') {
    const { data } = await apiClient.get('/insights/query/mongo', { params: buildDbParams(params) })
    const response = mapApiResponse(data, params.since, params.until)
    return applyObjectFilterToResponse(response, params)
  }

  if (params.source === 'mongo_redis') {
    const { data } = await apiClient.get('/insights/query/mongo_redis', { params: buildDbParams(params) })
    const response = mapApiResponse(data, params.since, params.until)
    return applyObjectFilterToResponse(response, params)
  }

  if (params.source === 'realtime') {
    const { data } = await apiClient.post('/insights/query', buildRealtimePayload(params))
    const response = mapApiResponse(data, params.since, params.until)
    return applyObjectFilterToResponse(response, params)
  }

  // mongo_from_last: MongoDB + Facebook API from-last gap fill (server-side merge)
  const { data } = await apiClient.post('/insights/query/mongo_from-last', buildHybridPayload(params))
  const response = mapApiResponse(data, params.since, params.until)
  return applyObjectFilterToResponse(response, params)
}

export interface InsightsSyncTriggerPayload {
  accountIds?: string[]
  since: string
  until: string
}

export const createInsightsSyncRun = async (
  payload: InsightsSyncTriggerPayload
): Promise<InsightSyncTriggerResult> => {
  const { data } = await apiClient.post('/insights/sync/runs', payload)
  const body = data?.data ?? data ?? {}
  const total =
    body?.total_accounts ??
    body?.totalAccounts ??
    Object.keys(body?.processed_accounts ?? body?.processedAccounts ?? {}).length

  const processedSource =
    body?.processed_accounts ?? body?.processedAccounts ?? ({} as Record<string, any>)
  const processedEntries = Object.entries(processedSource).map(([accountId, summary]) => {
    const normalized = (summary ?? {}) as Record<string, any>
    return [
      accountId,
      {
        mode: normalized.mode ?? 'unknown',
        since: normalized.since ?? '',
        until: normalized.until ?? '',
        records: Number(normalized.records ?? 0),
        trigger: normalized.trigger ?? null,
        triggeredBy: normalized.triggered_by ?? normalized.triggeredBy ?? null
      }
    ]
  })

  const failedSource =
    body?.failed_accounts ?? body?.failedAccounts ?? ({} as Record<string, string>)

  return {
    totalAccounts: Number(total ?? 0),
    processedAccounts: Object.fromEntries(processedEntries),
    failedAccounts: failedSource as Record<string, string>
  }
}

export interface SyncEntityNamesPayload {
  adAccountId: string
  entityIds: string[]
  entityType: 'ad' | 'adset' | 'campaign'
}

export interface SyncedEntityName {
  entityId: string
  entityName: string | null
  configuredStatus: string | null
  effectiveStatus: string | null
  entityType: 'ad' | 'adset' | 'campaign'
  accountId: string | null
}

export interface SyncEntityNamesResult {
  synced: number
  failed: number
  total: number
  rateLimited: number
  entities: SyncedEntityName[]
  failedEntities: string[]
}

export const syncEntityNames = async (
  payload: SyncEntityNamesPayload
): Promise<SyncEntityNamesResult> => {
  // Entity-name sync can take a while (sequential FB API calls). Scale timeout with request size.
  const baseTimeout = 30000
  const perEntityBuffer = 1200 // ms per entity to allow API + backoff
  const timeoutMs = Math.min(120000, Math.max(baseTimeout, payload.entityIds.length * perEntityBuffer))

  const requestBody = {
    ad_account_id: payload.adAccountId,
    entity_ids: payload.entityIds,
    entity_type: payload.entityType
  }

  const { data } = await apiClient.post('/insights/entity-name-syncs', requestBody, {
    timeout: timeoutMs
  })
  const result = data?.data ?? data ?? {}

  const entitiesSource = Array.isArray(result.entities) ? result.entities : []
  const entities: SyncedEntityName[] = entitiesSource.map((item: any) => {
    const rawAccountId =
      item?.account_id ?? item?.accountId ?? payload.adAccountId ?? null

    return {
      entityId: item?.entity_id ?? item?.entityId ?? '',
      entityName: item?.entity_name ?? item?.entityName ?? null,
      configuredStatus: item?.configured_status ?? item?.configuredStatus ?? null,
      effectiveStatus: item?.effective_status ?? item?.effectiveStatus ?? null,
      entityType: (item?.entity_type ?? item?.entityType ?? payload.entityType) as SyncedEntityName['entityType'],
      accountId: rawAccountId ? String(rawAccountId).replace(/^act_/, '') : null
    }
  })

  const failedEntitiesSource = result.failed_entities ?? result.failedEntities ?? []
  const failedEntities = Array.isArray(failedEntitiesSource) ? failedEntitiesSource : []

  return {
    synced: Number(result.synced ?? 0),
    failed: Number(result.failed ?? 0),
    total: Number(result.total ?? 0),
    rateLimited: Number(result.rate_limited ?? result.rateLimited ?? 0),
    entities,
    failedEntities
  }
}


// ===== New Simplified Insights API =====

export type InsightsDataSource = 'mongo' | 'redis' | 'mongo_redis'

export interface InsightsOverviewQuery {
  accountIds: string[]
  since: string
  until: string
  source?: InsightsDataSource
}

export interface AccountOverviewItem {
  accountId: string
  accountName: string | null
  metrics: InsightRecord['metrics']
  dateCount: number
  startDate: string | null
  endDate: string | null
}

export interface InsightsOverviewResponse {
  items: AccountOverviewItem[]
  totals: InsightRecord['metrics'] | null
  dateRange: { since: string; until: string }
}

const mapAccountOverviewItem = (item: any): AccountOverviewItem => ({
  accountId: item?.account_id ?? item?.accountId ?? '',
  accountName: item?.account_name ?? item?.accountName ?? null,
  metrics: mapMetrics(item?.metrics ?? {}),
  dateCount: Number(item?.date_count ?? item?.dateCount ?? 0),
  startDate: item?.start_date ?? item?.startDate ?? null,
  endDate: item?.end_date ?? item?.endDate ?? null,
})

const mapMetrics = (m: any): InsightRecord['metrics'] => ({
  spend: Number(m?.spend ?? 0),
  impressions: Number(m?.impressions ?? 0),
  reach: Number(m?.reach ?? 0),
  clicks: Number(m?.clicks ?? 0),
  inlineLinkClicks: Number(m?.inline_link_clicks ?? m?.inlineLinkClicks ?? 0),
  outboundClicks: Number(m?.outbound_clicks ?? m?.outboundClicks ?? 0),
  landingPageView: Number(m?.landing_page_view ?? m?.landingPageView ?? 0),
  onsiteWebAddToCart: Number(m?.onsite_web_add_to_cart ?? m?.onsiteWebAddToCart ?? 0),
  onsiteWebAddToCartValue: Number(m?.onsite_web_add_to_cart_value ?? m?.onsiteWebAddToCartValue ?? 0),
  onsiteWebCheckout: Number(m?.onsite_web_checkout ?? m?.onsiteWebCheckout ?? 0),
  onsiteWebCheckoutValue: Number(m?.onsite_web_checkout_value ?? m?.onsiteWebCheckoutValue ?? 0),
  onsiteWebPurchase: Number(m?.onsite_web_purchase ?? m?.onsiteWebPurchase ?? 0),
  onsiteWebPurchaseValue: Number(m?.onsite_web_purchase_value ?? m?.onsiteWebPurchaseValue ?? 0),
})

/**
 * Fetch account-level overview (initial page load)
 */
export const fetchInsightsOverview = async (
  query: InsightsOverviewQuery
): Promise<InsightsOverviewResponse> => {
  const params = new URLSearchParams()
  query.accountIds.forEach(id => params.append('account_ids', id))
  params.set('since', query.since)
  params.set('until', query.until)
  params.set('source', query.source ?? 'mongo_redis')

  const { data } = await apiClient.get(`/insights/overview?${params.toString()}`)
  const payload = data?.data ?? data ?? {}

  return {
    items: Array.isArray(payload?.items) ? payload.items.map(mapAccountOverviewItem) : [],
    totals: payload?.totals ? mapMetrics(payload.totals) : null,
    dateRange: payload?.date_range ?? payload?.dateRange ?? { since: query.since, until: query.until },
  }
}

export interface EntitySelection {
  accountId: string
  campaignId: string | null
  adsetId: string | null
  adId: string | null
}

export type DrilldownLevel = 'campaign' | 'adset' | 'ad'

export interface InsightsDrilldownQuery {
  selections: EntitySelection[]
  level: DrilldownLevel
  since: string
  until: string
  source?: InsightsDataSource
}

/**
 * Fetch insights with entity drilldown (selection paths)
 */
export const fetchInsightsDrilldown = async (
  query: InsightsDrilldownQuery
): Promise<InsightsDataResponse> => {
  const requestBody = {
    selections: query.selections.map(sel => ({
      account_id: sel.accountId,
      campaign_id: sel.campaignId,
      adset_id: sel.adsetId,
      ad_id: sel.adId,
    })),
    level: query.level,
    since: query.since,
    until: query.until,
    source: query.source ?? 'mongo_redis',
  }

  const { data } = await apiClient.post('/insights/drilldown', requestBody)
  const payload = data?.data ?? data ?? {}

  return {
    insights: Array.isArray(payload?.insights) ? payload.insights.map(mapInsightRecordFromApi) : [],
    totalRecords: Number(payload?.total_records ?? payload?.totalRecords ?? 0),
    dateRange: payload?.date_range ?? payload?.dateRange ?? { since: query.since, until: query.until },
  }
}
