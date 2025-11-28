import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { executeRuleManually, fetchBindingExecutions } from '../../api/ruleEngine'
import type { RuleBinding, RuleExecutionLog, ParametersSchema } from '../../types/rule-engine'
import SmartParameterForm from './SmartParameterForm'
import { formatDateTime } from '../../lib/datetime'

interface RuleBindingTestPanelProps {
  binding: RuleBinding
  parametersSchema?: ParametersSchema
}

const RuleBindingTestPanel = ({ binding, parametersSchema }: RuleBindingTestPanelProps) => {
  const [parameters, setParameters] = useState<Record<string, any>>({})
  const [selectedExecutionId, setSelectedExecutionId] = useState<string | null>(null)
  const [showParamsDialog, setShowParamsDialog] = useState(false)

  // Debug logging
  console.log('[RuleBindingTestPanel] parametersSchema:', parametersSchema)
  console.log('[RuleBindingTestPanel] parametersSchema keys:', parametersSchema ? Object.keys(parametersSchema) : 'undefined')

  // Fetch execution history
  const {
    data: executionsData,
    isLoading: isLoadingExecutions,
    refetch: refetchExecutions
  } = useQuery({
    queryKey: ['binding-executions', binding.id],
    queryFn: () => fetchBindingExecutions(binding.id, 20),
    refetchInterval: 5000, // Auto-refresh every 5 seconds
  })

  // Execute rule mutation
  const { mutate: runRule, isPending } = useMutation({
    mutationFn: (params: Record<string, any>) => executeRuleManually({
      bindingId: binding.id,
      trigger: 'manual',
      params: params,
    }),
    onSuccess: () => {
      // Close dialog and refresh execution history after running
      setShowParamsDialog(false)
      setTimeout(() => {
        refetchExecutions()
      }, 1000)
    }
  })

  const handleRunRuleClick = () => {
    // Show parameters dialog
    setShowParamsDialog(true)
  }

  const handleConfirmRun = () => {
    runRule(parameters)
  }

  const executions = executionsData?.executions ?? []
  const selectedExecution = executions.find(e => e.id === selectedExecutionId)

  return (
    <div className="card" style={{ marginTop: '1rem' }}>
      <div className="card__header">
        <div>
          <div className="card__title">规则执行</div>
          <div className="card__subtitle">
            运行规则并查看执行��史
          </div>
        </div>
      </div>

      <div style={{ padding: '1rem' }}>
        {/* Run Button */}
        <div style={{ marginBottom: '1.5rem' }}>
          <button
            className="button button--primary"
            onClick={handleRunRuleClick}
            disabled={isPending}
            style={{ minWidth: '120px' }}
          >
            {isPending ? '运行中...' : '运行规则'}
          </button>
          <small style={{ marginLeft: '1rem', color: 'var(--color-text-muted)' }}>
            执行将在后台运行，结果将在下方历史记录中显示
          </small>
        </div>

        {/* Execution History */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h4 style={{ fontSize: '1rem', fontWeight: 600 }}>
              执行历史 {executionsData && `(${executionsData.total})`}
            </h4>
            <button
              className="button button--ghost button--small"
              onClick={() => refetchExecutions()}
              disabled={isLoadingExecutions}
            >
              {isLoadingExecutions ? '刷新中...' : '刷新'}
            </button>
          </div>

          {isLoadingExecutions ? (
            <div className="empty-state">加载中...</div>
          ) : executions.length === 0 ? (
            <div className="empty-state">暂无执行记录</div>
          ) : (
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>执行时间</th>
                    <th>触发方式</th>
                    <th>状态</th>
                    <th>耗时</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {executions.map(execution => (
                    <tr key={execution.id}>
                      <td>{formatDateTime(execution.actualStartTime)}</td>
                      <td>
                        {execution.trigger === 'manual' ? '手动' :
                         execution.trigger === 'scheduler' ? '调度' :
                         execution.trigger === 'test' ? '测试' : execution.trigger}
                      </td>
                      <td>
                        <span className={
                          execution.status === 'success' ? 'badge badge--success' :
                          execution.status === 'failed' ? 'badge badge--danger' :
                          'badge badge--disabled'
                        }>
                          {execution.status === 'success' ? '成功' :
                           execution.status === 'failed' ? '失败' : '跳过'}
                        </span>
                      </td>
                      <td>
                        {execution.durationMs !== undefined ? `${execution.durationMs}ms` : '—'}
                      </td>
                      <td>
                        <button
                          className="button button--ghost button--small"
                          onClick={() => setSelectedExecutionId(
                            selectedExecutionId === execution.id ? null : execution.id
                          )}
                        >
                          {selectedExecutionId === execution.id ? '关闭' : '查看'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Execution Details */}
          {selectedExecution && (
            <ExecutionDetails execution={selectedExecution} onClose={() => setSelectedExecutionId(null)} />
          )}
        </div>
      </div>

      {/* Parameters Dialog */}
      {showParamsDialog && (
        <ParametersDialog
          parametersSchema={parametersSchema}
          parameters={parameters}
          onChange={setParameters}
          onConfirm={handleConfirmRun}
          onCancel={() => setShowParamsDialog(false)}
          isPending={isPending}
        />
      )}
    </div>
  )
}

interface ParametersDialogProps {
  parametersSchema?: ParametersSchema
  parameters: Record<string, any>
  onChange: (params: Record<string, any>) => void
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}

const ParametersDialog = ({
  parametersSchema,
  parameters,
  onChange,
  onConfirm,
  onCancel,
  isPending
}: ParametersDialogProps) => {
  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(0, 0, 0, 0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
    }}>
      <div style={{
        backgroundColor: '#ffffff',
        borderRadius: '8px',
        padding: '1.5rem',
        maxWidth: '600px',
        width: '90%',
        maxHeight: '80vh',
        overflowY: 'auto',
        boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
      }}>
        <h3 style={{ marginBottom: '1rem', fontSize: '1.25rem', fontWeight: 600 }}>
          配置执行参数
        </h3>

        {parametersSchema && Object.keys(parametersSchema).length > 0 ? (
          <div style={{ marginBottom: '1.5rem' }}>
            <SmartParameterForm
              schema={parametersSchema}
              values={parameters}
              onChange={onChange}
            />
          </div>
        ) : (
          <p style={{ marginBottom: '1.5rem', color: 'var(--color-text-muted)' }}>
            该规则没有可配置的参数
          </p>
        )}

        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
          <button
            className="button button--ghost"
            onClick={onCancel}
            disabled={isPending}
          >
            取消
          </button>
          <button
            className="button button--primary"
            onClick={onConfirm}
            disabled={isPending}
          >
            {isPending ? '运行中...' : '确认运行'}
          </button>
        </div>
      </div>
    </div>
  )
}

interface ExecutionDetailsProps {
  execution: RuleExecutionLog
  onClose: () => void
}

const ExecutionDetails = ({ execution, onClose }: ExecutionDetailsProps) => {
  const { actions = [], reasonCodes = [], metrics = {}, executionLogs = [] } = execution

  const getDecisionClass = () => {
    if (actions.some((a: any) => a.action === 'pause_ad' && a.severity === 'high')) {
      return 'critical'
    }
    if (actions.some((a: any) => a.action === 'pause_ad')) {
      return 'warning'
    }
    return 'ok'
  }

  const getDecisionText = () => {
    if (actions.some((a: any) => a.action === 'pause_ad')) {
      return '🔴 建议暂停广告'
    }
    if (actions.some((a: any) => a.type === 'informational')) {
      return '✅ 广告表现正常'
    }
    return '⚠️ 无明确建议'
  }

  const decisionClass = getDecisionClass()

  return (
    <div style={{
      marginTop: '1rem',
      padding: '1.5rem',
      border: '1px solid var(--color-border)',
      borderRadius: '8px',
      backgroundColor: 'var(--color-background)'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h5 style={{ fontSize: '1rem', fontWeight: 600 }}>执行详情</h5>
        <button onClick={onClose} className="button button--ghost button--small">关闭</button>
      </div>

      {/* Error Message */}
      {execution.errorMessage && (
        <div style={{
          padding: '1rem',
          marginBottom: '1rem',
          backgroundColor: 'var(--color-danger-background)',
          borderLeft: '4px solid var(--color-danger)',
          borderRadius: '4px'
        }}>
          <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>执行错误</div>
          <div style={{ fontSize: '0.875rem' }}>{execution.errorMessage}</div>
        </div>
      )}

      {/* Decision Summary */}
      {execution.status === 'success' && (
        <div style={{
          padding: '1rem',
          borderRadius: '6px',
          marginBottom: '1.5rem',
          backgroundColor: decisionClass === 'critical' ? 'var(--color-danger-background)' :
            decisionClass === 'warning' ? 'var(--color-warning-background)' :
              'var(--color-success-background)',
          borderLeft: `4px solid ${decisionClass === 'critical' ? 'var(--color-danger)' :
            decisionClass === 'warning' ? 'var(--color-warning)' :
              'var(--color-success)'}`
        }}>
          <div style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
            {getDecisionText()}
          </div>
          {reasonCodes.length > 0 && (
            <div style={{ marginTop: '0.75rem' }}>
              {reasonCodes.map((reason, idx) => (
                <div key={idx} style={{ fontSize: '0.875rem', marginTop: '0.25rem' }}>
                  📋 {reason}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      {actions.length > 0 && (
        <div style={{ marginBottom: '1.5rem' }}>
          <h6 style={{ marginBottom: '0.75rem', fontSize: '0.95rem', fontWeight: 600 }}>
            推荐操作
          </h6>
          {actions.map((action: any, idx) => (
            <div key={idx} style={{
              padding: '0.75rem',
              marginBottom: '0.5rem',
              borderRadius: '4px',
              border: '1px solid var(--color-border)',
              backgroundColor: 'var(--color-background-muted)'
            }}>
              <div style={{ fontWeight: 500, marginBottom: '0.25rem' }}>
                {action.action === 'pause_ad' ? '暂停广告' :
                  action.action === 'no_change' ? '保持现状' :
                    action.action}
              </div>
              {action.reason && (
                <div style={{ fontSize: '0.875rem', color: 'var(--color-text-muted)' }}>
                  原因: {action.reason}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Metrics */}
      {Object.keys(metrics).length > 0 && (
        <div style={{ marginBottom: '1.5rem' }}>
          <h6 style={{ marginBottom: '0.75rem', fontSize: '0.95rem', fontWeight: 600 }}>
            评估指标
          </h6>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
            gap: '0.75rem'
          }}>
            {Object.entries(metrics).map(([key, value]) => (
              <div key={key} style={{
                padding: '0.75rem',
                borderRadius: '4px',
                border: '1px solid var(--color-border)',
                backgroundColor: 'var(--color-background-muted)'
              }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>
                  {key}
                </div>
                <div style={{ fontSize: '1rem', fontWeight: 600 }}>
                  {typeof value === 'number' ? value.toLocaleString() : String(value)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Execution Logs */}
      {executionLogs.length > 0 && (
        <div>
          <h6 style={{ marginBottom: '0.75rem', fontSize: '0.95rem', fontWeight: 600 }}>
            执行日志 ({executionLogs.length}条)
          </h6>
          <div style={{
            padding: '1rem',
            borderRadius: '4px',
            border: '1px solid var(--color-border)',
            backgroundColor: 'var(--color-background-muted)',
            fontFamily: 'monospace',
            fontSize: '0.875rem',
            maxHeight: '400px',
            overflowY: 'auto'
          }}>
            {executionLogs.map((log, idx) => {
              // Parse log level from log string (e.g., "[INFO] message" or "[PRINT] message")
              const match = log.match(/^\[(\w+)\]\s+(.*)$/)
              const level = match ? match[1] : 'INFO'
              const message = match ? match[2] : log

              // Color coding by log level
              const levelColor =
                level === 'WARNING' || level === 'WARN' ? 'var(--color-warning)' :
                level === 'ERROR' ? 'var(--color-danger)' :
                level === 'DEBUG' ? 'var(--color-text-muted)' :
                level === 'PRINT' ? 'var(--color-info)' :
                'var(--color-text)'

              return (
                <div key={idx} style={{
                  marginBottom: '0.5rem',
                  lineHeight: '1.5',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word'
                }}>
                  <span style={{ color: levelColor, fontWeight: 600 }}>
                    [{level}]
                  </span>
                  <span style={{ marginLeft: '0.5rem' }}>
                    {message}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

export default RuleBindingTestPanel
