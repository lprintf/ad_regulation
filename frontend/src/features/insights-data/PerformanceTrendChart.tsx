import { useState, useMemo } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { cn } from '@/lib/utils'
import type { InsightRecord } from '../../types/insights'

interface PerformanceTrendChartProps {
  data: InsightRecord[]
  onDateSelect?: (date: string) => void
  selectedDate?: string | null
}

const METRIC_CONFIG = [
  { key: 'spend', label: 'Spend ($)', color: '#3b82f6', yAxisId: 'left' },
  { key: 'roas', label: 'ROAS', color: '#22c55e', yAxisId: 'roas' },
  { key: 'ctr', label: 'CTR (%)', color: '#eab308', yAxisId: 'percent' },
  { key: 'impressions', label: 'Impressions', color: '#10b981', yAxisId: 'right' },
  { key: 'reach', label: 'Reach', color: '#8b5cf6', yAxisId: 'right' },
  { key: 'clicks', label: 'Clicks', color: '#f59e0b', yAxisId: 'right' },
  { key: 'cpc', label: 'CPC ($)', color: '#6366f1', yAxisId: 'left' },
  { key: 'cpm', label: 'CPM ($)', color: '#8b5cf6', yAxisId: 'left' },
  { key: 'inlineLinkClicks', label: 'Inline Link Clicks', color: '#ef4444', yAxisId: 'right' },
  { key: 'outboundClicks', label: 'Outbound Clicks', color: '#ec4899', yAxisId: 'right' },
  { key: 'landingPageView', label: 'Landing Page Views', color: '#06b6d4', yAxisId: 'right' },
  { key: 'onsiteWebAddToCart', label: 'Add to Cart', color: '#84cc16', yAxisId: 'right' },
  { key: 'onsiteWebCheckout', label: 'Checkout', color: '#f97316', yAxisId: 'right' },
  { key: 'onsiteWebPurchase', label: 'Purchase', color: '#14b8a6', yAxisId: 'right' },
  { key: 'onsiteWebPurchaseValue', label: 'Purchase Value ($)', color: '#a855f7', yAxisId: 'left' },
] as const

type MetricKey = typeof METRIC_CONFIG[number]['key']

const PerformanceTrendChart = ({ data, onDateSelect, selectedDate }: PerformanceTrendChartProps) => {
  const [selectedMetrics, setSelectedMetrics] = useState<MetricKey[]>(['spend', 'roas', 'ctr'])

  const chartData = useMemo(() => {
    const dateMap = new Map<string, Record<string, number>>()
    data.forEach(record => {
      const date = record.date
      if (!dateMap.has(date)) dateMap.set(date, {})
      const metrics = dateMap.get(date)!
      METRIC_CONFIG.forEach(config => {
        const value = record.metrics[config.key as keyof typeof record.metrics] || 0
        metrics[config.key] = (metrics[config.key] || 0) + value
      })
    })
    return Array.from(dateMap.entries())
      .map(([date, metrics]) => ({ date, ...metrics }))
      .sort((a, b) => a.date.localeCompare(b.date))
  }, [data])

  const toggleMetric = (metricKey: MetricKey) => {
    setSelectedMetrics(prev =>
      prev.includes(metricKey) ? prev.filter(k => k !== metricKey) : [...prev, metricKey]
    )
  }

  const handleChartClick = (data: any) => {
    if (data?.activePayload?.[0]?.payload?.date && onDateSelect) {
      onDateSelect(data.activePayload[0].payload.date)
    }
  }

  if (chartData.length === 0) {
    return <div className="py-8 text-center text-muted-foreground">暂无数据</div>
  }

  return (
    <div>
      {/* Metric Selection */}
      <div className="mb-4 p-4 bg-muted/50 rounded-lg border border-border">
        <div className="mb-2 font-semibold text-sm">选择指标 (点击切换):</div>
        <div className="flex flex-wrap gap-2">
          {METRIC_CONFIG.map(config => (
            <button
              key={config.key}
              onClick={() => toggleMetric(config.key)}
              className={cn(
                "px-3 py-1.5 rounded text-sm font-medium border-2 transition-all",
                selectedMetrics.includes(config.key)
                  ? "text-white"
                  : "bg-white"
              )}
              style={{
                borderColor: config.color,
                backgroundColor: selectedMetrics.includes(config.key) ? config.color : undefined,
                color: selectedMetrics.includes(config.key) ? 'white' : config.color,
              }}
            >
              {config.label}
            </button>
          ))}
        </div>
        {selectedDate && (
          <div className="mt-3 px-3 py-2 bg-blue-50 border border-blue-500 rounded text-blue-800 text-sm">
            已选择日期: <strong>{selectedDate}</strong> (点击图表上的点可选择不同日期)
          </div>
        )}
      </div>

      {/* Chart */}
      {selectedMetrics.length === 0 ? (
        <div className="py-8 text-center text-muted-foreground">请至少选择一个指标</div>
      ) : (
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={chartData} onClick={handleChartClick} style={{ cursor: 'pointer' }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
            <XAxis dataKey="date" tick={{ fontSize: 12 }} angle={-45} textAnchor="end" height={80} />

            {selectedMetrics.some(m => METRIC_CONFIG.find(c => c.key === m)?.yAxisId === 'left') && (
              <YAxis yAxisId="left" tick={{ fontSize: 12 }} label={{ value: 'Amount ($)', angle: -90, position: 'insideLeft' }} />
            )}
            {selectedMetrics.some(m => METRIC_CONFIG.find(c => c.key === m)?.yAxisId === 'right') && (
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12 }} label={{ value: 'Count', angle: 90, position: 'insideRight' }} />
            )}
            {selectedMetrics.some(m => METRIC_CONFIG.find(c => c.key === m)?.yAxisId === 'roas') && (
              <YAxis yAxisId="roas" orientation="right" tick={{ fontSize: 12, fill: '#22c55e' }} axisLine={{ stroke: '#22c55e' }} tickLine={{ stroke: '#22c55e' }} />
            )}
            {selectedMetrics.some(m => METRIC_CONFIG.find(c => c.key === m)?.yAxisId === 'percent') && (
              <YAxis yAxisId="percent" orientation="right" tick={{ fontSize: 12, fill: '#eab308' }} axisLine={{ stroke: '#eab308' }} tickLine={{ stroke: '#eab308' }} tickFormatter={(value) => `${(value * 100).toFixed(1)}%`} />
            )}

            <Tooltip
              contentStyle={{ background: 'rgba(255,255,255,0.96)', border: '1px solid #e0e0e0', borderRadius: '8px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}
              formatter={(value: any, name: string) => {
                if (typeof value === 'number') {
                  if (name === 'CTR (%)') return `${(value * 100).toFixed(2)}%`
                  return value.toFixed(2)
                }
                return value
              }}
            />
            <Legend wrapperStyle={{ paddingTop: '20px' }} iconType="line" />

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

      <div className="mt-4 text-sm text-center text-muted-foreground">
        共 {chartData.length} 天数据 · 点击图表上的数据点可选择该日期作为规则测试参数
      </div>
    </div>
  )
}

export default PerformanceTrendChart
