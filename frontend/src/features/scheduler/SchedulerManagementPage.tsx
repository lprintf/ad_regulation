import { useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Tabs } from '@/components/ui'
import {
  fetchSchedulerTasks,
  runSchedulerTaskNow,
  updateSchedulerTask,
  updateSchedulerTaskState,
  fetchExecutionLogs,
  executeRuleManually,
  fetchAvailableRules
} from '../../api/ruleEngine'
import { formatDateTime, formatRelativeTime } from '../../lib/datetime'
import type { SchedulerTask, SchedulerNamespace, RuleExecutionLog, ExecutionStatus } from '../../types/rule-engine'

const statusClass: Record<string, string> = {
  running: 'badge badge--success',
  paused: 'badge badge--disabled',
  error: 'badge badge--failure'
}

const statusBadgeClass: Record<ExecutionStatus, string> = {
  success: 'badge badge--success',
  failed: 'badge badge--failure',
  skipped: 'badge badge--skipped'
}

const triggerLabels: Record<string, string> = {
  manual: '人工触发',
  scheduler: '调度任务',
  auto_unbind: '自动解绑',
  test: '测试'
}

// ===== Scheduler Tasks Tab =====
const SchedulerTasksTab = () => {
  const queryClient = useQueryClient()
  const [editingTask, setEditingTask] = useState<SchedulerTask | null>(null)
  const [cronInput, setCronInput] = useState('')
  const [metadataInput, setMetadataInput] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const tasksQuery = useQuery({
    queryKey: ['scheduler-tasks'],
    queryFn: fetchSchedulerTasks,
    refetchInterval: 60_000
  })

  const updateStateMutation = useMutation({
    mutationFn: ({ namespace, taskId, action }: { namespace: SchedulerNamespace; taskId: string; action: 'pause' | 'resume' }) => 
      updateSchedulerTaskState({ namespace, taskId, action }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scheduler-tasks'] })
  })

  const runNowMutation = useMutation({
    mutationFn: ({ namespace, taskId }: { namespace: SchedulerNamespace; taskId: string }) => 
      runSchedulerTaskNow({ namespace, taskId }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scheduler-tasks'] })
  })

  const updateTaskMutation = useMutation({
    mutationFn: ({ namespace, taskId, payload }: { namespace: SchedulerNamespace; taskId: string; payload: { cron?: string; metadata?: Record<string, unknown> } }) =>
      updateSchedulerTask({ namespace, taskId, payload }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduler-tasks'] })
      setEditingTask(null)
      setFormError(null)
    },
    onError: (error: any) => {
      setFormError(error?.response?.data?.detail ?? error?.message ?? '更新失败')
    }
  })

  const openEditForm = (task: SchedulerTask) => {
    setEditingTask(task)
    setCronInput(task.cron ?? '')
    const defaultMetadata = task.metadata && Object.keys(task.metadata).length > 0 ? task.metadata : {}
    setMetadataInput(JSON.stringify(defaultMetadata, null, 2))
    setFormError(null)
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!editingTask) return

    const cronValue = cronInput.trim()
    if (!cronValue || !cronValue.startsWith('cron[') || !cronValue.endsWith(']')) {
      setFormError("Cron 表达式需保持 APScheduler 的 `cron[...]` 格式")
      return
    }

    let parsedMetadata: Record<string, unknown> = {}
    if (metadataInput.trim()) {
      try {
        const parsed = JSON.parse(metadataInput)
        if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
          setFormError('调度配置需为对象')
          return
        }
        parsedMetadata = parsed
      } catch {
        setFormError('JSON 格式错误')
        return
      }
    }

    updateTaskMutation.mutate({
      namespace: editingTask.namespace,
      taskId: editingTask.id,
      payload: { cron: cronValue, metadata: parsedMetadata }
    })
  }

  const summarizeMetadata = (metadata?: Record<string, unknown>) => {
    if (!metadata) return ''
    const entries = Object.entries(metadata).filter(([, v]) => v !== undefined && v !== null && v !== '')
    if (!entries.length) return ''
    return entries.map(([k, v]) => Array.isArray(v) ? `${k}=[${v.join(', ')}]` : `${k}=${String(v)}`).join('；')
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <div className="text-muted-foreground text-sm">
          管理 APScheduler 调度任务的运行状态
        </div>
        <button className="button button--secondary" onClick={() => tasksQuery.refetch()} disabled={tasksQuery.isFetching}>
          {tasksQuery.isFetching ? '刷新中...' : '刷新'}
        </button>
      </div>

      {tasksQuery.isError ? (
        <div className="empty-state">加载失败</div>
      ) : tasksQuery.isLoading ? (
        <div className="empty-state">加载中...</div>
      ) : (tasksQuery.data ?? []).length === 0 ? (
        <div className="empty-state">暂无调度任务</div>
      ) : (
        <div className="table-wrapper">
          <table className="table">
            <thead>
              <tr>
                <th>任务</th>
                <th>Cron</th>
                <th>状态</th>
                <th>调度时间</th>
                <th>延迟</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {(tasksQuery.data ?? []).map(task => (
                <tr key={task.id}>
                  <td>
                    <div className="font-semibold">{task.name}</div>
                    <div className="text-xs text-muted-foreground">命名空间：{task.namespace}</div>
                    {task.lastError && <div className="text-destructive text-sm">{task.lastError}</div>}
                  </td>
                  <td>
                    <code>{task.cron}</code>
                    {summarizeMetadata(task.metadata) && (
                      <div className="mt-1 text-xs text-muted-foreground">
                        配置：{summarizeMetadata(task.metadata)}
                      </div>
                    )}
                  </td>
                  <td>
                    <span className={statusClass[task.status] ?? 'badge'}>
                      {task.status === 'running' ? '运行中' : task.status === 'paused' ? '暂停' : '异常'}
                    </span>
                  </td>
                  <td>
                    <div>上次：{formatDateTime(task.lastRunAt)}</div>
                    <div className="text-xs text-muted-foreground">下一次：{formatDateTime(task.nextRunAt)}</div>
                  </td>
                  <td>
                    <div>平均：{task.averageLatencyMs ?? '—'} ms</div>
                    <div className="text-xs text-muted-foreground">峰值：{task.maxLatencyMs ?? '—'} ms</div>
                  </td>
                  <td>
                    <div className="flex gap-2 flex-wrap">
                      <button className="button button--ghost" onClick={() => openEditForm(task)}>编辑</button>
                      <button className="button button--secondary" onClick={() => runNowMutation.mutate({ namespace: task.namespace, taskId: task.id })} disabled={runNowMutation.isPending}>
                        立即执行
                      </button>
                      <button className="button button--ghost" onClick={() => updateStateMutation.mutate({ namespace: task.namespace, taskId: task.id, action: task.status === 'running' ? 'pause' : 'resume' })}>
                        {task.status === 'running' ? '暂停' : '恢复'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editingTask && (
        <div className="mt-6 p-4 border border-border rounded-lg">
          <h4 className="mb-4">编辑任务：{editingTask.name}</h4>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <label className="form-label">
              <span>Cron 表达式</span>
              <input className="input" value={cronInput} onChange={e => setCronInput(e.target.value)} placeholder="cron[minute='*/30']" />
            </label>
            <label className="form-label">
              <span>任务配置（JSON）</span>
              <textarea className="textarea" rows={4} value={metadataInput} onChange={e => setMetadataInput(e.target.value)} />
            </label>
            {formError && <div className="text-destructive text-sm">{formError}</div>}
            <div className="flex gap-3">
              <button className="button button--primary" type="submit" disabled={updateTaskMutation.isPending}>保存</button>
              <button className="button button--ghost" type="button" onClick={() => setEditingTask(null)}>取消</button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}

// ===== Execution Logs Tab =====
const ExecutionLogsTab = () => {
  const queryClient = useQueryClient()
  const [selectedLog, setSelectedLog] = useState<RuleExecutionLog | null>(null)
  const [filters, setFilters] = useState<{ ruleId: string; status: ExecutionStatus | 'all'; trigger: string }>({
    ruleId: '',
    status: 'all',
    trigger: 'all'
  })

  const rulesQuery = useQuery({
    queryKey: ['available-rules'],
    queryFn: fetchAvailableRules,
    staleTime: 60_000
  })

  const logsQuery = useQuery({
    queryKey: ['rule-executions', filters],
    queryFn: () => fetchExecutionLogs({
      ruleId: filters.ruleId || undefined,
      status: filters.status,
      trigger: filters.trigger as any
    }),
    refetchInterval: 30_000
  })

  const executeMutation = useMutation({
    mutationFn: executeRuleManually,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['rule-executions'] })
  })

  const logItems = logsQuery.data?.items ?? []
  const rules = rulesQuery.data ?? []

  return (
    <div>
      <div className="toolbar mb-4">
        <div className="toolbar__group">
          <select className="select" value={filters.ruleId} onChange={e => setFilters(prev => ({ ...prev, ruleId: e.target.value }))}>
            <option value="">全部规则</option>
            {rules.map(rule => <option key={rule.name} value={rule.name}>{rule.name}</option>)}
          </select>
        </div>
        <div className="toolbar__group">
          <select className="select" value={filters.status} onChange={e => setFilters(prev => ({ ...prev, status: e.target.value as any }))}>
            <option value="all">全部状态</option>
            <option value="success">成功</option>
            <option value="failed">失败</option>
            <option value="skipped">跳过</option>
          </select>
        </div>
        <div className="toolbar__group">
          <select className="select" value={filters.trigger} onChange={e => setFilters(prev => ({ ...prev, trigger: e.target.value }))}>
            <option value="all">全部触发</option>
            <option value="scheduler">调度任务</option>
            <option value="manual">人工触发</option>
            <option value="test">测试</option>
          </select>
        </div>
        <button className="button button--secondary" onClick={() => logsQuery.refetch()} disabled={logsQuery.isFetching}>
          刷新
        </button>
      </div>

      {logsQuery.isError ? (
        <div className="empty-state">加载失败</div>
      ) : logsQuery.isLoading ? (
        <div className="empty-state">加载中...</div>
      ) : logItems.length === 0 ? (
        <div className="empty-state">暂无执行记录</div>
      ) : (
        <div className="table-wrapper">
          <table className="table">
            <thead>
              <tr>
                <th>规则</th>
                <th>触发</th>
                <th>状态</th>
                <th>执行时间</th>
                <th>耗时</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {logItems.map(log => (
                <tr key={log.id} onClick={() => setSelectedLog(log)} className="cursor-pointer">
                  <td>
                    <div className="font-semibold">{log.ruleName}</div>
                    <div className="text-xs text-muted-foreground">
                      {log.bindingId ? `绑定 #${log.bindingId.slice(-8)}` : '未绑定'}
                    </div>
                  </td>
                  <td>{triggerLabels[log.trigger] ?? log.trigger}</td>
                  <td>
                    <span className={statusBadgeClass[log.status]}>
                      {log.status === 'success' ? '成功' : log.status === 'failed' ? '失败' : '跳过'}
                    </span>
                  </td>
                  <td>
                    <div>{formatDateTime(log.actualStartTime)}</div>
                    <div className="text-xs text-muted-foreground">{formatRelativeTime(log.actualStartTime)}</div>
                  </td>
                  <td>{log.durationMs !== undefined ? `${(log.durationMs / 1000).toFixed(2)}s` : '—'}</td>
                  <td onClick={e => e.stopPropagation()}>
                    <button
                      className="button button--ghost"
                      onClick={() => executeMutation.mutate({ bindingId: log.bindingId, ruleId: log.ruleId, trigger: 'manual' })}
                      disabled={executeMutation.isPending}
                    >
                      重新执行
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedLog && (
        <div className="mt-6 p-4 border border-border rounded-lg">
          <div className="flex justify-between items-center mb-4">
            <h4>执行详情 · {selectedLog.ruleName}</h4>
            <button className="button button--ghost" onClick={() => setSelectedLog(null)}>关闭</button>
          </div>
          <div className="grid gap-4">
            <div>
              <strong>状态：</strong>
              <span className={`${statusBadgeClass[selectedLog.status]} ml-2`}>
                {selectedLog.status === 'success' ? '成功' : selectedLog.status === 'failed' ? '失败' : '跳过'}
              </span>
              <span className="ml-4">触发：{triggerLabels[selectedLog.trigger]}</span>
              <span className="ml-4">耗时：{selectedLog.durationMs ?? '—'}ms</span>
            </div>
            {selectedLog.errorMessage && (
              <div>
                <strong className="text-destructive">错误信息：</strong>
                <pre className="my-2 p-2 bg-red-500/10 rounded text-destructive whitespace-pre-wrap">
                  {selectedLog.errorMessage}
                </pre>
              </div>
            )}
            {selectedLog.contextSnapshot && Object.keys(selectedLog.contextSnapshot).length > 0 && (
              <div>
                <strong>上下文快照：</strong>
                <pre className="my-2 p-2 bg-slate-500/5 rounded max-h-[200px] overflow-auto">
                  {JSON.stringify(selectedLog.contextSnapshot, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ===== Main Page =====
const SchedulerManagementPage = () => {
  return (
    <div className="page">
      <section className="card mb-4">
        <div className="card__header border-b-0 pb-0">
          <div>
            <div className="card__title">调度管理</div>
            <div className="card__subtitle">管理调度任务和查看执行日志</div>
          </div>
        </div>
      </section>

      <Tabs
        defaultActiveKey="tasks"
        items={[
          { key: 'tasks', label: '调度任务', children: <SchedulerTasksTab /> },
          { key: 'logs', label: '执行日志', children: <ExecutionLogsTab /> }
        ]}
      />
    </div>
  )
}

export default SchedulerManagementPage
