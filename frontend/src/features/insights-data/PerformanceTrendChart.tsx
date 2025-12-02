import { useState, useMemo } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import type { InsightRecord } from '../../types/insights'

interface PerformanceTrendChartProps {
  data: InsightRecord[]
  onDateSelect?: (date: string) => void
  selectedDate?: string | null
}

const METRIC_CONFIG = [
  { key: 'spend', label: 'Spend ($)', color: '#3b82f6', yAxisId: 'left' },
  { key: 'impressions', label: 'Impressions', color: '#10b981', yAxisId: 'right' },
  { key: 'reach', label: 'Reach', color: '#8b5cf6', yAxisId: 'right' },
  { key: 'clicks', label: 'Clicks', color: '#f59e0b', yAxisId: 'right' },
  { key: 'inlineLinkClicks', label: 'Inline Link Clicks', color: '#ef4444', yAxisId: 'right' },
  { key: 'outboundClicks', label: 'Outbound Clicks', color: '#ec4899', yAxisId: 'right' },
  { key: 'landingPageView', label: 'Landing Page Views', color: '#06b6d4', yAxisId: 'right' },
  { key: 'onsiteWebAddToCart', label: 'Add to Cart', color: '#84cc16', yAxisId: 'right' },
  { key: 'onsiteWebCheckout', label: 'Checkout', color: '#f97316', yAxisId: 'right' },
  { key: 'onsiteWebPurchase', label: 'Purchase', color: '#14b8a6', yAxisId: 'right' },
  { key: 'onsiteWebPurchaseValue', label: 'Purchase Value ($)', color: '#a855f7', yAxisId: 'left' },
] as const

type MetricKey = typeof METRIC_CONFIG[number]['key']

const PerformanceTrendChart = ({
  data,
  onDateSelect,
  selectedDate
}: PerformanceTrendChartProps) => {
  const [selectedMetrics, setSelectedMetrics] = useState<MetricKey[]>(['spend', 'clicks', 'onsiteWebPurchase'])

  // Group by date and aggregate metrics
  const chartData = useMemo(() => {
    const dateMap = new Map<string, Record<string, number>>()

    data.forEach(record => {
      const date = record.date
      if (!dateMap.has(date)) {
        dateMap.set(date, {})
      }
      const metrics = dateMap.get(date)!

      // Aggregate metrics
      METRIC_CONFIG.forEach(config => {
        const value = record.metrics[config.key as keyof typeof record.metrics] || 0
        metrics[config.key] = (metrics[config.key] || 0) + value
      })
    })

    // Convert to array and sort by date
    return Array.from(dateMap.entries())
      .map(([date, metrics]) => ({ date, ...metrics }))
      .sort((a, b) => a.date.localeCompare(b.date))
  }, [data])

  const toggleMetric = (metricKey: MetricKey) => {
    setSelectedMetrics(prev =>
      prev.includes(metricKey)
        ? prev.filter(k => k !== metricKey)
        : [...prev, metricKey]
    )
  }

  const handleChartClick = (data: any) => {
    if (data && data.activePayload && data.activePayload.length > 0) {
      const date = data.activePayload[0].payload.date
      if (date && onDateSelect) {
        onDateSelect(date)
      }
    }
  }

  if (chartData.length === 0) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
        暂无数据
      </div>
    )
  }

  return (
    <div>
      {/* Metric Selection */}
      <div style={{
        marginBottom: '1rem',
        padding: '1rem',
        background: 'var(--color-bg-muted, #fafafa)',
        borderRadius: '8px',
        border: '1px solid var(--color-border, #f0f0f0)'
      }}>
        <div style={{ marginBottom: '0.5rem', fontWeight: 600, fontSize: '0.9rem' }}>
          选择指标 (点击切换):
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {METRIC_CONFIG.map(config => (
            <button
              key={config.key}
              onClick={() => toggleMetric(config.key)}
              style={{
                padding: '6px 12px',
                borderRadius: '4px',
                border: `2px solid ${config.color}`,
                background: selectedMetrics.includes(config.key) ? config.color : 'white',
                color: selectedMetrics.includes(config.key) ? 'white' : config.color,
                cursor: 'pointer',
                fontSize: '0.85rem',
                fontWeight: 500,
                transition: 'all 0.2s'
              }}
            >
              {config.label}
            </button>
          ))}
        </div>
        {selectedDate && (
          <div style={{
            marginTop: '0.75rem',
            padding: '8px 12px',
            background: '#eff6ff',
            border: '1px solid #3b82f6',
            borderRadius: '4px',
            color: '#1e40af',
            fontSize: '0.9rem'
          }}>
            已选择日期: <strong>{selectedDate}</strong> (点击图表上的点可选择不同日期)
          </div>
        )}
      </div>

      {/* Chart */}
      {selectedMetrics.length === 0 ? (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
          请至少选择一个指标
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          <LineChart
            data={chartData}
            onClick={handleChartClick}
            style={{ cursor: 'pointer' }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12 }}
              angle={-45}
              textAnchor="end"
              height={80}
            />

            {/* Left Y-Axis for spend and purchase value */}
            {selectedMetrics.some(m => METRIC_CONFIG.find(c => c.key === m)?.yAxisId === 'left') && (
              <YAxis
                yAxisId="left"
                tick={{ fontSize: 12 }}
                label={{ value: 'Amount ($)', angle: -90, position: 'insideLeft' }}
              />
            )}

            {/* Right Y-Axis for counts */}
            {selectedMetrics.some(m => METRIC_CONFIG.find(c => c.key === m)?.yAxisId === 'right') && (
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fontSize: 12 }}
                label={{ value: 'Count', angle: 90, position: 'insideRight' }}
              />
            )}

            <Tooltip
              contentStyle={{
                background: 'rgba(255, 255, 255, 0.96)',
                border: '1px solid #e0e0e0',
                borderRadius: '8px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
              }}
              formatter={(value: any) => {
                if (typeof value === 'number') {
                  return value.toFixed(2)
                }
                return value
              }}
            />
            <Legend
              wrapperStyle={{ paddingTop: '20px' }}
              iconType="line"
            />

            {selectedMetrics.map(metricKey => {
              const config = METRIC_CONFIG.find(c => c.key === metricKey)!
              return (
                <Line
                  key={metricKey}
                  type="monotone"
                  dataKey={metricKey}
                  name={config.label}
                  stroke={config.color}
                  strokeWidth={2}
                  yAxisId={config.yAxisId}
                  dot={{ r: 4, fill: config.color }}
                  activeDot={{ r: 6, fill: config.color, stroke: 'white', strokeWidth: 2 }}
                />
              )
            })}
          </LineChart>
        </ResponsiveContainer>
      )}

      <div style={{
        marginTop: '1rem',
        fontSize: '0.85rem',
        color: 'var(--color-text-muted)',
        textAlign: 'center'
      }}>
        共 {chartData.length} 天数据 · 点击图表上的数据点可选择该日期作为规则测试参数
      </div>
    </div>
  )
}

export default PerformanceTrendChart
