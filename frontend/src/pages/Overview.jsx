import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import {
  FileCode2,
  CheckCircle2,
  XCircle,
  Clock,
  TrendingUp,
  Play,
  Video,
  Plus,
  Sparkles,
  ArrowRight,
  RefreshCw,
  Layers,
  ChevronRight,
  ShieldCheck,
} from 'lucide-react';
import { api } from '../services/api';
import { useProject } from '../context/ProjectContext';
import { useWebSocket } from '../context/WebSocketContext';
import { useToast } from '../context/ToastContext';

export function Overview() {
  const { currentProject } = useProject();
  const { subscribe } = useWebSocket();
  const { showToast } = useToast();
  const { openRecordModal } = useOutletContext() || {};
  const navigate = useNavigate();

  const [metrics, setMetrics] = useState({
    total_testcases: 0,
    total_executions: 0,
    passed_executions: 0,
    failed_executions: 0,
    running_executions: 0,
    success_rate: 100,
    avg_duration_sec: 0,
    recent_executions: [],
    execution_trends: [],
  });
  const [loading, setLoading] = useState(true);

  const fetchDashboardData = useCallback(async () => {
    try {
      const data = await api.getMetrics(currentProject?.id);
      setMetrics(data);
    } catch (err) {
      console.error('Failed to load metrics:', err);
    } finally {
      setLoading(false);
    }
  }, [currentProject?.id]);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  // Subscribe to live execution progress
  useEffect(() => {
    const unsubscribe = subscribe('executions', (event) => {
      if (
        event.type === 'execution_completed' ||
        event.type === 'execution_started' ||
        event.type === 'execution_queued'
      ) {
        fetchDashboardData();
      }
    });
    return unsubscribe;
  }, [subscribe, fetchDashboardData]);

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* Top Welcome & Actions Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 rounded-2xl bg-gradient-to-r from-brand-900/40 via-surface-cardDark to-surface-cardDark border border-slate-200 dark:border-surface-borderDark relative overflow-hidden">
        <div className="relative z-10">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-brand-400 mb-1">
            <ShieldCheck className="w-4 h-4" />
            <span>Autonomous QA Platform</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            {currentProject?.name || 'Workspace Overview'}
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Real user interaction recording, resilient self-healing replays, and AI-driven quality intelligence.
          </p>
        </div>

        <div className="relative z-10 flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => openRecordModal?.() || navigate('/recorder')}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-600/25 transition-all"
          >
            <Video className="w-4 h-4" />
            <span>Record Browser</span>
          </button>
          <button
            onClick={() => navigate('/ai-assistant')}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-500/25 transition-all"
          >
            <Sparkles className="w-4 h-4" />
            <span>AI Assistant</span>
          </button>
          <button
            onClick={fetchDashboardData}
            className="p-2.5 rounded-xl border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 hover:text-slate-900 dark:hover:text-slate-100 transition-colors"
            title="Refresh metrics"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Total Test Cases */}
        <div className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-xs font-semibold uppercase tracking-wider">Total Test Cases</span>
            <div className="p-2 rounded-xl bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400">
              <FileCode2 className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4">
            <div className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
              {metrics.total_testcases}
            </div>
            <div className="text-xs text-slate-400 dark:text-slate-500 mt-1 flex items-center gap-1">
              <span>Recorded workflows ready to run</span>
            </div>
          </div>
        </div>

        {/* Card 2: Passed vs Failed Executions */}
        <div className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-xs font-semibold uppercase tracking-wider">Test Executions</span>
            <div className="p-2 rounded-xl bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4">
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400">
                {metrics.passed_executions}
              </span>
              <span className="text-xs font-medium text-slate-400">passed</span>
              <span className="text-xl font-bold text-rose-500 ml-2">
                {metrics.failed_executions}
              </span>
              <span className="text-xs font-medium text-slate-400">failed</span>
            </div>
            <div className="text-xs text-slate-400 dark:text-slate-500 mt-1">
              {metrics.total_executions} total runs recorded
            </div>
          </div>
        </div>

        {/* Card 3: Success Rate */}
        <div className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-xs font-semibold uppercase tracking-wider">Success Rate</span>
            <div className="p-2 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
              <TrendingUp className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4">
            <div className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
              {metrics.success_rate}%
            </div>
            <div className="w-full bg-slate-100 dark:bg-slate-800 rounded-full h-1.5 mt-2 overflow-hidden">
              <div
                className="bg-brand-500 h-1.5 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(metrics.success_rate, 100)}%` }}
              />
            </div>
          </div>
        </div>

        {/* Card 4: Avg Execution Time */}
        <div className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-xs font-semibold uppercase tracking-wider">Avg Duration</span>
            <div className="p-2 rounded-xl bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400">
              <Clock className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4">
            <div className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
              {metrics.avg_duration_sec > 0 ? `${metrics.avg_duration_sec}s` : '0.0s'}
            </div>
            <div className="text-xs text-slate-400 dark:text-slate-500 mt-1">
              Per testcase replay cycle
            </div>
          </div>
        </div>
      </div>

      {/* Quick Action Shortcuts */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <button
          onClick={() => navigate('/testcases')}
          className="flex items-center gap-3.5 p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark hover:border-brand-500/50 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-all text-left group"
        >
          <div className="p-2.5 rounded-xl bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400 shrink-0 group-hover:scale-110 transition-transform">
            <Plus className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-slate-900 dark:text-white truncate">
              Test Cases
            </div>
            <div className="text-xs text-slate-500 truncate">Inspect and edit steps</div>
          </div>
          <ChevronRight className="w-4 h-4 text-slate-400 group-hover:translate-x-0.5 transition-transform" />
        </button>

        <button
          onClick={() => openRecordModal?.() || navigate('/recorder')}
          className="flex items-center gap-3.5 p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark hover:border-rose-500/50 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-all text-left group"
        >
          <div className="p-2.5 rounded-xl bg-rose-50 dark:bg-rose-950/60 text-rose-500 shrink-0 group-hover:scale-110 transition-transform">
            <Video className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-slate-900 dark:text-white truncate">
              Browser Recorder
            </div>
            <div className="text-xs text-slate-500 truncate">Capture real user session</div>
          </div>
          <ChevronRight className="w-4 h-4 text-slate-400 group-hover:translate-x-0.5 transition-transform" />
        </button>

        <button
          onClick={() => navigate('/suites')}
          className="flex items-center gap-3.5 p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark hover:border-indigo-500/50 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-all text-left group"
        >
          <div className="p-2.5 rounded-xl bg-indigo-50 dark:bg-indigo-950/60 text-indigo-500 shrink-0 group-hover:scale-110 transition-transform">
            <Layers className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-slate-900 dark:text-white truncate">
              Run Test Suite
            </div>
            <div className="text-xs text-slate-500 truncate">Batch run test collections</div>
          </div>
          <ChevronRight className="w-4 h-4 text-slate-400 group-hover:translate-x-0.5 transition-transform" />
        </button>

        <button
          onClick={() => navigate('/ai-assistant')}
          className="flex items-center gap-3.5 p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark hover:border-brand-500/50 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-all text-left group"
        >
          <div className="p-2.5 rounded-xl bg-purple-50 dark:bg-purple-950/60 text-purple-500 shrink-0 group-hover:scale-110 transition-transform">
            <Sparkles className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-slate-900 dark:text-white truncate">
              Generate with AI
            </div>
            <div className="text-xs text-slate-500 truncate">Auto-derive tests & checks</div>
          </div>
          <ChevronRight className="w-4 h-4 text-slate-400 group-hover:translate-x-0.5 transition-transform" />
        </button>
      </div>

      {/* Recent Executions & Activity */}
      <div className="rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark overflow-hidden shadow-sm">
        <div className="p-5 border-b border-slate-100 dark:border-surface-borderDark flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-slate-900 dark:text-white">
              Recent Test Executions
            </h2>
            <p className="text-xs text-slate-500">Live results and execution audit history</p>
          </div>
          <button
            onClick={() => navigate('/executions')}
            className="text-xs font-semibold text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-1"
          >
            <span>View all runs</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        {metrics.recent_executions.length === 0 ? (
          <div className="p-12 text-center">
            <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800 text-slate-400 mx-auto flex items-center justify-center mb-3">
              <Play className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
              No executions recorded yet
            </h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              Run a test case from the Test Cases library or launch a browser recording to see live execution metrics.
            </p>
            <button
              onClick={() => navigate('/testcases')}
              className="mt-4 px-4 py-2 text-xs font-semibold rounded-lg bg-brand-600 hover:bg-brand-500 text-white transition-all shadow-sm"
            >
              Browse Test Cases
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-100 dark:border-surface-borderDark text-[11px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider bg-slate-50/50 dark:bg-slate-900/30">
                  <th className="px-5 py-3">Test Case</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Browser</th>
                  <th className="px-5 py-3">Steps</th>
                  <th className="px-5 py-3">Duration</th>
                  <th className="px-5 py-3">Started</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60 text-sm">
                {metrics.recent_executions.map((run) => (
                  <tr
                    key={run.id}
                    className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors cursor-pointer"
                    onClick={() => navigate(`/executions?id=${run.id}`)}
                  >
                    <td className="px-5 py-3.5 font-medium text-slate-900 dark:text-slate-100">
                      <div className="flex items-center gap-2">
                        <FileCode2 className="w-4 h-4 text-slate-400" />
                        <span className="truncate max-w-[240px]">{run.testcase_name}</span>
                      </div>
                    </td>
                    <td className="px-5 py-3.5">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${
                          run.status === 'passed'
                            ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800'
                            : run.status === 'failed' || run.status === 'error'
                            ? 'bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-800'
                            : 'bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 border border-amber-200 dark:border-amber-800'
                        }`}
                      >
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${
                            run.status === 'passed'
                              ? 'bg-emerald-500'
                              : run.status === 'failed' || run.status === 'error'
                              ? 'bg-rose-500'
                              : 'bg-amber-500 animate-pulse'
                          }`}
                        />
                        <span className="capitalize">{run.status}</span>
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-slate-500 capitalize">{run.browser}</td>
                    <td className="px-5 py-3.5 text-slate-500">
                      {run.passed_steps || 0} / {run.total_steps || 0}
                    </td>
                    <td className="px-5 py-3.5 text-slate-500 font-mono text-xs">
                      {run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : '-'}
                    </td>
                    <td className="px-5 py-3.5 text-slate-400 text-xs">
                      {new Date(run.started_at).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/executions?id=${run.id}`);
                        }}
                        className="px-2.5 py-1 rounded-lg text-xs font-semibold text-brand-600 dark:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-950/50 transition-colors"
                      >
                        View Logs
                      </button>
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
