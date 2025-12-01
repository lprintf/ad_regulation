import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Spin } from 'antd'
import AppLayout from './components/layout/AppLayout'

// 路由级懒加载
const RuleDefinitionsPage = lazy(() => import('./features/rule-definitions/RuleDefinitionsPage'))
const RuleBindingsPage = lazy(() => import('./features/rule-bindings/RuleBindingsPage'))
const ExecutionLogsPage = lazy(() => import('./features/execution-logs/ExecutionLogsPage'))
const SchedulerPage = lazy(() => import('./features/scheduler/SchedulerPage'))
const InsightsDataPage = lazy(() => import('./features/insights-data/InsightsDataPage'))
const InsightsSyncPage = lazy(() => import('./features/insights-sync/InsightsSyncPage'))
const FacebookAuthPage = lazy(() => import('./features/facebook-auth/FacebookAuthPage'))

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
            <Route index element={<Navigate to="/rules/definitions" replace />} />
            <Route path="/rules/definitions" element={<RuleDefinitionsPage />} />
            <Route path="/rules/bindings" element={<RuleBindingsPage />} />
            <Route path="/rules/executions" element={<ExecutionLogsPage />} />
            <Route path="/rules/scheduler" element={<SchedulerPage />} />
            <Route path="/insights/data" element={<InsightsDataPage />} />
            <Route path="/integrations/facebook" element={<FacebookAuthPage />} />
            <Route path="/insights/sync-runs" element={<InsightsSyncPage />} />
            <Route path="*" element={<Navigate to="/rules/definitions" replace />} />
          </Routes>
        </Suspense>
      </AppLayout>
    </BrowserRouter>
  )
}

export default App
