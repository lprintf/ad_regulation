import apiClient from '../lib/apiClient'
import {
  extractResponseData,
  extractPaginatedResponse,
  extractSingleObject
} from '../lib/apiResponse'
import type {
  BindingSource,
  ExecutionStatus,
  RuleBinding,
  RuleDefinition,
  RuleEntityType,
  RuleExecutionLog,
  SchedulerTask,
  SchedulerNamespace,
  ExecutionTrigger
} from '../types/rule-engine'

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

// ===== Rule Definitions (Read-only from Registry) =====

export const fetchAvailableRules = async (): Promise<RuleDefinition[]> => {
  const { data } = await apiClient.get('/rules/available')
  const payload = extractResponseData(data, [])
  return Array.isArray(payload) ? payload.map(mapRuleFromApi) : []
}

export const fetchRuleInfo = async (ruleName: string): Promise<RuleDefinition> => {
  const { data } = await apiClient.get(`/rules/available/${ruleName}`)
  return mapRuleFromApi(extractSingleObject(data))
}

const mapRuleFromApi = (item: any): RuleDefinition => {
  return {
    id: item?.name ?? '',  // Use name as ID since rules are code-based
    name: item?.name ?? '',
    description: item?.description ?? '',
    version: item?.version ?? '1.0.0',
    tags: item?.tags ?? [],
    parameters_schema: item?.parameters_schema ?? {},
    // Read-only rules don't have these fields
    code: '',
    status: 'published',
    created_at: '',
    updated_at: ''
  }
}

// ===== Rule Configs (Clone rules with modified parameters) =====

export interface RuleConfig {
  id: string
  name: string
  base_rule: string
  description: string | null
  version: string
  parameter_overrides: Record<string, any>
  parameters_schema: Record<string, any>
  tags: string[]
  is_active: boolean
  created_by: string | null
  updated_by: string | null
  created_at: string
  updated_at: string
}

export interface RuleConfigCreate {
  name: string
  base_rule: string
  description?: string
  parameter_overrides?: Record<string, any>
  tags?: string[]
}

export interface RuleConfigClone {
  new_name: string
  parameter_overrides?: Record<string, any>
  description?: string
}

export const fetchRuleConfigs = async (baseRule?: string): Promise<RuleConfig[]> => {
  const { data } = await apiClient.get('/rules/configs', {
    params: { base_rule: baseRule }
  })
  const payload = extractResponseData(data, [])
  return Array.isArray(payload) ? payload : []
}

export const createRuleConfig = async (payload: RuleConfigCreate): Promise<RuleConfig> => {
  const { data } = await apiClient.post('/rules/configs', payload)
  return extractSingleObject<RuleConfig>(data)
}

export const updateRuleConfig = async (
  configId: string,
  payload: { description?: string; parameter_overrides?: Record<string, any>; tags?: string[]; is_active?: boolean }
): Promise<RuleConfig> => {
  const { data } = await apiClient.patch(`/rules/configs/${configId}`, payload)
  return extractSingleObject<RuleConfig>(data)
}

export const cloneRuleConfig = async (configId: string, payload: RuleConfigClone): Promise<RuleConfig> => {
  const { data } = await apiClient.post(`/rules/configs/${configId}/clone`, payload)
  return extractSingleObject<RuleConfig>(data)
}

export const deleteRuleConfig = async (configId: string): Promise<void> => {
  await apiClient.delete(`/rules/configs/${configId}`)
}

// ===== Rule Bindings =====

export interface RuleBindingFilters {
  ruleName?: string
  entityId?: string
  entityType?: RuleEntityType | 'all'
  activeOnly?: boolean
}

export interface RuleBindingPayload {
  ruleId: string  // This is now rule_name
  ruleConfigId?: string | null
  entityType: RuleEntityType
  entityId: string

  // Ad hierarchy fields - required for indexing
  adAccountId: string
  campaignId?: string | null
  adsetId?: string | null
  adId?: string | null

  source?: BindingSource
}

