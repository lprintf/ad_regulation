export type InsightSyncStatus = 'pending' | 'running' | 'success' | 'failed'

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
  adId: string // Entity ID - represents ad_id, adset_id, or campaign_id depending on query level
  adsetId?: string | null // AdSet ID (populated when level=adset)
  campaignId?: string | null // Campaign ID (populated when level=campaign)
  // Entity names for better readability
  adName?: string | null // Ad name (if available)
  adsetName?: string | null // AdSet name (populated when level=adset, if available)
  campaignName?: string | null // Campaign name (populated when level=campaign, if available)
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



