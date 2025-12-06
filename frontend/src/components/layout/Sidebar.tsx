import { NavLink } from 'react-router-dom'

const navItems = [
  {
    label: '广告管理',
    to: '/ads',
    description: '查看广告数据与绑定规则'
  },
  {
    label: '规则管理',
    to: '/rules',
    description: '管理规则定义、配置与绑定'
  },
  {
    label: '调度管理',
    to: '/scheduler',
    description: '调度任务与执行日志'
  },
  {
    label: '账号管理',
    to: '/accounts',
    description: '广告账号授权与数据同步'
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