export const fetchRuleBindings = async (
  filters: RuleBindingFilters = {}
): Promise<PaginatedResponse<RuleBinding>> => {
  const { data } = await apiClient.get('/rules/bindings', {
    params: {
      rule_name: filters.ruleName,
      entity_id: filters.entityId,
      entity_type: filters.entityType === 'all' ? undefined : filters.entityType,
      active_only: filters.activeOnly
    }
  })

  return extractPaginatedResponse<RuleBinding>(data, mapBindingFromApi)
}

export const createRuleBinding = async (
  payload: RuleBindingPayload
): Promise<RuleBinding> => {
  const { data } = await apiClient.post('/rules/bindings', {
    rule_id: payload.ruleId,  // Backend accepts rule_name as rule_id
    rule_config_id: payload.ruleConfigId || undefined,
    entity_type: payload.entityType,
    entity_id: payload.entityId,
    ad_account_id: payload.adAccountId,
    campaign_id: payload.campaignId || undefined,
    adset_id: payload.adsetId || undefined,
    ad_id: payload.adId || undefined,
    source: payload.source
  })
  return mapBindingFromApi(extractSingleObject(data))
}

export const updateRuleBinding = async (
  bindingId: string,
  payload: { ruleConfigId?: string | null; active?: boolean }
): Promise<RuleBinding> => {
  const body: Record<string, unknown> = {}
  if (payload.ruleConfigId !== undefined) {
    body['rule_config_id'] = payload.ruleConfigId
  }
  if (payload.active !== undefined) {
    body['is_active'] = payload.active
  }
  const { data } = await apiClient.patch(`/rules/bindings/${bindingId}`, body)
  return mapBindingFromApi(extractSingleObject(data))
}

export const deleteRuleBinding = async (bindingId: string): Promise<void> => {
  await apiClient.delete(`/rules/bindings/${bindingId}`)
}

// ===== Execution Logs =====

export interface ExecutionLogFilters {
  ruleId?: string
  status?: ExecutionStatus | 'all'
  trigger?: 'all' | 'scheduler' | 'manual' | 'auto_unbind' | 'test'
  from?: string
  to?: string
}

export const fetchExecutionLogs = async (
  filters: ExecutionLogFilters = {}
): Promise<PaginatedResponse<RuleExecutionLog>> => {
  const { data } = await apiClient.get('/rules/executions', {
    params: {
      rule_id: filters.ruleId,
      status: filters.status === 'all' ? undefined : filters.status,
      trigger: filters.trigger === 'all' ? undefined : filters.trigger,
      from: filters.from,
      to: filters.to
    }
  })

  return extractPaginatedResponse<RuleExecutionLog>(data, mapExecutionLogFromApi)
}

export const fetchBindingExecutions = async (
  bindingId: string,
  limit: number = 50
): Promise<{ executions: RuleExecutionLog[]; total: number }> => {
  const { data } = await apiClient.get(`/rules/bindings/${bindingId}/executions`, {
    params: { limit }
  })

  const payload = extractResponseData(data)
  const rawExecutions = payload?.executions ?? payload?.items ?? (Array.isArray(payload) ? payload : [])
  const executions = Array.isArray(rawExecutions) ? rawExecutions.map(mapExecutionLogFromApi) : []

  return {
    executions,
    total: payload?.total ?? executions.length
  }
}

export const executeRuleManually = async (payload: {
  bindingId?: string
  ruleId?: string  // This is now rule_name
  trigger?: 'manual' | 'test'
  context?: Record<string, unknown>
  params?: Record<string, any>
}) => {
  const body: any = {
    binding_id: payload.bindingId,
    rule_id: payload.ruleId,
    trigger: payload.trigger,
    context: payload.context,
    params: payload.params,
  }

  const { data } = await apiClient.post('/rules/execute', body)
  return extractSingleObject(data)
}

// ===== Mappers =====

