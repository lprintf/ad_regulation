import apiClient from '../lib/apiClient'
import type {
  InsightAccountSyncStatus,
  InsightRecord,
  InsightsDataResponse,
  InsightSyncStatus,
  InsightSyncTriggerResult
} from '../types/insights'

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
  return {
    adId: item?.ad_id ?? item?.adId ?? '',
    adsetId: item?.adset_id ?? item?.adsetId ?? null,
    campaignId: item?.campaign_id ?? item?.campaignId ?? null,
    adName: item?.ad_name ?? item?.adName ?? null,
    adsetName: item?.adset_name ?? item?.adsetName ?? null,
    campaignName: item?.campaign_name ?? item?.campaignName ?? null,
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

export type InsightsDataSource = 'database' | 'realtime' | 'hybrid'

export interface InsightsDataQuery {
  accountId: string
  since: string
  until: string
  level?: 'ad' | 'adset' | 'campaign'
  timeIncrement?: number | null
  breakdowns?: string
  source: InsightsDataSource
  fields?: string[]
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
  return payload
}

const buildFromLastParams = (params: InsightsDataQuery) => {
  const payload: Record<string, unknown> = {
    ad_account_id: params.accountId,
    until: params.until,
    cache_window_hint: buildCacheWindowHint(),
    ...buildCommonParams(params)
  }
  if (params.timeIncrement !== undefined) {
    payload.time_increment = params.timeIncrement
  }
  if (params.breakdowns) {
    payload.breakdowns = params.breakdowns
  }
  if (params.fields?.length) {
    payload.fields = params.fields.join(',')
  }
  return payload
}

export const fetchInsightsData = async (params: InsightsDataQuery): Promise<InsightsDataResponse> => {
  if (params.source === 'database') {
    const { data } = await apiClient.get('/insights', { params: buildDbParams(params) })
    return mapApiResponse(data, params.since, params.until)
  }

  if (params.source === 'realtime') {
    const { data } = await apiClient.post('/insights/query', buildRealtimePayload(params))
    return mapApiResponse(data, params.since, params.until)
  }

  // hybrid: fetch DB + realtime (gap) and merge
  const [dbResponse, realtimeResponse] = await Promise.all([
    apiClient.get('/insights', { params: buildDbParams(params) }),
    apiClient.get('/insights/query/from-last', { params: buildFromLastParams(params) })
  ])

  const dbResult = mapApiResponse(dbResponse.data, params.since, params.until)
  const realtimeResult = mapApiResponse(realtimeResponse.data, params.since, params.until)

  const recordMap = new Map<string, InsightRecord>()
  const makeKey = (record: InsightRecord) => `${record.date}-${record.adId}`

  for (const record of dbResult.insights) {
    recordMap.set(makeKey(record), record)
  }
  for (const record of realtimeResult.insights) {
    recordMap.set(makeKey(record), record)
  }

  const mergedInsights = Array.from(recordMap.values()).sort((a, b) => {
    const dateCompare = a.date.localeCompare(b.date)
    if (dateCompare !== 0) {
      return dateCompare
    }
    return a.adId.localeCompare(b.adId)
  })

  return {
    insights: mergedInsights,
    totalRecords: mergedInsights.length,
    dateRange: {
      since: params.since,
      until: params.until
    }
  }
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
