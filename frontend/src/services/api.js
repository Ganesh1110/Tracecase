/**
 * Tracecase Studio - REST API Client
 */

const BASE_URL = '/api';

async function request(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint}`;
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorDetail = `HTTP ${response.status} ${response.statusText}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) errorDetail = errJson.detail;
    } catch {
      // ignore
    }
    throw new Error(errorDetail);
  }

  const contentType = response.headers.get('content-type');
  if (contentType && contentType.includes('application/json')) {
    return response.json();
  }
  return response.text();
}

export const api = {
  // Dashboard Metrics
  getMetrics: (projectId, days = 7) => {
    const params = new URLSearchParams();
    if (projectId) params.set('project_id', projectId);
    if (days) params.set('days', days);
    return request(`/dashboard/metrics?${params.toString()}`);
  },

  // Projects
  getProjects: () => request('/projects'),
  getProject: (id) => request(`/projects/${id}`),
  createProject: (data) =>
    request('/projects', { method: 'POST', body: JSON.stringify(data) }),
  updateProject: (id, data) =>
    request(`/projects/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteProject: (id, force = false) =>
    request(`/projects/${id}${force ? '?force=true' : ''}`, { method: 'DELETE' }),

  // Test Suites
  getSuites: (projectId) =>
    request(`/suites${projectId ? `?project_id=${projectId}` : ''}`),
  getSuite: (id) => request(`/suites/${id}`),
  createSuite: (data) =>
    request('/suites', { method: 'POST', body: JSON.stringify(data) }),
  updateSuite: (id, data) =>
    request(`/suites/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteSuite: (id) => request(`/suites/${id}`, { method: 'DELETE' }),
  runSuite: (id, options = {}) =>
    request(`/suites/${id}/run`, { method: 'POST', body: JSON.stringify(options) }),
  runSuiteMatrix: (id, options = {}) =>
    request(`/suites/${id}/run_matrix`, { method: 'POST', body: JSON.stringify(options) }),
  addCaseToSuite: (suiteId, testcaseId) =>
    request(`/suites/${suiteId}/testcases/${testcaseId}`, { method: 'POST' }),
  removeCaseFromSuite: (suiteId, testcaseId) =>
    request(`/suites/${suiteId}/testcases/${testcaseId}`, { method: 'DELETE' }),
  getSuiteExecutions: (suiteId) => request(`/suites/${suiteId}/executions`),

  // Test Cases
  getTestCases: (projectId) =>
    request(`/testcases${projectId ? `?project_id=${projectId}` : ''}`),
  getTestCase: (id) => request(`/testcases/${id}`),
  createTestCase: (data) =>
    request('/testcases', { method: 'POST', body: JSON.stringify(data) }),
  updateTestCase: (id, data) =>
    request(`/testcases/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteTestCase: (id) => request(`/testcases/${id}`, { method: 'DELETE' }),
  getTestCaseHtml: (id) => request(`/testcases/${id}/html`),
  getCodegen: (id) => request(`/testcases/${id}/codegen`, { method: 'POST' }),
  getHar: (id) => request(`/testcases/${id}/har`),

  // Step Operations
  updateStep: (testcaseId, stepNumber, data) =>
    request(`/testcases/${testcaseId}/steps/${stepNumber}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  createStep: (testcaseId, data) =>
    request(`/testcases/${testcaseId}/steps`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteStep: (testcaseId, stepNumber) =>
    request(`/testcases/${testcaseId}/steps/${stepNumber}`, { method: 'DELETE' }),
  reorderStep: (testcaseId, stepNumber, direction) =>
    request(`/testcases/${testcaseId}/steps/${stepNumber}/reorder`, {
      method: 'POST',
      body: JSON.stringify({ direction }),
    }),

  // Assertions
  addAssertion: (testcaseId, data) =>
    request(`/testcases/${testcaseId}/assertions`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateAssertion: (testcaseId, index, data) =>
    request(`/testcases/${testcaseId}/assertions/${index}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  deleteAssertion: (testcaseId, index) =>
    request(`/testcases/${testcaseId}/assertions/${index}`, { method: 'DELETE' }),

  // Executions
  getExecutions: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.projectId) params.set('project_id', filters.projectId);
    if (filters.testcaseId) params.set('testcase_id', filters.testcaseId);
    if (filters.suiteId) params.set('suite_id', filters.suiteId);
    if (filters.status) params.set('status', filters.status);
    if (filters.batchId) params.set('batch_id', filters.batchId);
    if (filters.workerId) params.set('worker_id', filters.workerId);
    if (filters.limit) params.set('limit', filters.limit);
    const qs = params.toString();
    return request(`/executions${qs ? `?${qs}` : ''}`);
  },
  getExecution: (id) => request(`/executions/${id}`),
  getExecutionAttempts: (id) => request(`/executions/${id}/attempts`),
  getTestcaseFlakiness: (testcaseId, limit = 30) =>
    request(`/testcases/${encodeURIComponent(testcaseId)}/flakiness?limit=${limit}`),
  startExecution: (data) =>
    request('/executions', { method: 'POST', body: JSON.stringify(data) }),
  cancelExecution: (id) =>
    request(`/executions/${id}/cancel`, { method: 'POST' }),

  // Batch / Parallel Executions
  getBatches: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.projectId) params.set('project_id', filters.projectId);
    if (filters.suiteId) params.set('suite_id', filters.suiteId);
    if (filters.status) params.set('status', filters.status);
    if (filters.limit) params.set('limit', filters.limit);
    const qs = params.toString();
    return request(`/executions/batches${qs ? `?${qs}` : ''}`);
  },
  getBatch: (batchId) => request(`/executions/batches/${batchId}`),
  startBatchExecution: (data) =>
    request('/executions/batch', { method: 'POST', body: JSON.stringify(data) }),
  cancelBatchExecution: (batchId) =>
    request(`/executions/batches/${batchId}/cancel`, { method: 'POST' }),

  // Cross-Browser Matrices
  getMatrices: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.projectId) params.set('project_id', filters.projectId);
    if (filters.suiteId) params.set('suite_id', filters.suiteId);
    if (filters.status) params.set('status', filters.status);
    if (filters.limit) params.set('limit', filters.limit);
    const qs = params.toString();
    return request(`/executions/matrices${qs ? `?${qs}` : ''}`);
  },
  getMatrix: (matrixId) => request(`/executions/matrices/${matrixId}`),
  startMatrixExecution: (data) =>
    request('/executions/matrix', { method: 'POST', body: JSON.stringify(data) }),
  cancelMatrixExecution: (matrixId) =>
    request(`/executions/matrices/${matrixId}/cancel`, { method: 'POST' }),

  // Recorder
  startRecording: (data) =>
    request('/record/start', { method: 'POST', body: JSON.stringify(data) }),
  pauseRecording: () => request('/record/pause', { method: 'POST' }),
  resumeRecording: () => request('/record/resume', { method: 'POST' }),
  stopRecording: () => request('/record/stop', { method: 'POST' }),
  getRecordingStatus: () => request('/record/status'),

  // Visual Diff
  compareVisual: (data) =>
    request('/diff', { method: 'POST', body: JSON.stringify(data) }),
  runStepVisualDiff: (testcaseId, stepNumber, data) =>
    request(`/testcases/${testcaseId}/steps/${stepNumber}/visual-diff`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // AI Intelligence
  analyzeTestCase: (testcaseId) =>
    request(`/ai/analyze?testcase_id=${encodeURIComponent(testcaseId)}`, {
      method: 'POST',
    }),
  getAIAnalyses: (testcaseId) => request(`/ai/analyses/${testcaseId}`),
  sendAIChat: (data) =>
    request('/ai/chat', { method: 'POST', body: JSON.stringify(data) }),
  suggestAssertions: (testcaseId) =>
    request('/ai/suggest-assertions', {
      method: 'POST',
      body: JSON.stringify({ testcase_id: testcaseId }),
    }),
  applySuggestedAssertions: (testcaseId, suggestions) =>
    request(`/testcases/${testcaseId}/assertions/apply-suggestions`, {
      method: 'POST',
      body: JSON.stringify({ suggestions }),
    }),
  auditSelectors: (testcaseId) =>
    request(`/testcases/${testcaseId}/selectors/audit`),
  verifySelectorLive: (testcaseId, data) =>
    request(`/testcases/${testcaseId}/selectors/verify-live`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  applySelectorFix: (testcaseId, stepNumber, selector, requireVerification = false) =>
    request(`/testcases/${testcaseId}/selectors/apply-fix`, {
      method: 'POST',
      body: JSON.stringify({
        step_number: stepNumber,
        selector,
        require_verification: requireVerification,
      }),
    }),
  analyzeFailure: (executionId) =>
    request('/ai/failure-analysis', {
      method: 'POST',
      body: JSON.stringify({ execution_id: executionId }),
    }),
  generateVariations: (data) =>
    request('/ai/generate-variations', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getCoverageInsights: (projectId) =>
    request(`/ai/coverage-insights${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`),

  // Mutations
  generateMutations: (data) =>
    request('/mutations/generate', { method: 'POST', body: JSON.stringify(data) }),

  // Repository & Coverage
  searchRepository: (query, limit = 15) =>
    request(`/repository/search?query=${encodeURIComponent(query)}&limit=${limit}`),
  getCoverage: () => request('/repository/coverage'),
  reindexRepository: () => request('/repository/reindex', { method: 'POST' }),

  // Autonomous Exploration
  startExploration: (config) =>
    request('/autonomous/explore', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  listExplorationRuns: (projectId) =>
    request(`/autonomous/runs${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`),
  getExplorationRun: (id) => request(`/autonomous/runs/${id}`),
  getExplorationGraph: (id) => request(`/autonomous/runs/${id}/graph`),
  cancelExploration: (id) =>
    request(`/autonomous/runs/${id}/cancel`, { method: 'POST' }),
  deleteExplorationRun: (id) =>
    request(`/autonomous/runs/${id}`, { method: 'DELETE' }),

  // Journey Synthesis & Human Approval
  synthesizeJourneys: (explorationId, data = {}) =>
    request(`/autonomous/runs/${explorationId}/synthesize`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  listDrafts: (params = {}) => {
    const q = new URLSearchParams();
    if (params.project_id) q.set('project_id', params.project_id);
    if (params.exploration_id) q.set('exploration_id', params.exploration_id);
    if (params.status) q.set('status', params.status);
    const qs = q.toString();
    return request(`/autonomous/drafts${qs ? `?${qs}` : ''}`);
  },
  getDraft: (draftId) => request(`/autonomous/drafts/${draftId}`),
  approveDraft: (draftId, data = {}) =>
    request(`/autonomous/drafts/${draftId}/approve`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  rejectDraft: (draftId, data = {}) =>
    request(`/autonomous/drafts/${draftId}/reject`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateDraft: (draftId, data) =>
    request(`/autonomous/drafts/${draftId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  // Requirements Planning & Intelligent Regression
  planRequirement: (data) =>
    request('/autonomous/requirements/plan', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  selectRegression: (data) =>
    request('/autonomous/regression/select', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Storage Management
  getStorageStats: () => request('/storage/stats'),
  getStorageSummary: () => request('/storage/summary'),
  cleanStorage: (data = {}) =>
    request('/storage/clean', { method: 'POST', body: JSON.stringify(data) }),
  pruneStorage: (data = {}) =>
    request('/storage/prune', { method: 'POST', body: JSON.stringify(data) }),
  getRetentionPolicy: () => request('/storage/retention'),
  updateRetentionPolicy: (policy) =>
    request('/storage/retention', { method: 'PUT', body: JSON.stringify(policy) }),

  // Settings
  getSettings: () => request('/settings'),
  updateSettings: (settings) =>
    request('/settings', { method: 'PUT', body: JSON.stringify({ settings }) }),
};
