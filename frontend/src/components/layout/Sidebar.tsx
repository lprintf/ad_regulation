import { NavLink } from 'react-router-dom'

const navItems = [
  {
    label: '规则定义',
    to: '/rules/definitions',
    description: '管理规则版本与发布状态'
  },
  {
    label: '规则绑定',
    to: '/rules/bindings',
    description: '维护规则与广告实体的绑定关系'
  },
  {
    label: '执行日志',
    to: '/rules/executions',
    description: '查看规则执行结果与审计记录'
  },
  {
    label: '调度监控',
    to: '/rules/scheduler',
    description: 'APScheduler 任务状态与延迟'
  },
  {
    label: '洞察数据',
    to: '/insights/data',
    description: '查询已入库的洞察指标明细'
  },
  {
    label: '洞察同步',
    to: '/insights/sync',
    description: '历史数据同步状态与手动重试'
  },
  {
    label: 'FB 授权',
    to: '/integrations/facebook',
    description: '管理 Facebook App Token 与广告账户'
  }
]

const Sidebar = () => {
  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <span className="sidebar__brand-dot" />
        <div>
          <div className="sidebar__brand-title">AdOps Rule Engine</div>
          <div className="sidebar__brand-subtitle">Automation Control Center</div>
        </div>
      </div>

      <nav className="sidebar__nav">
        {navItems.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              [
                'sidebar__nav-item',
                isActive ? 'sidebar__nav-item--active' : undefined
              ]
                .filter(Boolean)
                .join(' ')
            }
          >
            <div className="sidebar__nav-label">{item.label}</div>
            <div className="sidebar__nav-desc">{item.description}</div>
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}

export default Sidebar
