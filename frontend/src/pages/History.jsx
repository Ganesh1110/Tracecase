import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { History as HistoryIcon, Clock, CheckCircle2, XCircle, Search, ArrowRight } from 'lucide-react';
import { api } from '../services/api';

export function History() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    api
      .getExecutions({ limit: 100 })
      .then(setRuns)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const filtered = runs.filter((r) =>
    r.testcase_name.toLowerCase().includes(search.toLowerCase()) ||
    r.id.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          Execution History
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Complete audit trail of all previous test runs, pass/fail results, and execution timings.
        </p>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3.5 top-2.5 w-4 h-4 text-slate-400" />
        <input
          type="text"
          placeholder="Filter history by testcase or ID..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
      </div>

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
                <th className="px-5 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60 text-sm">
              {filtered.map((run) => (
                <tr
                  key={run.id}
                  onClick={() => navigate(`/executions?id=${run.id}`)}
                  className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors cursor-pointer"
                >
                  <td className="px-5 py-3.5 font-mono text-xs text-slate-400">{run.id}</td>
                  <td className="px-5 py-3.5 font-medium text-slate-900 dark:text-slate-100">
                    {run.testcase_name}
                  </td>
                  <td className="px-5 py-3.5">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold capitalize ${
                        run.status === 'passed'
                          ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-500 border border-emerald-200 dark:border-emerald-800'
                          : run.status === 'failed' || run.status === 'error'
                          ? 'bg-rose-50 dark:bg-rose-950/60 text-rose-500 border border-rose-200 dark:border-rose-800'
                          : 'bg-amber-50 dark:bg-amber-950/60 text-amber-500'
                      }`}
                    >
                      {run.status}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-xs text-slate-500 capitalize">{run.browser}</td>
                  <td className="px-5 py-3.5 text-xs text-slate-500">
                    {run.passed_steps || 0} / {run.total_steps || 0}
                  </td>
                  <td className="px-5 py-3.5 text-xs font-mono text-slate-500">
                    {run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : '-'}
                  </td>
                  <td className="px-5 py-3.5 text-xs text-slate-400">
                    {new Date(run.started_at).toLocaleString()}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(`/executions?id=${run.id}`);
                      }}
                      className="text-xs font-semibold text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-1 justify-end ml-auto"
                    >
                      <span>Logs</span>
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
