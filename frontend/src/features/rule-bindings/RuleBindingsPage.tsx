import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createRuleBinding,
  deleteRuleBinding,
  fetchRuleBindings,
  fetchRuleDefinition,
  fetchRuleDefinitions,
  updateRuleBinding
} from '../../api/ruleEngine'
import type { RuleBindingPayload } from '../../api/ruleEngine'
import type {
  RuleBinding,
  RuleEntityType,
  RuleStatus
} from '../../types/rule-engine'
import { formatDateTime } from '../../lib/datetime'
import RuleBindingForm, { type RuleBindingFormValues } from './RuleBindingForm'
import RuleBindingTestPanel from './RuleBindingTestPanel'
import { mergeBindingMetadata } from './utils'

const entityTypeLabel: Record<RuleEntityType, string> = {
  account: '广告账号',
  campaign: '广告系列',
  adset: '广告组',
  ad: '广告'
}

const sourceLabels: Record<string, string> = {
  manual: '手动',
  auto: '自动任务',
  naming_parser: '命名解析'
}

const RuleBindingsPage = () => {
  const queryClient = useQueryClient()

  const [filters, setFilters] = useState<{
    entityType: RuleEntityType | 'all'
    activeOnly: boolean
    entityId: string
    ruleId: string
  }>({
    entityType: 'all',
    activeOnly: true,
    entityId: '',
    ruleId: ''
  })

  const [isCreating, setIsCreating] = useState(false)
  const [editingBinding, setEditingBinding] = useState<RuleBinding | null>(null)
  const [selectedBinding, setSelectedBinding] = useState<RuleBinding | null>(null)

  const rulesQuery = useQuery({
    queryKey: ['rule-definitions', { status: 'published' satisfies RuleStatus, scope: 'bindings' }],
    queryFn: () => fetchRuleDefinitions({ status: 'published' })
  })

  const bindingsQuery = useQuery({
    queryKey: ['rule-bindings', filters],
    queryFn: () =>
      fetchRuleBindings({
        ruleId: filters.ruleId || undefined,
        entityId: filters.entityId || undefined,
        entityType: filters.entityType,
        activeOnly: filters.activeOnly
      }),
    staleTime: 15_000
  })

  // Query for selected binding's rule definition (to get parameters_schema)
  const selectedRuleQuery = useQuery({
    queryKey: ['rule-definition', selectedBinding?.ruleId],
    queryFn: () => selectedBinding ? fetchRuleDefinition(selectedBinding.ruleId) : Promise.resolve(null),
    enabled: !!selectedBinding,
    staleTime: 0,  // Always treat data as stale
    refetchOnMount: 'always',  // Always refetch when component mounts
  })

  const toPayload = (values: RuleBindingFormValues): RuleBindingPayload => {
    const { ruleId, entityType, entityId, accountId, metadata, notes } = values
    const mergedMetadata = mergeBindingMetadata(metadata, accountId, notes)
    return {
      ruleId,
      entityType,
      entityId,
      metadata: mergedMetadata,
      source: 'manual'
    }
  }

  const toUpdatePayload = (
    values: Partial<RuleBindingFormValues>
  ): Partial<RuleBindingPayload & { active: boolean }> => {
    const payload: Partial<RuleBindingPayload & { active: boolean }> = {}
    if (
      values.metadata !== undefined ||
      values.accountId !== undefined ||
      values.notes !== undefined
    ) {
      payload.metadata = mergeBindingMetadata(values.metadata, values.accountId, values.notes)
    }
    if (values.active !== undefined) {
      payload.active = values.active
    }
    return payload
  }

  const createMutation = useMutation({
    mutationFn: createRuleBinding,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rule-bindings'] })
      setIsCreating(false)
    }
  })

  const updateMutation = useMutation({
    mutationFn: ({
      bindingId,
      values
    }: {
      bindingId: string
      values: Partial<RuleBindingPayload & { active: boolean }>
    }) => updateRuleBinding(bindingId, values),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rule-bindings'] })
      setEditingBinding(null)
    }
  })

  const deleteMutation = useMutation({
    mutationFn: deleteRuleBinding,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rule-bindings'] })
    }
  })

  const handleCreate = (values: RuleBindingFormValues) => {
    createMutation.mutate(toPayload(values))
  }

  const handleUpdate = (values: RuleBindingFormValues) => {
    if (!editingBinding) return
    updateMutation.mutate({ bindingId: editingBinding.id, values: toUpdatePayload(values) })
  }

  const publishedRules = rulesQuery.data?.items ?? []

  const isBusy =
    bindingsQuery.isFetching || createMutation.isPending || updateMutation.isPending

  const filteredBindings = useMemo(() => {
    const items = bindingsQuery.data?.items ?? []
    if (!filters.entityId) return items

    return items.filter(binding =>
      binding.entityId.toLowerCase().includes(filters.entityId.toLowerCase())
    )
  }, [bindingsQuery.data?.items, filters.entityId])

  return (
    <div className="page">
      <section className="card">
        <div className="card__header">
          <div>
            <div className="card__title">规则绑定</div>
            <div className="card__subtitle">
              管理规则与广告实体的绑定记录，支持自动解绑监控。
            </div>
          </div>
          <div className="toolbar__group">
            <button
              className="button button--primary"
              onClick={() => {
                setEditingBinding(null)
                setIsCreating(true)
              }}
            >
              新建绑定
            </button>
          </div>
        </div>

        <div className="toolbar">
          <div className="toolbar__group">
            <select
              className="select"
              value={filters.ruleId}
              onChange={event =>
                setFilters(current => ({ ...current, ruleId: event.target.value }))
              }
            >
              <option value="">全部规则</option>
              {rulesQuery.data?.items?.map(rule => (
                <option key={rule.id} value={rule.id}>
                  {rule.name}
                </option>
              ))}
            </select>
          </div>

          <div className="toolbar__group">
            <select
              className="select"
              value={filters.entityType}
              onChange={event =>
                setFilters(current => ({
                  ...current,
                  entityType: event.target.value as RuleEntityType | 'all'
                }))
              }
            >
              <option value="all">所有实体类型</option>
              <option value="account">账号</option>
              <option value="campaign">广告系列</option>
              <option value="adset">广告组</option>
              <option value="ad">广告</option>
            </select>
          </div>

          <div className="toolbar__group">
            <input
              className="input"
              placeholder="按实体 ID 模糊搜索"
              value={filters.entityId}
              onChange={event =>
                setFilters(current => ({ ...current, entityId: event.target.value }))
              }
              style={{ minWidth: '200px' }}
            />
          </div>

          <label className="form-label checkbox-label" style={{ marginBottom: 0 }}>
            <input
              type="checkbox"
              checked={filters.activeOnly}
              onChange={event =>
                setFilters(current => ({ ...current, activeOnly: event.target.checked }))
              }
            />
            仅显示启用绑定
          </label>
        </div>

        {bindingsQuery.isError ? (
          <div className="empty-state">
            加载绑定失败，
            {bindingsQuery.error instanceof Error ? bindingsQuery.error.message : '请稍后重试'}
          </div>
        ) : bindingsQuery.isLoading ? (
          <div className="empty-state">加载绑定中...</div>
        ) : filteredBindings.length === 0 ? (
          <div className="empty-state">暂无绑定记录，创建后将显示在此。</div>
        ) : (
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>规则</th>
                  <th>实体类型</th>
                  <th>实体 ID</th>
                  <th>账号</th>
                  <th>状态</th>
                  <th>备注</th>
                  <th>更新时间</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filteredBindings.map(binding => (
                  <tr key={binding.id}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{binding.ruleName}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                        来源：{sourceLabels[binding.source] ?? binding.source}
                      </div>
                    </td>
                    <td>{entityTypeLabel[binding.entityType]}</td>
                    <td>
                      <div>{binding.entityId}</div>
                      {binding.metadata && Object.keys(binding.metadata).length > 0 && (
                        <div
                          style={{
                            fontSize: '0.75rem',
                            color: 'var(--color-text-muted)'
                          }}
                        >
                          元数据: {Object.keys(binding.metadata).join(', ')}
                        </div>
                      )}
                    </td>
                    <td>{binding.accountId ?? '—'}</td>
                    <td>
                      <span className={binding.active ? 'badge badge--success' : 'badge badge--disabled'}>
                        {binding.active ? '启用' : '停用'}
                      </span>
                    </td>
                    <td style={{ maxWidth: '220px' }}>
                      <div style={{ color: 'var(--color-text-muted)' }}>
                        {binding.notes ?? '—'}
                      </div>
                    </td>
                    <td>
                      <div>{formatDateTime(binding.updated_at)}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
                        创建于 {formatDateTime(binding.created_at)}
                      </div>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                        <button
                          className="button button--primary"
                          onClick={() => setSelectedBinding(binding)}
                        >
                          测试
                        </button>
                        <button
                          className="button button--secondary"
                          onClick={() => {
                            setIsCreating(false)
                            setEditingBinding(binding)
                          }}
                        >
                          编辑
                        </button>
                        <button
                          className="button button--ghost"
                          onClick={() =>
                            updateMutation.mutate({
                              bindingId: binding.id,
                              values: { active: !binding.active }
                            })
                          }
                        >
                          {binding.active ? '停用' : '启用'}
                        </button>
                        <button
                          className="button button--danger"
                          onClick={() => {
                            if (
                              confirm(`确定要删除与 ${binding.entityId} 的绑定吗？操作不可恢复。`)
                            ) {
                              deleteMutation.mutate(binding.id)
                            }
                          }}
                        >
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {isBusy && (
              <div className="table-overlay">
                <div className="empty-state">更新中...</div>
              </div>
            )}
          </div>
        )}
      </section>

      {(isCreating || editingBinding) && (
        <RuleBindingForm
          mode={editingBinding ? 'edit' : 'create'}
          initialValues={editingBinding ?? undefined}
          rules={publishedRules}
          onSubmit={editingBinding ? handleUpdate : handleCreate}
          onCancel={() => {
            setIsCreating(false)
            setEditingBinding(null)
          }}
          isSubmitting={
            createMutation.isPending || updateMutation.isPending || deleteMutation.isPending
          }
        />
      )}

      {selectedBinding && (
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setSelectedBinding(null)}
            style={{
              position: 'absolute',
              top: '1rem',
              right: '1rem',
              zIndex: 10
            }}
            className="button button--ghost"
          >
            ✕ 关闭测试面板
          </button>
          <RuleBindingTestPanel
            binding={selectedBinding}
            parametersSchema={selectedRuleQuery.data?.parameters_schema}
          />
        </div>
      )}
    </div>
  )
}

export default RuleBindingsPage
