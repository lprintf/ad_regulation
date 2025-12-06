import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchEntityTimeline } from '../api/ruleEngine'

type MetricType = 'spend' | 'roas' | 'ctr'

const METRIC_CONFIG: Record<MetricType, { label: string; color: string; format: (v: number) => string }> = {
  spend: { label: '花费', color: '#3b82f6', format: (v) => `$${v.toFixed(2)}` },
  roas: { label: 'ROAS', color: '#10b981', format: (v) => v.toFixed(2) },
  ctr: { label: 'CTR', color: '#f59e0b', format: (v) => `${(v * 100).toFixed(2)}%` },
}

interface DateTimelineSelectorProps {
  adAccountId: string
  entityId: string
  entityType: string
  value: string
  onChange: (date: string) => void
}

const DateTimelineSelector = ({
  adAccountId,
  entityId,
  entityType,
  value,
  onChange
}: DateTimelineSelectorProps) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [hoveredDate, setHoveredDate] = useState<string | null>(null)
  const [selectedMetric, setSelectedMetric] = useState<MetricType>('spend')

  const { data: timeline, isLoading } = useQuery({
    queryKey: ['entity-timeline', adAccountId, entityId, entityType],
    queryFn: () => fetchEntityTimeline({
      adAccountId,
      entityId,
      entityType
    }),
    enabled: !!adAccountId && !!entityId
  })

  useEffect(() => {
    if (!timeline || !canvasRef.current || timeline.daily_data.length === 0) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dailyData = timeline.daily_data
    const width = canvas.width
    const height = canvas.height
    const padding = { top: 20, right: 20, bottom: 40, left: 60 }
    const chartWidth = width - padding.left - padding.right
    const chartHeight = height - padding.top - padding.bottom

    // Get metric value based on selected metric
    const getMetricValue = (point: typeof dailyData[0]) => {
      switch (selectedMetric) {
        case 'roas': return point.roas || 0
        case 'ctr': return point.ctr || 0
        default: return point.spend
      }
    }

    const config = METRIC_CONFIG[selectedMetric]

    // Clear canvas
    ctx.clearRect(0, 0, width, height)

    // Find max value for scaling
    const maxValue = Math.max(...dailyData.map(getMetricValue), 0.01)

    // Draw grid lines
    ctx.strokeStyle = '#e0e0e0'
    ctx.lineWidth = 1
    for (let i = 0; i <= 5; i++) {
      const y = padding.top + (chartHeight / 5) * i
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(padding.left + chartWidth, y)
      ctx.stroke()

      // Y-axis labels
      ctx.fillStyle = '#666'
      ctx.font = '11px sans-serif'
      ctx.textAlign = 'right'
      const labelValue = maxValue * (1 - i / 5)
      ctx.fillText(config.format(labelValue), padding.left - 5, y + 4)
    }

    // Draw line chart
    ctx.strokeStyle = config.color
    ctx.lineWidth = 2
    ctx.beginPath()

    dailyData.forEach((point, index) => {
      const x = padding.left + (chartWidth / Math.max(dailyData.length - 1, 1)) * index
      const metricValue = getMetricValue(point)
      const y = padding.top + chartHeight - (metricValue / maxValue) * chartHeight

      if (index === 0) {
        ctx.moveTo(x, y)
      } else {
        ctx.lineTo(x, y)
      }
    })
    ctx.stroke()

    // Draw data points
    dailyData.forEach((point, index) => {
      const x = padding.left + (chartWidth / Math.max(dailyData.length - 1, 1)) * index
      const metricValue = getMetricValue(point)
      const y = padding.top + chartHeight - (metricValue / maxValue) * chartHeight

      // Highlight selected date
      if (point.date === value) {
        ctx.fillStyle = '#ef4444'
        ctx.beginPath()
        ctx.arc(x, y, 5, 0, 2 * Math.PI)
        ctx.fill()
      } else if (point.date === hoveredDate) {
        ctx.fillStyle = config.color + '99'
        ctx.beginPath()
        ctx.arc(x, y, 4, 0, 2 * Math.PI)
        ctx.fill()
      } else {
        ctx.fillStyle = config.color
        ctx.beginPath()
        ctx.arc(x, y, 3, 0, 2 * Math.PI)
        ctx.fill()
      }
    })

    // Draw X-axis dates
    ctx.fillStyle = '#666'
    ctx.font = '10px sans-serif'
    ctx.textAlign = 'center'
    const step = Math.max(1, Math.floor(dailyData.length / 10))
    dailyData.forEach((point, index) => {
      if (index % step === 0 || index === dailyData.length - 1) {
        const x = padding.left + (chartWidth / Math.max(dailyData.length - 1, 1)) * index
        const dateLabel = point.date.slice(5) // Show MM-DD only
        ctx.fillText(dateLabel, x, height - padding.bottom + 15)
      }
    })
  }, [timeline, value, hoveredDate, selectedMetric])

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!timeline || !canvasRef.current) return

    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const x = (e.clientX - rect.left) * scaleX

    const dailyData = timeline.daily_data
    const padding = { left: 60, right: 20 }
    const chartWidth = canvas.width - padding.left - padding.right

    const pointWidth = chartWidth / Math.max(dailyData.length - 1, 1)
    const clickedIndex = Math.round((x - padding.left) / pointWidth)

    if (clickedIndex >= 0 && clickedIndex < dailyData.length) {
      onChange(dailyData[clickedIndex].date)
    }
  }

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!timeline || !canvasRef.current) return

    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const x = (e.clientX - rect.left) * scaleX

    const dailyData = timeline.daily_data
    const padding = { left: 60, right: 20 }
    const chartWidth = canvas.width - padding.left - padding.right

    const pointWidth = chartWidth / Math.max(dailyData.length - 1, 1)
    const hoveredIndex = Math.round((x - padding.left) / pointWidth)

    if (hoveredIndex >= 0 && hoveredIndex < dailyData.length) {
      setHoveredDate(dailyData[hoveredIndex].date)
    } else {
      setHoveredDate(null)
    }
  }

  if (isLoading) {
    return <div style={{ padding: '1rem', color: '#666' }}>加载时间线数据...</div>
  }

  if (!timeline || timeline.total_days === 0) {
    return (
      <div style={{ padding: '1rem', color: '#666' }}>
        该实体暂无历史数据
      </div>
    )
  }

  const hoveredPoint = timeline.daily_data.find(d => d.date === hoveredDate)

  return (
    <div>
      {/* Metric selector */}
      <div style={{ marginBottom: '0.5rem', display: 'flex', gap: '0.5rem' }}>
        {(Object.keys(METRIC_CONFIG) as MetricType[]).map(metric => (
          <button
            key={metric}
            onClick={() => setSelectedMetric(metric)}
            style={{
              padding: '4px 12px',
              fontSize: '12px',
              border: `1px solid ${METRIC_CONFIG[metric].color}`,
              borderRadius: '4px',
              backgroundColor: selectedMetric === metric ? METRIC_CONFIG[metric].color : 'transparent',
              color: selectedMetric === metric ? '#fff' : METRIC_CONFIG[metric].color,
              cursor: 'pointer',
              fontWeight: selectedMetric === metric ? 600 : 400,
            }}
          >
            {METRIC_CONFIG[metric].label}
          </button>
        ))}
      </div>

      <div style={{ position: 'relative' }}>
        <canvas
          ref={canvasRef}
          width={600}
          height={250}
          onClick={handleCanvasClick}
          onMouseMove={handleCanvasMouseMove}
          onMouseLeave={() => setHoveredDate(null)}
          style={{
            cursor: 'pointer',
            border: '1px solid #e0e0e0',
            borderRadius: '4px',
            display: 'block',
            width: '100%',
            maxWidth: '600px'
          }}
        />
        {hoveredPoint && (
          <div style={{
            position: 'absolute',
            top: '10px',
            right: '10px',
            backgroundColor: 'rgba(255, 255, 255, 0.95)',
            padding: '8px 12px',
            borderRadius: '4px',
            border: '1px solid #e0e0e0',
            fontSize: '12px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
          }}>
            <div><strong>{hoveredPoint.date}</strong></div>
            <div style={{ color: METRIC_CONFIG.spend.color }}>
              花费: ${hoveredPoint.spend.toFixed(2)}
            </div>
            <div>点击: {hoveredPoint.clicks} | 展示: {hoveredPoint.impressions.toLocaleString()}</div>
            {hoveredPoint.roas !== undefined && (
              <div style={{ color: METRIC_CONFIG.roas.color }}>
                ROAS: {hoveredPoint.roas.toFixed(2)}
              </div>
            )}
            {hoveredPoint.ctr !== undefined && (
              <div style={{ color: METRIC_CONFIG.ctr.color }}>
                CTR: {(hoveredPoint.ctr * 100).toFixed(2)}%
              </div>
            )}
          </div>
        )}
      </div>
      <div style={{ marginTop: '0.5rem', fontSize: '0.875rem', color: '#666' }}>
        {timeline.total_days} 天数据 ({timeline.date_range.since} 到 {timeline.date_range.until})
        {value && <span style={{ marginLeft: '1rem', color: '#3b82f6', fontWeight: 500 }}>
          已选择: {value}
        </span>}
      </div>
    </div>
  )
}

export default DateTimelineSelector
