import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Modal, Spinner } from '@/components/ui'
import { fetchRuleBindings, deleteRuleBinding, updateRuleBinding, fetchBindingExecutions } from '../api/ruleEngine'
import type { RuleBinding, RuleExecutionLog } from '../types/rule-engine'
import { formatDateTime } from '../lib/datetime'

interface RuleBindingsListProps {
  ruleName?: string
  entityId?: string
  showRuleName?: boolean
  showEntityId?: boolean
  onBindingClick?: (binding: RuleBinding) => void
  allowDelete?: boolean
  allowToggle?: boolean
}

const entityTypeLabel: Record<string, string> = {
  account: '广告账号',
  campaign: '广告系列',
  adset: '广告组',
  ad: '广告'
}

const statusBadge: Record<string, { class: string; label: string }> = {
  success: { class: 'badge--success', label: '成功' },
  failed: { class: 'badge--danger', label: '失败' },
  running: { class: 'badge--info', label: '运行中' },
  pending: { class: 'badge--warning', label: '待执行' }
}

const ExecutionLogsModal = ({ bindingId, ruleName, open, onClose }: { 
  bindingId: string; ruleName: string; open: boolean; onClose: () => void 
}) => {
  const { data, isLoading } = useQuery({
    queryKey: ['binding-executions', bindingId],
    queryFn: () => fetchBindingExecutions(bindingId, 20),
    enabled: open && !!bindingId,
    staleTime: 10_000
  })

  const executions = data?.executions ?? []

  return (
    <Modal title={`执行日志 - ${ruleName}`} open={open} onClose={onClose} width={900}>
      {isLoading ? (
        <div className="flex items-center justify-center gap-2 py-8">
          <Spinner size="sm" />
          <span className="text-muted-foreground">加载执行日志...</span>
        </div>
      ) : executions.length === 0 ? (
        <div className="py-8 text-center text-muted-foreground">暂无执行记录</div>
      ) : (
        <div className="table-wrapper max-h-[500px] overflow-auto">
          <table className="table">
            <thead>
              <tr>
                <th>执行时间</th>
                <th>触发方式</th>
                <th>状态</th>
                <th>决策</th>
                <th>耗时</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>
              {executions.map((log: RuleExecutionLog) => {
                const badge = statusBadge[log.status] || { class: 'badge--muted', label: log.status }
                return (
                  <tr key={log.id}>
                    <td className="whitespace-nowrap text-sm">{formatDateTime(log.actualStartTime)}</td>
                    <td>
                      <span className="chip chip--muted text-xs">
                        {log.trigger === 'manual' ? '手动' : log.trigger === 'scheduler' ? '定时' : log.trigger}
                      </span>
                    </td>
                    <td><span className={`badge ${badge.class}`}>{badge.label}</span></td>
                    <td>
                      {log.actions?.length ? (
                        <div className="flex flex-wrap gap-1">
                          {log.actions.map((action, i) => (
                            <span key={i} className="chip chip--primary text-xs">
                              {action.type}{action.message ? `: ${action.message}` : ''}
                            </span>
                          ))}
                        </div>
                      ) : <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="text-sm text-muted-foreground">
                      {log.durationMs != null ? `${log.durationMs}ms` : '—'}
                    </td>
                    <td className="text-sm max-w-[300px]">
                      {log.reasonCodes?.length ? (
                        <div className={`max-h-16 overflow-auto ${log.status === 'failed' ? 'text-destructive' : ''}`}>
                          {log.reasonCodes.map((r, i) => <div key={i}>{r}</div>)}
                        </div>
                      ) : log.errorMessage ? (
                        <span className="text-destructive">{log.errorMessage}</span>
                      ) : <span className="text-muted-foreground">—</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  )
}

const RuleBindingsList = ({
  ruleName, entityId, showRuleName = true, showEntityId = true,
  onBindingClick, allowDelete = false, allowToggle = true
}: RuleBindingsListProps) => {
  const queryClient = useQueryClient()
  const [selectedBinding, setSelectedBinding] = useState<RuleBinding | null>(null)

  const { data: bindingsResponse, isLoading, isError, error } = useQuery({
    queryKey: ['rule-bindings', { ruleName, entityId }],
    queryFn: () => fetchRuleBindings({ ruleName, entityId }),
    enabled: !!(ruleName || entityId),
    staleTime: 30_000
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => updateRuleBinding(id, { active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['rule-bindings'] })
  })

  const deleteMutation = useMutation({
    mutationFn: deleteRuleBinding,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['rule-bindings'] })
  })

  const bindings = bindingsResponse?.items ?? []

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-8">
        <Spinner size="sm" />
        <span className="text-muted-foreground">加载绑定列表...</span>
      </div>
    )
  }

  if (isError) {
    return <div className="p-4 text-destructive">加载失败: {error instanceof Error ? error.message : '未知错误'}</div>
  }

  if (bindings.length === 0) {
    return <div className="py-8 text-center text-muted-foreground">暂无绑定记录</div>
  }

  return (
    <>
      <div className="table-wrapper">
        <table className="table">
          <thead>
            <tr>
              {showRuleName && <th>规则</th>}
              {showEntityId && <th>实体</th>}
              <th>类型</th>
              <th>广告账号</th>
              <th>状态</th>
              <th>更新时间</th>
              <th className="w-44" />
            </tr>
          </thead>
          <tbody>
            {bindings.map(binding => (
              <tr 
                key={binding.id}
                onClick={() => onBindingClick?.(binding)}
                className={onBindingClick ? 'cursor-pointer hover:bg-muted/50' : ''}
              >
                {showRuleName && <td className="font-semibold">{binding.ruleName}</td>}
                {showEntityId && (
                  <td>
                    <code className="bg-muted px-1.5 py-0.5 rounded text-sm">{binding.entityId}</code>
                  </td>
                )}
                <td>{entityTypeLabel[binding.entityType] || binding.entityType}</td>
                <td>{binding.adAccountId || '—'}</td>
                <td>
                  <span className={binding.active ? 'badge badge--success' : 'badge badge--disabled'}>
                    {binding.active ? '启用' : '停用'}
                  </span>
                </td>
                <td className="text-sm text-muted-foreground">{formatDateTime(binding.updated_at)}</td>
                <td onClick={e => e.stopPropagation()}>
                  <div className="flex gap-2 justify-end">
                    <button className="button button--secondary px-2 py-1 text-xs" onClick={() => setSelectedBinding(binding)}>
                      执行日志
                    </button>
                    {allowToggle && (
                      <button
                        className="button button--ghost px-2 py-1 text-xs"
                        onClick={() => toggleMutation.mutate({ id: binding.id, active: !binding.active })}
                        disabled={toggleMutation.isPending}
                      >
                        {binding.active ? '停用' : '启用'}
                      </button>
                    )}
                    {allowDelete && (
                      <button
                        className="button button--ghost px-2 py-1 text-xs text-destructive"
                        onClick={() => confirm('确定删除此绑定？') && deleteMutation.mutate(binding.id)}
                        disabled={deleteMutation.isPending}
                      >
                        删除
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selectedBinding && (
        <ExecutionLogsModal
          bindingId={selectedBinding.id}
          ruleName={selectedBinding.ruleName}
          open={!!selectedBinding}
          onClose={() => setSelectedBinding(null)}
        />
      )}
    </>
  )
}

export default RuleBindingsList
