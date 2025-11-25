import { useMemo } from 'react'
import UserInfo from './UserInfo'

const getEnvLabel = () => {
  const url = import.meta.env.VITE_API_BASE_URL ?? ''
  if (url.includes('localhost') || url.includes('127.0.0.1')) {
    return '本地开发'
  }

  if (url.includes('staging')) {
    return 'Staging'
  }

  if (url.includes('prod')) {
    return 'Production'
  }

  return 'Custom'
}

const Topbar = () => {
  const currentEnv = useMemo(() => getEnvLabel(), [])

  return (
    <header className="topbar">
      <div className="topbar__path">
        <div className="topbar__title">规则引擎控制台</div>
        <div className="topbar__subtitle">
          按照 docs/rule_engine_development_plan.md 实现的前端界面
        </div>
      </div>
      <div className="topbar__meta">
        <span className="chip chip--primary">API: {currentEnv}</span>
        <span className="chip chip--muted">
          {new Date().toLocaleDateString('zh-CN')}
        </span>
        <UserInfo />
      </div>
    </header>
  )
}

export default Topbar
