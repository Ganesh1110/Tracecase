import React, { useEffect, useState, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
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
  Play,
  FileText,
  Camera,
  X,
  Copy,
  Layers,
  Filter,
  Sparkles,
  Loader2,
} from 'lucide-react';
import { api } from '../services/api';
import { useWebSocket } from '../context/WebSocketContext';
import { useToast } from '../context/ToastContext';

export function Executions() {
  const [searchParams] = useSearchParams();
  const focusedRunId = searchParams.get('id');
  const navigate = useNavigate();

  const [runs, setRuns] = useState([]);
  const [selectedRun, setSelectedRun] = useState(null);
  const [liveLogs, setLiveLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedScreenshot, setSelectedScreenshot] = useState(null);
  const [failureAnalysis, setFailureAnalysis] = useState(null);
  const [analyzingFailure, setAnalyzingFailure] = useState(false);

  const { subscribe } = useWebSocket();
  const { showToast } = useToast();
  const terminalEndRef = useRef(null);

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
        if (event.data?.log) {
          setLiveLogs((prev) => [...prev, event.data.log]);
        }
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
      setFailureAnalysis(null);
    } catch (err) {
      showToast('Could not load run details: ' + err.message, 'error');
    }
  };

  const handleAnalyzeFailure = async (runId) => {
    try {
      setAnalyzingFailure(true);
      const res = await api.analyzeFailure(runId);
      setFailureAnalysis(res);
      showToast('AI Failure Diagnostics generated!', 'success');
    } catch (err) {
      showToast('Failure analysis failed: ' + err.message, 'error');
    } finally {
      setAnalyzingFailure(false);
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

  const handleReRun = async () => {
    if (!selectedRun?.testcase_id) return;
    try {
      showToast('Starting re-run...', 'info');
      const run = await api.startExecution({
        testcase_id: selectedRun.testcase_id,
        browser: selectedRun.browser,
        headed: Boolean(selectedRun.headed),
        heal: Boolean(selectedRun.heal),
        assertions: Boolean(selectedRun.assertions),
      });
      showToast('Execution started!', 'success');
      handleSelectRun(run.id);
      loadRuns();
    } catch (err) {
      showToast('Failed to launch re-run: ' + err.message, 'error');
    }
  };

  const filteredRuns = runs.filter((r) => {
    if (statusFilter === 'all') return true;
    if (statusFilter === 'running') return r.status === 'running' || r.status === 'queued';
    return r.status === statusFilter;
  });

  const isRunning = selectedRun?.status === 'running' || selectedRun?.status === 'queued';

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2.5">
            <PlayCircle className="w-6 h-6 text-brand-500" />
            <span>Test Executions & Live Replay</span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Real-time step-by-step execution monitor, self-healing diagnostics, and logs.
          </p>
        </div>
        <button
          onClick={loadRuns}
          className="p-2 rounded-xl border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 transition-colors self-start sm:self-auto"
          title="Refresh runs"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Executions History List */}
        <div className="rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm overflow-hidden flex flex-col h-[740px]">
          <div className="p-3.5 border-b border-slate-100 dark:border-surface-borderDark bg-slate-50/50 dark:bg-slate-900/30 flex items-center justify-between gap-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Execution Runs ({filteredRuns.length})
            </h3>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="text-xs px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300"
            >
              <option value="all">All Statuses</option>
              <option value="running">Running</option>
              <option value="passed">Passed</option>
              <option value="failed">Failed</option>
            </select>
          </div>

          <div className="flex-1 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800/60">
            {filteredRuns.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500">No matching execution runs.</div>
            ) : (
              filteredRuns.map((r) => {
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
                        <span>•</span>
                        <span>{((r.duration_ms || 0) / 1000).toFixed(1)}s</span>
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
        <div className="lg:col-span-2 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm overflow-hidden flex flex-col h-[740px]">
          {selectedRun ? (
            <>
              {/* Header */}
              <div className="p-5 border-b border-slate-100 dark:border-surface-borderDark flex flex-wrap items-center justify-between gap-4 bg-slate-50/50 dark:bg-slate-900/30">
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
                  <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400 mt-1 font-mono">
                    <span>ID: {selectedRun.id}</span>
                    <span>•</span>
                    <span>Browser: {selectedRun.browser}</span>
                    <span>•</span>
                    <span>Duration: {((selectedRun.duration_ms || 0) / 1000).toFixed(1)}s</span>
                    <span>•</span>
                    <span>
                      Passed: {selectedRun.passed_steps || 0} / {selectedRun.total_steps || 0}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => navigate(`/reports?executionId=${selectedRun.id}`)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-colors"
                  >
                    <FileText className="w-3.5 h-3.5" />
                    <span>View Report</span>
                  </button>

                  {isRunning ? (
                    <button
                      onClick={() => handleCancelRun(selectedRun.id)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-50 dark:bg-rose-950/60 text-rose-500 hover:bg-rose-100 border border-rose-200 dark:border-rose-800 transition-colors"
                    >
                      <StopCircle className="w-3.5 h-3.5" />
                      <span>Cancel</span>
                    </button>
                  ) : (
                    <button
                      onClick={handleReRun}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-100 border border-emerald-200 dark:border-emerald-800 transition-colors"
                    >
                      <Play className="w-3.5 h-3.5 fill-current" />
                      <span>Re-run</span>
                    </button>
                  )}
                </div>
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
                        (((selectedRun.passed_steps || 0) + (selectedRun.failed_steps || 0)) /
                          selectedRun.total_steps) *
                          100,
                        100
                      )}%`,
                    }}
                  />
                </div>
              )}

              {/* Main Content Area */}
              <div className="flex-1 overflow-y-auto p-5 space-y-5">
                {/* Error Banner */}
                {selectedRun.error_message && (
                  <div className="p-3.5 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs flex items-start gap-2.5">
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    <div className="font-mono whitespace-pre-wrap">{selectedRun.error_message}</div>
                  </div>
                )}

                {/* AI Failure Diagnostics */}
                {(selectedRun.status === 'failed' || selectedRun.error_message) && (
                  <div className="p-4 rounded-2xl bg-white dark:bg-surface-cardDark border border-slate-200 dark:border-surface-borderDark shadow-sm space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Sparkles className="w-4 h-4 text-brand-500" />
                        <h4 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider">
                          AI Root Cause & Failure Analysis
                        </h4>
                      </div>
                      {!failureAnalysis ? (
                        <button
                          onClick={() => handleAnalyzeFailure(selectedRun.id)}
                          disabled={analyzingFailure}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-brand-600 hover:bg-brand-500 text-white shadow-sm disabled:opacity-50"
                        >
                          {analyzingFailure ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Sparkles className="w-3.5 h-3.5" />
                          )}
                          <span>Analyze Failure</span>
                        </button>
                      ) : (
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-semibold text-slate-400">
                            Confidence: {Math.round(failureAnalysis.confidence * 100)}%
                          </span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-rose-50 text-rose-600 dark:bg-rose-950/50 dark:text-rose-400 border border-rose-200 dark:border-rose-800">
                            {failureAnalysis.category}
                          </span>
                        </div>
                      )}
                    </div>

                    {failureAnalysis && (
                      <div className="space-y-3 pt-2 text-xs border-t border-slate-100 dark:border-slate-800 animate-in fade-in">
                        <div>
                          <strong className="text-slate-800 dark:text-slate-200">Root Cause: </strong>
                          <span className="text-slate-600 dark:text-slate-400">{failureAnalysis.root_cause}</span>
                        </div>

                        {failureAnalysis.step_number_failed && (
                          <div className="text-slate-500">
                            Failed at Step: <span className="font-mono font-bold">#{failureAnalysis.step_number_failed}</span>
                          </div>
                        )}

                        {failureAnalysis.remediation && (
                          <div className="p-3 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-100 dark:border-slate-800">
                            <strong className="text-brand-600 dark:text-brand-400 block mb-1">Recommended Remediation:</strong>
                            <p className="text-slate-700 dark:text-slate-300 leading-relaxed">{failureAnalysis.remediation}</p>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Step Diagnostics */}
                <div className="space-y-3">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                    <span>Step Diagnostics ({selectedRun.step_logs?.length || 0})</span>
                  </h3>

                  {selectedRun.step_logs?.length === 0 ? (
                    <div className="text-xs text-slate-500 italic p-4 text-center border border-dashed border-slate-200 dark:border-slate-800 rounded-xl">
                      Waiting for step execution events...
                    </div>
                  ) : (
                    selectedRun.step_logs?.map((step) => {
                      const shotName = step.screenshot_path?.replace(/^.*[\\/]/, '');

                      return (
                        <div
                          key={step.id || step.step_number}
                          className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/40 dark:bg-slate-900/40 space-y-2.5"
                        >
                          <div className="flex items-center justify-between text-xs">
                            <div className="flex items-center gap-2.5 flex-1 min-w-0">
                              <span className="font-mono font-bold text-slate-500">
                                #{step.step_number}
                              </span>
                              <span className="font-bold uppercase text-slate-800 dark:text-slate-200 bg-slate-200/60 dark:bg-slate-800 px-1.5 py-0.5 rounded text-[10px]">
                                {step.action_type || 'action'}
                              </span>
                              {step.selector_used && (
                                <span className="font-mono text-slate-500 truncate max-w-xs text-[11px]">
                                  {step.selector_used}
                                </span>
                              )}
                              {step.healed_from && (
                                <span className="px-1.5 py-0.5 rounded bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 font-mono text-[10px] border border-amber-200 dark:border-amber-800">
                                  Healed from '{step.healed_from}'
                                </span>
                              )}
                            </div>

                            <div className="flex items-center gap-3 shrink-0">
                              <span className="text-slate-400 font-mono text-[11px]">
                                {(step.duration_ms || 0).toFixed(1)}ms
                              </span>
                              <span
                                className={`font-bold uppercase text-[10px] px-2 py-0.5 rounded-full ${
                                  step.status === 'passed'
                                    ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-500 border border-emerald-200 dark:border-emerald-800'
                                    : 'bg-rose-50 dark:bg-rose-950/60 text-rose-500 border border-rose-200 dark:border-rose-800'
                                }`}
                              >
                                {step.status}
                              </span>
                            </div>
                          </div>

                          {/* Assertions Evaluation Pills */}
                          {step.assertions && step.assertions.length > 0 && (
                            <div className="pt-1.5 border-t border-slate-200/50 dark:border-slate-800/50 space-y-1">
                              {step.assertions.map((ast, aIdx) => (
                                <div
                                  key={aIdx}
                                  className="flex items-center justify-between text-[11px] p-1.5 rounded bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800"
                                >
                                  <div className="flex items-center gap-2">
                                    <span
                                      className={`w-2 h-2 rounded-full ${
                                        ast.passed ? 'bg-emerald-500' : 'bg-rose-500'
                                      }`}
                                    />
                                    <span className="font-semibold uppercase text-slate-700 dark:text-slate-300">
                                      Assert [{ast.kind}]
                                    </span>
                                    {ast.expected && (
                                      <span className="text-slate-500">
                                        Expected: <span className="font-mono text-slate-700 dark:text-slate-300">"{ast.expected}"</span>
                                      </span>
                                    )}
                                    {ast.actual && (
                                      <span className="text-slate-500">
                                        Actual: <span className="font-mono text-slate-700 dark:text-slate-300">"{ast.actual}"</span>
                                      </span>
                                    )}
                                  </div>
                                  <span
                                    className={`font-bold uppercase text-[9px] px-1.5 py-0.5 rounded ${
                                      ast.passed
                                        ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400'
                                        : 'bg-rose-50 text-rose-600 dark:bg-rose-950/60 dark:text-rose-400'
                                    }`}
                                  >
                                    {ast.passed ? 'Passed' : 'Failed'}
                                  </span>
                                </div>
                              ))}
                            </div>
                          )}

                          {/* Step Error */}
                          {step.error && (
                            <div className="text-xs text-rose-500 font-mono bg-rose-50/50 dark:bg-rose-950/30 p-2 rounded border border-rose-200/50 dark:border-rose-800/50">
                              {step.error}
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>

                {/* Console Log Terminal */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                      <Terminal className="w-3.5 h-3.5" />
                      <span>Execution Logs</span>
                    </h3>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(liveLogs.join('\n'));
                        showToast('Logs copied to clipboard', 'success');
                      }}
                      className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center gap-1"
                    >
                      <Copy className="w-3 h-3" />
                      <span>Copy</span>
                    </button>
                  </div>
                  <div className="p-4 rounded-xl bg-slate-950 text-slate-300 font-mono text-xs leading-relaxed max-h-56 overflow-y-auto selection:bg-brand-600 space-y-1">
                    {liveLogs.length === 0 ? (
                      <span className="text-slate-600 italic">No output logged for this run.</span>
                    ) : (
                      liveLogs.map((log, i) => (
                        <div key={i} className="whitespace-pre-wrap">
                          {log}
                        </div>
                      ))
                    )}
                    <div ref={terminalEndRef} />
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