const mapBindingFromApi = (item: any): RuleBinding => {
  return {
    id: item?.id ?? '',
    ruleId: item?.rule_id ?? item?.ruleId ?? '',
    ruleName: item?.rule_name ?? item?.ruleName ?? '',
    ruleConfigId: item?.rule_config_id ?? item?.ruleConfigId ?? null,
    entityType: (item?.entity_type ?? item?.entityType ?? 'ad') as RuleEntityType,
    entityId: item?.entity_id ?? item?.entityId ?? '',
    adAccountId: item?.ad_account_id ?? item?.adAccountId ?? '',
    campaignId: item?.campaign_id ?? item?.campaignId ?? null,
    adsetId: item?.adset_id ?? item?.adsetId ?? null,
    adId: item?.ad_id ?? item?.adId ?? null,
    source: (item?.source ?? 'manual') as BindingSource,
    active: Boolean(
      item?.is_active ?? item?.isActive ?? item?.active ?? false
    ),
    created_at: item?.created_at ?? item?.createdAt ?? '',
    updated_at: item?.updated_at ?? item?.updatedAt ?? '',
    lastExecutedAt: item?.last_executed_at ?? item?.lastExecutedAt ?? undefined
  }
}

const mapExecutionLogFromApi = (item: any): RuleExecutionLog => {
  const rawStatus = (item?.status ?? item?.execution_status ?? 'success') as string
  const status: ExecutionStatus =
    rawStatus === 'failure'
      ? 'failed'
      : (rawStatus as ExecutionStatus)

  const rawTrigger = (item?.trigger ?? 'manual') as string
  const trigger: ExecutionTrigger =
    rawTrigger === 'scheduled'
      ? 'scheduler'
      : (rawTrigger as ExecutionTrigger)
  const rawDuration =
    item?.execution_duration_ms ??
    item?.executionDurationMs ??
    item?.durationMs ??
    undefined
  const durationMs =
    typeof rawDuration === 'number'
      ? rawDuration
      : typeof rawDuration === 'string'
        ? Number.parseFloat(rawDuration)
        : undefined

  const metricsValue = item?.metrics ?? {}

  return {
    id: item?.id ?? '',
    ruleId: item?.rule_id ?? item?.ruleId ?? '',
    ruleName: item?.rule_name ?? item?.ruleName ?? '未绑定执行',
    bindingId: item?.binding_id ?? item?.bindingId ?? undefined,
    entityType: item?.entity_type ?? item?.entityType ?? undefined,
    entityId: item?.entity_id ?? item?.entityId ?? undefined,
    status,
    trigger,
    scheduledRunTime:
      item?.scheduled_run_time ?? item?.scheduledRunTime ?? undefined,
    actualStartTime:
      item?.actual_start_time ?? item?.actualStartTime ?? undefined,
    completedAt:
      item?.completed_at ?? item?.completedAt ?? undefined,
    durationMs: Number.isFinite(durationMs) ? durationMs : undefined,
    actions: Array.isArray(item?.actions) ? item.actions : [],
    reasonCodes: Array.isArray(item?.reasons) ? item.reasons : [],
    metrics:
      metricsValue && typeof metricsValue === 'object' && !Array.isArray(metricsValue)
        ? metricsValue
        : {},
    contextSnapshot: item?.context_snapshot ?? item?.contextSnapshot ?? {},
    errorMessage: item?.error_message ?? item?.errorMessage ?? undefined,
    executionLogs: Array.isArray(item?.execution_logs)
      ? item.execution_logs
      : Array.isArray(item?.executionLogs)
        ? item.executionLogs
        : []
  }
}

// ===== Entity Timeline =====

export interface EntityTimelineDataPoint {
  date: string
  spend: number
  clicks: number
  impressions: number
  // Extended metrics from /api/insights
  reach?: number
  cpc?: number
  cpm?: number
  ctr?: number
  roas?: number
}

export interface EntityTimelineResponse {
  entity_type: string
  entity_id: string
  date_range: {
    since: string
    until: string
  }
  daily_data: EntityTimelineDataPoint[]
  total_days: number
}

