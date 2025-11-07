import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { InputHTMLAttributes } from 'react'
import { fetchAdAccounts } from '../api/adAccounts'
import type { AdAccount } from '../types/ad-accounts'

type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'list'>

interface AdAccountSelectProps extends InputProps {
  value: string
  onChange: (value: string) => void
  helperText?: string
  allowClear?: boolean
  className?: string
  inputClassName?: string
  showSelectedName?: boolean
}

const ensureActPrefix = (value: string): string => {
  const trimmed = value.trim()
  if (!trimmed) {
    return ''
  }
  return trimmed.toLowerCase().startsWith('act_')
    ? `act_${trimmed.slice(4)}`
    : `act_${trimmed.replace(/^act_/i, '')}`
}

const AdAccountSelect = ({
  value,
  onChange,
  helperText,
  allowClear,
  className,
  inputClassName = 'input',
  showSelectedName = true,
  ...inputProps
}: AdAccountSelectProps) => {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [isOpen, setIsOpen] = useState(false)
  const [highlightIndex, setHighlightIndex] = useState<number>(-1)
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['ad-accounts'],
    queryFn: fetchAdAccounts,
    staleTime: 5 * 60_000
  })

  const accounts = data ?? []
  const trimmedValue = value.trim()

  const fuzzyMatches = useMemo(() => {
    if (accounts.length === 0) {
      return []
    }
    const query = trimmedValue.toLowerCase()
    if (!query) {
      return accounts.slice(0, 20).map(account => ({ account, score: 0 }))
    }

    const normalize = (text: string) => text.toLowerCase()

    const getScore = (candidate: string): number | null => {
      const needle = query
      const haystack = normalize(candidate)
      let score = 0
      let needleIndex = 0
      for (let i = 0; i < haystack.length && needleIndex < needle.length; i += 1) {
        if (haystack[i] === needle[needleIndex]) {
          score += i
          needleIndex += 1
        }
      }
      if (needleIndex !== needle.length) {
        return null
      }
      return score
    }

    const result = accounts
      .map(account => {
        const idScore = getScore(account.id)
        const nameScore = account.name ? getScore(account.name) : null
        if (idScore === null && nameScore === null) {
          return null
        }
        const score = Math.min(
          idScore ?? Number.POSITIVE_INFINITY,
          nameScore ?? Number.POSITIVE_INFINITY
        )
        return { account, score }
      })
      .filter((item): item is { account: AdAccount; score: number } => item !== null)
      .sort((a, b) => a.score - b.score)
      .slice(0, 20)

    if (result.length === 0 && !ensureActPrefix(trimmedValue)) {
      return accounts.slice(0, 20).map(account => ({ account, score: 0 }))
    }
    return result
  }, [accounts, trimmedValue])

  const selectedAccount = useMemo(() => {
    if (!showSelectedName) {
      return null
    }
    const normalized = ensureActPrefix(trimmedValue)
    if (!normalized) {
      return null
    }
    return accounts.find(account => account.id === normalized) ?? null
  }, [accounts, trimmedValue, showSelectedName])

  useEffect(() => {
    setHighlightIndex(fuzzyMatches.length > 0 ? 0 : -1)
  }, [fuzzyMatches.length, trimmedValue])

  useEffect(() => {
    const listenerOptions: AddEventListenerOptions = { capture: true }
    const handlePointerDown = (event: PointerEvent) => {
      if (!containerRef.current) {
        return
      }
      if (!containerRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    window.addEventListener('pointerdown', handlePointerDown, listenerOptions)
    return () => {
      window.removeEventListener('pointerdown', handlePointerDown, listenerOptions)
    }
  }, [])

  const effectivePlaceholder =
    inputProps.placeholder ??
    (isLoading || isFetching ? '广告账号列表加载中…' : '选择或输入广告账号 ID')

  const clearable = allowClear ?? !inputProps.required

  const statusMessage = (() => {
    if (isError) {
      return (
        <div className="form-hint" style={{ color: 'var(--color-danger)', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <span>广告账号加载失败</span>
          <button
            type="button"
            className="button button--ghost"
            onClick={() => refetch()}
            style={{ padding: '0 0.5rem', fontSize: '0.78rem' }}
          >
            重试
          </button>
        </div>
      )
    }
    if (isLoading || isFetching) {
      return <div className="form-hint">广告账号列表加载中…</div>
    }
    if (selectedAccount) {
      return (
        <div className="form-hint">
          已选择：{selectedAccount.name}
          {!selectedAccount.hasAuth && (
            <span style={{ color: 'var(--color-warning)', marginLeft: '0.35rem' }}>（未配置授权）</span>
          )}
        </div>
      )
    }
    return helperText ? <div className="form-hint">{helperText}</div> : null
  })()

  const handleSelect = (account: AdAccount) => {
    onChange(account.id)
    setIsOpen(false)
  }

  const handleKeyDown: React.KeyboardEventHandler<HTMLInputElement> = event => {
    if (!isOpen && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
      setIsOpen(true)
      event.preventDefault()
      return
    }
    if (!fuzzyMatches.length) {
      return
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlightIndex(current =>
        current < fuzzyMatches.length - 1 ? current + 1 : fuzzyMatches.length - 1
      )
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlightIndex(current => (current > 0 ? current - 1 : 0))
    } else if (event.key === 'Enter') {
      if (highlightIndex >= 0 && highlightIndex < fuzzyMatches.length) {
        event.preventDefault()
        handleSelect(fuzzyMatches[highlightIndex].account)
      }
    } else if (event.key === 'Escape') {
      setIsOpen(false)
    }
  }

  return (
    <div
      ref={containerRef}
      className={['ad-account-select', className].filter(Boolean).join(' ')}
    >
      <div
        className="ad-account-select__control"
        style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}
      >
        <input
          {...inputProps}
          className={inputClassName}
          value={value}
          onChange={event => {
            onChange(event.target.value)
            setIsOpen(true)
          }}
          placeholder={effectivePlaceholder}
          autoComplete="off"
          spellCheck={false}
          onFocus={event => {
            inputProps.onFocus?.(event)
            setIsOpen(true)
          }}
          onBlur={inputProps.onBlur}
          onKeyDown={handleKeyDown}
        />
        {clearable && value && (
          <button
            type="button"
            className="button button--ghost"
            onClick={() => onChange('')}
            disabled={inputProps.disabled}
            style={{ padding: '0.35rem 0.75rem', whiteSpace: 'nowrap' }}
          >
            清除
          </button>
        )}
      </div>

      {isOpen && fuzzyMatches.length > 0 && (
        <div className="ad-account-select__dropdown">
          {fuzzyMatches.map(({ account }, index) => {
            const active = index === highlightIndex
            return (
              <button
                type="button"
                key={account.id}
                className={[
                  'ad-account-select__option',
                  active ? 'ad-account-select__option--active' : ''
                ]
                  .filter(Boolean)
                  .join(' ')}
                onMouseDown={event => {
                  // Prevent input blur before selection
                  event.preventDefault()
                }}
                onClick={() => handleSelect(account)}
              >
                <div className="ad-account-select__option-title">{account.name}</div>
                <div className="ad-account-select__option-subtitle">{account.id}</div>
                {!account.hasAuth && (
                  <span className="ad-account-select__option-badge">未授权</span>
                )}
              </button>
            )
          })}
        </div>
      )}

      {statusMessage}
    </div>
  )
}

export default AdAccountSelect
