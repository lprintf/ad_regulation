import { useEffect, useState } from 'react'
import type {
  RuleBinding,
  RuleDefinition,
  RuleEntityType
} from '../../types/rule-engine'
import { mergeBindingMetadata, stripReservedMetadata } from './utils'

export interface RuleBindingFormValues {
  ruleId: string
  entityType: RuleEntityType
  entityId: string
  accountId?: string
  metadata?: Record<string, unknown>
  notes?: string
  active?: boolean
}

interface RuleBindingFormProps {
  mode: 'create' | 'edit'
  initialValues?: RuleBinding
  rules: RuleDefinition[]
  onSubmit: (values: RuleBindingFormValues) => void
  onCancel: () => void
  isSubmitting?: boolean
}

const entityTypeLabels: Record<RuleEntityType, string> = {
  account: '广告账号',
  campaign: '广告系列',
  adset: '广告组',
  ad: '广告'
}

const RuleBindingForm = ({
  mode,
  initialValues,
  rules,
  onSubmit,
  onCancel,
  isSubmitting = false
}: RuleBindingFormProps) => {
  const [ruleId, setRuleId] = useState('')
  const [entityType, setEntityType] = useState<RuleEntityType>('account')
  const [entityId, setEntityId] = useState('')
  const [accountId, setAccountId] = useState('')
  const [metadata, setMetadata] = useState('')
  const [metadataError, setMetadataError] = useState('')
  const [notes, setNotes] = useState('')
  const [active, setActive] = useState(true)

  useEffect(() => {
    if (initialValues) {
      setRuleId(initialValues.ruleId)
      setEntityType(initialValues.entityType)
      setEntityId(initialValues.entityId)
      setAccountId(initialValues.accountId ?? '')

      const editableMetadata = stripReservedMetadata(initialValues.metadata)
      setMetadata(
        editableMetadata ? JSON.stringify(editableMetadata, null, 2) : ''
      )
      setNotes(initialValues.notes ?? '')
      setActive(initialValues.active)
    } else if (rules.length > 0) {
      setRuleId(rules[0].id)
    }
  }, [initialValues, rules])

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setMetadataError('')

    let metadataObject: Record<string, unknown> | undefined
    if (metadata.trim().length > 0) {
      try {
        const parsed = JSON.parse(metadata)
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          metadataObject = parsed as Record<string, unknown>
        } else {
          setMetadataError('元数据需要是一个 JSON 对象')
          return
        }
      } catch (parseError) {
        setMetadataError('元数据必须为合法的 JSON 字符串')
        return
      }
    }

    const normalizedAccountId = accountId.trim()
    const normalizedNotes = notes.trim()

    const mergedMetadata = mergeBindingMetadata(
      metadataObject,
      accountId === '' ? '' : normalizedAccountId,
      notes === '' ? '' : normalizedNotes
    )

    onSubmit({
      ruleId,
      entityType,
      entityId,
      accountId: accountId === '' ? '' : normalizedAccountId,
      metadata: mergedMetadata,
      notes: notes === '' ? '' : normalizedNotes,
      active
    })
  }

  const title = mode === 'create' ? '创建规则绑定' : '编辑规则绑定'

  return (
    <form className="card" onSubmit={handleSubmit}>
      <div className="card__header">
        <div>
          <div className="card__title">{title}</div>
          <div className="card__subtitle">
            绑定规则到指定实体，支持手动绑定或与命名解析逻辑保持一致。
          </div>
        </div>
        <div className="toolbar__group">
          <button
            type="button"
            className="button button--ghost"
            onClick={onCancel}
            disabled={isSubmitting}
          >
            取消
          </button>
          <button type="submit" className="button button--primary" disabled={isSubmitting}>
            {isSubmitting ? '保存中...' : '保存'}
          </button>
        </div>
      </div>

      <div className="grid-two-columns">
        <label className="form-label">
          <span>关联规则</span>
          <select
            className="select"
            value={ruleId}
            onChange={event => setRuleId(event.target.value)}
            required
          >
            {rules.length === 0 && <option value="">暂无规则</option>}
            {rules.map(rule => (
              <option key={rule.id} value={rule.id}>
                {rule.name} (v{rule.version})
              </option>
            ))}
          </select>
        </label>

        <label className="form-label">
          <span>实体类型</span>
          <select
            className="select"
            value={entityType}
            onChange={event => setEntityType(event.target.value as RuleEntityType)}
          >
            {Object.entries(entityTypeLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid-two-columns">
        <label className="form-label">
          <span>实体 ID</span>
          <input
            className="input"
            placeholder="广告/广告组/广告系列/账号 ID"
            value={entityId}
            onChange={event => setEntityId(event.target.value)}
            required
          />
        </label>

        <label className="form-label">
          <span>所属账号 (可选)</span>
          <input
            className="input"
            placeholder="act_ 开头的账号 ID"
            value={accountId}
            onChange={event => setAccountId(event.target.value)}
          />
        </label>
      </div>

      <label className="form-label">
        <span>元数据 JSON (可选)</span>
        <textarea
          className="textarea"
          rows={4}
          placeholder='{"ad_account_id": "act_123", "budget_guard": true}'
          value={metadata}
          onChange={event => setMetadata(event.target.value)}
        />
        {metadataError && <div className="form-hint" style={{ color: 'var(--color-danger)' }}>{metadataError}</div>}
      </label>

      <label className="form-label">
        <span>备注 (可选)</span>
        <textarea
          className="textarea"
          rows={3}
          placeholder="额外说明，例如绑定原因或生命周期。"
          value={notes}
          onChange={event => setNotes(event.target.value)}
        />
      </label>

      {mode === 'edit' && (
        <label className="form-label checkbox-label">
          <input
            type="checkbox"
            checked={active}
            onChange={event => setActive(event.target.checked)}
          />
          启用绑定
        </label>
      )}
    </form>
  )
}

export default RuleBindingForm
