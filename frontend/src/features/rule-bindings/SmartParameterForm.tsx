import { type ParametersSchema } from '../../types/rule-engine'
import DateTimelineSelector from '../../components/DateTimelineSelector'

interface SmartParameterFormProps {
  schema: ParametersSchema
  values: Record<string, any>
  onChange: (values: Record<string, any>) => void
  errors?: Record<string, string>
  // Context for date timeline selector
  adAccountId?: string
  entityId?: string
  entityType?: string
}

const SmartParameterForm = ({
  schema,
  values,
  onChange,
  errors = {},
  adAccountId,
  entityId,
  entityType
}: SmartParameterFormProps) => {
  const updateValue = (key: string, value: any) => {
    onChange({ ...values, [key]: value })
  }

  return (
    <div className="smart-parameter-form">
      {Object.entries(schema).map(([key, config]) => (
        <ParameterField
          key={key}
          paramKey={key}
          config={config}
          value={values[key]}
          onChange={(value) => updateValue(key, value)}
          error={errors[key]}
          adAccountId={adAccountId}
          entityId={entityId}
          entityType={entityType}
        />
      ))}
    </div>
  )
}

interface ParameterFieldProps {
  paramKey: string
  config: ParametersSchema[string]
  value: any
  onChange: (value: any) => void
  error?: string
  adAccountId?: string
  entityId?: string
  entityType?: string
}

const ParameterField = ({ paramKey, config, value, onChange, error, adAccountId, entityId, entityType }: ParameterFieldProps) => {
  const defaultValue = config.default ?? config.defaultValue
  const currentValue = value !== undefined && value !== null ? value : defaultValue

  // Special handling for evaluation_date with timeline selector
  const isEvaluationDate = paramKey === 'evaluation_date' && config.type === 'string'
  const canShowTimeline = isEvaluationDate && adAccountId && entityId && entityType

  const renderInput = () => {
    // Date timeline selector for evaluation_date
    if (canShowTimeline) {
      return (
        <div>
          <DateTimelineSelector
            adAccountId={adAccountId!}
            entityId={entityId!}
            entityType={entityType!}
            value={currentValue || ''}
            onChange={onChange}
          />
          <div style={{ marginTop: '0.5rem' }}>
            <input
              type="text"
              className={`input ${error ? 'input--error' : ''}`}
              value={currentValue || ''}
              onChange={(e) => onChange(e.target.value)}
              placeholder="YYYY-MM-DD 或点击图表选择"
              style={{ width: '100%' }}
            />
          </div>
        </div>
      )
    }

    // evaluation_date without timeline (missing ad account info)
    if (isEvaluationDate) {
      return (
        <div>
          <input
            type="text"
            className={`input ${error ? 'input--error' : ''}`}
            value={currentValue || ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder="YYYY-MM-DD（手动输入日期）"
            style={{ width: '100%' }}
          />
          {!adAccountId && (
            <div style={{
              marginTop: '0.5rem',
              padding: '0.5rem',
              background: '#fff3cd',
              border: '1px solid #ffc107',
              borderRadius: '4px',
              fontSize: '0.85rem',
              color: '#856404'
            }}>
              ⚠️ 无法加载时间轴图表：缺少广告账号信息。请在绑定规则时设置 ad_account_id。
            </div>
          )}
        </div>
      )
    }

    switch (config.type) {
      case 'number':
      case 'integer':
        return (
          <>
            <input
              type="number"
              className={`input ${error ? 'input--error' : ''}`}
              value={currentValue ?? ''}
              onChange={(e) => {
                const val = e.target.value === '' ? null :
                  config.type === 'integer' ? parseInt(e.target.value, 10) : parseFloat(e.target.value)
                onChange(val)
              }}
              min={config.min}
              max={config.max}
              step={config.step ?? (config.type === 'integer' ? 1 : 0.1)}
              required={config.required}
            />
            {config.unit && (
              <span className="input-unit" style={{ marginLeft: '0.5rem', color: 'var(--color-text-muted)' }}>
                {config.unit}
              </span>
            )}
          </>
        )

      case 'boolean':
        return (
          <label className="checkbox-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <input
              type="checkbox"
              checked={currentValue ?? false}
              onChange={(e) => onChange(e.target.checked)}
            />
            <span>{config.label}</span>
          </label>
        )

      case 'enum':
        return (
          <select
            className={`select ${error ? 'select--error' : ''}`}
            value={currentValue ?? ''}
            onChange={(e) => onChange(e.target.value)}
            required={config.required}
          >
            <option value="">请选择...</option>
            {config.options?.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        )

      case 'string':
      default:
        return (
          <input
            type="text"
            className={`input ${error ? 'input--error' : ''}`}
            value={currentValue ?? ''}
            onChange={(e) => onChange(e.target.value)}
            required={config.required}
          />
        )
    }
  }

  // Boolean type has label integrated in the checkbox
  if (config.type === 'boolean') {
    return (
      <div className="form-label" style={{ marginBottom: '1rem' }}>
        {renderInput()}
        {config.description && (
          <small className="form-hint" style={{ marginTop: '0.25rem', display: 'block' }}>
            {config.description}
          </small>
        )}
        {config.hint && (
          <small className="form-hint-extra" style={{
            marginTop: '0.25rem',
            display: 'block',
            color: 'var(--color-info)'
          }}>
            💡 {config.hint}
          </small>
        )}
        {error && (
          <div className="form-error" style={{ marginTop: '0.25rem', color: 'var(--color-danger)' }}>
            {error}
          </div>
        )}
      </div>
    )
  }

  return (
    <label className="form-label" style={{ marginBottom: '1rem' }}>
      <span className="parameter-label" style={{ display: 'block', marginBottom: '0.25rem', fontWeight: 500 }}>
        {config.label || paramKey}
        {config.required && <span style={{ color: 'var(--color-danger)', marginLeft: '0.25rem' }}>*</span>}
        {config.unit && config.type !== 'number' && config.type !== 'integer' && (
          <span style={{ marginLeft: '0.5rem', color: 'var(--color-text-muted)', fontWeight: 400 }}>
            ({config.unit})
          </span>
        )}
      </span>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        {renderInput()}
      </div>

      {config.description && (
        <small className="form-hint" style={{ marginTop: '0.25rem', display: 'block' }}>
          {config.description}
        </small>
      )}

      {config.hint && (
        <small className="form-hint-extra" style={{
          marginTop: '0.25rem',
          display: 'block',
          color: 'var(--color-info)',
          fontStyle: 'italic'
        }}>
          💡 {config.hint}
        </small>
      )}

      {config.min !== undefined || config.max !== undefined ? (
        <small className="form-hint" style={{ marginTop: '0.25rem', display: 'block', color: 'var(--color-text-muted)' }}>
          范围: {config.min ?? '−∞'} ~ {config.max ?? '+∞'}
          {config.step && ` (步进: ${config.step})`}
        </small>
      ) : null}

      {error && (
        <div className="form-error" style={{ marginTop: '0.25rem', color: 'var(--color-danger)', fontSize: '0.875rem' }}>
          ⚠️ {error}
        </div>
      )}
    </label>
  )
}

export default SmartParameterForm
