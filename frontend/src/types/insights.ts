export type InsightSyncStatus = 'pending' | 'running' | 'success' | 'failed'

export type TriggerType = 'manual' | 'auto' | 'retry'

export type SyncMode = 'sync' | 'async'

export type DataTarget = 'mongodb' | 'redis' | 'hybrid'

export interface SyncHistoryRecord {
  id: string
  accountId: string
  accountName?: string | null
  triggerType: TriggerType
  triggeredBy?: string | null
  since: string
  until: string
  mode: SyncMode
  dataTarget: DataTarget
  status: InsightSyncStatus
  startedAt: string
  completedAt?: string | null
  recordsCount: number
  errorMessage?: string | null
  durationSeconds?: number | null
  percentComplete: number
  totalDays: number
  processedDays: number
}

export interface SyncHistoryListResponse {
  items: SyncHistoryRecord[]
  total: number
  page: number
  pageSize: number
}

export interface SyncOverviewItem {
  accountId: string
  accountName?: string | null
  status: InsightSyncStatus
  lastSyncedAt?: string | null
  lastSyncedDate?: string | null
  // MongoDB 数据覆盖范围
  mongodbCoverageSince?: string | null
  mongodbCoverageUntil?: string | null
  // Redis 缓存覆盖范围
  redisCacheSince?: string | null
  redisCacheUntil?: string | null
  redisCacheUpdatedAt?: string | null
  lastError?: string | null
  isRunning: boolean
  lastHistoryId?: string | null
}

export interface SyncOverviewResponse {
  items: SyncOverviewItem[]
  totalAccounts: number
}

// Keep for backward compatibility
export interface InsightAccountSyncStatus {
  accountId: string
  accountName?: string | null
  status: InsightSyncStatus
  since?: string | null
  until?: string | null
  obsSince?: string | null
  obsUntil?: string | null
  lastSyncedAt?: string | null
  rangeSince?: string | null
  rangeUntil?: string | null
  mode?: string | null
  trigger?: string | null
  triggeredBy?: string | null
  lastError?: string | null
  updatedAt?: string | null
}

export interface InsightSyncManualSummary {
  mode: string
  since: string
  until: string
  records: number
  trigger?: string | null
  triggeredBy?: string | null
}

export interface InsightSyncTriggerResult {
  totalAccounts: number
  processedAccounts: Record<string, InsightSyncManualSummary>
  failedAccounts: Record<string, string>
}

export interface InsightMetrics {
  spend: number
  impressions: number
  reach: number
  clicks: number
  inlineLinkClicks: number
  outboundClicks: number
  landingPageView: number
  onsiteWebCheckout: number
  onsiteWebAddToCart: number
  onsiteWebPurchase: number
  onsiteWebCheckoutValue: number
  onsiteWebAddToCartValue: number
  onsiteWebPurchaseValue: number
}

export interface InsightRecord {
  adAccountId: string
  adId?: string | null // Ad ID (only for ad-level data)
  adsetId?: string | null // AdSet ID (populated when level=adset)
  campaignId?: string | null // Campaign ID (populated when level=campaign)
  // Entity names for better readability
  adName?: string | null // Ad name (if available)
  adsetName?: string | null // AdSet name (populated when level=adset, if available)
  campaignName?: string | null // Campaign name (populated when level=campaign, if available)
  configuredStatus?: string | null // Configured status for the entity at the requested level
  effectiveStatus?: string | null // Effective status for the entity at the requested level
  date: string
  metrics: InsightMetrics
}

export interface InsightsDataResponse {
  insights: InsightRecord[]
  totalRecords: number
  dateRange: {
    since: string
    until: string
  }
}
