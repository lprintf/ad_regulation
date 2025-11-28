import { type ParametersSchema } from '../../types/rule-engine'

interface SmartParameterFormProps {
  schema: ParametersSchema
  values: Record<string, any>
  onChange: (values: Record<string, any>) => void
  errors?: Record<string, string>
}

const SmartParameterForm = ({ schema, values, onChange, errors = {} }: SmartParameterFormProps) => {
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
}

const ParameterField = ({ paramKey, config, value, onChange, error }: ParameterFieldProps) => {
  const defaultValue = config.default ?? config.defaultValue
  const currentValue = value !== undefined && value !== null ? value : defaultValue

  const renderInput = () => {
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