export const fetchEntityTimeline = async (params: {
  adAccountId: string
  entityId: string
  entityType: string
}): Promise<EntityTimelineResponse> => {
  // Calculate 360 days date range
  const until = new Date()
  const since = new Date()
  since.setDate(since.getDate() - 360)
  
  const formatDate = (d: Date) => d.toISOString().split('T')[0]
  
  const { data } = await apiClient.get('/insights', {
    params: {
      ad_account_id: params.adAccountId,
      since: formatDate(since),
      until: formatDate(until),
      level: params.entityType,
      time_increment: 1
    },
  })
  
  const response = extractSingleObject<{ insights: any[], date_range: { since: string, until: string } }>(data)
  const insights = response?.insights || []
  
  // Filter by entity_id and transform to timeline format
  const entityIdField = params.entityType === 'ad' ? 'ad_id' 
    : params.entityType === 'adset' ? 'adset_id' 
    : params.entityType === 'campaign' ? 'campaign_id' 
    : 'ad_account_id'
  
  const filtered = insights.filter((item: any) => item[entityIdField] === params.entityId)
  
  // Sort by date and build daily_data
  const sorted = filtered.sort((a: any, b: any) => a.date.localeCompare(b.date))
  
  const daily_data: EntityTimelineDataPoint[] = sorted.map((item: any) => ({
    date: item.date,
    spend: item.metrics?.spend || 0,
    clicks: item.metrics?.clicks || 0,
    impressions: item.metrics?.impressions || 0,
    reach: item.metrics?.reach || 0,
    cpc: item.metrics?.cpc || 0,
    cpm: item.metrics?.cpm || 0,
    ctr: item.metrics?.ctr || 0,
    roas: item.metrics?.roas || 0,
  }))
  
  const dateRange = daily_data.length > 0 
    ? { since: daily_data[0].date, until: daily_data[daily_data.length - 1].date }
    : { since: '', until: '' }
  
  return {
    entity_type: params.entityType,
    entity_id: params.entityId,
    date_range: dateRange,
    daily_data,
    total_days: daily_data.length
  }
}

// ===== Scheduler =====

export const fetchSchedulerTasks = async (): Promise<SchedulerTask[]> => {
  const { data } = await apiClient.get('/scheduler/tasks')
  const payload = extractResponseData(data)
  const items = payload?.items ?? (Array.isArray(payload) ? payload : [])
  return Array.isArray(items) ? items.map(mapSchedulerTaskFromApi) : []
}

export const updateSchedulerTaskState = async (params: {
  namespace: SchedulerNamespace
  taskId: string
  action: 'pause' | 'resume'
}) => {
  const { namespace, taskId, action } = params
  const { data } = await apiClient.post(`/scheduler/tasks/${namespace}/${taskId}/${action}`)
  return extractSingleObject(data)
}

export const runSchedulerTaskNow = async (params: {
  namespace: SchedulerNamespace
  taskId: string
}) => {
  const { namespace, taskId } = params
  const { data } = await apiClient.post(`/scheduler/tasks/${namespace}/${taskId}/run`)
  return extractSingleObject(data)
}

export const updateSchedulerTask = async (params: {
  namespace: SchedulerNamespace
  taskId: string
  payload: { cron?: string; metadata?: Record<string, unknown> }
}): Promise<SchedulerTask> => {
  const { namespace, taskId, payload } = params
  const { data } = await apiClient.patch(`/scheduler/tasks/${namespace}/${taskId}`, payload)
  const body = extractSingleObject(data)
  return mapSchedulerTaskFromApi(body)
}

const mapSchedulerTaskFromApi = (item: any): SchedulerTask => {
  const metadataValue = item?.metadata
  const metadata =
    metadataValue && typeof metadataValue === 'object' && !Array.isArray(metadataValue)
      ? (metadataValue as Record<string, unknown>)
      : undefined

  return {
    namespace: (item?.namespace ?? 'rules') as SchedulerNamespace,
    id: item?.id ?? '',
    name: item?.name ?? '',
    cron: item?.cron ?? '',
    status: (item?.status ?? 'running') as SchedulerTask['status'],
    lastRunAt: item?.last_run_at ?? item?.lastRunAt ?? undefined,
    nextRunAt: item?.next_run_at ?? item?.nextRunAt ?? undefined,
    averageLatencyMs: item?.average_latency_ms ?? item?.averageLatencyMs ?? undefined,
    maxLatencyMs: item?.max_latency_ms ?? item?.maxLatencyMs ?? undefined,
    lastError: item?.last_error ?? item?.lastError ?? undefined,
    metadata
  }
}
