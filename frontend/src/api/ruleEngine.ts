import apiClient from '../lib/apiClient'
import type {
  BindingSource,
  ExecutionStatus,
  RuleBinding,
  RuleDefinition,
  RuleEntityType,
  RuleExecutionLog,
  RuleStatus,
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

export interface RuleDefinitionFilters {
  search?: string
  status?: RuleStatus | 'all'
  tag?: string
}

export interface RuleDefinitionPayload {
  name: string
  description?: string
  code: string
  status: RuleStatus
  parameters?: RuleDefinition['parameters']
  tags?: string[]
}

export const fetchRuleDefinitions = async (
  filters: RuleDefinitionFilters = {}
): Promise<PaginatedResponse<RuleDefinition>> => {
  const { data } = await apiClient.get('/rules/definitions', {
    params: {
      search: filters.search,
      status: filters.status === 'all' ? undefined : filters.status,
      tag: filters.tag
    }
  })

  if (Array.isArray(data?.data)) {
    return {
      items: data.data,
      total: data.data.length,
      page: 1,
      pageSize: data.data.length
    }
  }

  return data?.data ?? {
    items: [],
    total: 0,
    page: 1,
    pageSize: 50
  }
}

export const createRuleDefinition = async (
  payload: RuleDefinitionPayload
): Promise<RuleDefinition> => {
  const { data } = await apiClient.post('/rules/definitions', payload)
  return data?.data ?? data
}

export const updateRuleDefinition = async (
  ruleId: string,
  payload: Partial<RuleDefinitionPayload>
): Promise<RuleDefinition> => {
  const { data } = await apiClient.patch(`/rules/definitions/${ruleId}`, payload)
  return data?.data ?? data
}

export const fetchRuleDefinition = async (ruleId: string): Promise<RuleDefinition> => {
  const { data } = await apiClient.get(`/rules/definitions/${ruleId}`)
  return data?.data ?? data
}

export interface CloneRulePayload {
  new_name: string
  new_version?: string
  parameter_overrides?: Record<string, any>
  description?: string
  created_by?: string
}

export const cloneRuleDefinition = async (
  ruleId: string,
  payload: CloneRulePayload
): Promise<RuleDefinition> => {
  const { data } = await apiClient.post(`/rules/definitions/${ruleId}/clone`, payload)
  return data?.data ?? data
}

export interface RuleBindingFilters {
  ruleId?: string
  entityId?: string
  entityType?: RuleEntityType | 'all'
  activeOnly?: boolean
}

export interface RuleBindingPayload {
  ruleId: string
  entityId: string
  entityType: RuleEntityType
  source?: BindingSource
  metadata?: Record<string, unknown>
}

export const fetchRuleBindings = async (
  filters: RuleBindingFilters = {}
): Promise<PaginatedResponse<RuleBinding>> => {
  const { data } = await apiClient.get('/rules/bindings', {
    params: {
      rule_id: filters.ruleId,
      entity_id: filters.entityId,
      entity_type: filters.entityType === 'all' ? undefined : filters.entityType,
      active_only: filters.activeOnly
    }
  })

  const rawItems: any[] = (() => {
    if (Array.isArray(data?.data)) {
      return data.data
    }
    if (Array.isArray(data)) {
      return data
    }
    if (Array.isArray(data?.items)) {
      return data.items
    }
    const payload = data?.data
    if (Array.isArray(payload?.items)) {
      return payload.items
    }
    if (Array.isArray(payload)) {
      return payload
    }
    return []
  })()

  const items = rawItems.map(mapBindingFromApi)

  const total =
    data?.data?.total ??
    data?.total ??
    rawItems.length

  return {
    items,
    total,
    page: data?.data?.page ?? 1,
    pageSize: data?.data?.pageSize ?? (items.length || 50)
  }
}

export const createRuleBinding = async (
  payload: RuleBindingPayload
): Promise<RuleBinding> => {
  const { data } = await apiClient.post('/rules/bindings', {
    rule_id: payload.ruleId,
    entity_id: payload.entityId,
    entity_type: payload.entityType,
    source: payload.source,
    metadata: payload.metadata
  })
  return mapBindingFromApi(data?.data ?? data)
}

export const updateRuleBinding = async (
  bindingId: string,
  payload: Partial<RuleBindingPayload & { active: boolean }>
): Promise<RuleBinding> => {
  const body: Record<string, unknown> = {}
  if (payload.metadata !== undefined) {
    body['metadata'] = payload.metadata
  }
  if (payload.active !== undefined) {
    body['is_active'] = payload.active
  }
  const { data } = await apiClient.patch(`/rules/bindings/${bindingId}`, body)
  return mapBindingFromApi(data?.data ?? data)
}

export const deleteRuleBinding = async (bindingId: string): Promise<void> => {
  await apiClient.delete(`/rules/bindings/${bindingId}`)
}

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

  if (Array.isArray(data?.data)) {
    return {
      items: data.data,
      total: data.data.length,
      page: 1,
      pageSize: data.data.length
    }
  }

  const payload = data?.data ?? data ?? {}
  const items =
    payload.executions ??
    payload.items ??
    (Array.isArray(payload) ? payload : [])
  const total =
    payload.total ??
    (Array.isArray(items) ? items.length : 0)

  const normalizedItems = Array.isArray(items)
    ? items.map(mapExecutionLogFromApi)
    : []

  return {
    items: normalizedItems,
    total: typeof total === 'number' ? total : 0,
    page: payload.page ?? 1,
    pageSize: payload.pageSize ?? (normalizedItems.length || 50)
  }
}

