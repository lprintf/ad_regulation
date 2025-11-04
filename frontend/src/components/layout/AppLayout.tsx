import type { PropsWithChildren } from 'react'
import Sidebar from './Sidebar'
import Topbar from './Topbar'

const AppLayout = ({ children }: PropsWithChildren) => {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-shell__main">
        <Topbar />
        <main className="app-shell__content">{children}</main>
      </div>
    </div>
  )
}

export default AppLayout
