import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ShieldCheck,
  ShieldAlert,
  GitPullRequest,
  GitCommit,
  GitBranch,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  ArrowRight,
  TrendingUp,
  BarChart2,
  Eye,
  Layers,
  Filter,
  RefreshCw,
  ExternalLink,
  ChevronRight,
  Sparkles,
  FileText,
  X,
  Sliders,
  Award,
} from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export function CIDashboard() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [activeTab, setActiveTab] = useState(runId ? 'intelligence' : 'runs'); // 'runs' | 'intelligence' | 'analytics'
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [driftData, setDriftData] = useState(null);
  const [analyticsData, setAnalyticsData] = useState(null);

  const [loading, setLoading] = useState(false);
  const [loadingDrift, setLoadingDrift] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [driftCategoryFilter, setDriftCategoryFilter] = useState('all');
  const [analyticsDays, setAnalyticsDays] = useState(30);

  // Visual Diff Modal State
  const [visualModal, setVisualModal] = useState({
    isOpen: false,
    loading: false,
    testcaseId: null,
    evidence: null,
  });

  // Load runs on mount
  useEffect(() => {
    loadRuns();
  }, [statusFilter]);

  // If runId URL param changes, load specific run
  useEffect(() => {
    if (runId) {
      loadRunDetails(runId);
      setActiveTab('intelligence');
    }
  }, [runId]);

  // Load analytics when switching to analytics tab
  useEffect(() => {
    if (activeTab === 'analytics') {
      loadAnalytics(analyticsDays);
    }
  }, [activeTab, analyticsDays]);

  const loadRuns = async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter !== 'all') params.status = statusFilter;
      const data = await api.getCIRuns(params);
      setRuns(data);
    } catch (err) {
      showToast(err.message || 'Failed to load CI runs', 'error');
    } finally {
      setLoading(false);
    }
  };

  const loadRunDetails = async (id) => {
    setLoadingDrift(true);
    try {
      const [runRes, driftRes] = await Promise.all([
        api.getCIRunById(id),
        api.getCIRunDrift(id),
      ]);
      setSelectedRun(runRes);
      setDriftData(driftRes);
    } catch (err) {
      showToast(err.message || 'Failed to load PR drift details', 'error');
    } finally {
      setLoadingDrift(false);
    }
  };

  const loadAnalytics = async (days) => {
    try {
      const data = await api.getCIAnalytics({ days });
      setAnalyticsData(data);
    } catch (err) {
      showToast(err.message || 'Failed to load historical analytics', 'error');
    }
  };

  const openVisualEvidence = async (runId, testcaseId) => {
    setVisualModal({
      isOpen: true,
      loading: true,
      testcaseId,
      evidence: null,
    });
    try {
      const evidence = await api.getCIVisualDiff(runId, testcaseId);
      setVisualModal({
        isOpen: true,
        loading: false,
        testcaseId,
        evidence,
      });
    } catch (err) {
      showToast(err.message || 'Failed to load visual comparison', 'error');
      setVisualModal({ isOpen: false, loading: false, testcaseId: null, evidence: null });
    }
  };

  // Helper for status badge styling
  const getStatusBadge = (status) => {
    switch (status) {
      case 'PASSED':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3.5 h-3.5" />
            PASSED
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20">
            <XCircle className="w-3.5 h-3.5" />
            GATE BLOCKED
          </span>
        );
      case 'ERROR':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
            <AlertTriangle className="w-3.5 h-3.5" />
            INFRA ERROR
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-500/10 text-slate-600 dark:text-slate-400 border border-slate-500/20">
            {status}
          </span>
        );
    }
  };

  // Helper for transition badges in drift table
  const renderTransitionPill = (baseStatus, prStatus) => {
    const statusColor = (s) => {
      if (s === 'passed') return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20';
      if (s === 'failed') return 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20';
      if (s === 'flaky') return 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20';
      return 'bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20';
    };

    return (
      <div className="flex items-center gap-1.5 font-mono text-xs">
        <span className={`px-2 py-0.5 rounded border ${statusColor(baseStatus || 'none')}`}>
          {baseStatus || 'no base'}
        </span>
        <ArrowRight className="w-3 h-3 text-slate-400" />
        <span className={`px-2 py-0.5 rounded border font-semibold ${statusColor(prStatus)}`}>
          {prStatus}
        </span>
      </div>
    );
  };

  // Filter drift items for the PR intelligence view
  const getFilteredDriftItems = () => {
    if (!driftData || !driftData.items) return [];
    if (driftCategoryFilter === 'all') return driftData.items;
    if (driftCategoryFilter === 'new_regressions') {
      return driftData.items.filter((i) => i.classification === 'new_regression');
    }
    if (driftCategoryFilter === 'pre_existing') {
      return driftData.items.filter((i) => i.classification === 'pre_existing_failure');
    }
    if (driftCategoryFilter === 'fixed') {
      return driftData.items.filter((i) => i.classification === 'fixed_regression');
    }
    if (driftCategoryFilter === 'flaky') {
      return driftData.items.filter((i) => ['newly_flaky', 'persistent_flaky'].includes(i.classification));
    }
    if (driftCategoryFilter === 'definition_drift') {
      return driftData.items.filter((i) => i.test_definition_drift);
    }
    return driftData.items;
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 dark:border-surface-borderDark pb-5">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-gradient-to-tr from-brand-600 to-indigo-600 text-white shadow-md shadow-brand-500/20">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 flex items-center gap-2">
                CI Quality Gate & Regression Drift
                <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20">
                  Continuous Quality
                </span>
              </h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Deterministic baseline verification, regression drift classification, and continuous pull request quality gates.
              </p>
            </div>
          </div>
        </div>

        {/* Tab navigation pills */}
        <div className="flex items-center bg-slate-100 dark:bg-surface-panelDark p-1 rounded-xl border border-slate-200 dark:border-surface-borderDark shrink-0">
          <button
            onClick={() => {
              setActiveTab('runs');
              navigate('/ci');
            }}
            className={`flex items-center gap-2 px-3.5 py-1.5 text-sm font-medium rounded-lg transition-all ${
              activeTab === 'runs'
                ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
            }`}
          >
            <GitPullRequest className="w-4 h-4" />
            CI Runs History
          </button>
          <button
            onClick={() => {
              if (selectedRun) setActiveTab('intelligence');
            }}
            disabled={!selectedRun}
            className={`flex items-center gap-2 px-3.5 py-1.5 text-sm font-medium rounded-lg transition-all ${
              !selectedRun ? 'opacity-40 cursor-not-allowed text-slate-400' : ''
            } ${
              activeTab === 'intelligence'
                ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
            }`}
          >
            <Sparkles className="w-4 h-4" />
            PR Intelligence
            {selectedRun && (
              <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
            )}
          </button>
          <button
            onClick={() => setActiveTab('analytics')}
            className={`flex items-center gap-2 px-3.5 py-1.5 text-sm font-medium rounded-lg transition-all ${
              activeTab === 'analytics'
                ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
            }`}
          >
            <BarChart2 className="w-4 h-4" />
            Historical Analytics
          </button>
        </div>
      </div>

      {/* -------------------------------------------------------------------- */}
      {/* TAB 1: CI Runs History Dashboard                                    */}
      {/* -------------------------------------------------------------------- */}
      {activeTab === 'runs' && (
        <div className="space-y-6">
          {/* Quick Metrics Bar */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark shadow-sm">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Total CI Runs</span>
              <div className="mt-2 flex items-baseline justify-between">
                <span className="text-2xl font-bold text-slate-900 dark:text-slate-100">{runs.length}</span>
                <span className="text-xs text-slate-400">Persisted Runs</span>
              </div>
            </div>
            <div className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark shadow-sm">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Quality Gate Pass Rate</span>
              <div className="mt-2 flex items-baseline justify-between">
                <span className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                  {runs.length > 0
                    ? `${Math.round((runs.filter((r) => r.gate_passed === 1).length / runs.length) * 100)}%`
                    : '100%'}
                </span>
                <span className="text-xs text-emerald-600 dark:text-emerald-400">Standard Policy</span>
              </div>
            </div>
            <div className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark shadow-sm">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">New Regressions Blocked</span>
              <div className="mt-2 flex items-baseline justify-between">
                <span className="text-2xl font-bold text-rose-600 dark:text-rose-400">
                  {runs.reduce((acc, r) => acc + (r.new_regressions_count || 0), 0)}
                </span>
                <span className="text-xs text-rose-600 dark:text-rose-400">True PR Breaches</span>
              </div>
            </div>
            <div className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark shadow-sm">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Pre-Existing Debt Tolerated</span>
              <div className="mt-2 flex items-baseline justify-between">
                <span className="text-2xl font-bold text-amber-600 dark:text-amber-400">
                  {runs.reduce((acc, r) => acc + (r.pre_existing_failures_count || 0), 0)}
                </span>
                <span className="text-xs text-slate-400">Unblocked PRs</span>
              </div>
            </div>
          </div>

          {/* Filter Bar */}
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400 flex items-center gap-1">
                <Filter className="w-3.5 h-3.5" /> Filter Status:
              </span>
              {['all', 'PASSED', 'FAILED', 'ERROR'].map((st) => (
                <button
                  key={st}
                  onClick={() => setStatusFilter(st)}
                  className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                    statusFilter === st
                      ? 'bg-brand-600 text-white'
                      : 'bg-slate-100 dark:bg-surface-panelDark text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-800'
                  }`}
                >
                  {st === 'all' ? 'All Runs' : st}
                </button>
              ))}
            </div>

            <button
              onClick={loadRuns}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-surface-borderDark text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-surface-panelDark"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          {/* Runs Table */}
          <div className="border border-slate-200 dark:border-surface-borderDark rounded-xl overflow-hidden bg-white dark:bg-surface-panelDark shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 dark:bg-slate-900/40 text-xs font-semibold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-surface-borderDark">
                  <tr>
                    <th className="px-4 py-3">Gate Status</th>
                    <th className="px-4 py-3">Commit & Branch</th>
                    <th className="px-4 py-3">Policy</th>
                    <th className="px-4 py-3">Regression Impact</th>
                    <th className="px-4 py-3">Execution Tests</th>
                    <th className="px-4 py-3">Duration</th>
                    <th className="px-4 py-3">Triggered</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-surface-borderDark">
                  {runs.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="px-4 py-12 text-center text-slate-400">
                        No CI quality gate runs found. Execute tests via <code className="text-xs bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded font-mono">tracecase ci</code> or CI workflows.
                      </td>
                    </tr>
                  ) : (
                    runs.map((r) => (
                      <tr
                        key={r.id}
                        className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 cursor-pointer transition-colors"
                        onClick={() => {
                          navigate(`/ci/${r.id}`);
                        }}
                      >
                        <td className="px-4 py-3.5 whitespace-nowrap">
                          {getStatusBadge(r.status)}
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="flex flex-col">
                            <div className="flex items-center gap-1.5 font-mono text-xs font-semibold text-slate-800 dark:text-slate-200">
                              <GitCommit className="w-3.5 h-3.5 text-slate-400" />
                              {(r.commit_hash || 'HEAD').slice(0, 8)}
                            </div>
                            <div className="flex items-center gap-1 text-xs text-slate-400 font-mono mt-0.5">
                              <GitBranch className="w-3 h-3" />
                              {r.branch || 'detached'}
                              {r.base_ref && (
                                <span className="text-slate-500">→ {r.base_ref}</span>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap">
                          <span className="text-xs uppercase tracking-wider font-mono font-medium px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                            {r.policy_name}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap">
                          <div className="flex items-center gap-1.5">
                            {r.new_regressions_count > 0 ? (
                              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20">
                                +{r.new_regressions_count} new regression
                              </span>
                            ) : (
                              <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                                0 new
                              </span>
                            )}
                            {r.pre_existing_failures_count > 0 && (
                              <span className="text-xs text-slate-400 font-medium">
                                ({r.pre_existing_failures_count} pre-existing)
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap text-xs text-slate-600 dark:text-slate-300">
                          <span className="font-semibold text-slate-900 dark:text-slate-100">
                            {r.executed_count}
                          </span>{' '}
                          / {r.total_considered} selected
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap font-mono text-xs text-slate-500">
                          <div className="flex items-center gap-1">
                            <Clock className="w-3.5 h-3.5" />
                            {Number(r.duration_seconds || 0).toFixed(1)}s
                          </div>
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap text-xs text-slate-400">
                          {new Date(r.created_at).toLocaleString([], {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap text-right">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              navigate(`/ci/${r.id}`);
                            }}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium text-brand-600 dark:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-500/10"
                          >
                            PR Drift <ChevronRight className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* -------------------------------------------------------------------- */}
      {/* TAB 2: PR Regression Intelligence Detail                            */}
      {/* -------------------------------------------------------------------- */}
      {activeTab === 'intelligence' && (
        <div className="space-y-6">
          {loadingDrift ? (
            <div className="p-12 text-center text-slate-400">
              <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
              Loading PR regression intelligence & drift analysis...
            </div>
          ) : !selectedRun ? (
            <div className="p-12 text-center text-slate-400">
              No CI run selected. Select a run from the CI Runs History tab.
            </div>
          ) : (
            <>
              {/* Back breadcrumb */}
              <button
                onClick={() => {
                  setActiveTab('runs');
                  navigate('/ci');
                }}
                className="text-xs text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-1 font-medium"
              >
                ← Back to CI Runs History
              </button>

              {/* Gate Result Banner */}
              <div
                className={`p-5 rounded-xl border ${
                  selectedRun.gate_passed === 1
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-900 dark:text-emerald-100'
                    : 'bg-rose-500/10 border-rose-500/30 text-rose-900 dark:text-rose-100'
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3">
                    {selectedRun.gate_passed === 1 ? (
                      <CheckCircle2 className="w-6 h-6 text-emerald-600 dark:text-emerald-400 mt-0.5 shrink-0" />
                    ) : (
                      <XCircle className="w-6 h-6 text-rose-600 dark:text-rose-400 mt-0.5 shrink-0" />
                    )}
                    <div>
                      <h2 className="text-lg font-bold flex items-center gap-2">
                        {selectedRun.gate_passed === 1
                          ? 'QUALITY GATE PASSED'
                          : 'QUALITY GATE BLOCKED'}
                        <span className="text-xs px-2 py-0.5 rounded uppercase font-mono font-medium bg-white/20 dark:bg-black/20">
                          Policy: {selectedRun.policy_name}
                        </span>
                      </h2>
                      <p className="text-sm mt-1 opacity-90">{selectedRun.gate_summary}</p>
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <span className="text-xs font-mono block opacity-75">
                      Exit Code: {selectedRun.exit_code}
                    </span>
                    <span className="text-xs font-mono block opacity-75">
                      Duration: {Number(selectedRun.duration_seconds).toFixed(2)}s
                    </span>
                  </div>
                </div>
              </div>

              {/* PR Git Context Banner */}
              <div className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-slate-50 dark:bg-slate-900/40 flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3 text-sm">
                  <div className="flex items-center gap-1.5 font-mono text-xs font-semibold">
                    <GitBranch className="w-4 h-4 text-slate-400" />
                    {selectedRun.branch || 'detached'}
                  </div>
                  <ArrowRight className="w-4 h-4 text-slate-400" />
                  <div className="flex items-center gap-1.5 font-mono text-xs">
                    <span className="text-slate-500">Base:</span>
                    <span className="font-semibold">{selectedRun.base_ref || 'origin/main'}</span>
                  </div>
                  <span className="text-slate-300 dark:text-slate-700">|</span>
                  <div className="flex items-center gap-1.5 font-mono text-xs">
                    <GitCommit className="w-3.5 h-3.5 text-slate-400" />
                    <span>{(selectedRun.commit_hash || '').slice(0, 8)}</span>
                  </div>
                </div>

                <div className="text-xs text-slate-500 font-mono">
                  Surface Code Coverage: <strong>{Number(selectedRun.surface_coverage_pct || 100).toFixed(1)}%</strong>
                </div>
              </div>

              {/* 5 Regression KPI Cards */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div
                  onClick={() => setDriftCategoryFilter('new_regressions')}
                  className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                    driftCategoryFilter === 'new_regressions'
                      ? 'border-rose-500 ring-2 ring-rose-500/20 bg-rose-500/10'
                      : 'border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark hover:border-slate-300'
                  }`}
                >
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400 block">
                    New Regressions
                  </span>
                  <div className="mt-1.5 flex items-baseline justify-between">
                    <span className="text-2xl font-bold text-rose-600 dark:text-rose-400">
                      {selectedRun.new_regressions_count || 0}
                    </span>
                    <span className="text-xs text-rose-600 dark:text-rose-400 font-semibold">Blocks Gate</span>
                  </div>
                </div>

                <div
                  onClick={() => setDriftCategoryFilter('pre_existing')}
                  className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                    driftCategoryFilter === 'pre_existing'
                      ? 'border-amber-500 ring-2 ring-amber-500/20 bg-amber-500/10'
                      : 'border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark hover:border-slate-300'
                  }`}
                >
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400 block">
                    Pre-Existing Failures
                  </span>
                  <div className="mt-1.5 flex items-baseline justify-between">
                    <span className="text-2xl font-bold text-amber-600 dark:text-amber-400">
                      {selectedRun.pre_existing_failures_count || 0}
                    </span>
                    <span className="text-xs text-amber-600 dark:text-amber-400 font-medium">Tolerated</span>
                  </div>
                </div>

                <div
                  onClick={() => setDriftCategoryFilter('fixed')}
                  className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                    driftCategoryFilter === 'fixed'
                      ? 'border-emerald-500 ring-2 ring-emerald-500/20 bg-emerald-500/10'
                      : 'border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark hover:border-slate-300'
                  }`}
                >
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400 block">
                    Fixed Regressions
                  </span>
                  <div className="mt-1.5 flex items-baseline justify-between">
                    <span className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                      {selectedRun.fixed_regressions_count || 0}
                    </span>
                    <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">Resolved</span>
                  </div>
                </div>

                <div
                  onClick={() => setDriftCategoryFilter('flaky')}
                  className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                    driftCategoryFilter === 'flaky'
                      ? 'border-purple-500 ring-2 ring-purple-500/20 bg-purple-500/10'
                      : 'border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark hover:border-slate-300'
                  }`}
                >
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400 block">
                    Newly Flaky Tests
                  </span>
                  <div className="mt-1.5 flex items-baseline justify-between">
                    <span className="text-2xl font-bold text-purple-600 dark:text-purple-400">
                      {driftData?.summary?.newly_flaky_count || 0}
                    </span>
                    <span className="text-xs text-purple-600 dark:text-purple-400 font-medium">Recovered</span>
                  </div>
                </div>

                <div
                  onClick={() => setDriftCategoryFilter('definition_drift')}
                  className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                    driftCategoryFilter === 'definition_drift'
                      ? 'border-blue-500 ring-2 ring-blue-500/20 bg-blue-500/10'
                      : 'border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark hover:border-slate-300'
                  }`}
                >
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400 block">
                    Definition Drift
                  </span>
                  <div className="mt-1.5 flex items-baseline justify-between">
                    <span className="text-2xl font-bold text-blue-600 dark:text-blue-400">
                      {driftData?.grouped?.definition_drift?.length || 0}
                    </span>
                    <span className="text-xs text-blue-600 dark:text-blue-400 font-medium">Steps Changed</span>
                  </div>
                </div>
              </div>

              {/* Categorization Tabs */}
              <div className="flex items-center gap-2 border-b border-slate-200 dark:border-surface-borderDark pb-2 overflow-x-auto text-xs font-medium">
                <button
                  onClick={() => setDriftCategoryFilter('all')}
                  className={`px-3 py-1.5 rounded-lg transition-colors ${
                    driftCategoryFilter === 'all'
                      ? 'bg-brand-600 text-white'
                      : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                  }`}
                >
                  All Test Items ({driftData?.items?.length || 0})
                </button>
                <button
                  onClick={() => setDriftCategoryFilter('new_regressions')}
                  className={`px-3 py-1.5 rounded-lg transition-colors ${
                    driftCategoryFilter === 'new_regressions'
                      ? 'bg-rose-600 text-white'
                      : 'text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-500/10'
                  }`}
                >
                  New Regressions ({selectedRun.new_regressions_count || 0})
                </button>
                <button
                  onClick={() => setDriftCategoryFilter('pre_existing')}
                  className={`px-3 py-1.5 rounded-lg transition-colors ${
                    driftCategoryFilter === 'pre_existing'
                      ? 'bg-amber-600 text-white'
                      : 'text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-500/10'
                  }`}
                >
                  Pre-Existing Failures ({selectedRun.pre_existing_failures_count || 0})
                </button>
                <button
                  onClick={() => setDriftCategoryFilter('fixed')}
                  className={`px-3 py-1.5 rounded-lg transition-colors ${
                    driftCategoryFilter === 'fixed'
                      ? 'bg-emerald-600 text-white'
                      : 'text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-500/10'
                  }`}
                >
                  Fixed Regressions ({selectedRun.fixed_regressions_count || 0})
                </button>
                <button
                  onClick={() => setDriftCategoryFilter('flaky')}
                  className={`px-3 py-1.5 rounded-lg transition-colors ${
                    driftCategoryFilter === 'flaky'
                      ? 'bg-purple-600 text-white'
                      : 'text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-500/10'
                  }`}
                >
                  Flaky Tests ({driftData?.summary?.newly_flaky_count || 0})
                </button>
                <button
                  onClick={() => setDriftCategoryFilter('definition_drift')}
                  className={`px-3 py-1.5 rounded-lg transition-colors ${
                    driftCategoryFilter === 'definition_drift'
                      ? 'bg-blue-600 text-white'
                      : 'text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-500/10'
                  }`}
                >
                  Definition Drift ({driftData?.grouped?.definition_drift?.length || 0})
                </button>
              </div>

              {/* Drift Test Breakdown Table */}
              <div className="border border-slate-200 dark:border-surface-borderDark rounded-xl overflow-hidden bg-white dark:bg-surface-panelDark shadow-sm">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-slate-50 dark:bg-slate-900/40 text-xs font-semibold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-surface-borderDark">
                      <tr>
                        <th className="px-4 py-3">Test Case Name</th>
                        <th className="px-4 py-3">Outcome Transition</th>
                        <th className="px-4 py-3">Attribution & Category</th>
                        <th className="px-4 py-3">Duration & Delta (Δ)</th>
                        <th className="px-4 py-3">Definition Drift</th>
                        <th className="px-4 py-3 text-right">Evidence</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-surface-borderDark">
                      {getFilteredDriftItems().length === 0 ? (
                        <tr>
                          <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                            No test items found for selected filter.
                          </td>
                        </tr>
                      ) : (
                        getFilteredDriftItems().map((item) => (
                          <tr
                            key={item.testcase_id}
                            className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition-colors"
                          >
                            <td className="px-4 py-3 font-medium text-slate-900 dark:text-slate-100">
                              <div>{item.testcase_name || item.testcase_id}</div>
                              <div className="text-xs text-slate-400 font-mono mt-0.5">
                                {item.testcase_id}
                              </div>
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap">
                              {renderTransitionPill(item.base_status, item.pr_status)}
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold font-mono uppercase ${
                                  item.classification === 'new_regression'
                                    ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                                    : item.classification === 'pre_existing_failure'
                                    ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                                    : item.classification === 'fixed_regression'
                                    ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                                    : item.classification === 'newly_flaky'
                                    ? 'bg-purple-500/10 text-purple-600 dark:text-purple-400'
                                    : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400'
                                }`}
                              >
                                {item.classification.replace(/_/g, ' ')}
                              </span>
                              {item.explanation && (
                                <p className="text-xs text-slate-500 mt-1 line-clamp-1">
                                  {item.explanation}
                                </p>
                              )}
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap font-mono text-xs">
                              <div>{Math.round(item.pr_duration_ms || 0)}ms</div>
                              {item.duration_delta_ms !== null && (
                                <div
                                  className={`text-xs ${
                                    item.duration_delta_ms > 0
                                      ? 'text-amber-600 dark:text-amber-400'
                                      : 'text-emerald-600 dark:text-emerald-400'
                                  }`}
                                >
                                  {item.duration_delta_ms > 0 ? '+' : ''}
                                  {Math.round(item.duration_delta_ms)}ms
                                </div>
                              )}
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap">
                              {item.test_definition_drift ? (
                                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                                  Locators Modified
                                </span>
                              ) : (
                                <span className="text-xs text-slate-400">Identical</span>
                              )}
                            </td>
                            <td className="px-4 py-3 whitespace-nowrap text-right">
                              <button
                                onClick={() => openVisualEvidence(selectedRun.id, item.testcase_id)}
                                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg border border-slate-200 dark:border-surface-borderDark text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                              >
                                <Eye className="w-3.5 h-3.5 text-brand-500" />
                                Evidence
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* -------------------------------------------------------------------- */}
      {/* TAB 3: Historical CI Analytics                                      */}
      {/* -------------------------------------------------------------------- */}
      {activeTab === 'analytics' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
              CI Quality Gate Metrics & Flakiness Analytics
            </h2>
            <div className="flex items-center gap-1 bg-slate-100 dark:bg-surface-panelDark p-1 rounded-lg border border-slate-200 dark:border-surface-borderDark text-xs font-medium">
              {[7, 14, 30, 90].map((d) => (
                <button
                  key={d}
                  onClick={() => setAnalyticsDays(d)}
                  className={`px-2.5 py-1 rounded ${
                    analyticsDays === d
                      ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 shadow-sm'
                      : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>
          </div>

          {analyticsData && (
            <>
              {/* Overview Metrics Cards */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark shadow-sm">
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Total CI Runs</span>
                  <div className="mt-2 text-2xl font-bold text-slate-900 dark:text-slate-100">
                    {analyticsData.overview.total_runs || 0}
                  </div>
                </div>
                <div className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark shadow-sm">
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Pass Rate</span>
                  <div className="mt-2 text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                    {analyticsData.overview.pass_rate_pct || 100}%
                  </div>
                </div>
                <div className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark shadow-sm">
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Avg Run Duration</span>
                  <div className="mt-2 text-2xl font-bold text-slate-900 dark:text-slate-100 font-mono">
                    {Number(analyticsData.overview.avg_duration_s || 0).toFixed(1)}s
                  </div>
                </div>
                <div className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark shadow-sm">
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400">Total Regressions Blocked</span>
                  <div className="mt-2 text-2xl font-bold text-rose-600 dark:text-rose-400">
                    {analyticsData.overview.total_new_regressions || 0}
                  </div>
                </div>
              </div>

              {/* Two Column Layout: Daily Trends & Branch Breakdown */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Daily Activity Breakdown */}
                <div className="p-5 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark shadow-sm space-y-4">
                  <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-brand-600" />
                    Daily CI Run Volume & Regressions
                  </h3>
                  {analyticsData.runs_by_day.length === 0 ? (
                    <p className="text-xs text-slate-400 py-6 text-center">No runs in this time window.</p>
                  ) : (
                    <div className="space-y-2">
                      {analyticsData.runs_by_day.map((day) => (
                        <div key={day.date} className="flex items-center justify-between text-xs py-1.5 border-b border-slate-100 dark:border-slate-800">
                          <span className="font-mono text-slate-600 dark:text-slate-400">{day.date}</span>
                          <div className="flex items-center gap-3">
                            <span className="text-slate-900 dark:text-slate-200 font-semibold">{day.total} runs</span>
                            <span className="text-emerald-600 font-medium">{day.passed} passed</span>
                            {day.new_regressions > 0 && (
                              <span className="text-rose-600 font-medium">+{day.new_regressions} reg</span>
                            )}
                            <span className="font-mono text-slate-400">{day.avg_duration_s}s</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Branch Breakdown */}
                <div className="p-5 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark shadow-sm space-y-4">
                  <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                    <GitBranch className="w-4 h-4 text-brand-600" />
                    Branch Distribution & Regression Frequency
                  </h3>
                  {analyticsData.branch_breakdown.length === 0 ? (
                    <p className="text-xs text-slate-400 py-6 text-center">No branch activity recorded.</p>
                  ) : (
                    <div className="space-y-2">
                      {analyticsData.branch_breakdown.map((b) => (
                        <div key={b.branch_name} className="flex items-center justify-between text-xs py-1.5 border-b border-slate-100 dark:border-slate-800">
                          <span className="font-mono font-medium text-slate-800 dark:text-slate-200">{b.branch_name}</span>
                          <div className="flex items-center gap-3">
                            <span className="text-slate-500">{b.total_runs} runs</span>
                            <span className="text-emerald-600 font-semibold">
                              {Math.round((b.passed_runs / b.total_runs) * 100)}% pass
                            </span>
                            {b.new_regressions > 0 ? (
                              <span className="text-rose-600 font-semibold">+{b.new_regressions} new reg</span>
                            ) : (
                              <span className="text-slate-400">0 reg</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Flakiest Tests Leaderboard */}
              <div className="p-5 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-panelDark shadow-sm space-y-4">
                <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                  <Award className="w-4 h-4 text-purple-600" />
                  CI Flakiest Tests Leaderboard
                </h3>
                {analyticsData.top_flaky_tests.length === 0 ? (
                  <p className="text-xs text-slate-400 py-4 text-center">
                    Zero test flakiness recorded in the last {analyticsDays} days!
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-50 dark:bg-slate-900/40 text-slate-500 font-semibold border-b border-slate-200 dark:border-surface-borderDark">
                        <tr>
                          <th className="px-3 py-2">Test Case</th>
                          <th className="px-3 py-2">Flaky Occurrences</th>
                          <th className="px-3 py-2">Newly Flaky</th>
                          <th className="px-3 py-2">Persistent Flaky</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200 dark:divide-surface-borderDark">
                        {analyticsData.top_flaky_tests.map((f) => (
                          <tr key={f.testcase_id}>
                            <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">
                              {f.testcase_name || f.testcase_id}
                              <span className="block text-[10px] font-mono text-slate-400">{f.testcase_id}</span>
                            </td>
                            <td className="px-3 py-2 font-bold text-purple-600 dark:text-purple-400">
                              {f.flaky_occurrences}
                            </td>
                            <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                              {f.newly_flaky_count}
                            </td>
                            <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                              {f.persistent_flaky_count}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* -------------------------------------------------------------------- */}
      {/* Visual Evidence Comparison Modal (Subphase 8.4.3)                   */}
      {/* -------------------------------------------------------------------- */}
      {visualModal.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
          <div className="bg-white dark:bg-surface-panelDark border border-slate-200 dark:border-surface-borderDark rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto shadow-2xl p-6 space-y-6">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-surface-borderDark pb-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                  <Eye className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">
                    Visual Evidence & Regression Trace
                  </h3>
                  <p className="text-xs text-slate-500 font-mono">
                    {visualModal.evidence?.testcase_name || visualModal.testcaseId}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setVisualModal({ isOpen: false, loading: false, testcaseId: null, evidence: null })}
                className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {visualModal.loading ? (
              <div className="py-12 text-center text-slate-400">
                <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2" />
                Retrieving side-by-side execution artifacts...
              </div>
            ) : visualModal.evidence ? (
              <div className="space-y-6">
                {/* Classification Banner */}
                <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-surface-borderDark flex items-center justify-between flex-wrap gap-2 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-700 dark:text-slate-300">Classification:</span>
                    <span className="px-2 py-0.5 rounded font-mono font-bold uppercase bg-brand-500/10 text-brand-600 dark:text-brand-400">
                      {visualModal.evidence.classification}
                    </span>
                  </div>
                  {visualModal.evidence.test_definition_drift && (
                    <span className="px-2 py-0.5 rounded font-semibold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                      ⚠️ Test Definition Changed in PR
                    </span>
                  )}
                  {visualModal.evidence.duration_delta_ms !== null && (
                    <div className="font-mono text-slate-500">
                      Duration Delta (Δ):{' '}
                      <strong>{Math.round(visualModal.evidence.duration_delta_ms)}ms</strong>
                    </div>
                  )}
                </div>

                {/* Side by Side Comparison Panels */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Left: Base Run Evidence */}
                  <div className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-slate-50/50 dark:bg-slate-900/30 space-y-3">
                    <div className="flex items-center justify-between border-b border-slate-200 dark:border-surface-borderDark pb-2">
                      <span className="text-xs font-bold uppercase text-slate-500">Base Execution</span>
                      <span className="text-xs font-semibold px-2 py-0.5 rounded uppercase font-mono bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                        {visualModal.evidence.base_evidence?.status || 'No Baseline'}
                      </span>
                    </div>

                    <div className="space-y-1 text-xs">
                      <div className="text-slate-500">Duration:</div>
                      <div className="font-mono font-medium">
                        {visualModal.evidence.base_evidence?.duration_ms || 0}ms
                      </div>
                    </div>

                    <div className="space-y-1 text-xs">
                      <div className="text-slate-500">Error / Exception:</div>
                      <div className="p-2.5 rounded bg-slate-100 dark:bg-slate-900 font-mono text-[11px] text-slate-600 dark:text-slate-400 overflow-x-auto max-h-24">
                        {visualModal.evidence.base_evidence?.error_message || 'None (Clean Run)'}
                      </div>
                    </div>

                    <div className="space-y-1 text-xs">
                      <div className="text-slate-500">Screenshot:</div>
                      <div className="h-36 rounded border border-dashed border-slate-300 dark:border-slate-700 flex items-center justify-center text-slate-400 bg-white/50 dark:bg-black/20 text-center p-2">
                        {visualModal.evidence.base_evidence?.screenshot_path ? (
                          <img
                            src={visualModal.evidence.base_evidence.screenshot_path}
                            alt="Base screenshot"
                            className="max-h-full rounded object-contain"
                          />
                        ) : (
                          'No baseline screenshot stored'
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Right: PR Run Evidence */}
                  <div className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-slate-50/50 dark:bg-slate-900/30 space-y-3">
                    <div className="flex items-center justify-between border-b border-slate-200 dark:border-surface-borderDark pb-2">
                      <span className="text-xs font-bold uppercase text-slate-500">PR Execution (Candidate)</span>
                      <span
                        className={`text-xs font-semibold px-2 py-0.5 rounded uppercase font-mono ${
                          visualModal.evidence.pr_evidence?.status === 'failed'
                            ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                            : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                        }`}
                      >
                        {visualModal.evidence.pr_evidence?.status || 'Unknown'}
                      </span>
                    </div>

                    <div className="space-y-1 text-xs">
                      <div className="text-slate-500">Duration:</div>
                      <div className="font-mono font-medium">
                        {visualModal.evidence.pr_evidence?.duration_ms || 0}ms
                      </div>
                    </div>

                    <div className="space-y-1 text-xs">
                      <div className="text-slate-500">Error / Exception:</div>
                      <div className="p-2.5 rounded bg-slate-100 dark:bg-slate-900 font-mono text-[11px] text-rose-600 dark:text-rose-400 overflow-x-auto max-h-24">
                        {visualModal.evidence.pr_evidence?.error_message || 'None (Clean Run)'}
                      </div>
                    </div>

                    <div className="space-y-1 text-xs">
                      <div className="text-slate-500">Screenshot / Failed View:</div>
                      <div className="h-36 rounded border border-dashed border-slate-300 dark:border-slate-700 flex items-center justify-center text-slate-400 bg-white/50 dark:bg-black/20 text-center p-2">
                        {visualModal.evidence.pr_evidence?.screenshot_path ? (
                          <img
                            src={visualModal.evidence.pr_evidence.screenshot_path}
                            alt="PR screenshot"
                            className="max-h-full rounded object-contain"
                          />
                        ) : (
                          'No PR screenshot stored'
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setVisualModal({ isOpen: false, loading: false, testcaseId: null, evidence: null })}
                className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200"
              >
                Close Comparison
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CIDashboard;