const mapBindingFromApi = (item: any): RuleBinding => {
  const metadata = (item?.metadata ?? {}) as Record<string, unknown>
  const accountId =
    (metadata.ad_account_id as string | undefined) ??
    (metadata.account_id as string | undefined) ??
    (metadata.accountId as string | undefined)
  const notes =
    (metadata.notes as string | undefined) ??
    (metadata.note as string | undefined) ??
    (metadata.remark as string | undefined)

  return {
    id: item?.id ?? '',
    ruleId: item?.rule_id ?? item?.ruleId ?? '',
    ruleName: item?.rule_name ?? item?.ruleName ?? '',
    entityType: (item?.entity_type ?? item?.entityType ?? 'ad') as RuleEntityType,
    entityId: item?.entity_id ?? item?.entityId ?? '',
    source: (item?.source ?? 'manual') as BindingSource,
    metadata,
    active: Boolean(
      item?.is_active ?? item?.isActive ?? item?.active ?? false
    ),
    accountId: accountId || undefined,
    notes: notes || undefined,
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

export const executeRuleManually = async (payload: {
  bindingId?: string
  ruleId?: string
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
  return data?.data ?? data
}

export const fetchBindingExecutions = async (
  bindingId: string,
  limit: number = 50
): Promise<{ executions: RuleExecutionLog[]; total: number }> => {
  const { data } = await apiClient.get(`/rules/bindings/${bindingId}/executions`, {
    params: { limit }
  })

  const payload = data?.data ?? data
  const executions = Array.isArray(payload?.executions)
    ? payload.executions.map(mapExecutionLogFromApi)
    : []

  return {
    executions,
    total: payload?.total ?? executions.length
  }
}

export interface EntityTimelineDataPoint {
  date: string
  spend: number
  clicks: number
  impressions: number
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
  const { data } = await apiClient.get('/insights/entity-timeline', {
    params: {
      ad_account_id: params.adAccountId,
      entity_id: params.entityId,
      entity_type: params.entityType,
    },
  })
  return data?.data ?? data
}

export const fetchSchedulerTasks = async (): Promise<SchedulerTask[]> => {
  const { data } = await apiClient.get('/scheduler/tasks')
  const payload = data?.data ?? data ?? []
  if (Array.isArray(payload)) {
    return payload.map(mapSchedulerTaskFromApi)
  }
  return Array.isArray(payload?.items)
    ? payload.items.map(mapSchedulerTaskFromApi)
    : []
}

export const updateSchedulerTaskState = async (params: {
  namespace: SchedulerNamespace
  taskId: string
  action: 'pause' | 'resume'
}) => {
  const { namespace, taskId, action } = params
  const { data } = await apiClient.post(`/scheduler/tasks/${namespace}/${taskId}/${action}`)
  return data?.data ?? data
}

export const runSchedulerTaskNow = async (params: {
  namespace: SchedulerNamespace
  taskId: string
}) => {
  const { namespace, taskId } = params
  const { data } = await apiClient.post(`/scheduler/tasks/${namespace}/${taskId}/run`)
  return data?.data ?? data
}

export const updateSchedulerTask = async (params: {
  namespace: SchedulerNamespace
  taskId: string
  payload: { cron?: string; metadata?: Record<string, unknown> }
}): Promise<SchedulerTask> => {
  const { namespace, taskId, payload } = params
  const { data } = await apiClient.patch(`/scheduler/tasks/${namespace}/${taskId}`, payload)
  const body = data?.data ?? data
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
