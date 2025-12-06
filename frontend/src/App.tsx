import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Spin } from 'antd'
import AppLayout from './components/layout/AppLayout'

// 路由级懒加载
const AdManagementPage = lazy(() => import('./features/insights-data/InsightsDataPage'))
const RuleManagementPage = lazy(() => import('./features/rule-definitions/RuleDefinitionsPage'))
const SchedulerManagementPage = lazy(() => import('./features/scheduler/SchedulerManagementPage'))
const AccountManagementPage = lazy(() => import('./features/accounts/AccountManagementPage'))

const App = () => {
  return (
    <BrowserRouter>
      <AppLayout>
        <Suspense fallback={
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: '60vh'
          }}>
            <Spin size="large" tip="加载中..." />
          </div>
        }>
          <Routes>
            <Route index element={<Navigate to="/ads" replace />} />
            <Route path="/ads" element={<AdManagementPage />} />
            <Route path="/rules" element={<RuleManagementPage />} />
            <Route path="/scheduler" element={<SchedulerManagementPage />} />
            <Route path="/accounts" element={<AccountManagementPage />} />
            {/* Legacy redirects */}
            <Route path="/insights/data" element={<Navigate to="/ads" replace />} />
            <Route path="/rules/definitions" element={<Navigate to="/rules" replace />} />
            <Route path="/rules/bindings" element={<Navigate to="/rules" replace />} />
            <Route path="/rules/executions" element={<Navigate to="/scheduler" replace />} />
            <Route path="/rules/scheduler" element={<Navigate to="/scheduler" replace />} />
            <Route path="/insights/sync-runs" element={<Navigate to="/accounts" replace />} />
            <Route path="/integrations/facebook" element={<Navigate to="/accounts" replace />} />
            <Route path="*" element={<Navigate to="/ads" replace />} />
          </Routes>
        </Suspense>
      </AppLayout>
    </BrowserRouter>
  )
}

export default App
