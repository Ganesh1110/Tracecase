import React, { useEffect, useState } from 'react';
import {
  Layers,
  Plus,
  Play,
  Trash2,
  CheckCircle2,
  ChevronRight,
  FileCode2,
  Edit3,
  X,
  History,
  TrendingUp,
  Clock,
  AlertCircle,
  Sliders,
  Cpu,
} from 'lucide-react';
import { api } from '../services/api';
import { useProject } from '../context/ProjectContext';
import { useToast } from '../context/ToastContext';
import { useNavigate } from 'react-router-dom';

export function TestSuites() {
  const { currentProject } = useProject();
  const { showToast } = useToast();
  const navigate = useNavigate();

  const [suites, setSuites] = useState([]);
  const [testcases, setTestCases] = useState([]);
  const [loading, setLoading] = useState(true);

  // Modal / drawer states
  const [isCreating, setIsCreating] = useState(false);
  const [editingSuite, setEditingSuite] = useState(null);
  const [viewingSuite, setViewingSuite] = useState(null);
  const [runSuiteModal, setRunSuiteModal] = useState(null);
  const [suiteExecutions, setSuiteExecutions] = useState([]);
  const [selectedCaseToAdd, setSelectedCaseToAdd] = useState('');

  // Form states for creation
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selectedCaseIds, setSelectedCaseIds] = useState([]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [suitesData, casesData] = await Promise.all([
        api.getSuites(currentProject?.id),
        api.getTestCases(currentProject?.id),
      ]);
      setSuites(suitesData);
      setTestCases(casesData);
      if (viewingSuite) {
        const refreshed = suitesData.find((s) => s.id === viewingSuite.id);
        if (refreshed) setViewingSuite(refreshed);
      }
    } catch (err) {
      showToast('Failed to load suites: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [currentProject?.id]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      // Deduplicate selected IDs
      const deduped = Array.from(new Set(selectedCaseIds));
      await api.createSuite({
        name: name.trim(),
        project_id: currentProject?.id || 'default_project',
        description: description.trim(),
        testcase_ids: deduped,
      });
      showToast('Suite created successfully!', 'success');
      setName('');
      setDescription('');
      setSelectedCaseIds([]);
      setIsCreating(false);
      loadData();
    } catch (err) {
      showToast('Failed to create suite: ' + err.message, 'error');
    }
  };

  const handleEditSubmit = async (e) => {
    e.preventDefault();
    if (!editingSuite || !editingSuite.name.trim()) return;
    try {
      const deduped = Array.from(new Set(editingSuite.testcase_ids || []));
      await api.updateSuite(editingSuite.id, {
        name: editingSuite.name.trim(),
        description: editingSuite.description?.trim() || '',
        testcase_ids: deduped,
      });
      showToast('Suite updated successfully!', 'success');
      setEditingSuite(null);
      loadData();
    } catch (err) {
      showToast('Failed to update suite: ' + err.message, 'error');
    }
  };

  const openRunModal = (suite) => {
    if (!suite) return;
    setRunSuiteModal({
      suiteId: suite.id,
      suiteName: suite.name,
      testcaseCount: (suite.testcase_ids || []).length,
      concurrency: 2,
      browser: 'chromium',
      headed: false,
      heal: true,
      assertions: true,
    });
  };

  const handleConfirmRunSuite = async () => {
    if (!runSuiteModal) return;
    try {
      showToast(`Launching ${runSuiteModal.suiteName} (Workers: ${runSuiteModal.concurrency})...`, 'info');
      const runs = await api.runSuite(runSuiteModal.suiteId, {
        concurrency: runSuiteModal.concurrency,
        browser: runSuiteModal.browser,
        headed: runSuiteModal.headed,
        heal: runSuiteModal.heal,
        assertions: runSuiteModal.assertions,
      });
      const count = Array.isArray(runs) ? runs.length : (runs?.runs?.length || 0);
      showToast(`Started ${count} test executions with concurrency ${runSuiteModal.concurrency}!`, 'success');
      setRunSuiteModal(null);
      loadData();
    } catch (err) {
      showToast('Failed to run suite: ' + err.message, 'error');
    }
  };

  const handleDelete = async (suiteId) => {
    if (!confirm('Are you sure you want to delete this test suite?')) return;
    try {
      await api.deleteSuite(suiteId);
      showToast('Suite deleted.', 'info');
      if (viewingSuite?.id === suiteId) setViewingSuite(null);
      loadData();
    } catch (err) {
      showToast('Failed to delete suite: ' + err.message, 'error');
    }
  };

  const handleAddCaseToSuite = async (suiteId, caseId) => {
    if (!caseId) return;
    try {
      await api.addCaseToSuite(suiteId, caseId);
      showToast('Test case added to suite.', 'success');
      setSelectedCaseToAdd('');
      loadData();
    } catch (err) {
      showToast('Failed to add case: ' + err.message, 'error');
    }
  };

  const handleRemoveCaseFromSuite = async (suiteId, caseId) => {
    try {
      await api.removeCaseFromSuite(suiteId, caseId);
      showToast('Test case removed from suite.', 'info');
      loadData();
    } catch (err) {
      showToast('Failed to remove case: ' + err.message, 'error');
    }
  };

  const openSuiteDetails = async (suite) => {
    setViewingSuite(suite);
    try {
      const execs = await api.getSuiteExecutions(suite.id);
      setSuiteExecutions(execs);
    } catch {
      setSuiteExecutions([]);
    }
  };

  const toggleCaseSelect = (caseId) => {
    setSelectedCaseIds((prev) =>
      prev.includes(caseId) ? prev.filter((id) => id !== caseId) : [...prev, caseId]
    );
  };

  const toggleEditCaseSelect = (caseId) => {
    if (!editingSuite) return;
    const current = editingSuite.testcase_ids || [];
    const updated = current.includes(caseId)
      ? current.filter((id) => id !== caseId)
      : [...current, caseId];
    setEditingSuite({ ...editingSuite, testcase_ids: updated });
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            Test Suites
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Group test cases into smoke, regression, or feature suites for batch execution.
          </p>
        </div>
        <button
          onClick={() => {
            setIsCreating(!isCreating);
            setEditingSuite(null);
          }}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-md shadow-brand-500/20 transition-all"
        >
          <Plus className="w-4 h-4" />
          <span>New Suite</span>
        </button>
      </div>

      {/* Creation Form */}
      {isCreating && (
        <form
          onSubmit={handleCreate}
          className="p-5 rounded-2xl border border-brand-500/30 bg-brand-50/20 dark:bg-brand-950/20 space-y-4"
        >
          <h3 className="text-sm font-bold text-slate-900 dark:text-white">Create Test Suite</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <input
              type="text"
              placeholder="Suite Name (e.g. Critical User Flows)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
              autoFocus
            />
            <input
              type="text"
              placeholder="Description (Optional)"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-2">
              Select Included Test Cases:
            </label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-48 overflow-y-auto p-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
              {testcases.map((tc) => (
                <label
                  key={tc.id}
                  className="flex items-center gap-2.5 p-2 rounded-md hover:bg-slate-50 dark:hover:bg-slate-800/60 cursor-pointer text-xs"
                >
                  <input
                    type="checkbox"
                    checked={selectedCaseIds.includes(tc.id)}
                    onChange={() => toggleCaseSelect(tc.id)}
                    className="rounded text-brand-600 focus:ring-brand-500"
                  />
                  <span className="font-medium text-slate-800 dark:text-slate-200 truncate">
                    {tc.name}
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setIsCreating(false)}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg text-slate-500"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-brand-600 hover:bg-brand-500 text-white"
            >
              Save Suite
            </button>
          </div>
        </form>
      )}

      {/* Edit Suite Modal */}
      {editingSuite && (
        <form
          onSubmit={handleEditSubmit}
          className="p-5 rounded-2xl border border-indigo-500/30 bg-indigo-50/20 dark:bg-indigo-950/20 space-y-4"
        >
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              Edit Test Suite
            </h3>
            <button
              type="button"
              onClick={() => setEditingSuite(null)}
              className="text-slate-400 hover:text-slate-600"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <input
              type="text"
              value={editingSuite.name}
              onChange={(e) => setEditingSuite({ ...editingSuite, name: e.target.value })}
              className="px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
              autoFocus
            />
            <input
              type="text"
              value={editingSuite.description || ''}
              onChange={(e) => setEditingSuite({ ...editingSuite, description: e.target.value })}
              placeholder="Description"
              className="px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-2">
              Select Included Test Cases:
            </label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-48 overflow-y-auto p-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
              {testcases.map((tc) => (
                <label
                  key={tc.id}
                  className="flex items-center gap-2.5 p-2 rounded-md hover:bg-slate-50 dark:hover:bg-slate-800/60 cursor-pointer text-xs"
                >
                  <input
                    type="checkbox"
                    checked={(editingSuite.testcase_ids || []).includes(tc.id)}
                    onChange={() => toggleEditCaseSelect(tc.id)}
                    className="rounded text-brand-600 focus:ring-brand-500"
                  />
                  <span className="font-medium text-slate-800 dark:text-slate-200 truncate">
                    {tc.name}
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={() => setEditingSuite(null)}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg text-slate-500"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white"
            >
              Update Suite
            </button>
          </div>
        </form>
      )}

      {/* Viewing Suite Detail Drawer / Modal */}
      {viewingSuite && (
        <div className="p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark space-y-5 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-500">
                <Layers className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-slate-900 dark:text-white">
                  {viewingSuite.name}
                </h2>
                <p className="text-xs text-slate-500">
                  {viewingSuite.description || 'No description provided.'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => openRunModal(viewingSuite)}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/20"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Run Suite Now</span>
              </button>
              <button
                onClick={() => setViewingSuite(null)}
                className="p-2 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Aggregated Suite Stats */}
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 p-4 rounded-xl bg-slate-50/70 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-800/60">
            <div>
              <span className="text-[11px] font-semibold text-slate-400 uppercase">Test Cases</span>
              <div className="text-lg font-bold text-slate-900 dark:text-white mt-0.5">
                {viewingSuite.testcase_ids?.length || 0}
              </div>
            </div>
            <div>
              <span className="text-[11px] font-semibold text-slate-400 uppercase">Total Runs</span>
              <div className="text-lg font-bold text-slate-900 dark:text-white mt-0.5">
                {viewingSuite.total_runs || 0}
              </div>
            </div>
            <div>
              <span className="text-[11px] font-semibold text-slate-400 uppercase">Pass Rate</span>
              <div className="text-lg font-bold text-emerald-500 mt-0.5">
                {viewingSuite.pass_rate !== null && viewingSuite.pass_rate !== undefined
                  ? `${viewingSuite.pass_rate}%`
                  : 'N/A'}
              </div>
            </div>
            <div>
              <span className="text-[11px] font-semibold text-slate-400 uppercase">Last Execution</span>
              <div className="text-xs font-mono text-slate-600 dark:text-slate-400 mt-1">
                {viewingSuite.last_run_at
                  ? new Date(viewingSuite.last_run_at).toLocaleString()
                  : 'Never'}
              </div>
            </div>
          </div>

          {/* Test Cases in Suite */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                Included Test Cases
              </h3>

              {/* Add case to suite dropdown */}
              <div className="flex items-center gap-2">
                <select
                  value={selectedCaseToAdd}
                  onChange={(e) => setSelectedCaseToAdd(e.target.value)}
                  className="px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200"
                >
                  <option value="">-- Add Test Case --</option>
                  {testcases
                    .filter((tc) => !(viewingSuite.testcase_ids || []).includes(tc.id))
                    .map((tc) => (
                      <option key={tc.id} value={tc.id}>
                        {tc.name}
                      </option>
                    ))}
                </select>
                <button
                  onClick={() => handleAddCaseToSuite(viewingSuite.id, selectedCaseToAdd)}
                  disabled={!selectedCaseToAdd}
                  className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-brand-600 hover:bg-brand-500 text-white disabled:opacity-40"
                >
                  Add
                </button>
              </div>
            </div>

            {viewingSuite.testcase_ids?.length === 0 ? (
              <p className="text-xs text-slate-400 italic">
                No test cases included in this suite yet.
              </p>
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden">
                {viewingSuite.testcase_ids?.map((cid) => {
                  const tc = testcases.find((c) => c.id === cid) || { id: cid, name: cid };
                  return (
                    <div
                      key={cid}
                      className="p-3 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-800/40"
                    >
                      <div className="flex items-center gap-2.5">
                        <FileCode2 className="w-4 h-4 text-slate-400" />
                        <div>
                          <div className="text-xs font-bold text-slate-900 dark:text-white">
                            {tc.name}
                          </div>
                          <span className="text-[10px] text-slate-400 font-mono">{cid}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => navigate(`/testcases/${cid}`)}
                          className="px-2 py-1 text-[11px] font-semibold text-brand-600 dark:text-brand-400 hover:underline"
                        >
                          View Details
                        </button>
                        <button
                          onClick={() => handleRemoveCaseFromSuite(viewingSuite.id, cid)}
                          className="p-1 rounded text-slate-400 hover:text-rose-500"
                          title="Remove from suite"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Recent Runs for this Suite */}
          {suiteExecutions.length > 0 && (
            <div className="space-y-2 pt-2">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                Recent Suite Executions
              </h3>
              <div className="divide-y divide-slate-100 dark:divide-slate-800 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden text-xs">
                {suiteExecutions.slice(0, 5).map((run) => (
                  <div
                    key={run.id}
                    onClick={() => navigate(`/executions?id=${run.id}`)}
                    className="p-3 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-800/40 cursor-pointer"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={`w-2 h-2 rounded-full ${
                          run.status === 'passed' ? 'bg-emerald-500' : 'bg-rose-500'
                        }`}
                      />
                      <span className="font-semibold text-slate-800 dark:text-slate-200">
                        {run.testcase_name}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-slate-400 font-mono text-[11px]">
                      <span>{run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : '-'}</span>
                      <span>{new Date(run.started_at).toLocaleTimeString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Suites Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {suites.length === 0 ? (
          <div className="col-span-full p-12 text-center text-slate-500 bg-white dark:bg-surface-cardDark rounded-2xl border border-slate-200 dark:border-surface-borderDark">
            <Layers className="w-10 h-10 text-slate-400 mx-auto mb-3" />
            <h3 className="text-sm font-bold text-slate-700 dark:text-slate-300">
              No test suites created yet
            </h3>
            <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
              Create a test suite to group test cases into smoke or regression batches.
            </p>
          </div>
        ) : (
          suites.map((suite) => (
            <div
              key={suite.id}
              className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="p-2 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-500">
                      <Layers className="w-5 h-5" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-slate-900 dark:text-white">
                        {suite.name}
                      </h3>
                      <span className="text-xs text-slate-400 font-mono">
                        {suite.total_cases} test cases
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => setEditingSuite(suite)}
                      className="p-1 rounded text-slate-400 hover:text-indigo-500"
                      title="Edit suite"
                    >
                      <Edit3 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(suite.id)}
                      className="p-1 rounded text-slate-400 hover:text-rose-500"
                      title="Delete suite"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <p className="text-xs text-slate-500 mt-3 line-clamp-2">
                  {suite.description || 'No description provided.'}
                </p>

                {/* Quick metrics pill */}
                {suite.pass_rate !== null && suite.pass_rate !== undefined && (
                  <div className="mt-3 flex items-center gap-2 text-[11px]">
                    <span className="font-semibold text-emerald-500">
                      {suite.pass_rate}% pass rate
                    </span>
                    <span className="text-slate-400">({suite.total_runs} runs)</span>
                  </div>
                )}
              </div>

              <div className="mt-5 pt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
                <button
                  onClick={() => openSuiteDetails(suite)}
                  className="text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-brand-500 flex items-center gap-1"
                >
                  <span>Manage</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => openRunModal(suite)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>Run Suite</span>
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Parallel Run Configuration Modal */}
      {runSuiteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl max-w-lg w-full p-6 space-y-5 animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-indigo-50 dark:bg-indigo-950/60 rounded-xl text-indigo-600 dark:text-indigo-400">
                  <Sliders className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white">
                    Run Suite Configuration
                  </h3>
                  <p className="text-xs text-slate-400">
                    {runSuiteModal.suiteName} ({runSuiteModal.testcaseCount} test cases)
                  </p>
                </div>
              </div>
              <button
                onClick={() => setRunSuiteModal(null)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Concurrency Selector */}
            <div className="space-y-2">
              <div className="flex justify-between items-center text-xs font-semibold text-slate-700 dark:text-slate-300">
                <span className="flex items-center gap-1.5">
                  <Cpu className="w-4 h-4 text-indigo-500" />
                  <span>Parallel Concurrency Pool</span>
                </span>
                <span className="font-mono text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/60 px-2 py-0.5 rounded text-xs font-bold">
                  {runSuiteModal.concurrency} {runSuiteModal.concurrency === 1 ? 'Worker (Sequential)' : 'Workers (Parallel)'}
                </span>
              </div>
              <input
                type="range"
                min="1"
                max="8"
                step="1"
                value={runSuiteModal.concurrency}
                onChange={(e) =>
                  setRunSuiteModal({ ...runSuiteModal, concurrency: parseInt(e.target.value, 10) })
                }
                className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-indigo-600"
              />
              <div className="flex justify-between text-[10px] text-slate-400">
                <span>1 (Sequential)</span>
                <span className="text-indigo-500 font-semibold">2 (Default)</span>
                <span>4</span>
                <span>8 (Maximum)</span>
              </div>
            </div>

            {/* Browser Selection */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                Browser Engine
              </label>
              <div className="grid grid-cols-3 gap-2">
                {['chromium', 'firefox', 'webkit'].map((b) => (
                  <button
                    key={b}
                    type="button"
                    onClick={() => setRunSuiteModal({ ...runSuiteModal, browser: b })}
                    className={`py-2 px-3 rounded-xl text-xs font-semibold capitalize border transition-all ${
                      runSuiteModal.browser === b
                        ? 'border-indigo-600 bg-indigo-50/70 dark:bg-indigo-950/50 text-indigo-600 dark:text-indigo-400 shadow-sm'
                        : 'border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800'
                    }`}
                  >
                    {b}
                  </button>
                ))}
              </div>
            </div>

            {/* Options Checkboxes */}
            <div className="grid grid-cols-2 gap-3 pt-1">
              <label className="flex items-center gap-2 p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 cursor-pointer text-xs text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/40">
                <input
                  type="checkbox"
                  checked={runSuiteModal.headed}
                  onChange={(e) =>
                    setRunSuiteModal({ ...runSuiteModal, headed: e.target.checked })
                  }
                  className="rounded text-indigo-600 focus:ring-indigo-500"
                />
                <span className="font-medium">Headed Browser</span>
              </label>
              <label className="flex items-center gap-2 p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 cursor-pointer text-xs text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/40">
                <input
                  type="checkbox"
                  checked={runSuiteModal.heal}
                  onChange={(e) =>
                    setRunSuiteModal({ ...runSuiteModal, heal: e.target.checked })
                  }
                  className="rounded text-indigo-600 focus:ring-indigo-500"
                />
                <span className="font-medium">Self-Healing</span>
              </label>
            </div>

            {/* Action buttons */}
            <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-slate-100 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setRunSuiteModal(null)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmRunSuite}
                className="flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/25"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Launch Execution ({runSuiteModal.concurrency} Workers)</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
