import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  FileText,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  Layers,
  Camera,
  ExternalLink,
  ShieldCheck,
  RefreshCw,
  Play,
  Copy,
  Terminal,
  X,
  FileCode2,
  Sparkles,
  Loader2,
} from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export function Reports() {
  const [searchParams] = useSearchParams();
  const executionIdParam = searchParams.get('executionId');
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [activeTab, setActiveTab] = useState('execution'); // 'execution' | 'html'
  const [executions, setExecutions] = useState([]);
  const [selectedExecutionId, setSelectedExecutionId] = useState(executionIdParam || '');
  const [reportData, setReportData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedScreenshot, setSelectedScreenshot] = useState(null);
  const [failureAnalysis, setFailureAnalysis] = useState(null);
  const [analyzingFailure, setAnalyzingFailure] = useState(false);

  // HTML reports state
  const [testcases, setTestCases] = useState([]);
  const [selectedCase, setSelectedCase] = useState('');

  useEffect(() => {
    loadExecutions();
    api.getTestCases().then((cases) => {
      setTestCases(cases);
      if (cases.length > 0) setSelectedCase(cases[0].id);
    });
  }, []);

  const loadExecutions = async () => {
    try {
      setLoading(true);
      const runs = await api.getExecutions({ limit: 50 });
      setExecutions(runs);
      const targetId = executionIdParam || (runs.length > 0 ? runs[0].id : '');
      if (targetId) {
        setSelectedExecutionId(targetId);
        loadExecutionReport(targetId);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadExecutionReport = async (id) => {
    try {
      setLoading(true);
      setFailureAnalysis(null);
      const data = await api.getExecution(id);
      setReportData(data);
    } catch (err) {
      showToast('Failed to load execution report: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleAnalyzeFailure = async (id) => {
    try {
      setAnalyzingFailure(true);
      const res = await api.analyzeFailure(id);
      setFailureAnalysis(res);
      showToast('AI Failure Diagnostics generated!', 'success');
    } catch (err) {
      showToast('Failure analysis failed: ' + err.message, 'error');
    } finally {
      setAnalyzingFailure(false);
    }
  };

  const handleSelectExecution = (e) => {
    const id = e.target.value;
    setSelectedExecutionId(id);
    loadExecutionReport(id);
  };

  const healedStepsCount =
    reportData?.step_logs?.filter((s) => Boolean(s.healed_from)).length || 0;

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2.5">
            <FileText className="w-6 h-6 text-brand-500" />
            <span>Execution & Test Reports</span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Detailed post-run test reports, step assertions, screenshots, and visual diffs.
          </p>
        </div>

        {/* Tab Controls */}
        <div className="flex items-center gap-1.5 p-1 rounded-xl bg-slate-100 dark:bg-slate-800 self-start sm:self-auto">
          <button
            onClick={() => setActiveTab('execution')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'execution'
                ? 'bg-white dark:bg-surface-cardDark text-slate-900 dark:text-white shadow-sm'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            Execution Run Report
          </button>
          <button
            onClick={() => setActiveTab('html')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'html'
                ? 'bg-white dark:bg-surface-cardDark text-slate-900 dark:text-white shadow-sm'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            Standalone HTML Artifact
          </button>
        </div>
      </div>

      {activeTab === 'execution' && (
        <div className="space-y-6">
          {/* Selector Bar */}
          <div className="p-4 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark flex flex-wrap items-center justify-between gap-4 shadow-sm">
            <div className="flex items-center gap-3">
              <label className="text-xs font-semibold text-slate-500">Execution Run:</label>
              <select
                value={selectedExecutionId}
                onChange={handleSelectExecution}
                className="px-3 py-1.5 text-xs font-medium rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                {executions.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.testcase_name} • {r.status.toUpperCase()} ({new Date(r.started_at).toLocaleString()})
                  </option>
                ))}
              </select>
            </div>

            {reportData && (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => navigate(`/executions?id=${reportData.id}`)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-colors"
                >
                  <Terminal className="w-3.5 h-3.5" />
                  <span>Open in Monitor</span>
                </button>
                <button
                  onClick={loadExecutions}
                  className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500"
                  title="Refresh"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>

          {reportData ? (
            <div className="space-y-6">
              {/* Report Summary Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="p-4 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    Execution Status
                  </span>
                  <div className="mt-2 flex items-center gap-2">
                    {reportData.status === 'passed' ? (
                      <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0" />
                    ) : (
                      <XCircle className="w-5 h-5 text-rose-500 shrink-0" />
                    )}
                    <span
                      className={`text-lg font-bold capitalize ${
                        reportData.status === 'passed' ? 'text-emerald-500' : 'text-rose-500'
                      }`}
                    >
                      {reportData.status}
                    </span>
                  </div>
                </div>

                <div className="p-4 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    Total Duration
                  </span>
                  <div className="mt-2 flex items-center gap-2">
                    <Clock className="w-5 h-5 text-blue-500 shrink-0" />
                    <span className="text-lg font-bold text-slate-900 dark:text-white font-mono">
                      {((reportData.duration_ms || 0) / 1000).toFixed(2)}s
                    </span>
                  </div>
                </div>

                <div className="p-4 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    Step Results
                  </span>
                  <div className="mt-2 flex items-center gap-2">
                    <Layers className="w-5 h-5 text-purple-500 shrink-0" />
                    <span className="text-lg font-bold text-slate-900 dark:text-white">
                      {reportData.passed_steps || 0} / {reportData.total_steps || 0} Passed
                    </span>
                  </div>
                </div>

                <div className="p-4 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    Healed Selectors
                  </span>
                  <div className="mt-2 flex items-center gap-2">
                    <ShieldCheck className="w-5 h-5 text-amber-500 shrink-0" />
                    <span className="text-lg font-bold text-slate-900 dark:text-white">
                      {healedStepsCount} Healed
                    </span>
                  </div>
                </div>
              </div>

              {/* Error Message if failed */}
              {reportData.error_message && (
                <div className="p-4 rounded-2xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs flex items-start gap-3">
                  <AlertCircle className="w-5 h-5 text-rose-500 shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-bold mb-1">Execution Failure Diagnostic</h4>
                    <p className="font-mono whitespace-pre-wrap">{reportData.error_message}</p>
                  </div>
                </div>
              )}

              {/* AI Failure Diagnostics */}
              {(reportData.status === 'failed' || reportData.error_message) && (
                <div className="p-4 rounded-2xl bg-white dark:bg-surface-cardDark border border-slate-200 dark:border-surface-borderDark shadow-sm space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-brand-500" />
                      <h4 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider">
                        AI Failure Root Cause & Remediation
                      </h4>
                    </div>
                    {!failureAnalysis ? (
                      <button
                        onClick={() => handleAnalyzeFailure(reportData.id)}
                        disabled={analyzingFailure}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-brand-600 hover:bg-brand-500 text-white shadow-sm disabled:opacity-50"
                      >
                        {analyzingFailure ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Sparkles className="w-3.5 h-3.5" />
                        )}
                        <span>Analyze Failure with AI</span>
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

              {/* Step Execution Breakdown Table */}
              <div className="rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark overflow-hidden shadow-sm">
                <div className="p-4 border-b border-slate-100 dark:border-surface-borderDark bg-slate-50/50 dark:bg-slate-900/30 flex items-center justify-between">
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                    Step-by-Step Execution Report
                  </h3>
                  <span className="text-xs text-slate-400 font-mono">
                    Browser: {reportData.browser}
                  </span>
                </div>

                <div className="divide-y divide-slate-100 dark:divide-slate-800">
                  {reportData.step_logs?.map((step) => {
                    const shotName = step.screenshot_path?.replace(/^.*[\\/]/, '');

                    return (
                      <div key={step.id || step.step_number} className="p-4 space-y-3">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <span className="w-7 h-7 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-bold text-xs flex items-center justify-center">
                              {step.step_number}
                            </span>
                            <span className="px-2 py-0.5 text-[10px] font-bold rounded uppercase bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                              {step.action_type || 'action'}
                            </span>
                            {step.selector_used && (
                              <span className="text-xs font-mono text-slate-600 dark:text-slate-400 truncate max-w-md">
                                {step.selector_used}
                              </span>
                            )}
                            {step.healed_from && (
                              <span className="px-2 py-0.5 rounded bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 font-mono text-[10px] border border-amber-200 dark:border-amber-800">
                                Healed from '{step.healed_from}'
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-3">
                            <span className="text-xs font-mono text-slate-400">
                              {(step.duration_ms || 0).toFixed(1)}ms
                            </span>
                            <span
                              className={`text-xs font-bold uppercase px-2.5 py-0.5 rounded-full ${
                                step.status === 'passed'
                                  ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-500 border border-emerald-200 dark:border-emerald-800'
                                  : 'bg-rose-50 dark:bg-rose-950/60 text-rose-500 border border-rose-200 dark:border-rose-800'
                              }`}
                            >
                              {step.status}
                            </span>
                          </div>
                        </div>

                        {/* Assertions Evaluation in Report */}
                        {step.assertions && step.assertions.length > 0 && (
                          <div className="pl-10 space-y-1.5">
                            <span className="text-[10px] font-bold uppercase text-slate-400">
                              Assertions Evaluation
                            </span>
                            {step.assertions.map((ast, aIdx) => (
                              <div
                                key={aIdx}
                                className="flex items-center justify-between text-xs p-2 rounded-lg bg-slate-50 dark:bg-slate-900/60 border border-slate-100 dark:border-slate-800/80"
                              >
                                <div className="flex flex-wrap items-center gap-2">
                                  <span
                                    className={`w-2 h-2 rounded-full ${
                                      ast.passed ? 'bg-emerald-500' : 'bg-rose-500'
                                    }`}
                                  />
                                  <span className="font-semibold uppercase text-slate-700 dark:text-slate-300">
                                    {ast.kind}
                                  </span>
                                  {ast.expected && (
                                    <span className="text-slate-500">
                                      Expected: <span className="font-bold text-slate-800 dark:text-slate-200">"{ast.expected}"</span>
                                    </span>
                                  )}
                                  {ast.actual && (
                                    <span className="text-slate-500">
                                      Actual: <span className="font-mono text-slate-800 dark:text-slate-200">"{ast.actual}"</span>
                                    </span>
                                  )}
                                  {ast.message && (
                                    <span className="text-rose-500 text-[11px] italic">
                                      ({ast.message})
                                    </span>
                                  )}
                                </div>
                                <span
                                  className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                                    ast.passed
                                      ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400'
                                      : 'bg-rose-100 dark:bg-rose-950 text-rose-600 dark:text-rose-400'
                                  }`}
                                >
                                  {ast.passed ? 'PASSED' : 'FAILED'}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Step Error */}
                        {step.error && (
                          <div className="pl-10 text-xs font-mono text-rose-500 bg-rose-50/50 dark:bg-rose-950/30 p-2 rounded border border-rose-200/50 dark:border-rose-800/50">
                            {step.error}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : (
            <div className="p-12 text-center text-slate-500 text-sm">
              No execution runs available. Execute a test case to generate execution reports.
            </div>
          )}
        </div>
      )}

      {/* Tab: Standalone HTML Artifact */}
      {activeTab === 'html' && (
        <div className="space-y-4">
          <div className="p-4 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark flex items-center justify-between gap-4 shadow-sm">
            <div className="flex items-center gap-3">
              <label className="text-xs font-semibold text-slate-500">Select Test Case:</label>
              <select
                value={selectedCase || ''}
                onChange={(e) => setSelectedCase(e.target.value)}
                className="px-3 py-1.5 text-xs font-medium rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                {testcases.map((tc) => (
                  <option key={tc.id} value={tc.id}>
                    {tc.name} ({tc.id})
                  </option>
                ))}
              </select>
            </div>

            {selectedCase && (
              <a
                href={`/api/testcases/${selectedCase}/html`}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 text-slate-700 dark:text-slate-300 transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>Open in Full Browser</span>
              </a>
            )}
          </div>

          {selectedCase && (
            <div className="rounded-2xl border border-slate-200 dark:border-surface-borderDark overflow-hidden bg-white shadow-sm h-[750px]">
              <iframe
                src={`/api/testcases/${selectedCase}/html`}
                title="HTML Report"
                className="w-full h-full border-none"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
