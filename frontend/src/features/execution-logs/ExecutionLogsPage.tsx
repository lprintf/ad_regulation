import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode
} from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Dropdown, Select, Space, Table, Tag } from 'antd'
import type { ColumnsType, TablePaginationConfig, TableProps } from 'antd/es/table'
import type { SortOrder } from 'antd/es/table/interface'
import { FilterOutlined, ReloadOutlined } from '@ant-design/icons'

import {
  executeRuleManually,
  fetchExecutionLogs,
  fetchRuleDefinitions
} from '../../api/ruleEngine'
import type {
  ExecutionStatus,
  RuleExecutionLog,
  RuleStatus
} from '../../types/rule-engine'
import { formatDateTime } from '../../lib/datetime'

type FilterState = {
  ruleId: string
  status: ExecutionStatus | 'all'
  trigger: RuleExecutionLog['trigger'] | 'all'
}

type FiltersContextValue = {
  filters: FilterState
  setFilters: React.Dispatch<React.SetStateAction<FilterState>>
}

const FiltersContext = createContext<FiltersContextValue | null>(null)

const useFiltersContext = () => {
  const ctx = useContext(FiltersContext)
  if (!ctx) {
    throw new Error('FiltersContext is not available')
  }
  return ctx
}

type ColumnFilterProps = {
  label: string
  filterKey: keyof FilterState
  options: Array<{ label: string; value: string }>
  overlayWidth?: number
}

const ColumnFilter = ({
  label,
  filterKey,
  options,
  overlayWidth = 220
}: ColumnFilterProps) => {
  const { filters, setFilters } = useFiltersContext()
  const [open, setOpen] = useState(false)

  const currentValue = filters[filterKey]
  const isRuleFilter = filterKey === 'ruleId'
  const isActive = isRuleFilter ? currentValue !== '' : currentValue !== 'all'

  const handleChange = (value: string) => {
    setFilters(current => ({
      ...current,
      [filterKey]: value
    }))
    setOpen(false)
  }

  const handleClear = () => {
    setFilters(current => ({
      ...current,
      [filterKey]: isRuleFilter ? '' : 'all'
    }))
    setOpen(false)
  }

  return (
    <Dropdown
      open={open}
      onOpenChange={setOpen}
      trigger={['click']}
      dropdownRender={() => (
        <div
          style={{
            padding: '0.75rem',
            background: '#ffffff',
            borderRadius: 'var(--radius-md)',
            boxShadow: '0 8px 24px rgba(15, 23, 42, 0.15)',
            width: overlayWidth
          }}
          onClick={event => event.stopPropagation()}
        >
          <Select
            style={{ width: '100%' }}
            value={currentValue}
            options={options}
            showSearch
            onChange={handleChange}
            optionFilterProp="label"
          />
          {isActive ? (
            <Button
              type="link"
              onClick={handleClear}
              style={{ padding: 0, marginTop: '0.5rem' }}
            >
              清除
            </Button>
          ) : null}
        </div>
      )}
    >
      <Space size={4} style={{ cursor: 'pointer' }}>
        <span>{label}</span>
        <FilterOutlined
          style={{
            fontSize: 12,
            color: isActive ? 'var(--color-primary)' : 'var(--color-text-muted)'
          }}
        />
      </Space>
    </Dropdown>
  )
}

const statusBadgeClass: Record<ExecutionStatus, string> = {
  success: 'badge badge--success',
  failed: 'badge badge--failure',
  skipped: 'badge badge--skipped'
}

const triggerLabels: Record<RuleExecutionLog['trigger'], string> = {
  manual: '人工触发',
  scheduler: '调度任务',
  auto_unbind: '自动解绑',
  test: '测试'
}

