import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  fetchInsightsOverview,
  fetchInsightsDrilldown,
  type InsightsDataSource,
  type EntitySelection,
  type AccountOverviewItem,
} from '../../../api/insights'
import type { InsightRecord } from '../../../types/insights'

export type HierarchyLevel = 'account' | 'campaign' | 'adset' | 'ad'

export interface UseInsightsDataOptions {
  accountIds: string[]
  since: string
  until: string
  source: InsightsDataSource
  enabled?: boolean
}

export interface UseInsightsDataReturn {
  // Current state
  level: HierarchyLevel
  setLevel: (level: HierarchyLevel) => void
  selections: EntitySelection[]
  
  // Data
  overviewData: AccountOverviewItem[] | undefined
  drilldownData: InsightRecord[] | undefined
  isLoading: boolean
  isError: boolean
  error: Error | null
  
  // Actions
  selectEntity: (accountId: string, campaignId?: string | null, adsetId?: string | null) => void
  clearSelection: () => void
  refetch: () => void
}

/**
 * Hook for managing insights data fetching with simplified API
 */
export function useInsightsData(options: UseInsightsDataOptions): UseInsightsDataReturn {
  const { accountIds, since, until, source, enabled = true } = options
  
  const [level, setLevel] = useState<HierarchyLevel>('account')
  const [selections, setSelections] = useState<EntitySelection[]>([])
  
  // Overview query (account level)
  const overviewQuery = useQuery({
    queryKey: ['insights', 'overview', { accountIds, since, until, source }],
    queryFn: () => fetchInsightsOverview({ accountIds, since, until, source }),
    enabled: enabled && level === 'account' && accountIds.length > 0,
    staleTime: 30_000,
  })
  
  // Drilldown query (campaign/adset/ad level)
  const drilldownQuery = useQuery({
    queryKey: ['insights', 'drilldown', { selections, level, since, until, source }],
    queryFn: () => fetchInsightsDrilldown({
      selections,
      level: level as 'campaign' | 'adset' | 'ad',
      since,
      until,
      source,
    }),
    enabled: enabled && level !== 'account' && selections.length > 0,
    staleTime: 30_000,
  })
  
  const selectEntity = useCallback((
    accountId: string,
    campaignId?: string | null,
    adsetId?: string | null
  ) => {
    const newSelection: EntitySelection = {
      accountId,
      campaignId: campaignId ?? null,
      adsetId: adsetId ?? null,
      adId: null,
    }
    
    // Determine new level based on selection
    let newLevel: HierarchyLevel = 'campaign'
    if (adsetId) {
      newLevel = 'ad'
    } else if (campaignId) {
      newLevel = 'adset'
    }
    
    setSelections([newSelection])
    setLevel(newLevel)
  }, [])
  
  const clearSelection = useCallback(() => {
    setSelections([])
    setLevel('account')
  }, [])
  
  const refetch = useCallback(() => {
    if (level === 'account') {
      overviewQuery.refetch()
    } else {
      drilldownQuery.refetch()
    }
  }, [level, overviewQuery, drilldownQuery])
  
  const isLoading = level === 'account' ? overviewQuery.isLoading : drilldownQuery.isLoading
  const isError = level === 'account' ? overviewQuery.isError : drilldownQuery.isError
  const error = level === 'account' 
    ? (overviewQuery.error as Error | null) 
    : (drilldownQuery.error as Error | null)
  
  return {
    level,
    setLevel,
    selections,
    overviewData: overviewQuery.data?.items,
    drilldownData: drilldownQuery.data?.insights,
    isLoading,
    isError,
    error,
    selectEntity,
    clearSelection,
    refetch,
  }
}
