import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchEntityTimeline, type EntityTimelineDataPoint } from '../api/ruleEngine'

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
    const padding = { top: 20, right: 20, bottom: 40, left: 50 }
    const chartWidth = width - padding.left - padding.right
    const chartHeight = height - padding.top - padding.bottom

    // Clear canvas
    ctx.clearRect(0, 0, width, height)

    // Find max spend for scaling
    const maxSpend = Math.max(...dailyData.map(d => d.spend), 1)

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
      const labelValue = (maxSpend * (1 - i / 5)).toFixed(1)
      ctx.fillText(`$${labelValue}`, padding.left - 5, y + 4)
    }

    // Draw line chart
    ctx.strokeStyle = '#3b82f6'
    ctx.lineWidth = 2
    ctx.beginPath()

    dailyData.forEach((point, index) => {
      const x = padding.left + (chartWidth / (dailyData.length - 1)) * index
      const y = padding.top + chartHeight - (point.spend / maxSpend) * chartHeight

      if (index === 0) {
        ctx.moveTo(x, y)
      } else {
        ctx.lineTo(x, y)
      }
    })
    ctx.stroke()

    // Draw data points
    dailyData.forEach((point, index) => {
      const x = padding.left + (chartWidth / (dailyData.length - 1)) * index
      const y = padding.top + chartHeight - (point.spend / maxSpend) * chartHeight

      // Highlight selected date
      if (point.date === value) {
        ctx.fillStyle = '#ef4444'
        ctx.beginPath()
        ctx.arc(x, y, 5, 0, 2 * Math.PI)
        ctx.fill()
      } else if (point.date === hoveredDate) {
        ctx.fillStyle = '#60a5fa'
        ctx.beginPath()
        ctx.arc(x, y, 4, 0, 2 * Math.PI)
        ctx.fill()
      } else {
        ctx.fillStyle = '#3b82f6'
        ctx.beginPath()
        ctx.arc(x, y, 3, 0, 2 * Math.PI)
        ctx.fill()
      }
    })

    // Draw X-axis dates (show every 3 days to avoid clutter)
    ctx.fillStyle = '#666'
    ctx.font = '10px sans-serif'
    ctx.textAlign = 'center'
    dailyData.forEach((point, index) => {
      if (index % 3 === 0 || index === dailyData.length - 1) {
        const x = padding.left + (chartWidth / (dailyData.length - 1)) * index
        const dateLabel = point.date.slice(5) // Show MM-DD only
        ctx.fillText(dateLabel, x, height - padding.bottom + 15)
      }
    })
  }, [timeline, value, hoveredDate])

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!timeline || !canvasRef.current) return

    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const dailyData = timeline.daily_data

    const padding = { left: 50, right: 20 }
    const chartWidth = canvas.width - padding.left - padding.right

    // Find closest data point
    const pointWidth = chartWidth / (dailyData.length - 1)
    const clickedIndex = Math.round((x - padding.left) / pointWidth)

    if (clickedIndex >= 0 && clickedIndex < dailyData.length) {
      onChange(dailyData[clickedIndex].date)
    }
  }

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!timeline || !canvasRef.current) return

    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    const x = e.clientX - rect.left
    const dailyData = timeline.daily_data

    const padding = { left: 50, right: 20 }
    const chartWidth = canvas.width - padding.left - padding.right

    const pointWidth = chartWidth / (dailyData.length - 1)
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
            <div>花费: ${hoveredPoint.spend.toFixed(2)}</div>
            <div>点击: {hoveredPoint.clicks}</div>
            <div>展示: {hoveredPoint.impressions.toLocaleString()}</div>
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
