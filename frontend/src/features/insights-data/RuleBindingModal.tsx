import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Modal, Spinner, toast } from '@/components/ui'
import type { RuleEntityType } from '../../types/rule-engine'
import { createRuleBinding } from '../../api/ruleEngine'
import { useEntityRuleBindings, useAllRulesForBinding } from '../rule-bindings/hooks'

export interface RuleBindingTarget {
  entityId: string
  entityName: string | null
  entityType: RuleEntityType
  // Ad hierarchy - for proper indexing
  adAccountId: string
  campaignId?: string | null
  adsetId?: string | null
  adId?: string | null
}

interface RuleBindingModalProps {
  target: RuleBindingTarget | null
  open: boolean
  onClose: () => void
}

const RuleBindingModal = ({ target, open, onClose }: RuleBindingModalProps) => {
  const queryClient = useQueryClient()
  const { rules, isLoading: isLoadingRules, isError: isRuleError } = useAllRulesForBinding()
  const { data: bindingsResponse, isLoading: isLoadingBindings } = useEntityRuleBindings(
    target?.entityId,
    target?.entityType,
    open
  )

  const existingBindings = useMemo(() => bindingsResponse?.items ?? [], [bindingsResponse])

  const [selectedRuleId, setSelectedRuleId] = useState('')
  const [isInitialized, setIsInitialized] = useState(false)

  // Initialize selectedRuleId only once when modal opens
  useEffect(() => {
    if (!open) {
      // Reset initialization flag when modal closes
      setIsInitialized(false)
      setSelectedRuleId('')
      return
    }

    if (isInitialized || rules.length === 0) {
      return
    }

    // Prioritize latest binding if exists, otherwise use first rule
    if (existingBindings.length > 0) {
      setSelectedRuleId(existingBindings[0].ruleId)
    } else {
      setSelectedRuleId(rules[0].id)
    }

    setIsInitialized(true)
  }, [open, rules, existingBindings, isInitialized])

  const createBindingMutation = useMutation({
    mutationFn: createRuleBinding,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rule-bindings'] })
      toast.success('规则绑定成功')
      onClose()
    },
    onError: error => {
      const content =
        error instanceof Error ? error.message : '规则绑定失败，请稍后再试。'
      toast.error(content)
    }
  })

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!target || !selectedRuleId) {
      return
    }

    createBindingMutation.mutate({
      ruleId: selectedRuleId,
      entityType: target.entityType,
      entityId: target.entityId,
      adAccountId: target.adAccountId,
      campaignId: target.campaignId,
      adsetId: target.adsetId,
      adId: target.adId,
      source: 'manual'
    })
  }

  const titleEntity = useMemo(() => {
    if (!target) return ''
    return `${target.entityName ?? target.entityId} (${target.entityId})`
  }, [target])

  const handleClose = () => {
    if (createBindingMutation.isPending) return
    onClose()
  }

  return (
    <Modal
      title="绑定规则"
      open={open && Boolean(target)}
      onClose={handleClose}
      width={640}
    >
      {!target ? (
        <div>请选择要绑定的实体。</div>
      ) : (
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <section>
            <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{titleEntity}</div>
            <div style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
              类型：{target.entityType} · 所属账号：{target.adAccountId}
            </div>
          </section>

          {isRuleError ? (
            <div className="text-destructive">规则列表加载失败，请刷新页面。</div>
          ) : isLoadingRules ? (
            <div className="flex items-center gap-2">
              <Spinner size="sm" />
              <span>加载规则列表...</span>
            </div>
          ) : rules.length === 0 ? (
            <div style={{ color: 'var(--color-danger)' }}>暂无可用规则，请先创建规则。</div>
          ) : (
            <>
              <label className="form-label">
                <span>选择规则</span>
                <select
                  className="input"
                  value={selectedRuleId}
                  onChange={event => setSelectedRuleId(event.target.value)}
                  required
                >
                  <optgroup label="系统规则">
                    {rules.filter(r => !r.isUserConfig).map(rule => (
                      <option key={rule.id} value={rule.id}>
                        {rule.name} (v{rule.version})
                      </option>
                    ))}
                  </optgroup>
                  {rules.some(r => r.isUserConfig) && (
                    <optgroup label="用户配置">
                      {rules.filter(r => r.isUserConfig).map(rule => (
                        <option key={rule.id} value={rule.id}>
                          {rule.name} (v{rule.version})
                        </option>
                      ))}
                    </optgroup>
                  )}
                </select>
              </label>

              <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
                绑定创建后默认启用，可在规则绑定页面停用。如需自定义参数，请先在规则管理页面创建规则配置。
              </div>
            </>
          )}

          <div style={{ borderTop: '1px solid var(--color-border, #eee)', paddingTop: '1rem' }}>
            <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>已绑定规则</div>
            {isLoadingBindings ? (
              <div className="flex items-center gap-2">
                <Spinner size="sm" />
                <span>加载绑定...</span>
              </div>
            ) : existingBindings.length === 0 ? (
              <div style={{ color: 'var(--color-text-muted)' }}>暂无绑定记录。</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '200px', overflow: 'auto' }}>
                {existingBindings.map(binding => (
                  <div
                    key={binding.id}
                    style={{
                      padding: '0.5rem',
                      border: '1px solid var(--color-border, #eee)',
                      borderRadius: '6px',
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: '0.85rem'
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600 }}>{binding.ruleName}</div>
                      <div style={{ color: 'var(--color-text-muted)' }}>
                        {binding.active ? '启用' : '停用'} · 更新于{' '}
                        {binding.updated_at ? new Date(binding.updated_at).toLocaleString() : '--'}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
            <button
              type="button"
              className="button button--ghost"
              onClick={onClose}
              disabled={createBindingMutation.isPending}
            >
              取消
            </button>
            <button
              type="submit"
              className="button button--primary"
              disabled={!selectedRuleId || createBindingMutation.isPending || rules.length === 0}
            >
              {createBindingMutation.isPending ? '绑定中...' : '绑定规则'}
            </button>
          </div>
        </form>
      )}
    </Modal>
  )
}

export default RuleBindingModal
