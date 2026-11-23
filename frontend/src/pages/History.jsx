import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  History as HistoryIcon,
  Clock,
  CheckCircle2,
  XCircle,
  Search,
  ArrowRight,
  Play,
  FileText,
  Filter,
  RefreshCw,
} from "lucide-react";
import { api } from "../services/api";
import { useToast } from "../context/ToastContext";
import { useProject } from "../context/ProjectContext";

export function History() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [browserFilter, setBrowserFilter] = useState("all");

  const { currentProject } = useProject();
  const { showToast } = useToast();
  const navigate = useNavigate();

  const loadHistory = async () => {
    try {
      setLoading(true);
      const data = await api.getExecutions({
        projectId: currentProject?.id || undefined,
        limit: 100,
      });
      setRuns(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, [currentProject?.id]);

  const handleReRun = async (e, run) => {
    e.stopPropagation();
    try {
      showToast("Launching re-run...", "info");
      const newRun = await api.startExecution({
        testcase_id: run.testcase_id,
        browser: run.browser,
        headed: Boolean(run.headed),
        heal: Boolean(run.heal),
        assertions: Boolean(run.assertions),
      });
      showToast("Execution launched!", "success");
      navigate(`/executions?id=${newRun.id}`);
    } catch (err) {
      showToast("Failed to re-run: " + err.message, "error");
    }
  };

  const filtered = runs.filter((r) => {
    const matchesSearch =
      r.testcase_name.toLowerCase().includes(search.toLowerCase()) ||
      r.id.toLowerCase().includes(search.toLowerCase());
    const matchesStatus =
      statusFilter === "all" ||
      (statusFilter === "running"
        ? r.status === "running" || r.status === "queued"
        : r.status === statusFilter);
    const matchesBrowser =
      browserFilter === "all" || r.browser === browserFilter;
    return matchesSearch && matchesStatus && matchesBrowser;
  });

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2.5">
            <HistoryIcon className="w-6 h-6 text-brand-500" />
            <span>Execution History</span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Complete audit trail of all previous test runs, pass/fail
            diagnostics, and timings.
          </p>
        </div>

        <button
          onClick={loadHistory}
          className="p-2 rounded-xl border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 transition-colors self-start sm:self-auto"
          title="Refresh history"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Filters Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="relative flex-1 min-w-[240px] max-w-md">
          <Search className="absolute left-3.5 top-2.5 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search by testcase name or execution ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 text-xs font-semibold rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark text-slate-800 dark:text-slate-200"
          >
            <option value="all">All Statuses</option>
            <option value="passed">Passed</option>
            <option value="failed">Failed</option>
            <option value="running">Running</option>
          </select>

          <select
            value={browserFilter}
            onChange={(e) => setBrowserFilter(e.target.value)}
            className="px-3 py-2 text-xs font-semibold rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark text-slate-800 dark:text-slate-200"
          >
            <option value="all">All Browsers</option>
            <option value="chromium">Chromium</option>
            <option value="firefox">Firefox</option>
            <option value="webkit">WebKit (Safari)</option>
            <option value="msedge">Microsoft Edge</option>
          </select>
        </div>
      </div>

      {/* History Table */}
      <div className="rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-100 dark:border-surface-borderDark text-[11px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider bg-slate-50/50 dark:bg-slate-900/30">
                <th className="px-5 py-3">Execution ID</th>
                <th className="px-5 py-3">Test Case</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Browser</th>
                <th className="px-5 py-3">Steps</th>
                <th className="px-5 py-3">Duration</th>
                <th className="px-5 py-3">Timestamp</th>
                <th className="px-5 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60 text-sm">
              {filtered.length === 0 ? (
                <tr>
                  <td
                    colSpan={8}
                    className="p-8 text-center text-xs text-slate-500"
                  >
                    No execution history found matching the filters.
                  </td>
                </tr>
              ) : (
                filtered.map((run) => (
                  <tr
                    key={run.id}
                    onClick={() => navigate(`/executions?id=${run.id}`)}
                    className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors cursor-pointer"
                  >
                    <td className="px-5 py-3.5 font-mono text-xs text-slate-400">
                      {run.id}
                    </td>
                    <td className="px-5 py-3.5 font-medium text-slate-900 dark:text-slate-100">
                      {run.testcase_name}
                    </td>
                    <td className="px-5 py-3.5">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${
                          run.status === "passed"
                            ? "bg-emerald-50 dark:bg-emerald-950/60 text-emerald-500 border border-emerald-200 dark:border-emerald-800"
                            : run.status === "failed" || run.status === "error"
                              ? "bg-rose-50 dark:bg-rose-950/60 text-rose-500 border border-rose-200 dark:border-rose-800"
                              : "bg-amber-50 dark:bg-amber-950/60 text-amber-500"
                        }`}
                      >
                        {run.status}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-xs text-slate-500 capitalize">
                      {run.browser}
                    </td>
                    <td className="px-5 py-3.5 text-xs text-slate-500">
                      {run.passed_steps || 0} / {run.total_steps || 0}
                    </td>
                    <td className="px-5 py-3.5 text-xs font-mono text-slate-500">
                      {run.duration_ms
                        ? `${((run.duration_ms || 0) / 1000).toFixed(1)}s`
                        : "-"}
                    </td>
                    <td className="px-5 py-3.5 text-xs text-slate-400">
                      {new Date(run.started_at).toLocaleString()}
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <div
                        className="flex items-center justify-end gap-2"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          onClick={(e) => handleReRun(e, run)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-emerald-500 hover:bg-emerald-50 dark:hover:bg-emerald-950/40 transition-colors"
                          title="Re-run Test"
                        >
                          <Play className="w-3.5 h-3.5 fill-current" />
                        </button>
                        <button
                          onClick={() =>
                            navigate(`/reports?executionId=${run.id}`)
                          }
                          className="p-1.5 rounded-lg text-slate-400 hover:text-brand-500 hover:bg-brand-50 dark:hover:bg-brand-950/40 transition-colors"
                          title="View Execution Report"
                        >
                          <FileText className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => navigate(`/executions?id=${run.id}`)}
                          className="text-xs font-semibold text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-0.5 ml-1"
                        >
                          <span>Live</span>
                          <ArrowRight className="w-3 h-3" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
