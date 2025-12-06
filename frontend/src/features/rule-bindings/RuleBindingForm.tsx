import { useEffect, useState } from 'react'
import type {
  RuleBinding,
  RuleDefinition,
  RuleEntityType
} from '../../types/rule-engine'
import AdAccountSelect from '../../components/AdAccountSelect'

export interface RuleBindingFormValues {
  ruleId: string
  ruleConfigId?: string | null
  entityType: RuleEntityType
  entityId: string
  adAccountId: string
  campaignId?: string | null
  adsetId?: string | null
  adId?: string | null
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
  const [adAccountId, setAdAccountId] = useState('')
  const [campaignId, setCampaignId] = useState('')
  const [adsetId, setAdsetId] = useState('')
  const [adId, setAdId] = useState('')
  const [active, setActive] = useState(true)

  useEffect(() => {
    if (initialValues) {
      setRuleId(initialValues.ruleId)
      setEntityType(initialValues.entityType)
      setEntityId(initialValues.entityId)
      setAdAccountId(initialValues.adAccountId ?? '')
      setCampaignId(initialValues.campaignId ?? '')
      setAdsetId(initialValues.adsetId ?? '')
      setAdId(initialValues.adId ?? '')
      setActive(initialValues.active)
    } else if (rules.length > 0) {
      setRuleId(rules[0].id)
    }
  }, [initialValues, rules])

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    onSubmit({
      ruleId,
      entityType,
      entityId,
      adAccountId: adAccountId.trim(),
      campaignId: campaignId.trim() || null,
      adsetId: adsetId.trim() || null,
      adId: adId.trim() || null,
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
            绑定规则到指定实体，需要填写完整的广告层级信息。
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
          <span>实体 ID *</span>
          <input
            className="input"
            placeholder="广告/广告组/广告系列/账号 ID"
            value={entityId}
            onChange={event => setEntityId(event.target.value)}
            required
          />
        </label>

        <label className="form-label">
          <span>广告账号 ID *</span>
          <AdAccountSelect
            value={adAccountId}
            onChange={setAdAccountId}
            placeholder="act_ 开头的账号 ID"
            inputClassName="input"
            helperText="必填，用于查询索引"
          />
        </label>
      </div>

      <div className="grid-two-columns">
        <label className="form-label">
          <span>广告系列 ID {entityType !== 'account' ? '*' : '(可选)'}</span>
          <input
            className="input"
            placeholder="Campaign ID"
            value={campaignId}
            onChange={event => setCampaignId(event.target.value)}
            required={entityType !== 'account'}
          />
        </label>

        <label className="form-label">
          <span>广告组 ID {entityType === 'adset' || entityType === 'ad' ? '*' : '(可选)'}</span>
          <input
            className="input"
            placeholder="AdSet ID"
            value={adsetId}
            onChange={event => setAdsetId(event.target.value)}
            required={entityType === 'adset' || entityType === 'ad'}
          />
        </label>
      </div>

      {entityType === 'ad' && (
        <label className="form-label">
          <span>广告 ID *</span>
          <input
            className="input"
            placeholder="Ad ID"
            value={adId}
            onChange={event => setAdId(event.target.value)}
            required
          />
        </label>
      )}

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
