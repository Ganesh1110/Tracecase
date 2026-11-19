import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { Overview } from './pages/Overview';
import { Projects } from './pages/Projects';
import { TestCases } from './pages/TestCases';
import { TestCaseDetail } from './pages/TestCaseDetail';
import { TestSuites } from './pages/TestSuites';
import { Recorder } from './pages/Recorder';
import { Executions } from './pages/Executions';
import { History } from './pages/History';
import { Reports } from './pages/Reports';
import { VisualRegression } from './pages/VisualRegression';
import { AIAssistant } from './pages/AIAssistant';
import { TestAnalysis } from './pages/TestAnalysis';
import { Mutations } from './pages/Mutations';
import { TestRepository } from './pages/TestRepository';
import { Codegen } from './pages/Codegen';
import { NetworkInspector } from './pages/NetworkInspector';
import { MCPIntegrations } from './pages/MCPIntegrations';
import { Settings } from './pages/Settings';
import { StorageManagement } from './pages/StorageManagement';

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        {/* Workspace */}
        <Route index element={<Overview />} />
        <Route path="projects" element={<Projects />} />

        {/* Testing */}
        <Route path="testcases" element={<TestCases />} />
        <Route path="testcases/:id" element={<TestCaseDetail />} />
        <Route path="suites" element={<TestSuites />} />
        <Route path="recorder" element={<Recorder />} />
        <Route path="executions" element={<Executions />} />
        <Route path="history" element={<History />} />
        <Route path="reports" element={<Reports />} />
        <Route path="visual-diff" element={<VisualRegression />} />

        {/* Intelligence */}
        <Route path="ai-assistant" element={<AIAssistant />} />
        <Route path="test-analysis" element={<TestAnalysis />} />
        <Route path="mutations" element={<Mutations />} />
        <Route path="repository" element={<TestRepository />} />

        {/* Developer Tools */}
        <Route path="codegen" element={<Codegen />} />
        <Route path="network" element={<NetworkInspector />} />
        <Route path="mcp" element={<MCPIntegrations />} />

        {/* Administration */}
        <Route path="settings" element={<Settings />} />
        <Route path="storage" element={<StorageManagement />} />

        {/* Catch-all redirect */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
