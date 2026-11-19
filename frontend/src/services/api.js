/**
 * QA Auto Studio - REST API Client
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
  getMetrics: (projectId) =>
    request(`/dashboard/metrics${projectId ? `?project_id=${projectId}` : ''}`),

  // Projects
  getProjects: () => request('/projects'),
  getProject: (id) => request(`/projects/${id}`),
  createProject: (data) =>
    request('/projects', { method: 'POST', body: JSON.stringify(data) }),
  updateProject: (id, data) =>
    request(`/projects/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteProject: (id) => request(`/projects/${id}`, { method: 'DELETE' }),

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

  // Test Cases
  getTestCases: () => request('/testcases'),
  getTestCase: (id) => request(`/testcases/${id}`),
  createTestCase: (data) =>
    request('/testcases', { method: 'POST', body: JSON.stringify(data) }),
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
  deleteAssertion: (testcaseId, index) =>
    request(`/testcases/${testcaseId}/assertions/${index}`, { method: 'DELETE' }),

  // Executions
  getExecutions: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.projectId) params.set('project_id', filters.projectId);
    if (filters.testcaseId) params.set('testcase_id', filters.testcaseId);
    if (filters.status) params.set('status', filters.status);
    if (filters.limit) params.set('limit', filters.limit);
    const qs = params.toString();
    return request(`/executions${qs ? `?${qs}` : ''}`);
  },
  getExecution: (id) => request(`/executions/${id}`),
  startExecution: (data) =>
    request('/executions', { method: 'POST', body: JSON.stringify(data) }),
  cancelExecution: (id) =>
    request(`/executions/${id}/cancel`, { method: 'POST' }),

  // Recorder
  startRecording: (data) =>
    request('/record/start', { method: 'POST', body: JSON.stringify(data) }),
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

  // Mutations
  generateMutations: (data) =>
    request('/mutations/generate', { method: 'POST', body: JSON.stringify(data) }),

  // Repository & Coverage
  searchRepository: (query, limit = 15) =>
    request(`/repository/search?query=${encodeURIComponent(query)}&limit=${limit}`),
  getCoverage: () => request('/repository/coverage'),
  reindexRepository: () => request('/repository/reindex', { method: 'POST' }),

  // Storage Management
  getStorageStats: () => request('/storage/stats'),
  cleanStorage: (data = {}) =>
    request('/storage/clean', { method: 'POST', body: JSON.stringify(data) }),

  // Settings
  getSettings: () => request('/settings'),
  updateSettings: (settings) =>
    request('/settings', { method: 'PUT', body: JSON.stringify({ settings }) }),
};
