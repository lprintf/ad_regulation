import { useEffect, useMemo, useState } from 'react'
import type { RuleDefinition, RuleParameter, RuleStatus } from '../../types/rule-engine'

export interface RuleDefinitionFormValues {
  name: string
  description?: string
  status: RuleStatus
  code: string
  tags?: string[]
  parameters?: RuleParameter[]
}

interface RuleDefinitionFormProps {
  mode: 'create' | 'edit'
  initialValues?: RuleDefinition
  onSubmit: (values: RuleDefinitionFormValues) => void
  onCancel: () => void
  isSubmitting?: boolean
}

type ParameterDraft = RuleParameter & { id: string }

const createEmptyParameter = (): ParameterDraft => ({
  id: crypto.randomUUID(),
  key: '',
  label: '',
  type: 'string',
  required: false,
  defaultValue: '',
  description: ''
})

const RuleDefinitionForm = ({
  mode,
  initialValues,
  onSubmit,
  onCancel,
  isSubmitting = false
}: RuleDefinitionFormProps) => {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [status, setStatus] = useState<RuleStatus>('draft')
  const [code, setCode] = useState('')
  const [tags, setTags] = useState('')
  const [parameters, setParameters] = useState<ParameterDraft[]>([createEmptyParameter()])

  useEffect(() => {
    if (initialValues) {
      setName(initialValues.name)
      setDescription(initialValues.description ?? '')
      setCode(initialValues.code)
      setStatus(initialValues.status)
      setTags((initialValues.tags ?? []).join(', '))
      setParameters(
        initialValues.parameters?.length
          ? initialValues.parameters.map(param => ({
              id: crypto.randomUUID(),
              ...param
            }))
          : [createEmptyParameter()]
      )
    }
  }, [initialValues])

  const isEditMode = mode === 'edit'

  const hasAtLeastOneParameter = useMemo(
    () => parameters.some(param => param.key.trim().length > 0),
    [parameters]
  )

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const normalizedParameters = parameters
      .filter(param => param.key.trim().length > 0)
      .map(({ id, ...rest }) => ({
        ...rest,
        defaultValue: rest.defaultValue === '' ? null : rest.defaultValue
      }))

    onSubmit({
      name,
      description: description || undefined,
      status,
      code,
      tags: tags
        .split(',')
        .map(tag => tag.trim())
        .filter(Boolean),
      parameters: hasAtLeastOneParameter ? normalizedParameters : undefined
    })
  }

  const updateParameter = (id: string, updates: Partial<ParameterDraft>) => {
    setParameters(current =>
      current.map(param => (param.id === id ? { ...param, ...updates } : param))
    )
  }

  const addParameter = () => {
    setParameters(current => [...current, createEmptyParameter()])
  }

  const removeParameter = (id: string) => {
    setParameters(current => current.filter(param => param.id !== id))
  }

  return (
    <form className="card" onSubmit={handleSubmit}>
      <div className="card__header">
        <div>
          <div className="card__title">
            {isEditMode ? '编辑规则' : '创建新规则定义'}
          </div>
          <div className="card__subtitle">
            编写 Python 规则脚本，配置参数并设置发布状态。
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
            {isSubmitting ? '保存中...' : isEditMode ? '保存更新' : '创建规则'}
          </button>
        </div>
      </div>

      <div className="grid-two-columns">
        <div>
          <label className="form-label">
            <span>规则名称</span>
            <input
              className="input"
              placeholder="示例：spend_guard_revenue_gap"
              value={name}
              onChange={event => setName(event.target.value)}
              required
            />
          </label>
        </div>

        <div>
          <label className="form-label">
            <span>发布状态</span>
            <select
              className="select"
              value={status}
              onChange={event => setStatus(event.target.value as RuleStatus)}
            >
              <option value="draft">草稿</option>
              <option value="published">已发布</option>
              <option value="disabled">已禁用</option>
            </select>
          </label>
        </div>
      </div>

      <label className="form-label">
        <span>规则描述</span>
        <textarea
          className="textarea"
          placeholder="描述规则的业务目标、触发条件和推荐操作。"
          rows={3}
          value={description}
          onChange={event => setDescription(event.target.value)}
        />
      </label>

      <label className="form-label">
        <span>标签（逗号分隔）</span>
        <input
          className="input"
          placeholder="如：安全, spend-protection"
          value={tags}
          onChange={event => setTags(event.target.value)}
        />
      </label>

      <label className="form-label">
        <span>Python 规则脚本</span>
        <textarea
          className="textarea"
          rows={14}
          spellCheck={false}
          value={code}
          placeholder={`def evaluate(context, params):\n    # context 包含广告、预测、指标\n    # 返回 {'actions': [...], 'reasons': [...], 'metrics': {...}}\n    return {\n        "actions": [],\n        "reasons": [],\n        "metrics": {}\n    }\n`}
          onChange={event => setCode(event.target.value)}
          required
        />
        <small className="form-hint">
          发布前请确保脚本通过沙箱测试，遵循 docs/rule_engine_development_plan.md
        </small>
      </label>

      <section className="card card--nested">
        <div className="card__header">
          <div>
            <div className="card__title">参数配置</div>
            <div className="card__subtitle">可选，在执行时注入动态变量。</div>
          </div>
          <button className="button button--secondary" type="button" onClick={addParameter}>
            添加参数
          </button>
        </div>

        {parameters.map((parameter, index) => (
          <div key={parameter.id} className="parameter-row">
            <div className="parameter-row__header">
              <div className="parameter-row__title">参数 #{index + 1}</div>
              <button
                type="button"
                className="button button--ghost"
                onClick={() => removeParameter(parameter.id)}
                disabled={parameters.length === 1}
              >
                删除
              </button>
            </div>
            <div className="grid-two-columns">
              <label className="form-label">
                <span>参数 Key</span>
                <input
                  className="input"
                  value={parameter.key}
                  onChange={event => updateParameter(parameter.id, { key: event.target.value })}
                  placeholder="如 min_spend, lookback_days"
                />
              </label>
              <label className="form-label">
                <span>显示名称</span>
                <input
                  className="input"
                  value={parameter.label ?? ''}
                  onChange={event => updateParameter(parameter.id, { label: event.target.value })}
                  placeholder="参数描述，供操作人员理解"
                />
              </label>
            </div>

            <div className="grid-two-columns">
              <label className="form-label">
                <span>类型</span>
                <select
                  className="select"
                  value={parameter.type}
                  onChange={event =>
                    updateParameter(parameter.id, {
                      type: event.target.value as RuleParameter['type']
                    })
                  }
                >
                  <option value="string">字符串</option>
                  <option value="number">数字</option>
                  <option value="boolean">布尔值</option>
                  <option value="enum">枚举</option>
                </select>
              </label>

              <label className="form-label checkbox-label">
                <input
                  type="checkbox"
                  checked={parameter.required ?? false}
                  onChange={event => updateParameter(parameter.id, { required: event.target.checked })}
                />
                必填
              </label>
            </div>

            <label className="form-label">
              <span>默认值 / 枚举选项</span>
              <input
                className="input"
                value={String(parameter.defaultValue ?? '')}
                onChange={event => updateParameter(parameter.id, { defaultValue: event.target.value })}
                placeholder={
                  parameter.type === 'enum'
                    ? '枚举值请使用逗号分隔，例如: low,medium,high'
                    : '留空表示无默认值'
                }
              />
            </label>

            <label className="form-label">
              <span>参数说明</span>
              <textarea
                className="textarea"
                rows={2}
                value={parameter.description ?? ''}
                onChange={event =>
                  updateParameter(parameter.id, { description: event.target.value })
                }
              />
            </label>
          </div>
        ))}
      </section>
    </form>
  )
}

export default RuleDefinitionForm
