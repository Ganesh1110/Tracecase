import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  PlayCircle,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  Terminal,
  StopCircle,
  ArrowRight,
  ShieldCheck,
  RefreshCw,
} from 'lucide-react';
import { api } from '../services/api';
import { useWebSocket } from '../context/WebSocketContext';
import { useToast } from '../context/ToastContext';

export function Executions() {
  const [searchParams] = useSearchParams();
  const focusedRunId = searchParams.get('id');
  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [liveLogs, setLiveLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const { subscribe } = useWebSocket();
  const { showToast } = useToast();

  const loadRuns = async () => {
    try {
      setLoading(true);
      const data = await api.getExecutions({ limit: 50 });
      setRuns(data);
      if (focusedRunId) {
        const found = await api.getExecution(focusedRunId);
        setSelectedRun(found);
        setLiveLogs(found.logs || []);
      } else if (data.length > 0 && !selectedRun) {
        const first = await api.getExecution(data[0].id);
        setSelectedRun(first);
        setLiveLogs(first.logs || []);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRuns();
  }, [focusedRunId]);

  // Subscribe to WebSocket events for the selected run
  useEffect(() => {
    if (!selectedRun?.id) return;

    const channel = `execution:${selectedRun.id}`;
    const unsub = subscribe(channel, (event) => {
      if (event.type === 'step_progress') {
        setLiveLogs((prev) => [...prev, event.data.log]);
        // Refresh details
        api.getExecution(selectedRun.id).then(setSelectedRun).catch(console.error);
      } else if (event.type === 'execution_completed' || event.type === 'execution_failed') {
        api.getExecution(selectedRun.id).then(setSelectedRun).catch(console.error);
        loadRuns();
      }
    });

    return unsub;
  }, [selectedRun?.id, subscribe]);

  const handleSelectRun = async (runId) => {
    try {
      const data = await api.getExecution(runId);
      setSelectedRun(data);
      setLiveLogs(data.logs || []);
    } catch (err) {
      showToast('Could not load run details: ' + err.message, 'error');
    }
  };

  const handleCancelRun = async (runId) => {
    try {
      await api.cancelExecution(runId);
      showToast('Execution cancelled.', 'info');
      loadRuns();
    } catch (err) {
      showToast('Failed to cancel: ' + err.message, 'error');
    }
  };

  const isRunning = selectedRun?.status === 'running' || selectedRun?.status === 'queued';

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            Test Executions & Live Replay
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Real-time step-by-step execution monitor, self-healing diagnostics, and logs.
          </p>
        </div>
        <button
          onClick={loadRuns}
          className="p-2 rounded-xl border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500"
          title="Refresh runs"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Executions History List */}
        <div className="rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm overflow-hidden flex flex-col h-[700px]">
          <div className="p-4 border-b border-slate-100 dark:border-surface-borderDark bg-slate-50/50 dark:bg-slate-900/30">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Execution Runs ({runs.length})
            </h3>
          </div>
          <div className="flex-1 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800/60">
            {runs.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500">No execution runs yet.</div>
            ) : (
              runs.map((r) => {
                const isSelected = selectedRun?.id === r.id;
                return (
                  <button
                    key={r.id}
                    onClick={() => handleSelectRun(r.id)}
                    className={`w-full text-left p-4 transition-colors flex items-center justify-between ${
                      isSelected
                        ? 'bg-brand-50/60 dark:bg-brand-950/40 border-l-4 border-brand-500'
                        : 'hover:bg-slate-50/60 dark:hover:bg-slate-800/40'
                    }`}
                  >
                    <div className="min-w-0 flex-1 pr-2">
                      <div className="font-bold text-sm text-slate-900 dark:text-white truncate">
                        {r.testcase_name}
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-xs text-slate-400">
                        <span className="capitalize">{r.browser}</span>
                        <span>•</span>
                        <span>{new Date(r.started_at).toLocaleTimeString()}</span>
                      </div>
                    </div>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase shrink-0 ${
                        r.status === 'passed'
                          ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-500 border border-emerald-200 dark:border-emerald-800'
                          : r.status === 'failed' || r.status === 'error'
                          ? 'bg-rose-50 dark:bg-rose-950/60 text-rose-500 border border-rose-200 dark:border-rose-800'
                          : 'bg-amber-50 dark:bg-amber-950/60 text-amber-500 border border-amber-200 dark:border-amber-800 animate-pulse'
                      }`}
                    >
                      {r.status}
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Right: Selected Run Real-Time Monitor */}
        <div className="lg:col-span-2 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm overflow-hidden flex flex-col h-[700px]">
          {selectedRun ? (
            <>
              {/* Header */}
              <div className="p-5 border-b border-slate-100 dark:border-surface-borderDark flex items-center justify-between bg-slate-50/50 dark:bg-slate-900/30">
                <div>
                  <div className="flex items-center gap-2.5">
                    <h2 className="text-base font-bold text-slate-900 dark:text-white">
                      {selectedRun.testcase_name}
                    </h2>
                    <span
                      className={`px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase ${
                        selectedRun.status === 'passed'
                          ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-500 border border-emerald-200 dark:border-emerald-800'
                          : selectedRun.status === 'failed' || selectedRun.status === 'error'
                          ? 'bg-rose-50 dark:bg-rose-950/60 text-rose-500 border border-rose-200 dark:border-rose-800'
                          : 'bg-amber-50 dark:bg-amber-950/60 text-amber-500 border border-amber-200 dark:border-amber-800 animate-pulse'
                      }`}
                    >
                      {selectedRun.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-slate-400 mt-1 font-mono">
                    <span>ID: {selectedRun.id}</span>
                    <span>•</span>
                    <span>Duration: {(selectedRun.duration_ms / 1000).toFixed(1)}s</span>
                    <span>•</span>
                    <span>
                      Passed: {selectedRun.passed_steps || 0} / {selectedRun.total_steps || 0}
                    </span>
                  </div>
                </div>

                {isRunning && (
                  <button
                    onClick={() => handleCancelRun(selectedRun.id)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-50 dark:bg-rose-950/60 text-rose-500 hover:bg-rose-100 border border-rose-200 dark:border-rose-800 transition-colors"
                  >
                    <StopCircle className="w-3.5 h-3.5" />
                    <span>Cancel Run</span>
                  </button>
                )}
              </div>

              {/* Progress Bar */}
              {selectedRun.total_steps > 0 && (
                <div className="w-full bg-slate-100 dark:bg-slate-800 h-1.5 overflow-hidden">
                  <div
                    className={`h-full transition-all duration-300 ${
                      selectedRun.status === 'failed' || selectedRun.status === 'error'
                        ? 'bg-rose-500'
                        : 'bg-emerald-500'
                    }`}
                    style={{
                      width: `${Math.min(
                        ((selectedRun.passed_steps + (selectedRun.failed_steps || 0)) /
                          selectedRun.total_steps) *
                          100,
                        100
                      )}%`,
                    }}
                  />
                </div>
              )}

              {/* Step Logs & Terminal View */}
              <div className="flex-1 overflow-y-auto p-5 space-y-4">
                {/* Step List */}
                <div className="space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                    Step Diagnostics
                  </h3>
                  {selectedRun.step_logs?.length === 0 ? (
                    <div className="text-xs text-slate-500 italic p-3">
                      Waiting for step execution events...
                    </div>
                  ) : (
                    selectedRun.step_logs?.map((step) => (
                      <div
                        key={step.id}
                        className="p-3 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50/40 dark:bg-slate-900/40 flex items-center justify-between text-xs"
                      >
                        <div className="flex items-center gap-2.5">
                          <span className="font-mono font-bold text-slate-500">#{step.step_number}</span>
                          <span className="font-semibold uppercase text-slate-700 dark:text-slate-300">
                            {step.action_type || 'action'}
                          </span>
                          {step.healed_from && (
                            <span className="px-1.5 py-0.5 rounded bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 font-mono text-[10px] border border-amber-200 dark:border-amber-800">
                              Healed from {step.healed_from}
                            </span>
                          )}
                          {step.error && (
                            <span className="text-rose-500 truncate max-w-sm">{step.error}</span>
                          )}
                        </div>

                        <div className="flex items-center gap-3 font-mono">
                          <span className="text-slate-400">{step.duration_ms.toFixed(1)}ms</span>
                          <span
                            className={`font-bold uppercase ${
                              step.status === 'passed' ? 'text-emerald-500' : 'text-rose-500'
                            }`}
                          >
                            {step.status}
                          </span>
                        </div>
                      </div>
                    ))
                  )}
                </div>

                {/* Console Log Terminal */}
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1.5">
                    <Terminal className="w-3.5 h-3.5" />
                    <span>Live Console Output</span>
                  </h3>
                  <div className="p-4 rounded-xl bg-slate-950 text-slate-300 font-mono text-xs leading-relaxed max-h-56 overflow-y-auto selection:bg-brand-600">
                    {liveLogs.length === 0 ? (
                      <span className="text-slate-600 italic">No output logged for this run.</span>
                    ) : (
                      liveLogs.map((log, i) => (
                        <div key={i} className="whitespace-pre-wrap">
                          {log}
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="p-12 text-center text-slate-500 text-sm m-auto">
              Select an execution run from the list to inspect live diagnostics.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