const ExecutionLogsTable = ({
  data,
  rulesOptions,
  loading,
  retryLoading,
  onRefresh,
  onRetry,
  onRowSelect
}: {
  data: RuleExecutionLog[]
  rulesOptions: Array<{ label: string; value: string }>
  loading: boolean
  retryLoading: boolean
  onRefresh: () => void
  onRetry: (log: RuleExecutionLog) => void
  onRowSelect: (log: RuleExecutionLog) => void
}) => {
  const [pagination, setPagination] = useState<TablePaginationConfig>({
    current: 1,
    pageSize: 10
  })
  const [sorterState, setSorterState] = useState<{
    columnKey?: React.Key
    order?: SortOrder
  }>({
    columnKey: 'timing',
    order: 'descend'
  })

  const triggerOptions = useMemo(
    () => [
      { label: '全部触发', value: 'all' },
      { label: '调度任务', value: 'scheduler' },
      { label: '自动解绑', value: 'auto_unbind' },
      { label: '人工触发', value: 'manual' },
      { label: '测试', value: 'test' }
    ],
    []
  )

  const statusOptions = useMemo(
    () => [
      { label: '全部状态', value: 'all' },
      { label: '成功', value: 'success' },
      { label: '失败', value: 'failed' },
      { label: '跳过', value: 'skipped' }
    ],
    []
  )

  const tableData = useMemo(
    () => data.map(log => ({ ...log, key: log.id })),
    [data]
  )

  const columns: ColumnsType<RuleExecutionLog & { key: string }> = useMemo(
    () => [
      {
        title: (
          <ColumnFilter
            label="规则"
            filterKey="ruleId"
            options={[{ label: '全部规则', value: '' }, ...rulesOptions]}
          />
        ),
        dataIndex: 'ruleName',
        key: 'ruleName',
        render: (_: ReactNode, log) => (
          <div>
            <div style={{ fontWeight: 600 }}>{log.ruleName}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
              {log.ruleId ? `规则 ID: ${log.ruleId}` : '未绑定规则 ID'}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
              {log.bindingId ? `绑定 #${log.bindingId}` : '未绑定执行'}
            </div>
          </div>
        )
      },
      {
        title: (
          <ColumnFilter
            label="触发"
            filterKey="trigger"
            options={triggerOptions}
            overlayWidth={180}
          />
        ),
        dataIndex: 'trigger',
        key: 'trigger',
        sorter: (a, b) => a.trigger.localeCompare(b.trigger),
        sortOrder: sorterState.columnKey === 'trigger' ? sorterState.order : undefined,
        render: (value: RuleExecutionLog['trigger']) =>
          triggerLabels[value] ?? value
      },
      {
        title: (
          <ColumnFilter
            label="状态"
            filterKey="status"
            options={statusOptions}
            overlayWidth={180}
          />
        ),
        dataIndex: 'status',
        key: 'status',
        sorter: (a, b) => a.status.localeCompare(b.status),
        sortOrder: sorterState.columnKey === 'status' ? sorterState.order : undefined,
        render: (value: ExecutionStatus) => (
          <span className={statusBadgeClass[value]}>
            {value === 'success' ? '成功' : value === 'failed' ? '失败' : '跳过'}
          </span>
        )
      },
      {
        title: '调度时间',
        dataIndex: 'actualStartTime',
        key: 'timing',
        sorter: (a, b) => {
          const timeA = a.actualStartTime ? new Date(a.actualStartTime).getTime() : 0
          const timeB = b.actualStartTime ? new Date(b.actualStartTime).getTime() : 0
          return timeA - timeB
        },
        sortOrder: sorterState.columnKey === 'timing' ? sorterState.order : undefined,
        render: (_: ReactNode, log) => (
          <div>
            <div>计划：{formatDateTime(log.scheduledRunTime)}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
              实际：{formatDateTime(log.actualStartTime)}
            </div>
          </div>
        )
      },
      {
        title: '实际耗时',
        dataIndex: 'durationMs',
        key: 'duration',
        sorter: (a, b) => (a.durationMs ?? Infinity) - (b.durationMs ?? Infinity),
        sortOrder: sorterState.columnKey === 'duration' ? sorterState.order : undefined,
        render: (value: number | undefined, log) => (
          <div>
            <div>
              {value !== undefined ? `${(value / 1000).toFixed(2)} 秒` : '—'}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
              结束：{formatDateTime(log.completedAt)}
            </div>
          </div>
        )
      },
      {
        title: '动作',
        dataIndex: 'actions',
        key: 'actions',
        render: (_: ReactNode, log) =>
          log.actions?.length ? (
            <Space direction="vertical" size={4}>
              {log.actions.map(action => (
                <Tag key={action.type} color="blue">
                  {action.type}
                </Tag>
              ))}
            </Space>
          ) : (
            '—'
          )
      },
      {
        title: '操作',
        dataIndex: 'operations',
        key: 'operations',
        render: (_: ReactNode, log) => (
          <Button
            type="primary"
            ghost
            size="small"
            onClick={event => {
              event.stopPropagation()
              onRetry(log)
            }}
            loading={retryLoading}
          >
            重新执行
          </Button>
        )
      }
    ],
    [rulesOptions, sorterState, triggerOptions, statusOptions, retryLoading, onRetry]
  )

  const handleTableChange: TableProps<RuleExecutionLog & { key: string }>['onChange'] = (
    nextPagination,
    _filters,
    sorter
  ) => {
    setPagination({
      current: nextPagination.current ?? 1,
      pageSize: nextPagination.pageSize ?? 10
    })

    const sorterResult = Array.isArray(sorter) ? sorter[0] : sorter
    const columnKey = sorterResult?.columnKey ?? sorterResult?.field
    setSorterState({
      columnKey: Array.isArray(columnKey) ? columnKey[0] : columnKey,
      order: sorterResult?.order ?? undefined
    })
  }

  return (
    <div className="table-wrapper">
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '0.75rem'
        }}
      >
        <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
          共 {tableData.length} 条记录
        </div>
        <Button
          icon={<ReloadOutlined />}
          onClick={onRefresh}
          loading={loading}
          type="default"
          size="small"
        >
          刷新
        </Button>
      </div>
      <Table
        columns={columns}
        dataSource={tableData}
        loading={loading}
        pagination={{
          ...pagination,
          total: tableData.length,
          showSizeChanger: true,
          pageSizeOptions: [10, 20, 50],
          showTotal: total => `共 ${total} 条`
        }}
        onChange={handleTableChange}
        onRow={record => ({
          onClick: () => onRowSelect(record),
          style: { cursor: 'pointer' }
        })}
        locale={{
          emptyText: loading ? '加载中...' : '暂无执行记录。'
        }}
        rowKey="id"
      />
    </div>
  )
}

