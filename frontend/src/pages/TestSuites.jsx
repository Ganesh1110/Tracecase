import React, { useEffect, useState } from 'react';
import { Layers, Plus, Play, Trash2, CheckCircle2, ChevronRight, FileCode2 } from 'lucide-react';
import { api } from '../services/api';
import { useProject } from '../context/ProjectContext';
import { useToast } from '../context/ToastContext';

export function TestSuites() {
  const { currentProject } = useProject();
  const { showToast } = useToast();
  const [suites, setSuites] = useState([]);
  const [testcases, setTestCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selectedCaseIds, setSelectedCaseIds] = useState([]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [suitesData, casesData] = await Promise.all([
        api.getSuites(currentProject?.id),
        api.getTestCases(),
      ]);
      setSuites(suitesData);
      setTestCases(casesData);
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
      await api.createSuite({
        name: name.trim(),
        project_id: currentProject?.id || 'default_project',
        description: description.trim(),
        testcase_ids: selectedCaseIds,
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

  const handleRunSuite = async (suiteId) => {
    try {
      showToast('Launching suite execution...', 'info');
      const runs = await api.runSuite(suiteId);
      showToast(`Started ${runs.length} test executions!`, 'success');
    } catch (err) {
      showToast('Failed to run suite: ' + err.message, 'error');
    }
  };

  const handleDelete = async (suiteId) => {
    if (!confirm('Are you sure you want to delete this test suite?')) return;
    try {
      await api.deleteSuite(suiteId);
      showToast('Suite deleted.', 'info');
      loadData();
    } catch (err) {
      showToast('Failed to delete suite: ' + err.message, 'error');
    }
  };

  const toggleCaseSelect = (caseId) => {
    setSelectedCaseIds((prev) =>
      prev.includes(caseId) ? prev.filter((id) => id !== caseId) : [...prev, caseId]
    );
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
          onClick={() => setIsCreating(!isCreating)}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-md shadow-brand-500/20 transition-all"
        >
          <Plus className="w-4 h-4" />
          <span>New Suite</span>
        </button>
      </div>

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

      {/* Suites Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {suites.length === 0 ? (
          <div className="col-span-full p-12 text-center text-slate-500">
            No test suites created yet. Create a suite to execute collections of tests together.
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
                  <button
                    onClick={() => handleDelete(suite.id)}
                    className="p-1 rounded text-slate-400 hover:text-rose-500"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
                <p className="text-xs text-slate-500 mt-3 line-clamp-2">
                  {suite.description || 'No description provided.'}
                </p>
              </div>

              <div className="mt-5 pt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
                <span className="text-xs text-slate-400">
                  {new Date(suite.created_at).toLocaleDateString()}
                </span>
                <button
                  onClick={() => handleRunSuite(suite.id)}
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
    </div>
  );
}
