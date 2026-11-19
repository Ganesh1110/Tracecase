import React, { useEffect, useState } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import {
  FileCode2,
  Search,
  Plus,
  Play,
  Video,
  ExternalLink,
  Clock,
  Layers,
  ChevronRight,
  Filter,
  Trash2,
} from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';
import { useProject } from '../context/ProjectContext';

export function TestCases() {
  const { currentProject } = useProject();
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedBrowser, setSelectedBrowser] = useState('all');
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { openNewCaseModal } = useOutletContext() || {};

  const loadCases = async () => {
    try {
      setLoading(true);
      const data = await api.getTestCases(currentProject?.id);
      setCases(data);
    } catch (err) {
      showToast('Failed to load test cases: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteCase = async (e, caseId, name) => {
    e.stopPropagation();
    if (!confirm(`Are you sure you want to permanently delete "${name}"?`)) return;
    try {
      await api.deleteTestCase(caseId);
      showToast('Test case deleted.', 'success');
      loadCases();
    } catch (err) {
      showToast('Failed to delete: ' + err.message, 'error');
    }
  };

  useEffect(() => {
    loadCases();
  }, [currentProject?.id]);

  const handleQuickRun = async (e, caseId) => {
    e.stopPropagation();
    try {
      showToast('Dispatching test run...', 'info');
      const run = await api.startExecution({ testcase_id: caseId });
      showToast(`Execution dispatched (#${run.id.substring(4, 10)})!`, 'success');
      navigate(`/executions?id=${run.id}`);
    } catch (err) {
      showToast('Run failed: ' + err.message, 'error');
    }
  };

  const filteredCases = cases.filter((c) => {
    const matchesSearch =
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.start_url.toLowerCase().includes(search.toLowerCase()) ||
      c.id.toLowerCase().includes(search.toLowerCase());
    const matchesBrowser = selectedBrowser === 'all' || c.browser === selectedBrowser;
    return matchesSearch && matchesBrowser;
  });

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            Test Case Repository
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Manage recorded user workflows, inspect element selectors, and trigger self-healing replays.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => openNewCaseModal?.()}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white shadow-md shadow-brand-500/20 transition-all"
          >
            <Plus className="w-4 h-4" />
            <span>New Test Case</span>
          </button>
          <button
            onClick={() => navigate('/recorder')}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold bg-rose-600 hover:bg-rose-500 text-white shadow-md shadow-rose-600/20 transition-all"
          >
            <Video className="w-4 h-4" />
            <span>Record New Test</span>
          </button>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-2.5 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search test cases by name, start URL, or ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedBrowser}
            onChange={(e) => setSelectedBrowser(e.target.value)}
            className="px-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-500"
          >
            <option value="all">All Browsers</option>
            <option value="chromium">Chromium</option>
            <option value="firefox">Firefox</option>
            <option value="webkit">WebKit</option>
          </select>
        </div>
      </div>

      {/* Test Cases Table / List */}
      <div className="rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark overflow-hidden shadow-sm">
        {loading ? (
          <div className="p-12 text-center text-slate-500 text-sm">Loading test cases...</div>
        ) : filteredCases.length === 0 ? (
          <div className="p-12 text-center">
            <FileCode2 className="w-10 h-10 text-slate-400 mx-auto mb-3" />
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
              No test cases found
            </h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              {search
                ? 'Try adjusting your search filters.'
                : 'Start by recording a browser session to automatically capture test cases.'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-100 dark:border-surface-borderDark text-[11px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider bg-slate-50/50 dark:bg-slate-900/30">
                  <th className="px-5 py-3">Test Name & Flow</th>
                  <th className="px-5 py-3">Start URL</th>
                  <th className="px-5 py-3">Browser</th>
                  <th className="px-5 py-3">Steps</th>
                  <th className="px-5 py-3">Duration</th>
                  <th className="px-5 py-3">Created</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60 text-sm">
                {filteredCases.map((tc) => (
                  <tr
                    key={tc.id}
                    className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors cursor-pointer group"
                    onClick={() => navigate(`/testcases/${tc.id}`)}
                  >
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl bg-brand-50 dark:bg-brand-950/50 text-brand-600 dark:text-brand-400 flex items-center justify-center shrink-0">
                          <FileCode2 className="w-4 h-4" />
                        </div>
                        <div className="min-w-0">
                          <div className="font-bold text-slate-900 dark:text-white truncate max-w-xs group-hover:text-brand-500 transition-colors">
                            {tc.name}
                          </div>
                          <div className="text-[11px] text-slate-400 truncate font-mono">
                            {tc.id}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-4 text-xs font-mono text-slate-500 max-w-xs truncate">
                      {tc.start_url}
                    </td>
                    <td className="px-5 py-4 text-xs text-slate-600 dark:text-slate-400 capitalize">
                      {tc.browser || 'chromium'}
                    </td>
                    <td className="px-5 py-4 text-xs font-semibold text-slate-700 dark:text-slate-300">
                      {tc.total_steps} steps
                    </td>
                    <td className="px-5 py-4 text-xs font-mono text-slate-500">
                      {tc.total_duration ? `${tc.total_duration.toFixed(1)}s` : '-'}
                    </td>
                    <td className="px-5 py-4 text-xs text-slate-400">
                      {tc.created_at ? new Date(tc.created_at).toLocaleDateString() : '-'}
                    </td>
                    <td className="px-5 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={(e) => handleQuickRun(e, tc.id)}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-50 dark:bg-emerald-950/50 hover:bg-emerald-100 dark:hover:bg-emerald-900 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800 transition-colors shadow-sm"
                          title="Run Replay"
                        >
                          <Play className="w-3.5 h-3.5 fill-current" />
                          <span>Run</span>
                        </button>
                        <button
                          onClick={(e) => handleDeleteCase(e, tc.id, tc.name)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors"
                          title="Delete test case"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                        <ChevronRight className="w-4 h-4 text-slate-400 group-hover:translate-x-0.5 transition-transform" />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