const ExecutionLogsPage = () => {
  const queryClient = useQueryClient()
  const [selectedLog, setSelectedLog] = useState<RuleExecutionLog | null>(null)
  const [filters, setFilters] = useState<FilterState>({
    ruleId: '',
    status: 'all',
    trigger: 'all'
  })

  const rulesQuery = useQuery({
    queryKey: ['rule-definitions', { status: 'all' satisfies RuleStatus | 'all', scope: 'logs' }],
    queryFn: () => fetchRuleDefinitions({ status: 'all' })
  })

  const logsQuery = useQuery({
    queryKey: ['rule-executions', filters],
    queryFn: () =>
      fetchExecutionLogs({
        ruleId: filters.ruleId || undefined,
        status: filters.status,
        trigger: filters.trigger
      }),
    refetchInterval: 30_000
  })

  const executeMutation = useMutation({
    mutationFn: executeRuleManually,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rule-executions'] })
    }
  })

  const logItems = logsQuery.data?.items ?? []

  const rulesOptions = useMemo(
    () =>
      (rulesQuery.data?.items ?? []).map(rule => ({
        label: rule.name,
        value: rule.id
      })),
    [rulesQuery.data?.items]
  )

  return (
    <FiltersContext.Provider value={{ filters, setFilters }}>
      <div className="page">
        <section className="card">
          <div className="card__header">
            <div>
              <div className="card__title">执行日志</div>
              <div className="card__subtitle">
                追踪 APScheduler 调度执行的结果，支持失败溯源与动作查看。
              </div>
            </div>
          </div>

          {logsQuery.isError ? (
            <div className="empty-state">
              加载执行日志失败，
              {logsQuery.error instanceof Error ? logsQuery.error.message : '请稍后重试'}
            </div>
          ) : (
            <ExecutionLogsTable
              data={logItems}
              rulesOptions={rulesOptions}
              loading={logsQuery.isFetching}
              onRefresh={() => logsQuery.refetch()}
              onRetry={log =>
                executeMutation.mutate({
                  bindingId: log.bindingId,
                  ruleId: log.ruleId,
                  trigger: 'manual'
                })
              }
              retryLoading={executeMutation.isPending}
              onRowSelect={setSelectedLog}
            />
          )}
        </section>

        {selectedLog && (
          <section className="card">
            <div className="card__header">
              <div>
                <div className="card__title">
                  执行详情 · {selectedLog.ruleName} ·{' '}
                  {formatDateTime(selectedLog.actualStartTime)}
                </div>
                <div className="card__subtitle">
                  {selectedLog.bindingId ? `绑定 ID: ${selectedLog.bindingId}` : '未绑定上下文'}
                </div>
              </div>
              <button className="button button--ghost" onClick={() => setSelectedLog(null)}>
                关闭
              </button>
            </div>

            <div style={{ display: 'grid', gap: '1.5rem' }}>
              <div>
                <h4 style={{ marginBottom: '0.5rem' }}>状态与延迟</h4>
                <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>
                  <span className={statusBadgeClass[selectedLog.status]}>
                    {selectedLog.status === 'success'
                      ? '成功'
                      : selectedLog.status === 'failed'
                        ? '失败'
                        : '跳过'}
                  </span>
                  <span>
                    触发：{triggerLabels[selectedLog.trigger] ?? selectedLog.trigger}
                  </span>
                  <span>
                    耗时：
                    {selectedLog.durationMs !== undefined
                      ? `${selectedLog.durationMs}ms`
                      : '—'}
                  </span>
                </div>
              </div>

              {selectedLog.reasonCodes && selectedLog.reasonCodes.length > 0 ? (
                <div>
                  <h4 style={{ marginBottom: '0.5rem' }}>原因代码</h4>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    {selectedLog.reasonCodes.map(code => (
                      <span key={code} className="chip chip--muted">
                        {code}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}

              {selectedLog.actions?.length ? (
                <div>
                  <h4 style={{ marginBottom: '0.5rem' }}>动作</h4>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    {selectedLog.actions.map(action => (
                      <span key={action.type} className="chip chip--muted">
                        {action.type}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}

              {selectedLog.metrics && Object.keys(selectedLog.metrics).length > 0 ? (
                <div>
                  <h4 style={{ marginBottom: '0.5rem' }}>指标</h4>
                  <pre
                    style={{
                      margin: 0,
                      padding: '1rem',
                      background: 'rgba(15, 23, 42, 0.05)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: '0.85rem',
                      maxHeight: '300px',
                      overflow: 'auto'
                    }}
                  >
                    {JSON.stringify(selectedLog.metrics, null, 2)}
                  </pre>
                </div>
              ) : null}

              {selectedLog.errorMessage ? (
                <div>
                  <h4 style={{ marginBottom: '0.5rem', color: 'var(--color-danger)' }}>错误信息</h4>
                  <pre
                    style={{
                      margin: 0,
                      padding: '1rem',
                      background: 'rgba(239, 68, 68, 0.08)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: '0.85rem',
                      color: 'var(--color-danger)',
                      whiteSpace: 'pre-wrap'
                    }}
                  >
                    {selectedLog.errorMessage}
                  </pre>
                </div>
              ) : null}

              {selectedLog.contextSnapshot &&
              Object.keys(selectedLog.contextSnapshot).length > 0 ? (
                <div>
                  <h4 style={{ marginBottom: '0.5rem' }}>上下文快照</h4>
                  <pre
                    style={{
                      margin: 0,
                      padding: '1rem',
                      background: 'rgba(15, 23, 42, 0.05)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: '0.85rem',
                      maxHeight: '300px',
                      overflow: 'auto'
                    }}
                  >
                    {JSON.stringify(selectedLog.contextSnapshot, null, 2)}
                  </pre>
                </div>
              ) : null}
            </div>
          </section>
        )}
      </div>
    </FiltersContext.Provider>
  )
}

export default ExecutionLogsPage
