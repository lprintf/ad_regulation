import { useEffect, useMemo, useState } from 'react'
import { Modal, message, Spin } from 'antd'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { RuleEntityType } from '../../types/rule-engine'
import { createRuleBinding } from '../../api/ruleEngine'
import { mergeBindingMetadata, stripReservedMetadata } from '../rule-bindings/utils'
import { useEntityRuleBindings, usePublishedRules } from '../rule-bindings/hooks'

export interface RuleBindingTarget {
  entityId: string
  entityName: string | null
  entityType: RuleEntityType
  accountId: string | null
}

interface RuleBindingModalProps {
  target: RuleBindingTarget | null
  open: boolean
  onClose: () => void
}

const RuleBindingModal = ({ target, open, onClose }: RuleBindingModalProps) => {
  const queryClient = useQueryClient()
  const { rules, isLoading: isLoadingRules, isError: isRuleError } = usePublishedRules()
  const { data: bindingsResponse, isLoading: isLoadingBindings } = useEntityRuleBindings(
    target?.entityId,
    target?.entityType,
    open
  )

  const existingBindings = useMemo(() => bindingsResponse?.items ?? [], [bindingsResponse])

  const [selectedRuleId, setSelectedRuleId] = useState('')
  const [metadata, setMetadata] = useState('')
  const [metadataError, setMetadataError] = useState('')
  const [notes, setNotes] = useState('')

  useEffect(() => {
    if (open) {
      setMetadataError('')
      setNotes('')
      setMetadata('')
      if (rules.length > 0) {
        setSelectedRuleId(rules[0].id)
      }
    }
  }, [open, rules])

  useEffect(() => {
    if (!open || !existingBindings.length) {
      return
    }
    const latestBinding = existingBindings[0]
    setSelectedRuleId(prev => prev || latestBinding.ruleId)
    if (latestBinding.metadata) {
      const editableMetadata = stripReservedMetadata(latestBinding.metadata)
      setMetadata(editableMetadata ? JSON.stringify(editableMetadata, null, 2) : '')
      setNotes(typeof latestBinding.metadata.notes === 'string' ? latestBinding.metadata.notes : '')
    }
  }, [existingBindings, open])

  const createBindingMutation = useMutation({
    mutationFn: createRuleBinding,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rule-bindings'] })
      message.success('规则绑定成功')
      onClose()
    },
    onError: error => {
      const content =
        error instanceof Error ? error.message : '规则绑定失败，请稍后再试。'
      message.error(content)
    }
  })

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!target || !selectedRuleId) {
      return
    }
    setMetadataError('')

    let parsedMetadata: Record<string, unknown> | undefined
    if (metadata.trim()) {
      try {
        const parsed = JSON.parse(metadata)
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          parsedMetadata = parsed as Record<string, unknown>
        } else {
          setMetadataError('元数据需要是 JSON 对象')
          return
        }
      } catch {
        setMetadataError('元数据不是合法 JSON')
        return
      }
    }

    const mergedMetadata = mergeBindingMetadata(
      parsedMetadata,
      target.accountId ?? undefined,
      notes.trim() || undefined
    )

    createBindingMutation.mutate({
      ruleId: selectedRuleId,
      entityId: target.entityId,
      entityType: target.entityType,
      metadata: mergedMetadata,
      source: 'manual'
    })
  }

  const titleEntity = useMemo(() => {
    if (!target) return ''
    return `${target.entityName ?? target.entityId} (${target.entityId})`
  }, [target])

  return (
    <Modal
      title="绑定规则"
      open={open && Boolean(target)}
      onCancel={() => {
        if (createBindingMutation.isPending) {
          return
        }
        onClose()
      }}
      destroyOnClose
      footer={null}
      width={640}
    >
      {!target ? (
        <div>请选择要绑定的实体。</div>
      ) : (
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <section>
            <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{titleEntity}</div>
            <div style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem' }}>
              类型：{target.entityType} · 所属账号：{target.accountId ?? '未知'}
            </div>
          </section>

          {isRuleError ? (
            <div style={{ color: 'var(--color-danger)' }}>规则列表加载失败，请刷新页面。</div>
          ) : isLoadingRules ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Spin size="small" />
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
                  {rules.map(rule => (
                    <option key={rule.id} value={rule.id}>
                      {rule.name} (v{rule.version})
                    </option>
                  ))}
                </select>
              </label>

              <label className="form-label">
                <span>元数据 JSON（可选）</span>
                <textarea
                  className="textarea"
                  rows={4}
                  placeholder='{"guard": true}'
                  value={metadata}
                  onChange={event => setMetadata(event.target.value)}
                />
                {metadataError && (
                  <div style={{ color: 'var(--color-danger)' }}>{metadataError}</div>
                )}
              </label>

              <label className="form-label">
                <span>备注（可选）</span>
                <input
                  className="input"
                  value={notes}
                  onChange={event => setNotes(event.target.value)}
                  placeholder="绑定原因、使用场景等"
                />
              </label>

              <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
                绑定创建后默认启用，可在规则绑定页面停用或编辑。
              </div>
            </>
          )}

          <div style={{ borderTop: '1px solid var(--color-border, #eee)', paddingTop: '1rem' }}>
            <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>已绑定规则</div>
            {isLoadingBindings ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Spin size="small" />
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
                        {binding.updatedAt ? new Date(binding.updatedAt).toLocaleString() : '--'}
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
