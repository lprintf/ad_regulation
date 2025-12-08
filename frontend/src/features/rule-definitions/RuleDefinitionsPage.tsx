import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Modal, Tabs, Breadcrumb, toast } from '@/components/ui'
import { 
  fetchAvailableRules, 
  fetchRuleConfigs, 
  createRuleConfig,
  archiveRuleConfig,
  syncSystemRules,
  fetchRuleBindings,
  createRuleBinding,
  deleteRuleBinding,
  updateRuleBinding,
  fetchRuleInfo,
  type RuleConfig,
  type RuleConfigCreate,
  type RuleBindingPayload
} from '../../api/ruleEngine'
import type { RuleDefinition, RuleParameter, RuleBinding, RuleEntityType } from '../../types/rule-engine'
import RuleBindingsList from '../../components/RuleBindingsList'
import RuleBindingForm, { type RuleBindingFormValues } from '../rule-bindings/RuleBindingForm'
import RuleBindingTestPanel from '../rule-bindings/RuleBindingTestPanel'
import { formatDateTime } from '../../lib/datetime'

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

const RuleDefinitionsPage = () => {
  const queryClient = useQueryClient()
  
  // Top-level tab state
  const [activeTab, setActiveTab] = useState<'rules' | 'bindings'>('rules')
  
  // Rule list states
  const [selectedRule, setSelectedRule] = useState<RuleDefinition | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [cloneModalOpen, setCloneModalOpen] = useState(false)
  const [cloneTarget, setCloneTarget] = useState<RuleDefinition | RuleConfig | null>(null)
  const [cloneForm, setCloneForm] = useState<{
    suffix: string
    description: string
    overrides: Record<string, any>
  }>({ suffix: '', description: '', overrides: {} })

  // Binding tab states
  const [bindingFilters, setBindingFilters] = useState<{
    entityType: RuleEntityType | 'all'
    activeOnly: boolean
    entityId: string
    ruleName: string
  }>({
    entityType: 'all',
    activeOnly: true,
    entityId: '',
    ruleName: ''
  })
  const [isCreatingBinding, setIsCreatingBinding] = useState(false)
  const [editingBinding, setEditingBinding] = useState<RuleBinding | null>(null)
  const [selectedBinding, setSelectedBinding] = useState<RuleBinding | null>(null)

  // Queries
  const rulesQuery = useQuery({
    queryKey: ['available-rules'],
    queryFn: fetchAvailableRules,
    staleTime: 60_000
  })

  const configsQuery = useQuery({
    queryKey: ['rule-configs'],
    queryFn: () => fetchRuleConfigs({ includeArchived: false }),
    staleTime: 30_000
  })

  const bindingsQuery = useQuery({
    queryKey: ['rule-bindings', bindingFilters],
    queryFn: () =>
      fetchRuleBindings({
        ruleName: bindingFilters.ruleName || undefined,
        entityId: bindingFilters.entityId || undefined,
        entityType: bindingFilters.entityType,
        activeOnly: bindingFilters.activeOnly
      }),
    staleTime: 15_000
  })

  const selectedRuleQuery = useQuery({
    queryKey: ['rule-info', selectedBinding?.ruleName],
    queryFn: () => selectedBinding ? fetchRuleInfo(selectedBinding.ruleName) : Promise.resolve(null),
    enabled: !!selectedBinding,
    staleTime: 60_000,
  })

  // Mutations
  const createConfigMutation = useMutation({
    mutationFn: createRuleConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rule-configs'] })
      setCloneModalOpen(false)
      setCloneTarget(null)
      setCloneForm({ suffix: '', description: '', overrides: {} })
      toast.success('规则配置创建成功')
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || '创建失败')
    }
  })

  const archiveConfigMutation = useMutation({
    mutationFn: archiveRuleConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rule-configs'] })
      toast.success('规则已归档')
    }
  })

  const syncSystemRulesMutation = useMutation({
    mutationFn: syncSystemRules,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['rule-configs'] })
      queryClient.invalidateQueries({ queryKey: ['available-rules'] })
      toast.success(`已同步 ${result.synced_count} 个系统规则`)
    }
  })

  const createBindingMutation = useMutation({
    mutationFn: createRuleBinding,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rule-bindings'] })
      setIsCreatingBinding(false)
    }
  })

  const updateBindingMutation = useMutation({
    mutationFn: ({ bindingId, values }: { bindingId: string; values: Partial<RuleBindingPayload & { active: boolean }> }) => 
      updateRuleBinding(bindingId, values),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rule-bindings'] })
      setEditingBinding(null)
    }
  })

  const deleteBindingMutation = useMutation({
    mutationFn: deleteRuleBinding,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rule-bindings'] })
    }
  })

  // Derived data
  const rules = rulesQuery.data ?? []
  const configs = configsQuery.data ?? []

  const filteredConfigs = configs.filter(config =>
    config.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    config.base_rule.toLowerCase().includes(searchTerm.toLowerCase()) ||
    config.description?.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const filteredBindings = useMemo(() => {
    const items = bindingsQuery.data?.items ?? []
    if (!bindingFilters.entityId) return items
    return items.filter(binding =>
      binding.entityId.toLowerCase().includes(bindingFilters.entityId.toLowerCase())
    )
  }, [bindingsQuery.data?.items, bindingFilters.entityId])

  // Handlers
  const handleOpenCloneModal = (source: RuleDefinition | RuleConfig) => {
    const isConfig = 'base_rule' in source
    const baseSchema = isConfig 
      ? (source as RuleConfig).parameters_schema 
      : source.parameters_schema

    // Filter out evaluation_date from initial overrides (not allowed to override)
    const initialOverrides: Record<string, any> = {}
    if (baseSchema) {
      Object.entries(baseSchema).forEach(([key, param]) => {
        if (key === 'evaluation_date') return  // Skip evaluation_date
        const p = param as RuleParameter
        initialOverrides[key] = p.default ?? p.defaultValue ?? ''
      })
    }

    setCloneTarget(source)
    setCloneForm({
      suffix: 'copy',
      description: isConfig ? ((source as RuleConfig).description || '') : (source.description || ''),
      overrides: initialOverrides
    })
    setCloneModalOpen(true)
  }

  const handleCloneSubmit = () => {
    if (!cloneTarget || !cloneForm.suffix.trim()) return

    const isConfig = 'base_rule' in cloneTarget
    const baseRule = isConfig ? (cloneTarget as RuleConfig).base_rule : cloneTarget.name
    const templateId = isConfig ? (cloneTarget as RuleConfig).id : undefined

    // Filter out evaluation_date from overrides
    const filteredOverrides = Object.fromEntries(
      Object.entries(cloneForm.overrides).filter(([key]) => key !== 'evaluation_date')
    )

    const payload: RuleConfigCreate = {
      suffix: cloneForm.suffix.trim(),
      base_rule: baseRule,
      template_id: templateId,  // Track clone source for version calculation
      description: cloneForm.description.trim() || undefined,
      parameter_overrides: filteredOverrides
    }

    createConfigMutation.mutate(payload)
  }

  const toBindingPayload = (values: RuleBindingFormValues): RuleBindingPayload => ({
    ruleId: values.ruleId,
    ruleConfigId: values.ruleConfigId,
    entityType: values.entityType,
    entityId: values.entityId,
    adAccountId: values.adAccountId,
    campaignId: values.campaignId,
    adsetId: values.adsetId,
    adId: values.adId,
    source: 'manual'
  })

  const handleCreateBinding = (values: RuleBindingFormValues) => {
    createBindingMutation.mutate(toBindingPayload(values))
  }

  const handleUpdateBinding = (values: RuleBindingFormValues) => {
    if (!editingBinding) return
    const payload: { ruleConfigId?: string | null; active?: boolean } = {}
    if (values.ruleConfigId !== undefined) payload.ruleConfigId = values.ruleConfigId
    if (values.active !== undefined) payload.active = values.active
    updateBindingMutation.mutate({ bindingId: editingBinding.id, values: payload })
  }

  const handleCancelBindingEdit = () => {
    setIsCreatingBinding(false)
    setEditingBinding(null)
  }

  // Render helpers
  const renderParameterType = (param: RuleParameter): string => {
    const parts: string[] = [param.type]
    if (param.min !== undefined || param.max !== undefined) {
      parts.push(`[${param.min ?? ''}..${param.max ?? ''}]`)
    }
    if (param.unit) parts.push(`(${param.unit})`)
    return parts.join(' ')
  }

  const renderDefaultValue = (param: RuleParameter) => {
    const value = param.default ?? param.defaultValue
    if (value === undefined || value === null || value === '') return '—'
    if (typeof value === 'boolean') return value ? '是' : '否'
    return String(value)
  }

  const renderParameterInput = (key: string, param: RuleParameter) => {
    const value = cloneForm.overrides[key]
    const onChange = (newValue: any) => {
      setCloneForm(prev => ({
        ...prev,
        overrides: { ...prev.overrides, [key]: newValue }
      }))
    }

    if (param.type === 'boolean') {
      return (
        <select className="input" value={value === true ? 'true' : value === false ? 'false' : ''} onChange={e => onChange(e.target.value === 'true')}>
          <option value="true">是</option>
          <option value="false">否</option>
        </select>
      )
    }

    if (param.type === 'integer' || param.type === 'number') {
      return (
        <input
          type="number"
          className="input"
          value={value ?? ''}
          min={param.min}
          max={param.max}
          step={param.step ?? (param.type === 'integer' ? 1 : 0.01)}
          onChange={e => onChange(param.type === 'integer' ? parseInt(e.target.value) : parseFloat(e.target.value))}
        />
      )
    }

    return <input type="text" className="input" value={value ?? ''} onChange={e => onChange(e.target.value)} />
  }

  // View states for bindings tab
  const isBindingEditingOrCreating = isCreatingBinding || !!editingBinding
  const bindingView = isBindingEditingOrCreating ? 'form' : selectedBinding ? 'execution' : 'list'

  // Render rules tab content
  const renderRulesTab = () => {
    if (selectedRule) {
      return (
        <section className="card">
          <div className="card__header">
            <div>
              <button className="button button--secondary mb-2" onClick={() => setSelectedRule(null)}>
                ← 返回列表
              </button>
              <div className="card__title">{selectedRule.name}</div>
              <div className="card__subtitle">{selectedRule.description}</div>
            </div>
            <div className="toolbar__group">
              <span className="badge badge--published">v{selectedRule.version}</span>
              <button className="button button--primary" onClick={() => handleOpenCloneModal(selectedRule)}>
                复制规则
              </button>
            </div>
          </div>

          <Tabs
            defaultActiveKey="info"
            className="px-4 pb-4"
            items={[
              {
                key: 'info',
                label: '规则信息',
                children: (
                  <div>
                    {selectedRule.tags && selectedRule.tags.length > 0 && (
                      <div className="mb-6">
                        <h4 className="mb-2 text-muted-foreground">标签</h4>
                        <div className="flex flex-wrap gap-1">
                          {selectedRule.tags.map(tag => <span key={tag} className="chip chip--muted">#{tag}</span>)}
                        </div>
                      </div>
                    )}
                    <div>
                      <h4 className="mb-3 text-muted-foreground">参数配置</h4>
                      {selectedRule.parameters_schema && Object.keys(selectedRule.parameters_schema).length > 0 ? (
                        <div className="table-wrapper">
                          <table className="table">
                            <thead>
                              <tr>
                                <th>参数名</th>
                                <th>标签</th>
                                <th>类型</th>
                                <th>参数值</th>
                                <th>描述</th>
                              </tr>
                            </thead>
                            <tbody>
                              {Object.entries(selectedRule.parameters_schema).map(([key, param]) => (
                                <tr key={key}>
                                  <td><code className="bg-muted px-1.5 py-0.5 rounded text-sm">{key}</code></td>
                                  <td>{param.label ?? key}</td>
                                  <td><span className="text-muted-foreground text-sm">{renderParameterType(param)}</span></td>
                                  <td><strong>{renderDefaultValue(param)}</strong></td>
                                  <td>
                                    <div>{param.description ?? '—'}</div>
                                    {param.hint && <div className="text-muted-foreground text-xs mt-1">{param.hint}</div>}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <div className="empty-state p-8">此规则没有可配置参数</div>
                      )}
                    </div>
                  </div>
                )
              },
              {
                key: 'bindings',
                label: '已绑定实体',
                children: (
                  <div>
                    <div className="mb-4 text-muted-foreground text-sm">
                      以下广告实体已绑定此规则，规则会按计划自动执行
                    </div>
                    <RuleBindingsList ruleName={selectedRule.name} showRuleName={false} showEntityId={true} allowDelete={true} allowToggle={true} />
                  </div>
                )
              }
            ]}
          />
        </section>
      )
    }

    // Helper to format source display
    const formatSource = (source: string) => {
      if (source === 'system') return { label: '系统', className: 'badge badge--info' }
      if (source.startsWith('user:')) return { label: source.replace('user:', '用户:'), className: 'badge badge--warning' }
      return { label: source, className: 'badge badge--muted' }
    }

    return (
      <section className="card">
        <div className="card__header">
          <div>
            <div className="card__title">规则列表</div>
            <div className="card__subtitle">统一管理系统规则和自定义配置</div>
          </div>
          <div className="toolbar__group">
            <button 
              className="button button--secondary" 
              onClick={() => syncSystemRulesMutation.mutate()}
              disabled={syncSystemRulesMutation.isPending}
            >
              {syncSystemRulesMutation.isPending ? '同步中...' : '同步系统规则'}
            </button>
          </div>
        </div>

        <div className="toolbar">
          <div className="toolbar__group" style={{ flex: 1 }}>
            <input className="input" placeholder="搜索规则..." value={searchTerm} onChange={e => setSearchTerm(e.target.value)} />
          </div>
        </div>

        {configsQuery.isError ? (
          <div className="empty-state"><p>加载规则失败</p></div>
        ) : configsQuery.isLoading ? (
          <div className="empty-state">加载中...</div>
        ) : filteredConfigs.length === 0 ? (
          <div className="empty-state">
            <p>{searchTerm ? '没有匹配的规则' : '暂无规则，请先同步系统规则'}</p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>规则名称</th>
                  <th>来源</th>
                  <th>基础规则</th>
                  <th>版本</th>
                  <th>标签</th>
                  <th>参数覆盖</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filteredConfigs.map(config => {
                  const sourceInfo = formatSource(config.source)
                  const isSystemRule = config.source === 'system'
                  return (
                    <tr key={config.id}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{config.name}</div>
                        <div style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>{config.description ?? '未填写描述'}</div>
                      </td>
                      <td><span className={sourceInfo.className}>{sourceInfo.label}</span></td>
                      <td>
                        {isSystemRule ? '—' : (
                          <div>
                            <div style={{ fontWeight: 500 }}>{config.base_rule_name || config.base_rule}</div>
                            <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>{config.base_rule}</div>
                          </div>
                        )}
                      </td>
                      <td><span className={isSystemRule ? 'badge badge--published' : 'badge badge--draft'}>v{config.version}</span></td>
                      <td>
                        {config.tags?.length ? (
                          <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                            {config.tags.map(tag => <span key={tag} className="chip chip--muted">#{tag}</span>)}
                          </div>
                        ) : '—'}
                      </td>
                      <td>{Object.keys(config.parameter_overrides).length || '—'}</td>
                      <td style={{ textAlign: 'right' }}>
                        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                          <button className="button button--secondary" onClick={() => {
                            // Find matching rule definition for detail view
                            const ruleName = config.base_rule_name || config.name.split(':')[0]
                            const rule = rules.find(r => r.name === ruleName)
                            if (rule) setSelectedRule(rule)
                          }}>详情</button>
                          <button className="button button--primary" onClick={() => handleOpenCloneModal(config)}>复制</button>
                          {!isSystemRule && (
                            <button className="button button--ghost" onClick={() => { if (confirm(`确定归档规则 "${config.name}"？归档后规则将被隐藏但不会删除。`)) archiveConfigMutation.mutate(config.id) }}>归档</button>
                          )}
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
    )
  }

  // Render bindings tab content
  const renderBindingsTab = () => {
    if (bindingView === 'execution') {
      return (
        <>
          <Breadcrumb
            items={[
              { title: '规则绑定', onClick: () => setSelectedBinding(null) },
              { title: `${selectedBinding!.ruleName} - ${selectedBinding!.entityId}` }
            ]}
            className="mb-4"
          />
          <RuleBindingTestPanel binding={selectedBinding!} parametersSchema={selectedRuleQuery.data?.parameters_schema} />
        </>
      )
    }

    if (bindingView === 'form') {
      return (
        <>
          <Breadcrumb
            items={[
              { title: '规则绑定', onClick: handleCancelBindingEdit },
              { title: editingBinding ? `编辑绑定: ${editingBinding.entityId}` : '创建新绑定' }
            ]}
            className="mb-4"
          />
          <RuleBindingForm
            mode={editingBinding ? 'edit' : 'create'}
            initialValues={editingBinding ?? undefined}
            rules={rules}
            onSubmit={editingBinding ? handleUpdateBinding : handleCreateBinding}
            onCancel={handleCancelBindingEdit}
            isSubmitting={createBindingMutation.isPending || updateBindingMutation.isPending}
          />
        </>
      )
    }

    return (
      <section className="card">
        <div className="card__header">
          <div>
            <div className="card__title">规则绑定</div>
            <div className="card__subtitle">管理规则与广告实体的绑定记录</div>
          </div>
          <div className="toolbar__group">
            <button className="button button--primary" onClick={() => { setEditingBinding(null); setIsCreatingBinding(true) }}>
              新建绑定
            </button>
          </div>
        </div>

        <div className="toolbar">
          <div className="toolbar__group">
            <select className="select" value={bindingFilters.ruleName} onChange={e => setBindingFilters(prev => ({ ...prev, ruleName: e.target.value }))}>
              <option value="">全部规则</option>
              {rules.map(rule => <option key={rule.name} value={rule.name}>{rule.name}</option>)}
            </select>
          </div>
          <div className="toolbar__group">
            <select className="select" value={bindingFilters.entityType} onChange={e => setBindingFilters(prev => ({ ...prev, entityType: e.target.value as RuleEntityType | 'all' }))}>
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
              value={bindingFilters.entityId}
              onChange={e => setBindingFilters(prev => ({ ...prev, entityId: e.target.value }))}
              style={{ minWidth: '200px' }}
            />
          </div>
          <label className="form-label checkbox-label" style={{ marginBottom: 0 }}>
            <input type="checkbox" checked={bindingFilters.activeOnly} onChange={e => setBindingFilters(prev => ({ ...prev, activeOnly: e.target.checked }))} />
            仅显示启用绑定
          </label>
        </div>

        {bindingsQuery.isError ? (
          <div className="empty-state">加载绑定失败</div>
        ) : bindingsQuery.isLoading ? (
          <div className="empty-state">加载绑定中...</div>
        ) : filteredBindings.length === 0 ? (
          <div className="empty-state">暂无绑定记录</div>
        ) : (
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>规则</th>
                  <th>实体类型</th>
                  <th>实体 ID</th>
                  <th>广告账号</th>
                  <th>状态</th>
                  <th>更新时间</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filteredBindings.map(binding => (
                  <tr key={binding.id}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{binding.ruleName}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>来源：{sourceLabels[binding.source] ?? binding.source}</div>
                    </td>
                    <td>{entityTypeLabel[binding.entityType]}</td>
                    <td>{binding.entityId}</td>
                    <td>{binding.adAccountId || '—'}</td>
                    <td>
                      <span className={binding.active ? 'badge badge--success' : 'badge badge--disabled'}>
                        {binding.active ? '启用' : '停用'}
                      </span>
                    </td>
                    <td>
                      <div>{formatDateTime(binding.updated_at)}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>创建于 {formatDateTime(binding.created_at)}</div>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                        <button className="button button--secondary" onClick={() => setSelectedBinding(binding)}>详细</button>
                        <button className="button button--secondary" onClick={() => { setIsCreatingBinding(false); setEditingBinding(binding) }}>编辑</button>
                        <button className="button button--ghost" onClick={() => updateBindingMutation.mutate({ bindingId: binding.id, values: { active: !binding.active } })}>{binding.active ? '停用' : '启用'}</button>
                        <button className="button button--ghost text-destructive" onClick={() => { if (confirm(`确定要删除与 ${binding.entityId} 的绑定吗？`)) deleteBindingMutation.mutate(binding.id) }}>删除</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    )
  }

  return (
    <div className="page">
      <section className="card" style={{ marginBottom: '1rem' }}>
        <div className="card__header" style={{ borderBottom: 'none', paddingBottom: 0 }}>
          <div>
            <div className="card__title">规则管理</div>
            <div className="card__subtitle">管理规则定义、参数配置和绑定关系</div>
          </div>
        </div>
      </section>

      <Tabs
        activeKey={activeTab}
        onChange={key => {
          setActiveTab(key as 'rules' | 'bindings')
          // Reset sub-states when switching tabs
          if (key === 'rules') {
            setSelectedBinding(null)
            setIsCreatingBinding(false)
            setEditingBinding(null)
          } else {
            setSelectedRule(null)
          }
        }}
        items={[
          { key: 'rules', label: '规则列表', children: renderRulesTab() },
          { key: 'bindings', label: '规则绑定', children: renderBindingsTab() }
        ]}
      />

      {/* Clone Modal */}
      <Modal
        title="复制规则配置"
        open={cloneModalOpen}
        onClose={() => { setCloneModalOpen(false); setCloneTarget(null) }}
        width={700}
        footer={
          <>
            <button className="button button--ghost" onClick={() => { setCloneModalOpen(false); setCloneTarget(null) }}>取消</button>
            <button className="button button--primary" onClick={handleCloneSubmit} disabled={createConfigMutation.isPending}>
              {createConfigMutation.isPending ? '创建中...' : '创建'}
            </button>
          </>
        }
      >
        {cloneTarget && (() => {
          const isConfig = 'base_rule' in cloneTarget
          const baseRule = isConfig ? (cloneTarget as RuleConfig).base_rule : cloneTarget.name
          const previewName = `${baseRule}:{user_id}:${cloneForm.suffix || '...'}`
          
          return (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label className="form-label">
                  <span>规则后缀 *</span>
                  <input className="input" value={cloneForm.suffix} onChange={e => setCloneForm(prev => ({ ...prev, suffix: e.target.value }))} placeholder="例如：conservative, aggressive" />
                </label>
                <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>
                  最终名称: <code style={{ background: 'var(--color-bg-secondary)', padding: '0.1rem 0.3rem', borderRadius: '3px' }}>{previewName}</code>
                </div>
              </div>
              <div>
                <label className="form-label">
                  <span>描述</span>
                  <input className="input" value={cloneForm.description} onChange={e => setCloneForm(prev => ({ ...prev, description: e.target.value }))} placeholder="描述此配置的用途" />
                </label>
              </div>
              <div>
                <h4 style={{ marginBottom: '0.75rem' }}>参数配置</h4>
                <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>
                  注意: evaluation_date 参数不可覆盖
                </div>
                <div style={{ border: '1px solid var(--color-border)', borderRadius: '6px', maxHeight: '300px', overflow: 'auto' }}>
                  <table className="table" style={{ margin: 0 }}>
                    <thead>
                      <tr>
                        <th>参数</th>
                        <th>类型</th>
                        <th>值</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(isConfig ? (cloneTarget as RuleConfig).parameters_schema : (cloneTarget.parameters_schema || {}))
                        .filter(([key]) => key !== 'evaluation_date')  // Filter out evaluation_date
                        .map(([key, param]) => (
                          <tr key={key}>
                            <td>
                              <div style={{ fontWeight: 500 }}>{(param as RuleParameter).label || key}</div>
                              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>{(param as RuleParameter).description}</div>
                            </td>
                            <td style={{ color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>{renderParameterType(param as RuleParameter)}</td>
                            <td style={{ width: '200px' }}>{renderParameterInput(key, param as RuleParameter)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )
        })()}
      </Modal>
    </div>
  )
}

export default RuleDefinitionsPage
