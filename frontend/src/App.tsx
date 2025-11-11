import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import RuleDefinitionsPage from './features/rule-definitions/RuleDefinitionsPage'
import RuleBindingsPage from './features/rule-bindings/RuleBindingsPage'
import ExecutionLogsPage from './features/execution-logs/ExecutionLogsPage'
import SchedulerPage from './features/scheduler/SchedulerPage'
import InsightsDataPage from './features/insights-data/InsightsDataPage'
import InsightsSyncPage from './features/insights-sync/InsightsSyncPage'
import FacebookAuthPage from './features/facebook-auth/FacebookAuthPage'

const App = () => {
  return (
    <BrowserRouter>
      <AppLayout>
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
      </AppLayout>
    </BrowserRouter>
  )
}

export default App
