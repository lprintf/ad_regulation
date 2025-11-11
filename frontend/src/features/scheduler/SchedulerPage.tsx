import { useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  fetchSchedulerTasks,
  runSchedulerTaskNow,
  updateSchedulerTask,
  updateSchedulerTaskState
} from '../../api/ruleEngine'
import { formatDateTime, formatRelativeTime } from '../../lib/datetime'
import type { SchedulerTask, SchedulerNamespace } from '../../types/rule-engine'

const statusClass: Record<string, string> = {
  running: 'badge badge--success',
  paused: 'badge badge--disabled',
  error: 'badge badge--failure'
}

const SchedulerPage = () => {
  const queryClient = useQueryClient()
  const [editingTask, setEditingTask] = useState<SchedulerTask | null>(null)
  const [cronInput, setCronInput] = useState('')
  const [metadataInput, setMetadataInput] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const DEFAULT_METADATA_PLACEHOLDER =
    '{"ad_accounts": ["act_123"], "inactive_days": 7}'

  const tasksQuery = useQuery({
    queryKey: ['scheduler-tasks'],
    queryFn: fetchSchedulerTasks,
    refetchInterval: 60_000
  })

  const updateStateMutation = useMutation({
    mutationFn: ({
      namespace,
      taskId,
      action
    }: {
      namespace: SchedulerNamespace
      taskId: string
      action: 'pause' | 'resume'
    }) => updateSchedulerTaskState({ namespace, taskId, action }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduler-tasks'] })
    }
  })

  const runNowMutation = useMutation({
    mutationFn: ({
      namespace,
      taskId
    }: {
      namespace: SchedulerNamespace
      taskId: string
    }) => runSchedulerTaskNow({ namespace, taskId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduler-tasks'] })
    }
  })

  const updateTaskMutation = useMutation<
    SchedulerTask,
    unknown,
    {
      namespace: SchedulerNamespace
      taskId: string
      payload: { cron?: string; metadata?: Record<string, unknown> }
    }
  >({
    mutationFn: ({ namespace, taskId, payload }) =>
      updateSchedulerTask({ namespace, taskId, payload }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduler-tasks'] })
      setEditingTask(null)
      setFormError(null)
    },
    onError: error => {
      if (
        error &&
        typeof error === 'object' &&
        'response' in error &&
        (error as any)?.response?.data?.detail
      ) {
        setFormError((error as any).response.data.detail as string)
        return
      }
      if (error instanceof Error) {
        setFormError(error.message)
      } else {
        setFormError('调度任务更新失败，请稍后再试')
      }
    }
  })

  const openEditForm = (task: SchedulerTask) => {
    setEditingTask(task)
    setCronInput(task.cron ?? '')
    const defaultMetadata =
      task.metadata && Object.keys(task.metadata).length > 0
        ? task.metadata
        : task.id === 'rules::hourly_new_ad_scan'
          ? { ad_accounts: [] }
          : {}
    setMetadataInput(JSON.stringify(defaultMetadata, null, 2))
    setFormError(null)
  }

  const handleCancelEdit = () => {
    setEditingTask(null)
    setFormError(null)
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!editingTask) {
      return
    }

    const cronValue = cronInput.trim()
    if (!cronValue) {
      setFormError('请输入 Cron 配置')
      return
    }
    if (!cronValue.startsWith('cron[') || !cronValue.endsWith(']')) {
      setFormError("Cron 表达式需保持 APScheduler 的 `cron[...]` 格式")
      return
    }

    const metadataValue = metadataInput.trim()
    let parsedMetadata: Record<string, unknown> | undefined = undefined
    if (metadataValue) {
      try {
        const parsed = JSON.parse(metadataValue)
        if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
          setFormError('调度配置需为对象（key-value）')
          return
        }
        parsedMetadata = parsed as Record<string, unknown>
      } catch (err) {
        setFormError('调度配置 JSON 解析失败，请检查格式')
        return
      }
    } else {
      parsedMetadata = {}
    }

    setFormError(null)
    updateTaskMutation.mutate({
      namespace: editingTask.namespace,
      taskId: editingTask.id,
      payload: {
        cron: cronValue,
        metadata: parsedMetadata
      }
    })
  }

  const summarizeMetadata = (metadata?: Record<string, unknown>) => {
    if (!metadata) {
      return ''
    }
    const entries = Object.entries(metadata).filter(
      ([, value]) => value !== undefined && value !== null && value !== ''
    )
    if (!entries.length) {
      return ''
    }
    return entries
      .map(([key, value]) => {
        if (Array.isArray(value)) {
          return `${key}=[${value.map(item => String(item)).join(', ')}]`
        }
        if (typeof value === 'object') {
          return `${key}={...}`
        }
        return `${key}=${String(value)}`
      })
      .join('；')
  }

  return (
    <div className="page">
      <section className="card">
        <div className="card__header">
          <div>
            <div className="card__title">调度监控</div>
            <div className="card__subtitle">
              可视化 APScheduler 任务运行状态，监控延迟与异常。
            </div>
          </div>
          <button
            className="button button--secondary"
            onClick={() => tasksQuery.refetch()}
            disabled={tasksQuery.isFetching}
          >
            {tasksQuery.isFetching ? '刷新中...' : '刷新'}
          </button>
        </div>

        {tasksQuery.isError ? (
          <div className="empty-state">
            加载调度任务失败，
            {tasksQuery.error instanceof Error ? tasksQuery.error.message : '请稍后再试'}
          </div>
        ) : tasksQuery.isLoading ? (
          <div className="empty-state">加载中...</div>
        ) : (tasksQuery.data ?? []).length === 0 ? (
          <div className="empty-state">尚未配置调度任务。</div>
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
                {(tasksQuery.data ?? []).map(task => {
                  const metadataSummary = summarizeMetadata(task.metadata)
                  return (
                    <tr key={task.id}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{task.name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                          命名空间：{task.namespace}
                        </div>
                        {task.lastError && (
                          <div style={{ color: 'var(--color-danger)', fontSize: '0.8rem' }}>
                            {task.lastError}
                          </div>
                        )}
                      </td>
                      <td>
                        <code>{task.cron}</code>
                        {metadataSummary && (
                          <div
                            style={{
                              marginTop: '0.25rem',
                              fontSize: '0.75rem',
                              color: 'var(--color-text-muted)'
                            }}
                          >
                            配置：{metadataSummary}
                          </div>
                        )}
                      </td>
                      <td>
                        <span className={statusClass[task.status] ?? 'badge'}>
                          {task.status === 'running'
                            ? '运行中'
                            : task.status === 'paused'
                              ? '暂停'
                              : '异常'}
                        </span>
                      </td>
                      <td>
                        <div>上次：{formatDateTime(task.lastRunAt)}</div>
                        <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                          下一次：{formatDateTime(task.nextRunAt)}
                        </div>
                      </td>
                      <td>
                        <div>平均：{task.averageLatencyMs ?? '—'} ms</div>
                        <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                          峰值：{task.maxLatencyMs ?? '—'} ms
                        </div>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                          <button
                            className="button button--ghost"
                            onClick={() => openEditForm(task)}
                            disabled={updateTaskMutation.isPending && editingTask?.id === task.id}
                          >
                            编辑
                          </button>
                          <button
                            className="button button--secondary"
                            onClick={() =>
                              runNowMutation.mutate({
                                namespace: task.namespace,
                                taskId: task.id
                              })
                            }
                            disabled={runNowMutation.isPending}
                          >
                            立即执行
                          </button>
                          <button
                            className="button button--ghost"
                            onClick={() =>
                              updateStateMutation.mutate({
                                namespace: task.namespace,
                                taskId: task.id,
                                action: task.status === 'running' ? 'pause' : 'resume'
                              })
                            }
                            disabled={updateStateMutation.isPending}
                          >
                            {task.status === 'running' ? '暂停' : '恢复'}
                          </button>
                          <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                            {task.lastRunAt ? `最近：${formatRelativeTime(task.lastRunAt)}` : ''}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {editingTask && (
        <section className="card" style={{ marginTop: '1.5rem' }}>
          <div className="card__header">
            <div>
              <div className="card__title">编辑任务：{editingTask.name}</div>
              <div className="card__subtitle">
                修改 APScheduler Cron 表达式与任务配置，例如{' '}
                <code>cron[minute='*/30']</code>
                {'、'}
                <code>{"{\"ad_accounts\": [\"act_1\", \"act_2\"]}"}</code>
                {'。'}
              </div>
            </div>
          </div>
          <form
            onSubmit={handleSubmit}
            style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}
          >
            <label className="form-label">
              <span>Cron 表达式</span>
              <input
                className="input"
                value={cronInput}
                onChange={event => setCronInput(event.target.value)}
                placeholder="cron[minute='*/30']"
                spellCheck={false}
              />
              <div className="form-hint">
                保持 APScheduler 的 `cron[...]` 结构，可调整 minute/hour/day 等字段。
              </div>
            </label>
            <label className="form-label">
              <span>任务配置（JSON 对象）</span>
              <textarea
                className="textarea"
                rows={6}
                value={metadataInput}
                onChange={event => setMetadataInput(event.target.value)}
                placeholder={DEFAULT_METADATA_PLACEHOLDER}
                spellCheck={false}
              />
              <div className="form-hint">
                举例：{' '}
                <code>{"{\"ad_accounts\": [\"act_1\", \"act_2\"]}"}</code>
                {' 或 '}
                <code>{"{\"inactive_days\": 10}"}</code>
                {'。留空表示使用系统默认值。'}
              </div>
            </label>
            {formError && (
              <div style={{ color: 'var(--color-danger)', fontSize: '0.85rem' }}>{formError}</div>
            )}
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button
                className="button button--primary"
                type="submit"
                disabled={updateTaskMutation.isPending}
              >
                {updateTaskMutation.isPending ? '保存中...' : '保存配置'}
              </button>
              <button
                className="button button--ghost"
                type="button"
                onClick={handleCancelEdit}
                disabled={updateTaskMutation.isPending}
              >
                取消
              </button>
            </div>
          </form>
        </section>
      )}
    </div>
  )
}

export default SchedulerPage
