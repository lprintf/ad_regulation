import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Dropdown, Breadcrumb } from 'antd'
import {
  cloneRuleDefinition,
  createRuleDefinition,
  fetchRuleDefinitions,
  updateRuleDefinition
} from '../../api/ruleEngine'
import type { CloneRulePayload } from '../../api/ruleEngine'
import type { RuleDefinition, RuleStatus } from '../../types/rule-engine'
import { formatDateTime } from '../../lib/datetime'
import RuleDefinitionForm, { type RuleDefinitionFormValues } from './RuleDefinitionForm'

const statusBadgeClass: Record<RuleStatus, string> = {
  draft: 'badge badge--draft',
  published: 'badge badge--published',
  disabled: 'badge badge--disabled'
}

const RuleDefinitionsPage = () => {
  const queryClient = useQueryClient()
  const [filters, setFilters] = useState<{ search: string; status: RuleStatus | 'all' }>({
    search: '',
    status: 'all'
  })
  const [isCreating, setIsCreating] = useState(false)
  const [editingRule, setEditingRule] = useState<RuleDefinition | null>(null)

  const {
    data: definitions,
    isLoading,
    isFetching,
    isError,
    error
  } = useQuery({
    queryKey: ['rule-definitions', filters],
    queryFn: () => fetchRuleDefinitions(filters),
    staleTime: 30_000
  })

  const createMutation = useMutation({
    mutationFn: createRuleDefinition,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rule-definitions'] })
      setIsCreating(false)
    }
  })

  const updateMutation = useMutation({
    mutationFn: ({ ruleId, values }: { ruleId: string; values: Partial<RuleDefinitionFormValues> }) =>
      updateRuleDefinition(ruleId, values),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rule-definitions'] })
      setEditingRule(null)
    }
  })

  const cloneMutation = useMutation({
    mutationFn: ({ ruleId, payload }: { ruleId: string; payload: CloneRulePayload }) =>
      cloneRuleDefinition(ruleId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rule-definitions'] })
    }
  })

  const handleCreate = (values: RuleDefinitionFormValues) => {
    createMutation.mutate(values)
  }

  const handleUpdate = (values: RuleDefinitionFormValues) => {
    if (!editingRule) return
    updateMutation.mutate({ ruleId: editingRule.id, values })
  }

  const isBusy = isFetching || createMutation.isPending || updateMutation.isPending

  const isEditingOrCreating = isCreating || !!editingRule

  const handleCancelEdit = () => {
    setIsCreating(false)
    setEditingRule(null)
  }

  return (
    <div className="page">
      {/* Breadcrumb navigation - shown when editing or creating */}
      {isEditingOrCreating && (
        <Breadcrumb
          items={[
            {
              title: (
                <a onClick={handleCancelEdit} style={{ cursor: 'pointer' }}>
                  规则定义
                </a>
              )
            },
            {
              title: editingRule ? `编辑规则: ${editingRule.name}` : '创建新规则'
            }
          ]}
          style={{ marginBottom: '1rem' }}
        />
      )}

      {/* Conditional rendering: show list or edit form */}
      {isEditingOrCreating ? (
        <RuleDefinitionForm
          mode={editingRule ? 'edit' : 'create'}
          initialValues={editingRule ?? undefined}
          onSubmit={editingRule ? handleUpdate : handleCreate}
          onCancel={handleCancelEdit}
          isSubmitting={createMutation.isPending || updateMutation.isPending}
        />
      ) : (
        <section className="card">
        <div className="card__header">
          <div>
            <div className="card__title">规则定义</div>
            <div className="card__subtitle">
              统一管理规则脚本、版本与发布状态，支持参数化配置与审计。
            </div>
          </div>
          <div className="toolbar__group">
            <button
              className="button button--primary"
              onClick={() => {
                setEditingRule(null)
                setIsCreating(true)
              }}
            >
              新建规则
            </button>
          </div>
        </div>

        <div className="toolbar">
          <div className="toolbar__group" style={{ flex: 1 }}>
            <label className="visually-hidden" htmlFor="rule-search">
              搜索规则
            </label>
            <input
              id="rule-search"
              className="input"
              placeholder="按名称、描述或标签搜索..."
              value={filters.search}
              onChange={event =>
                setFilters(current => ({ ...current, search: event.target.value }))
              }
            />
          </div>

          <div className="toolbar__group">
            <label className="visually-hidden" htmlFor="rule-status">
              状态筛选
            </label>
            <select
              id="rule-status"
              className="select"
              value={filters.status}
              onChange={event =>
                setFilters(current => ({
                  ...current,
                  status: event.target.value as RuleStatus | 'all'
                }))
              }
            >
              <option value="all">全部状态</option>
              <option value="draft">草稿</option>
              <option value="published">已发布</option>
              <option value="disabled">已禁用</option>
            </select>
          </div>
        </div>

        {isError ? (
          <div className="empty-state">
            <p>加载规则失败：{error instanceof Error ? error.message : '未知错误'}</p>
          </div>
        ) : isLoading ? (
          <div className="empty-state">加载中...</div>
        ) : definitions && definitions.items.length > 0 ? (
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>名称</th>
                  <th>版本</th>
                  <th>状态</th>
                  <th>标签</th>
                  <th>最后更新</th>
                  <th>发布人</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {definitions.items.map(rule => (
                  <tr key={rule.id}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{rule.name}</div>
                      <div style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
                        {rule.description ?? '未填写描述'}
                      </div>
                    </td>
                    <td>v{rule.version}</td>
                    <td>
                      <span className={statusBadgeClass[rule.status]}>
                        {rule.status === 'draft'
                          ? '草稿'
                          : rule.status === 'published'
                            ? '已发布'
                            : '已禁用'}
                      </span>
                    </td>
                    <td>
                      {rule.tags?.length ? (
                        <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                          {rule.tags.map(tag => (
                            <span
                              key={tag}
                              className="chip chip--muted"
                              style={{
                                fontWeight: 500,
                                textTransform: 'none',
                                letterSpacing: '0'
                              }}
                            >
                              #{tag}
                            </span>
                          ))}
                        </div>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      <div>{formatDateTime(rule.updated_at)}</div>
                      <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                        创建于 {formatDateTime(rule.created_at)}
                      </div>
                    </td>
                    <td>{rule.published_by ?? '—'}</td>
                    <td style={{ textAlign: 'right' }}>
                      <Dropdown
                        menu={{
                          items: [
                            {
                              key: 'edit',
                              label: '编辑',
                              onClick: () => {
                                setIsCreating(false)
                                setEditingRule(rule)
                              }
                            },
                            {
                              key: 'clone',
                              label: '复制',
                              disabled: cloneMutation.isPending,
                              onClick: () => {
                                const newName = prompt('新规则名称', `${rule.name}_copy`)
                                if (newName) {
                                  cloneMutation.mutate({
                                    ruleId: rule.id,
                                    payload: {
                                      new_name: newName,
                                      new_version: rule.version,
                                      parameter_overrides: {},
                                      description: rule.description
                                    }
                                  })
                                }
                              }
                            }
                          ]
                        }}
                      >
                        <button className="button button--secondary">
                          操作 ▼
                        </button>
                      </Dropdown>
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
        ) : (
          <div className="empty-state">暂无规则定义，请先创建。</div>
        )}
      </section>
      )}
    </div>
  )
}

export default RuleDefinitionsPage
