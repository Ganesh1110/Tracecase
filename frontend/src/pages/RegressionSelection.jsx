import React, { useState, useEffect } from 'react';
import {
  Clock,
  ShieldAlert,
  ShieldCheck,
  Zap,
  Play,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  FileCode,
  GitCommit,
  Filter,
  Layers,
  ArrowRight,
  Loader2,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  FileText,
  FileJson,
  Download,
  Edit3,
  HelpCircle,
  Eye,
  Info,
} from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';
import { useNavigate } from 'react-router-dom';

export function RegressionSelection() {
  const [strategy, setStrategy] = useState('time_budget'); // 'time_budget' | 'risk_threshold' | 'top_k' | 'combined'
  const [timeBudget, setTimeBudget] = useState('120s');
  const [minTier, setMinTier] = useState('medium');
  const [topK, setTopK] = useState(5);
  const [includeCriticalExceptions, setIncludeCriticalExceptions] = useState(false);

  const [gitChanges, setGitChanges] = useState(null);
  const [selection, setSelection] = useState(null);
  const [explanations, setExplanations] = useState({});
  const [expandedRows, setExpandedRows] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [downloadingReport, setDownloadingReport] = useState(false);
  const [downloadingManifest, setDownloadingManifest] = useState(false);
  const [filterTab, setFilterTab] = useState('all'); // 'all' | 'selected' | 'excluded' | 'exceptions'

  // Override decision modal state
  const [overrideModal, setOverrideModal] = useState(null);
  const [overrideDecision, setOverrideDecision] = useState('selected');
  const [overrideReason, setOverrideReason] = useState('');
  const [overriding, setOverriding] = useState(false);

  const { showToast } = useToast();
  const navigate = useNavigate();

  useEffect(() => {
    // Load current git status on mount
    api.getGitChanges()
      .then((data) => setGitChanges(data))
      .catch((err) => console.error('Failed to load git changes', err));
  }, []);

  const fetchExplanations = async (selectionId) => {
    try {
      const traces = await api.getSelectionExplanations(selectionId);
      const traceMap = {};
      traces.forEach((t) => {
        traceMap[t.testcase_id] = t;
      });
      setExplanations(traceMap);
    } catch (err) {
      console.warn('Failed to load decision explanations', err);
    }
  };

  const handleRunSelection = async () => {
    setLoading(true);
    try {
      const payload = {
        strategy,
        time_budget: strategy === 'top_k' ? null : timeBudget,
        min_risk_tier: (strategy === 'risk_threshold' || strategy === 'combined') ? minTier : null,
        top_k: strategy === 'top_k' ? Number(topK) : null,
        include_critical_exceptions: includeCriticalExceptions,
        persist: true,
      };
      const result = await api.selectRegressionTests(payload);
      setSelection(result);
      await fetchExplanations(result.id);
      showToast('Smart regression selection completed with explainable traces', 'success');
    } catch (err) {
      showToast(`Selection error: ${err.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleApproveAndExecute = async () => {
    if (!selection) return;
    setExecuting(true);
    try {
      const res = await api.executeRegressionSelection(selection.id, {
        include_budget_exceptions: includeCriticalExceptions,
        concurrency: 2,
        retries: 1,
      });
      showToast(`Regression execution launched! Batch ID: ${res.batch_id}`, 'success');
      navigate('/executions');
    } catch (err) {
      showToast(`Execution launch failed: ${err.message}`, 'error');
    } finally {
      setExecuting(false);
    }
  };

  const toggleRowExpansion = (testcaseId) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(testcaseId)) {
        next.delete(testcaseId);
      } else {
        next.add(testcaseId);
      }
      return next;
    });
  };

  const handleDownloadMarkdown = async () => {
    if (!selection) return;
    setDownloadingReport(true);
    try {
      const md = await api.getSelectionReport(selection.id, 'markdown');
      const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `tracecase-regression-report-${selection.id}.md`;
      link.click();
      URL.revokeObjectURL(url);
      showToast('Markdown report downloaded', 'success');
    } catch (err) {
      showToast(`Report download failed: ${err.message}`, 'error');
    } finally {
      setDownloadingReport(false);
    }
  };

  const handleDownloadManifest = async () => {
    if (!selection) return;
    setDownloadingManifest(true);
    try {
      const manifest = await api.getSelectionManifest(selection.id);
      const jsonStr = JSON.stringify(manifest, null, 2);
      const blob = new Blob([jsonStr], { type: 'application/json;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `tracecase-regression-manifest-${selection.id}.json`;
      link.click();
      URL.revokeObjectURL(url);
      showToast('CI JSON manifest downloaded', 'success');
    } catch (err) {
      showToast(`Manifest download failed: ${err.message}`, 'error');
    } finally {
      setDownloadingManifest(false);
    }
  };

  const openOverrideModal = (testcaseId, testcaseName, currentDecision) => {
    const defaultNew = currentDecision === 'selected' ? 'excluded' : 'selected';
    setOverrideModal({
      testcase_id: testcaseId,
      testcase_name: testcaseName,
      current_decision: currentDecision,
    });
    setOverrideDecision(defaultNew);
    setOverrideReason('');
  };

  const handleSaveOverride = async () => {
    if (!overrideModal || !selection) return;
    if (!overrideReason.trim()) {
      showToast('Override reason is required for auditability', 'warning');
      return;
    }
    setOverriding(true);
    try {
      await api.overrideSelectionDecision(selection.id, {
        testcase_id: overrideModal.testcase_id,
        override_decision: overrideDecision,
        override_reason: overrideReason.trim(),
      });
      showToast(`Decision for ${overrideModal.testcase_id} overridden to ${overrideDecision.toUpperCase()}`, 'success');
      setOverrideModal(null);
      // Reload selection and explanations
      const updatedSel = await api.getRegressionSelection(selection.id);
      setSelection(updatedSel);
      await fetchExplanations(selection.id);
    } catch (err) {
      showToast(`Override failed: ${err.message}`, 'error');
    } finally {
      setOverriding(false);
    }
  };

  const testsToDisplay = selection ? selection.tests.filter((t) => {
    if (filterTab === 'selected') return t.decision === 'selected';
    if (filterTab === 'excluded') return t.decision === 'excluded';
    if (filterTab === 'exceptions') return t.decision === 'budget_exception';
    return true;
  }) : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Zap className="h-6 w-6 text-indigo-500" />
            Intelligent Regression Selection & Prioritization
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            Predictive, explainable test prioritization powered by Git changes, code mappings, and verifiable evidence.
          </p>
        </div>

        {selection && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownloadMarkdown}
              disabled={downloadingReport}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 text-xs font-medium transition-colors shadow-sm"
              title="Download human-readable Markdown regression report"
            >
              <FileText className="h-4 w-4 text-cyan-400" />
              {downloadingReport ? 'Generating...' : 'Export Markdown'}
            </button>
            <button
              onClick={handleDownloadManifest}
              disabled={downloadingManifest}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 text-xs font-medium transition-colors shadow-sm"
              title="Download machine-readable JSON regression manifest for CI/PR integration"
            >
              <FileJson className="h-4 w-4 text-emerald-400" />
              {downloadingManifest ? 'Generating...' : 'Export JSON'}
            </button>
          </div>
        )}
      </div>

      {/* Git Change Context Banner */}
      {gitChanges && (
        <div className="bg-gray-800/80 border border-gray-700 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-indigo-950/60 border border-indigo-800 text-indigo-400">
              <GitCommit className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
                <span>Branch: <code className="text-indigo-400">{gitChanges.current_branch || 'local'}</code></span>
                <span className="text-gray-500">•</span>
                <span>Commit: <code className="text-gray-400">{gitChanges.current_commit?.substring(0, 8) || 'working-tree'}</code></span>
              </div>
              <div className="text-xs text-gray-400 mt-0.5 flex items-center gap-3">
                <span>{gitChanges.total_changed_files} changed file{gitChanges.total_changed_files === 1 ? '' : 's'}</span>
                <span className="text-green-400">+{gitChanges.total_additions}</span>
                <span className="text-red-400">-{gitChanges.total_deletions}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs text-gray-400">
            <span className="px-2 py-1 rounded bg-gray-900 border border-gray-700 font-mono">
              Base: {gitChanges.base_ref || 'working tree'}
            </span>
            <span className="px-2 py-1 rounded bg-gray-900 border border-gray-700 font-mono">
              Target: {gitChanges.target_ref || 'HEAD'}
            </span>
          </div>
        </div>
      )}

      {/* Selection Configuration Panel */}
      <div className="bg-gray-800 border border-gray-700 rounded-xl p-5 shadow-lg space-y-4">
        <div className="flex items-center justify-between border-b border-gray-700/60 pb-3">
          <h2 className="text-base font-semibold text-gray-200 flex items-center gap-2">
            <Filter className="h-4 w-4 text-indigo-400" />
            Selection Strategy & Constraints
          </h2>
          <span className="text-xs text-gray-400 font-mono">Phase 7.5.4 & 7.5.5</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {/* Strategy */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Strategy</label>
            <select
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="time_budget">Time Budget (Max Value Density)</option>
              <option value="risk_threshold">Risk Threshold (Min Risk Tier)</option>
              <option value="top_k">Top-K Highest Priority Tests</option>
              <option value="combined">Combined (Budget + Min Risk Tier)</option>
            </select>
          </div>

          {/* Time Budget */}
          {(strategy === 'time_budget' || strategy === 'combined') && (
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Time Budget</label>
              <input
                type="text"
                value={timeBudget}
                onChange={(e) => setTimeBudget(e.target.value)}
                placeholder="e.g. 120s, 2m, 90"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500 font-mono"
              />
            </div>
          )}

          {/* Min Risk Tier */}
          {(strategy === 'risk_threshold' || strategy === 'combined') && (
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Minimum Risk Tier</label>
              <select
                value={minTier}
                onChange={(e) => setMinTier(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500"
              >
                <option value="critical">Critical Only (&ge; 80.0)</option>
                <option value="high">High & Critical (&ge; 60.0)</option>
                <option value="medium">Medium, High & Critical (&ge; 30.0)</option>
                <option value="low">All Tiers (Including Low)</option>
              </select>
            </div>
          )}

          {/* Top K */}
          {strategy === 'top_k' && (
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Top K Tests</label>
              <input
                type="number"
                min="1"
                max="100"
                value={topK}
                onChange={(e) => setTopK(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-indigo-500 font-mono"
              />
            </div>
          )}

          {/* Critical Safeguard Toggle */}
          <div className="flex flex-col justify-end">
            <label className="inline-flex items-center gap-2 cursor-pointer text-xs text-gray-300 py-2">
              <input
                type="checkbox"
                checked={includeCriticalExceptions}
                onChange={(e) => setIncludeCriticalExceptions(e.target.checked)}
                className="rounded border-gray-700 text-indigo-600 focus:ring-indigo-500 bg-gray-900 h-4 w-4"
              />
              <span>Include Critical Budget Exceptions</span>
            </label>
          </div>
        </div>

        {/* Action Button */}
        <div className="flex justify-end pt-2">
          <button
            onClick={handleRunSelection}
            disabled={loading}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors disabled:opacity-50 shadow-md"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Selecting Tests & Generating Explanations...
              </>
            ) : (
              <>
                <Zap className="h-4 w-4 fill-white" />
                Compute Intelligent Regression Set
              </>
            )}
          </button>
        </div>
      </div>

      {/* Results View */}
      {selection && (
        <div className="space-y-6">
          {/* Summary Metric Cards */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-4">
              <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">
                Selected Tests
              </div>
              <div className="text-2xl font-bold text-green-400 mt-1">
                {selection.selected_count} <span className="text-xs text-gray-500 font-normal">/ {selection.total_tests_considered} total</span>
              </div>
              <div className="text-xs text-gray-400 mt-1">
                {selection.excluded_count} excluded
              </div>
            </div>

            <div className="bg-gray-800 border border-gray-700 rounded-xl p-4">
              <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">
                Estimated Duration
              </div>
              <div className="text-2xl font-bold text-cyan-400 mt-1 flex items-center gap-1.5">
                <Clock className="h-5 w-5 text-cyan-400" />
                {selection.estimated_total_duration_s.toFixed(1)}s
              </div>
              <div className="text-xs text-gray-400 mt-1">
                {selection.time_budget_s ? `Budget: ${selection.time_budget_s}s` : 'Unconstrained'}
              </div>
            </div>

            <div className="bg-gray-800 border border-gray-700 rounded-xl p-4">
              <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">
                Risk Coverage
              </div>
              <div className="text-2xl font-bold text-indigo-400 mt-1">
                {selection.risk_coverage_pct.toFixed(1)}%
              </div>
              <div className="text-xs text-gray-400 mt-1">
                Aggregate failure risk covered
              </div>
            </div>

            <div className="bg-gray-800 border border-gray-700 rounded-xl p-4">
              <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">
                Critical Coverage
              </div>
              <div className="text-2xl font-bold text-red-400 mt-1">
                {selection.critical_coverage_pct.toFixed(1)}%
              </div>
              <div className="text-xs text-gray-400 mt-1">
                Critical breakage tests covered
              </div>
            </div>

            <div className="bg-gray-800 border border-gray-700 rounded-xl p-4">
              <div className="text-xs font-medium text-gray-400 uppercase tracking-wider">
                Evidence Certainty
              </div>
              <div className="text-2xl font-bold text-purple-400 mt-1">
                Audit Ready
              </div>
              <div className="text-xs text-gray-400 mt-1">
                Verifiable diff & locator traces
              </div>
            </div>
          </div>

          {/* Critical Risk Budget Exception Banner */}
          {selection.budget_exception_count > 0 && (
            <div className="bg-red-950/40 border border-red-700/60 rounded-xl p-4 flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
                <div>
                  <h3 className="text-sm font-semibold text-red-300">
                    ⚠️ Critical Risk Safeguard: {selection.budget_exception_count} Test(s) Exceed Time Budget
                  </h3>
                  <p className="text-xs text-red-200/80 mt-1">
                    Tracecase detected test cases with CRITICAL failure risk that exceed the allocated time budget.
                    To prevent silent regression escapes, these tests were NOT silently dropped.
                    Review them below and click Override or include them in execution.
                  </p>
                </div>
              </div>

              {!includeCriticalExceptions && (
                <button
                  onClick={() => {
                    setIncludeCriticalExceptions(true);
                    handleRunSelection();
                  }}
                  className="bg-red-600 hover:bg-red-500 text-white text-xs font-medium px-3 py-1.5 rounded-lg whitespace-nowrap"
                >
                  Include In Execution
                </button>
              )}
            </div>
          )}

          {/* Test Candidates Table Card */}
          <div className="bg-gray-800 border border-gray-700 rounded-xl overflow-hidden shadow-lg">
            {/* Table Header & Tabs */}
            <div className="p-4 border-b border-gray-700 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex items-center gap-1 bg-gray-900 p-1 rounded-lg">
                <button
                  onClick={() => setFilterTab('all')}
                  className={`text-xs px-3 py-1.5 rounded-md font-medium transition-colors ${
                    filterTab === 'all' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  All Candidates ({selection.tests.length})
                </button>
                <button
                  onClick={() => setFilterTab('selected')}
                  className={`text-xs px-3 py-1.5 rounded-md font-medium transition-colors ${
                    filterTab === 'selected' ? 'bg-green-600 text-white' : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  Selected ({selection.selected_count})
                </button>
                <button
                  onClick={() => setFilterTab('exceptions')}
                  className={`text-xs px-3 py-1.5 rounded-md font-medium transition-colors ${
                    filterTab === 'exceptions' ? 'bg-red-600 text-white' : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  Exceptions ({selection.budget_exception_count})
                </button>
                <button
                  onClick={() => setFilterTab('excluded')}
                  className={`text-xs px-3 py-1.5 rounded-md font-medium transition-colors ${
                    filterTab === 'excluded' ? 'bg-gray-700 text-gray-200' : 'text-gray-400 hover:text-gray-200'
                  }`}
                >
                  Excluded ({selection.excluded_count})
                </button>
              </div>

              {/* Execution Approval Action */}
              <div className="flex items-center gap-3">
                <button
                  onClick={handleApproveAndExecute}
                  disabled={executing || selection.selected_count === 0}
                  className="flex items-center gap-2 bg-green-600 hover:bg-green-500 text-white text-xs font-semibold px-4 py-2 rounded-lg transition-colors disabled:opacity-50 shadow-md"
                >
                  {executing ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Launching Worker Pool...
                    </>
                  ) : (
                    <>
                      <Play className="h-4 w-4 fill-white" />
                      Approve & Execute Regression ({selection.selected_count} tests)
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Candidates Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-gray-300">
                <thead className="text-xs uppercase bg-gray-900/60 text-gray-400 border-b border-gray-700">
                  <tr>
                    <th className="px-3 py-3 w-8"></th>
                    <th className="px-4 py-3">Decision</th>
                    <th className="px-4 py-3">Risk Tier</th>
                    <th className="px-4 py-3">Test Case</th>
                    <th className="px-4 py-3 text-right">Est Duration</th>
                    <th className="px-4 py-3">Certainty</th>
                    <th className="px-4 py-3">Primary Risk Driver & Rationale</th>
                    <th className="px-4 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-700/60 font-mono text-xs">
                  {testsToDisplay.map((item) => {
                    const isExpanded = expandedRows.has(item.testcase_id);
                    const trace = explanations[item.testcase_id];
                    const ev = trace?.evidence || {};
                    const obs = ev.observed || [];
                    const heu = ev.heuristic || [];
                    const mis = ev.missing || [];

                    return (
                      <React.Fragment key={item.testcase_id}>
                        <tr
                          onClick={() => toggleRowExpansion(item.testcase_id)}
                          className="hover:bg-gray-750/50 transition-colors cursor-pointer select-none"
                        >
                          <td className="px-3 py-3 text-gray-500">
                            {isExpanded ? (
                              <ChevronDown className="h-4 w-4 text-indigo-400" />
                            ) : (
                              <ChevronRight className="h-4 w-4" />
                            )}
                          </td>

                          <td className="px-4 py-3 whitespace-nowrap">
                            {item.decision === 'selected' ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-green-950/70 border border-green-700 text-green-300">
                                <CheckCircle2 className="h-3 w-3 text-green-400" />
                                SELECTED
                                {trace?.user_override ? ' (OVERRIDE)' : ''}
                              </span>
                            ) : item.decision === 'budget_exception' ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-red-950/70 border border-red-700 text-red-300">
                                <AlertTriangle className="h-3 w-3 text-red-400" />
                                EXCEPTION
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-gray-900 border border-gray-700 text-gray-400">
                                <XCircle className="h-3 w-3 text-gray-500" />
                                EXCLUDED
                                {trace?.user_override ? ' (OVERRIDE)' : ''}
                              </span>
                            )}
                          </td>

                          <td className="px-4 py-3 whitespace-nowrap">
                            <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                              item.risk_tier === 'critical' ? 'bg-red-900/80 text-red-200 border border-red-700' :
                              item.risk_tier === 'high' ? 'bg-amber-900/80 text-amber-200 border border-amber-700' :
                              item.risk_tier === 'medium' ? 'bg-yellow-900/80 text-yellow-200 border border-yellow-700' :
                              'bg-green-900/80 text-green-200 border border-green-700'
                            }`}>
                              {item.risk_tier.toUpperCase()} ({item.risk_score.toFixed(1)})
                            </span>
                          </td>

                          <td className="px-4 py-3 font-sans">
                            <div className="font-medium text-gray-200">{item.testcase_name || item.testcase_id}</div>
                            <div className="text-[11px] text-gray-500 font-mono">{item.testcase_id}</div>
                          </td>

                          <td className="px-4 py-3 text-right whitespace-nowrap font-mono">
                            <span className="text-cyan-400">{item.estimated_duration_s.toFixed(1)}s</span>{' '}
                            <span className="text-[10px] text-gray-500">
                              {item.duration_source === 'measured_history' ? '[hist]' :
                               item.duration_source === 'recorded_testcase' ? '[rec]' : '[est]'}
                            </span>
                          </td>

                          <td className="px-4 py-3 whitespace-nowrap">
                            <span className="px-2 py-0.5 rounded bg-gray-900 border border-gray-700 text-gray-300 text-[11px]">
                              {(item.mapping_confidence * 100).toFixed(0)}%
                            </span>
                          </td>

                          <td className="px-4 py-3 font-sans">
                            <div className="text-gray-300 font-medium">{item.primary_risk_driver || '-'}</div>
                            <div className="text-xs text-gray-500 mt-0.5">{item.decision_reason}</div>
                          </td>

                          <td className="px-4 py-3 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                            <button
                              onClick={() => openOverrideModal(item.testcase_id, item.testcase_name || item.testcase_id, item.decision)}
                              className="text-xs px-2.5 py-1 rounded bg-gray-800 hover:bg-gray-700 text-indigo-400 hover:text-indigo-300 border border-gray-700 inline-flex items-center gap-1 font-sans transition-colors"
                              title="Override decision with explicit audit rationale"
                            >
                              <Edit3 className="h-3 w-3" />
                              Override
                            </button>
                          </td>
                        </tr>

                        {/* Expanded Explanation Drawer */}
                        {isExpanded && (
                          <tr className="bg-gray-900/90 font-sans border-b border-gray-700">
                            <td colSpan="8" className="p-4 space-y-4">
                              {/* Distinction Callout */}
                              <div className="bg-indigo-950/30 border border-indigo-800/50 rounded-lg p-3 text-xs text-indigo-200 flex items-start gap-2">
                                <Info className="h-4 w-4 text-indigo-400 shrink-0 mt-0.5" />
                                <div>
                                  <span className="font-semibold text-indigo-300">Confidence vs. Risk:</span>{' '}
                                  Mapping confidence ({(item.mapping_confidence * 100).toFixed(0)}% certainty) measures
                                  how deterministically this test connects to modified code. Failure risk ({item.risk_score.toFixed(1)} {item.risk_tier.toUpperCase()})
                                  estimates the likelihood and severity of real application breakage.
                                </div>
                              </div>

                              {/* Categorized Evidence Grid */}
                              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                {/* Observed Evidence */}
                                <div className="bg-gray-800/90 border border-gray-700 rounded-lg p-3">
                                  <div className="flex items-center justify-between mb-2">
                                    <span className="text-xs font-semibold text-green-400 uppercase tracking-wider flex items-center gap-1">
                                      <CheckCircle2 className="h-3.5 w-3.5" />
                                      Observed Evidence ({obs.length})
                                    </span>
                                  </div>
                                  {obs.length === 0 ? (
                                    <p className="text-xs text-gray-500 italic">No direct diffs or historical failures recorded.</p>
                                  ) : (
                                    <ul className="space-y-1.5 text-xs text-gray-300">
                                      {obs.map((o, idx) => (
                                        <li key={idx} className="flex items-start gap-1.5">
                                          <span className="text-green-400 font-mono mt-0.5">✓</span>
                                          <span>{o.description}</span>
                                        </li>
                                      ))}
                                    </ul>
                                  )}
                                </div>

                                {/* Heuristic Inferences */}
                                <div className="bg-gray-800/90 border border-gray-700 rounded-lg p-3">
                                  <div className="flex items-center justify-between mb-2">
                                    <span className="text-xs font-semibold text-yellow-400 uppercase tracking-wider flex items-center gap-1">
                                      <Zap className="h-3.5 w-3.5" />
                                      Heuristic Inferences ({heu.length})
                                    </span>
                                  </div>
                                  {heu.length === 0 ? (
                                    <p className="text-xs text-gray-500 italic">No transitive heuristic factors applied.</p>
                                  ) : (
                                    <ul className="space-y-1.5 text-xs text-gray-300">
                                      {heu.map((h, idx) => (
                                        <li key={idx} className="flex items-start gap-1.5">
                                          <span className="text-yellow-400 font-mono mt-0.5">⚡</span>
                                          <span>{h.description}</span>
                                        </li>
                                      ))}
                                    </ul>
                                  )}
                                </div>

                                {/* Missing / Neutral Evidence */}
                                <div className="bg-gray-800/90 border border-gray-700 rounded-lg p-3">
                                  <div className="flex items-center justify-between mb-2">
                                    <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider flex items-center gap-1">
                                      <HelpCircle className="h-3.5 w-3.5" />
                                      Missing / Neutral Baseline ({mis.length})
                                    </span>
                                  </div>
                                  {mis.length === 0 ? (
                                    <p className="text-xs text-gray-500 italic">Complete empirical records available.</p>
                                  ) : (
                                    <ul className="space-y-1.5 text-xs text-gray-400">
                                      {mis.map((m, idx) => (
                                        <li key={idx} className="flex items-start gap-1.5">
                                          <span className="text-gray-500 font-mono mt-0.5">ℹ</span>
                                          <span>{m.description}</span>
                                        </li>
                                      ))}
                                    </ul>
                                  )}
                                </div>
                              </div>

                              {/* Rationale & User Overrides */}
                              <div className="p-3 bg-gray-800/60 rounded-lg border border-gray-700 text-xs space-y-1">
                                <div>
                                  <span className="font-semibold text-gray-300">Selection Rationale:</span>{' '}
                                  <span className="text-gray-300">{trace?.rationale || item.decision_reason}</span>
                                </div>
                                {trace?.user_override ? (
                                  <div className="text-yellow-300">
                                    <span className="font-semibold">User Audit Note:</span> {trace.override_reason}
                                  </div>
                                ) : null}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Disclaimer Footer */}
            <div className="p-3 bg-gray-900/50 border-t border-gray-700 text-[11px] text-gray-500 text-center">
              {selection.disclaimer}
            </div>
          </div>
        </div>
      )}

      {/* Decision Override Modal */}
      {overrideModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-gray-800 border border-gray-700 rounded-xl max-w-md w-full p-5 space-y-4 shadow-2xl">
            <h3 className="text-base font-semibold text-gray-100 flex items-center gap-2">
              <Edit3 className="h-4 w-4 text-indigo-400" />
              Override Prioritization Decision
            </h3>

            <p className="text-xs text-gray-400">
              Manually change the selection status of <code className="text-indigo-300">{overrideModal.testcase_name}</code> for this regression run.
              An audit trace with your rationale will be permanently recorded in SQLite.
            </p>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">New Decision</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setOverrideDecision('selected')}
                  className={`p-2.5 rounded-lg border text-xs font-medium transition-colors ${
                    overrideDecision === 'selected'
                      ? 'bg-green-950/70 border-green-600 text-green-300'
                      : 'bg-gray-900 border-gray-700 text-gray-400'
                  }`}
                >
                  Include (Selected)
                </button>
                <button
                  type="button"
                  onClick={() => setOverrideDecision('excluded')}
                  className={`p-2.5 rounded-lg border text-xs font-medium transition-colors ${
                    overrideDecision === 'excluded'
                      ? 'bg-gray-700 border-gray-500 text-gray-200'
                      : 'bg-gray-900 border-gray-700 text-gray-400'
                  }`}
                >
                  Exclude (Skip)
                </button>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">
                Override Reason <span className="text-red-400">*</span> (Required for Audit)
              </label>
              <textarea
                rows="3"
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="e.g. Critical path verified manually in staging; approved by Lead QA"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg p-2.5 text-xs text-gray-200 focus:outline-none focus:border-indigo-500"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-gray-700">
              <button
                type="button"
                onClick={() => setOverrideModal(null)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-400 hover:text-gray-200"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveOverride}
                disabled={overriding || !overrideReason.trim()}
                className="px-4 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-50"
              >
                {overriding ? 'Recording...' : 'Save & Record Audit'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
