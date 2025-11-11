export type RuleStatus = 'draft' | 'published' | 'disabled'

export interface RuleParameter {
  key: string
  label?: string
  type: 'string' | 'number' | 'boolean' | 'enum'
  required?: boolean
  defaultValue?: string | number | boolean | null
  description?: string
  options?: Array<{ value: string; label: string }>
}

export interface RuleDefinition {
  id: string
  name: string
  code: string
  version: number
  status: RuleStatus
  description?: string
  tags?: string[]
  parameters?: RuleParameter[]
  createdAt: string
  updatedAt: string
  publishedBy?: string
}

export type RuleEntityType = 'account' | 'campaign' | 'adset' | 'ad'

export type BindingSource = 'manual' | 'auto' | 'naming_parser'

export interface RuleBinding {
  id: string
  ruleId: string
  ruleName: string
  entityType: RuleEntityType
  entityId: string
  source: BindingSource
  metadata: Record<string, unknown>
  active: boolean
  accountId?: string
  notes?: string
  createdAt: string
  updatedAt: string
  lastExecutedAt?: string
}

export type ExecutionStatus = 'success' | 'failed' | 'skipped'
export type ExecutionTrigger = 'manual' | 'scheduler' | 'auto_unbind' | 'test'

export interface RuleExecutionLog {
  id: string
  ruleId: string
  ruleName: string
  bindingId?: string
  entityType?: RuleEntityType
  entityId?: string
  status: ExecutionStatus
  trigger: ExecutionTrigger
  scheduledRunTime?: string
  actualStartTime?: string
  completedAt?: string
  durationMs?: number
  actions?: Array<{
    type: string
    payload?: Record<string, unknown>
    message?: string
  }>
  reasonCodes?: string[]
  metrics?: Record<string, unknown>
  contextSnapshot?: Record<string, unknown>
  errorMessage?: string
}

export type SchedulerNamespace = 'rules' | 'insights'

export interface SchedulerTask {
  namespace: SchedulerNamespace
  id: string
  name: string
  cron: string
  status: 'running' | 'paused' | 'error'
  lastRunAt?: string
  nextRunAt?: string
  averageLatencyMs?: number
  maxLatencyMs?: number
  lastError?: string
  metadata?: Record<string, unknown>
}
