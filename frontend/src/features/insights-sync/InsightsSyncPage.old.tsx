import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { createInsightsSyncRun, fetchInsightsSyncRuns } from '../../api/insights'
import { formatDateTime, formatRelativeTime } from '../../lib/datetime'
import type {
  InsightAccountSyncStatus,
  InsightSyncStatus,
  InsightSyncTriggerResult
} from '../../types/insights'

const statusClassMap: Record<InsightSyncStatus, string> = {
  pending: 'badge badge--warning',
  running: 'badge badge--info',
  success: 'badge badge--success',
  failed: 'badge badge--failure'
}

const statusLabelMap: Record<InsightSyncStatus, string> = {
  pending: '待同步',
  running: '同步中',
  success: '已完成',
  failed: '失败'
}

const InsightsSyncPage = () => {
  const queryClient = useQueryClient()
  const [accountInput, setAccountInput] = useState('')
  const [sinceDate, setSinceDate] = useState('')
  const [untilDate, setUntilDate] = useState('')
  const [feedback, setFeedback] = useState<
    { type: 'success' | 'error'; message: string } | null
  >(null)
  const [lastResult, setLastResult] = useState<InsightSyncTriggerResult | null>(null)

  const statusQuery = useQuery({
    queryKey: ['insights-sync-runs'],
    queryFn: fetchInsightsSyncRuns,
    refetchInterval: 60_000
  })

  const items: InsightAccountSyncStatus[] = useMemo(() => {
    const data = statusQuery.data ?? []
    return [...data].sort((a, b) => {
      const updatedA = a.updatedAt ?? ''
      const updatedB = b.updatedAt ?? ''
      return updatedB.localeCompare(updatedA)
    })
  }, [statusQuery.data])

  useEffect(() => {
    if (!sinceDate && items.length > 0) {
      const candidates = items
        .map(item => item.since ?? item.until ?? null)
        .filter((value): value is string => Boolean(value))
      if (candidates.length > 0) {
        const earliest = candidates.sort()[0]
        setSinceDate(prev => prev || earliest)
      }
    }
  }, [items, sinceDate])

  useEffect(() => {
    if (!untilDate && items.length > 0) {
      const candidates = items
        .map(item => item.until ?? item.rangeUntil ?? null)
        .filter((value): value is string => Boolean(value))
      if (candidates.length > 0) {
        const latest = [...candidates].sort().reverse()[0]
        setUntilDate(prev => prev || latest)
      }
    }
  }, [items, untilDate])

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ['insights-sync-runs'] })
  }

  const manualSyncMutation = useMutation({
    mutationFn: createInsightsSyncRun,
    onSuccess: (result: InsightSyncTriggerResult) => {
      queryClient.invalidateQueries({ queryKey: ['insights-sync-runs'] })
      const processedCount = Object.keys(result.processedAccounts ?? {}).length
      const failedCount = Object.keys(result.failedAccounts ?? {}).length
      setLastResult(result)
      setFeedback({
        type: failedCount > 0 ? 'error' : 'success',
        message: `本次触发 ${result.totalAccounts} 个账号，成功 ${processedCount} 个，失败 ${failedCount} 个`
      })
    },
    onError: error => {
      const message =
        error instanceof Error ? error.message : '触发补采失败，请稍后再试'
      setLastResult(null)
      setFeedback({ type: 'error', message })
    }
  })

  const parseAccountIds = (raw: string): string[] => {
    const normalized = raw
      .split(/[\s,]+/)
      .map(segment => segment.trim())
      .filter(Boolean)
      .map(value => {
        const stripped = value.replace(/^act_/i, '')
        return stripped ? `act_${stripped}` : ''
      })
      .filter(Boolean)
    return Array.from(new Set(normalized))
  }

  const handleManualSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!sinceDate || !untilDate) {
      setFeedback({ type: 'error', message: '请选择起始和结束日期' })
      return
    }
    if (sinceDate > untilDate) {
      setFeedback({ type: 'error', message: '起始日期需不晚于结束日期' })
      return
    }
    const accountIds = parseAccountIds(accountInput)
    setFeedback(null)
    manualSyncMutation.mutate({
      accountIds: accountIds.length > 0 ? accountIds : undefined,
      since: sinceDate,
      until: untilDate
    })
  }

  return (
    <div className="page">
      <section className="card">
        <div className="card__header">
          <div>
            <div className="card__title">洞察数据同步概览</div>
            <div className="card__subtitle">按广告账号查看最新同步进度与覆盖区间。</div>
          </div>
          <button
            className="button button--ghost"
            onClick={handleRefresh}
            disabled={statusQuery.isFetching}
          >
            {statusQuery.isFetching ? '刷新中…' : '刷新'}
          </button>
        </div>

        <form
          onSubmit={handleManualSubmit}
          className="card__body"
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(220px, 2fr) repeat(2, minmax(140px, 1fr)) auto',
            gap: '1rem',
            alignItems: 'end'
          }}
        >
          <label className="form-label" style={{ display: 'flex', flexDirection: 'column' }}>
            <span>广告账号（可选，多值用逗号或换行分隔）</span>
            <textarea
              className="textarea"
              rows={3}
              value={accountInput}
              onChange={event => setAccountInput(event.target.value)}
              placeholder="act_123, act_456"
              spellCheck={false}
            />
          </label>
          <label className="form-label">
            <span>起始日期</span>
            <input
              className="input"
              type="date"
              value={sinceDate}
              onChange={event => setSinceDate(event.target.value)}
            />
          </label>
          <label className="form-label">
            <span>结束日期</span>
            <input
              className="input"
              type="date"
              value={untilDate}
              onChange={event => setUntilDate(event.target.value)}
            />
          </label>
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              className="button button--primary"
              type="submit"
              disabled={manualSyncMutation.isPending}
            >
              {manualSyncMutation.isPending ? '触发中…' : '手动触发'}
            </button>
            <button
              className="button button--ghost"
              type="button"
              onClick={() => {
                setAccountInput('')
                setSinceDate('')
                setUntilDate('')
                setFeedback(null)
                setLastResult(null)
              }}
              disabled={manualSyncMutation.isPending}
            >
              清空
            </button>
          </div>
          {lastResult && (
            <div
              style={{
                gridColumn: '1 / -1',
                padding: '0.75rem 1rem',
                borderRadius: '0.5rem',
                border: '1px solid var(--color-border)',
                backgroundColor: 'rgba(24, 119, 242, 0.05)'
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>最近一次触发结果</div>
              <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap', fontSize: '0.9rem' }}>
                <div>
                  <div style={{ fontWeight: 600 }}>成功账号</div>
                  {Object.entries(lastResult.processedAccounts).length > 0 ? (
                    <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.2rem' }}>
                      {Object.entries(lastResult.processedAccounts).map(([accountId, summary]) => (
                        <li key={accountId}>
                          {accountId}: {summary.since} → {summary.until} （{summary.mode}，记录 {summary.records}{summary.trigger ? `，触发 ${summary.trigger}` : ``}{summary.triggeredBy ? `（${summary.triggeredBy}）` : ``}）
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div style={{ color: 'var(--color-text-muted)' }}>无</div>
                  )}
                </div>
                <div>
                  <div style={{ fontWeight: 600 }}>失败账号</div>
                  {Object.entries(lastResult.failedAccounts).length > 0 ? (
                    <ul style={{ margin: '0.25rem 0 0', paddingLeft: '1.2rem', color: 'var(--color-danger)' }}>
                      {Object.entries(lastResult.failedAccounts).map(([accountId, reason]) => (
                        <li key={accountId}>
                          {accountId}: {reason}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <div style={{ color: 'var(--color-text-muted)' }}>无</div>
                  )}
                </div>
              </div>
            </div>
          )}
          {feedback && (
            <div
              style={{
                gridColumn: '1 / -1',
                padding: '0.75rem 1rem',
                borderRadius: '0.5rem',
                backgroundColor:
                  feedback.type === 'success'
                    ? 'rgba(38, 176, 108, 0.1)'
                    : 'rgba(225, 77, 64, 0.1)',
                color:
                  feedback.type === 'success'
                    ? 'var(--color-success)'
                    : 'var(--color-danger)'
              }}
            >
              {feedback.message}
            </div>
          )}
        </form>
      </section>

      <section className="card" style={{ marginTop: '1.5rem' }}>
        <div className="card__header">
          <div>
            <div className="card__title">同步记录</div>
            <div className="card__subtitle">展示所有广告账号的最新同步状态与覆盖范围。</div>
          </div>
        </div>
        {statusQuery.isLoading ? (
          <div className="card__body">数据加载中…</div>
        ) : statusQuery.isError ? (
          <div className="card__body" style={{ color: 'var(--color-danger)' }}>
            洞察同步状态获取失败，请稍后刷新重试。
          </div>
        ) : items.length === 0 ? (
          <div className="card__body">暂未找到同步记录。</div>
        ) : (
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: '220px' }}>广告账号</th>
                  <th style={{ width: '100px' }}>状态</th>
                  <th style={{ width: '140px' }}>since</th>
                  <th style={{ width: '140px' }}>until</th>
                  <th style={{ width: '140px' }}>obs since</th>
                  <th style={{ width: '140px' }}>obs until</th>
                  <th style={{ width: '200px' }}>最近同步时间</th>
                  <th style={{ width: '220px' }}>当前窗口</th>
                  <th>异常信息</th>
                  <th style={{ width: '160px' }}>更新于</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => {
                  const badgeClass = statusClassMap[item.status] ?? 'badge'
                  const accountLabel =
                    item.accountName && item.accountName !== item.accountId
                      ? item.accountName
                      : item.accountId
                  return (
                    <tr key={item.accountId}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{accountLabel ?? '—'}</div>
                        <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                          {item.accountId}
                        </div>
                      </td>
                      <td>
                        <span className={badgeClass}>{statusLabelMap[item.status]}</span>
                      </td>
                      <td>{item.since ?? '—'}</td>
                      <td>{item.until ?? '—'}</td>
                      <td>{item.obsSince ?? '—'}</td>
                      <td>{item.obsUntil ?? '—'}</td>
                      <td>
                        {item.lastSyncedAt ? (
                          <div>
                            <div>{formatDateTime(item.lastSyncedAt)}</div>
                            <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                              {formatRelativeTime(item.lastSyncedAt)}
                            </div>
                          </div>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td>
                        {item.rangeSince && item.rangeUntil ? (
                          <div>
                            <div>
                              {item.rangeSince} → {item.rangeUntil}
                            </div>
                            <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                              {[item.mode && `模式：${item.mode}`, item.trigger && `触发：${item.trigger}`, item.triggeredBy && `发起人：${item.triggeredBy}`]
                                .filter(Boolean)
                                .join(' / ')}
                            </div>
                          </div>
                        ) : (
                          <span style={{ color: 'var(--color-text-muted)' }}>无待同步区间</span>
                        )}
                      </td>
                      <td style={{ maxWidth: '260px' }}>
                        {item.lastError ? (
                          <div style={{ color: 'var(--color-danger)' }}>{item.lastError}</div>
                        ) : (
                          <span style={{ color: 'var(--color-text-muted)' }}>—</span>
                        )}
                      </td>
                      <td>
                        {item.updatedAt ? (
                          <div>
                            <div>{formatDateTime(item.updatedAt)}</div>
                            <div style={{ color: 'var(--color-text-muted)', fontSize: '0.75rem' }}>
                              {formatRelativeTime(item.updatedAt)}
                            </div>
                          </div>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

export default InsightsSyncPage

