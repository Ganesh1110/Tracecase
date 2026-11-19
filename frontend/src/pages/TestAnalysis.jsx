import React, { useEffect, useState } from 'react';
import { BarChart3, AlertTriangle, ShieldCheck, Sparkles, Loader2, CheckCircle2 } from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export function TestAnalysis() {
  const [testcases, setTestCases] = useState([]);
  const [selectedCase, setSelectedCase] = useState('');
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    api.getTestCases().then((cases) => {
      setTestCases(cases);
      if (cases.length > 0) setSelectedCase(cases[0].id);
    });
  }, []);

  const handleAnalyze = async () => {
    if (!selectedCase) return;
    try {
      setLoading(true);
      const res = await api.analyzeTestCase(selectedCase);
      setAnalysis(res);
      showToast('Analysis complete!', 'success');
    } catch (err) {
      showToast('Analysis failed: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          AI Test Analysis & Risk Auditing
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Detect unasserted flows, missing validations, and potential user experience edge-cases.
        </p>
      </div>

      <div className="flex items-center gap-3 p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
        <label className="text-xs font-semibold text-slate-500">Select Test Case:</label>
        <select
          value={selectedCase}
          onChange={(e) => setSelectedCase(e.target.value)}
          className="flex-1 max-w-md px-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900"
        >
          {testcases.map((tc) => (
            <option key={tc.id} value={tc.id}>
              {tc.name} ({tc.id})
            </option>
          ))}
        </select>
        <button
          onClick={handleAnalyze}
          disabled={loading || !selectedCase}
          className="flex items-center gap-2 px-5 py-2 text-xs font-bold rounded-xl bg-brand-600 hover:bg-brand-500 text-white shadow-md shadow-brand-500/20 disabled:opacity-50"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          <span>Run Analysis</span>
        </button>
      </div>

      {analysis && (
        <div className="p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm space-y-6">
          <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-slate-800">
            <div>
              <h2 className="text-base font-bold text-slate-900 dark:text-white">Analysis Findings</h2>
              <p className="text-xs text-slate-400">Model: {analysis.model_used}</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400">Risk Score:</span>
              <span
                className={`px-3 py-1 rounded-full text-xs font-bold ${
                  analysis.risk_score > 50
                    ? 'bg-rose-50 text-rose-500 border border-rose-200'
                    : 'bg-emerald-50 text-emerald-600 border border-emerald-200'
                }`}
              >
                {analysis.risk_score} / 100
              </span>
            </div>
          </div>

          <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-100 dark:border-slate-800 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
            {analysis.summary}
          </div>

          {analysis.raw_analysis?.risks?.length > 0 && (
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-rose-500 mb-2 flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4" />
                <span>Identified Risks</span>
              </h3>
              <ul className="space-y-1.5 text-xs text-slate-600 dark:text-slate-400">
                {analysis.raw_analysis.risks.map((r, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="text-rose-500">•</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {analysis.raw_analysis?.negative_scenarios?.length > 0 && (
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-brand-500 mb-2 flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4" />
                <span>Recommended Negative Test Variations</span>
              </h3>
              <ul className="space-y-1.5 text-xs text-slate-600 dark:text-slate-400">
                {analysis.raw_analysis.negative_scenarios.map((s, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="text-brand-500">•</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
