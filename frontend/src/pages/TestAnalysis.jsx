import React, { useEffect, useState } from 'react';
import {
  BarChart3,
  AlertTriangle,
  ShieldCheck,
  Sparkles,
  Loader2,
  CheckCircle2,
  Compass,
  Crosshair,
  Target,
  ArrowRight,
  Zap,
  Info,
  ShieldAlert,
  Code2,
} from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export function TestAnalysis() {
  const [testcases, setTestCases] = useState([]);
  const [selectedCase, setSelectedCase] = useState('');
  const [activeTab, setActiveTab] = useState('assertions'); // 'assertions' | 'selectors' | 'coverage' | 'risks'

  // AI Assertion Suggestions State
  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsMeta, setSuggestionsMeta] = useState({
    provider_used: 'heuristic',
    is_llm_generated: false,
  });
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [attachingSuggestions, setAttachingSuggestions] = useState(false);

  // Selector Audit State
  const [selectorReport, setSelectorReport] = useState(null);
  const [loadingSelectors, setLoadingSelectors] = useState(false);
  const [verifyingStep, setVerifyingStep] = useState(null);
  const [verifiedLocators, setVerifiedLocators] = useState({});
  const [fixingStep, setFixingStep] = useState(null);

  // Corpus Coverage State
  const [coverageReport, setCoverageReport] = useState(null);
  const [loadingCoverage, setLoadingCoverage] = useState(false);

  // General Risk Analysis State
  const [analysis, setAnalysis] = useState(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);

  const { showToast } = useToast();

  useEffect(() => {
    api.getTestCases().then((cases) => {
      setTestCases(cases);
      if (cases.length > 0) {
        setSelectedCase(cases[0].id);
      }
    });
  }, []);

  // 1. Suggest Assertions
  const handleSuggestAssertions = async () => {
    if (!selectedCase) return;
    try {
      setLoadingSuggestions(true);
      const res = await api.suggestAssertions(selectedCase);
      setSuggestions(res.suggestions || []);
      setSuggestionsMeta({
        provider_used: res.provider_used || 'heuristic',
        is_llm_generated: Boolean(res.is_llm_generated),
      });
      const providerLabel = res.is_llm_generated
        ? `LLM (${res.provider_used})`
        : `Deterministic Heuristic Engine`;
      showToast(
        `Generated ${res.suggestions?.length || 0} assertions via ${providerLabel}!`,
        'success'
      );
    } catch (err) {
      showToast('Failed to suggest assertions: ' + err.message, 'error');
    } finally {
      setLoadingSuggestions(false);
    }
  };

  const handleApplySingleSuggestion = async (suggestion) => {
    try {
      await api.applySuggestedAssertions(selectedCase, [suggestion]);
      setSuggestions((prev) => prev.filter((s) => s !== suggestion));
      showToast('Assertion attached to test case!', 'success');
    } catch (err) {
      showToast('Failed to attach assertion: ' + err.message, 'error');
    }
  };

  const handleApplyAllSuggestions = async () => {
    if (suggestions.length === 0) return;
    try {
      setAttachingSuggestions(true);
      await api.applySuggestedAssertions(selectedCase, suggestions);
      setSuggestions([]);
      showToast('All assertions attached successfully!', 'success');
    } catch (err) {
      showToast('Failed to attach assertions: ' + err.message, 'error');
    } finally {
      setAttachingSuggestions(false);
    }
  };

  // 2. Audit Selectors
  const handleAuditSelectors = async () => {
    if (!selectedCase) return;
    try {
      setLoadingSelectors(true);
      const res = await api.auditSelectors(selectedCase);
      setSelectorReport(res);
      setVerifiedLocators({});
      showToast(
        `Audit complete: ${res.safe_count} safe, ${res.fragile_count} fragile locators found.`,
        'info'
      );
    } catch (err) {
      showToast('Failed to audit selectors: ' + err.message, 'error');
    } finally {
      setLoadingSelectors(false);
    }
  };

  const handleVerifyLocator = async (item) => {
    if (!item.recommended_locator) return;
    try {
      setVerifyingStep(item.step_number);
      const res = await api.verifySelectorLive(selectedCase, {
        step_number: item.step_number,
        selector: item.recommended_locator,
      });
      setVerifiedLocators((prev) => ({ ...prev, [item.step_number]: res }));
      if (res.verified) {
        showToast(
          `Live DOM verified: Uniquely resolves to 1 visible <${res.matched_tag}>`,
          'success'
        );
      } else {
        showToast(`DOM verification failed: ${res.reason}`, 'error');
      }
    } catch (err) {
      showToast('Live DOM probe error: ' + err.message, 'error');
    } finally {
      setVerifyingStep(null);
    }
  };

  const handleApplySelectorFix = async (item) => {
    if (!item.recommended_locator) return;
    try {
      setFixingStep(item.step_number);
      await api.applySelectorFix(
        selectedCase,
        item.step_number,
        item.recommended_locator,
        false
      );
      showToast(`Step #${item.step_number} upgraded to ${item.recommended_locator}`, 'success');
      // Refresh audit
      const res = await api.auditSelectors(selectedCase);
      setSelectorReport(res);
    } catch (err) {
      showToast('Failed to apply resilient selector: ' + err.message, 'error');
    } finally {
      setFixingStep(null);
    }
  };

  // 3. Load Coverage Intelligence
  const handleLoadCoverage = async () => {
    try {
      setLoadingCoverage(true);
      const res = await api.getCoverageInsights();
      setCoverageReport(res);
      showToast('Corpus coverage intelligence updated!', 'success');
    } catch (err) {
      showToast('Failed to load coverage insights: ' + err.message, 'error');
    } finally {
      setLoadingCoverage(false);
    }
  };

  // 4. Run Risk Analysis
  const handleAnalyzeRisks = async () => {
    if (!selectedCase) return;
    try {
      setLoadingAnalysis(true);
      const res = await api.analyzeTestCase(selectedCase);
      setAnalysis(res);
      showToast('Risk analysis complete!', 'success');
    } catch (err) {
      showToast('Analysis failed: ' + err.message, 'error');
    } finally {
      setLoadingAnalysis(false);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-brand-500" />
            <span>AI QA Intelligence & Health</span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Intelligent assertion recommendations, selector fragility audits, and suite coverage insights.
          </p>
        </div>

        {/* Global Test Case Selector */}
        <div className="flex items-center gap-2 bg-white dark:bg-surface-cardDark p-2 rounded-xl border border-slate-200 dark:border-surface-borderDark shadow-sm">
          <label className="text-xs font-semibold text-slate-500 whitespace-nowrap pl-1">Target Test:</label>
          <select
            value={selectedCase}
            onChange={(e) => {
              setSelectedCase(e.target.value);
              setSuggestions([]);
              setSelectorReport(null);
              setAnalysis(null);
            }}
            className="text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-brand-500"
          >
            {testcases.map((tc) => (
              <option key={tc.id} value={tc.id}>
                {tc.name} ({tc.id})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-200 dark:border-surface-borderDark pb-2 text-xs font-bold">
        <button
          onClick={() => setActiveTab('assertions')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl transition-all ${
            activeTab === 'assertions'
              ? 'bg-brand-50 dark:bg-brand-950/40 text-brand-600 dark:text-brand-400 border border-brand-200 dark:border-brand-800'
              : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'
          }`}
        >
          <ShieldAlert className="w-4 h-4" />
          <span>Automatic Assertion Generation</span>
          {suggestions.length > 0 && (
            <span className="px-1.5 py-0.5 rounded-full text-[10px] bg-brand-500 text-white font-mono">
              {suggestions.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('selectors')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl transition-all ${
            activeTab === 'selectors'
              ? 'bg-brand-50 dark:bg-brand-950/40 text-brand-600 dark:text-brand-400 border border-brand-200 dark:border-brand-800'
              : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'
          }`}
        >
          <Crosshair className="w-4 h-4" />
          <span>Selector Intelligence & Healing</span>
        </button>

        <button
          onClick={() => {
            setActiveTab('coverage');
            if (!coverageReport) handleLoadCoverage();
          }}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl transition-all ${
            activeTab === 'coverage'
              ? 'bg-brand-50 dark:bg-brand-950/40 text-brand-600 dark:text-brand-400 border border-brand-200 dark:border-brand-800'
              : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'
          }`}
        >
          <Compass className="w-4 h-4" />
          <span>Corpus Coverage Intelligence</span>
        </button>

        <button
          onClick={() => setActiveTab('risks')}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl transition-all ${
            activeTab === 'risks'
              ? 'bg-brand-50 dark:bg-brand-950/40 text-brand-600 dark:text-brand-400 border border-brand-200 dark:border-brand-800'
              : 'text-slate-500 hover:text-slate-900 dark:hover:text-white'
          }`}
        >
          <AlertTriangle className="w-4 h-4" />
          <span>Workflow Risk Analysis</span>
        </button>
      </div>

      {/* Tab 1: Automatic Assertion Generation */}
      {activeTab === 'assertions' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm gap-4">
            <div>
              <h2 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Target className="w-4 h-4 text-brand-500" />
                <span>AI Assertion Recommendation Engine</span>
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                Analyzes recorded actions, network calls, and DOM states to recommend URL, visibility, and API response assertions.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleSuggestAssertions}
                disabled={loadingSuggestions || !selectedCase}
                className="flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl bg-brand-600 hover:bg-brand-500 text-white shadow-md shadow-brand-500/20 disabled:opacity-50"
              >
                {loadingSuggestions ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                <span>Suggest Assertions</span>
              </button>
              {suggestions.length > 0 && (
                <button
                  onClick={handleApplyAllSuggestions}
                  disabled={attachingSuggestions}
                  className="flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-500/20 disabled:opacity-50"
                >
                  {attachingSuggestions ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                  <span>Attach All ({suggestions.length})</span>
                </button>
              )}
            </div>
          </div>

          {suggestions.length > 0 ? (
            <div className="grid grid-cols-1 gap-3">
              {suggestions.map((s, idx) => (
                <div
                  key={idx}
                  className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm hover:border-brand-300 dark:hover:border-brand-800 transition-all"
                >
                  <div className="space-y-1.5 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-brand-50 text-brand-600 dark:bg-brand-950/60 dark:text-brand-300 border border-brand-200 dark:border-brand-800">
                        Step #{s.step_number} • {s.kind}
                      </span>
                      <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
                        {s.assertion_type}
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
                        Confidence: {Math.round(s.confidence * 100)}%
                      </span>
                    </div>

                    <p className="text-xs text-slate-600 dark:text-slate-400">{s.rationale}</p>

                    <div className="flex items-center gap-4 text-xs font-mono text-slate-500 dark:text-slate-400 pt-1">
                      {s.target && (
                        <span>
                          <strong className="text-slate-700 dark:text-slate-300">Target:</strong> {s.target}
                        </span>
                      )}
                      {s.expected && (
                        <span>
                          <strong className="text-slate-700 dark:text-slate-300">Expected:</strong> {s.expected}
                        </span>
                      )}
                    </div>
                  </div>

                  <button
                    onClick={() => handleApplySingleSuggestion(s)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-brand-50 hover:text-brand-600 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-all shrink-0"
                  >
                    <span>Attach to Test</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-12 text-center border border-dashed border-slate-200 dark:border-slate-800 rounded-2xl bg-slate-50/50 dark:bg-slate-900/20">
              <Sparkles className="w-8 h-8 text-slate-400 mx-auto mb-3" />
              <p className="text-sm font-medium text-slate-600 dark:text-slate-400">
                Click "Suggest Assertions" to analyze recorded steps and discover missing validation gates.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Selector Intelligence & Healing */}
      {activeTab === 'selectors' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm gap-4">
            <div>
              <h2 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Crosshair className="w-4 h-4 text-brand-500" />
                <span>Selector Fragility & Locator Audit</span>
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                Flags dynamic IDs, absolute XPaths, and hashed utility classes. Recommends resilient Playwright locators.
              </p>
            </div>
            <button
              onClick={handleAuditSelectors}
              disabled={loadingSelectors || !selectedCase}
              className="flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl bg-brand-600 hover:bg-brand-500 text-white shadow-md shadow-brand-500/20 disabled:opacity-50"
            >
              {loadingSelectors ? <Loader2 className="w-4 h-4 animate-spin" /> : <Crosshair className="w-4 h-4" />}
              <span>Audit Selectors</span>
            </button>
          </div>

          {selectorReport && (
            <div className="space-y-4">
              {/* Summary Stats */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark">
                  <span className="text-xs text-slate-400 font-medium">Evaluated Elements</span>
                  <div className="text-xl font-bold text-slate-900 dark:text-white mt-1">
                    {selectorReport.total_evaluated}
                  </div>
                </div>

                <div className="p-4 rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-950/20">
                  <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">Resilient Selectors</span>
                  <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400 mt-1">
                    {selectorReport.safe_count}
                  </div>
                </div>

                <div className="p-4 rounded-xl border border-rose-200 dark:border-rose-800 bg-rose-50/50 dark:bg-rose-950/20">
                  <span className="text-xs text-rose-500 font-medium">Fragile Locators</span>
                  <div className="text-xl font-bold text-rose-500 mt-1">
                    {selectorReport.fragile_count}
                  </div>
                </div>
              </div>

              {/* Selector Breakdown Table */}
              <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark overflow-hidden shadow-sm">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 dark:bg-slate-900/60 text-slate-400 uppercase tracking-wider font-semibold border-b border-slate-100 dark:border-slate-800">
                      <tr>
                        <th className="py-3 px-4">Step</th>
                        <th className="py-3 px-4">Current Selector</th>
                        <th className="py-3 px-4">Fragility</th>
                        <th className="py-3 px-4">Recommended Resilient Locator</th>
                        <th className="py-3 px-4 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                      {selectorReport.selectors.map((item, idx) => (
                        <tr key={idx} className="hover:bg-slate-50/50 dark:hover:bg-slate-900/30 transition-colors">
                          <td className="py-3 px-4 font-mono font-bold text-slate-600 dark:text-slate-400">
                            #{item.step_number}
                          </td>
                          <td className="py-3 px-4 font-mono max-w-xs truncate text-slate-800 dark:text-slate-200" title={item.current_selector}>
                            {item.current_selector}
                          </td>
                          <td className="py-3 px-4">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                item.is_fragile
                                  ? 'bg-rose-50 text-rose-600 dark:bg-rose-950/50 dark:text-rose-400 border border-rose-200 dark:border-rose-800'
                                  : 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800'
                              }`}
                            >
                              {item.fragility_score}/100 {item.is_fragile ? '• Fragile' : '• Resilient'}
                            </span>
                          </td>
                          <td className="py-3 px-4 font-mono font-semibold text-brand-600 dark:text-brand-400">
                            {item.recommended_locator || '—'}
                          </td>
                          <td className="py-3 px-4 text-right">
                            {item.is_fragile && item.recommended_locator ? (
                              <div className="flex items-center justify-end gap-2 flex-wrap">
                                {verifiedLocators[item.step_number] && (
                                  <span
                                    className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                      verifiedLocators[item.step_number].verified
                                        ? 'bg-emerald-50 text-emerald-600 border border-emerald-200 dark:bg-emerald-950/40 dark:border-emerald-800'
                                        : 'bg-rose-50 text-rose-600 border border-rose-200 dark:bg-rose-950/40 dark:border-rose-800'
                                    }`}
                                    title={verifiedLocators[item.step_number].reason}
                                  >
                                    {verifiedLocators[item.step_number].verified
                                      ? `✓ Verified (1 <${verifiedLocators[item.step_number].matched_tag}>)`
                                      : '✗ Verification Failed'}
                                  </span>
                                )}
                                <button
                                  onClick={() => handleVerifyLocator(item)}
                                  disabled={verifyingStep === item.step_number}
                                  className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700 dark:text-slate-300 transition-all disabled:opacity-50"
                                >
                                  {verifyingStep === item.step_number ? (
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  ) : (
                                    'Verify in DOM'
                                  )}
                                </button>
                                <button
                                  onClick={() => handleApplySelectorFix(item)}
                                  disabled={fixingStep === item.step_number}
                                  className="px-3 py-1 rounded-lg text-xs font-bold bg-brand-600 hover:bg-brand-500 text-white shadow-sm transition-all disabled:opacity-50"
                                >
                                  {fixingStep === item.step_number ? (
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  ) : (
                                    'Apply Fix'
                                  )}
                                </button>
                              </div>
                            ) : (
                              <span className="text-slate-400 text-[11px]">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Corpus Coverage Intelligence */}
      {activeTab === 'coverage' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm gap-4">
            <div>
              <h2 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Compass className="w-4 h-4 text-brand-500" />
                <span>Test Corpus Coverage & Test Gaps</span>
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                Analyzes visited routes, action diversity, and unasserted test cases across your active projects.
              </p>
            </div>
            <button
              onClick={handleLoadCoverage}
              disabled={loadingCoverage}
              className="flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl bg-brand-600 hover:bg-brand-500 text-white shadow-md shadow-brand-500/20 disabled:opacity-50"
            >
              {loadingCoverage ? <Loader2 className="w-4 h-4 animate-spin" /> : <Compass className="w-4 h-4" />}
              <span>Refresh Insights</span>
            </button>
          </div>

          {coverageReport && (
            <div className="space-y-4">
              {/* Score Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark">
                  <span className="text-xs text-slate-400 font-medium">Coverage Health</span>
                  <div className="text-2xl font-bold text-slate-900 dark:text-white mt-1">
                    {coverageReport.coverage_score} / 100
                  </div>
                </div>

                <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark">
                  <span className="text-xs text-slate-400 font-medium">Risk Level</span>
                  <div className="mt-1">
                    <span
                      className={`px-2.5 py-1 rounded-full text-xs font-bold ${
                        coverageReport.risk_level === 'Low'
                          ? 'bg-emerald-50 text-emerald-600 border border-emerald-200'
                          : coverageReport.risk_level === 'Moderate'
                          ? 'bg-amber-50 text-amber-600 border border-amber-200'
                          : 'bg-rose-50 text-rose-600 border border-rose-200'
                      }`}
                    >
                      {coverageReport.risk_level}
                    </span>
                  </div>
                </div>

                <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark">
                  <span className="text-xs text-slate-400 font-medium">Unique Routes</span>
                  <div className="text-2xl font-bold text-slate-900 dark:text-white mt-1">
                    {coverageReport.unique_routes_count}
                  </div>
                </div>

                <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark">
                  <span className="text-xs text-slate-400 font-medium">Assertion Density</span>
                  <div className="text-2xl font-bold text-slate-900 dark:text-white mt-1">
                    {coverageReport.assertion_density} / test
                  </div>
                </div>
              </div>

              {/* Actionable Recommendations */}
              {coverageReport.recommendations?.length > 0 && (
                <div className="p-5 rounded-2xl border border-brand-200 dark:border-brand-800 bg-brand-50/40 dark:bg-brand-950/20 space-y-3">
                  <h3 className="text-xs font-bold text-brand-700 dark:text-brand-300 uppercase tracking-wider flex items-center gap-1.5">
                    <Zap className="w-4 h-4 text-brand-500" />
                    <span>Actionable Recommendations</span>
                  </h3>
                  <div className="space-y-2">
                    {coverageReport.recommendations.map((rec, i) => (
                      <div key={i} className="p-3 rounded-xl bg-white dark:bg-surface-cardDark border border-slate-200 dark:border-slate-800 text-xs">
                        <span className="font-bold text-slate-900 dark:text-white">{rec.title}: </span>
                        <span className="text-slate-600 dark:text-slate-400">{rec.message}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Tab 4: Workflow Risk Analysis */}
      {activeTab === 'risks' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm gap-4">
            <div>
              <h2 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-rose-500" />
                <span>Heuristic & LLM Workflow Risk Audit</span>
              </h2>
              <p className="text-xs text-slate-500 mt-1">
                Deep semantic inspection of step sequences, missing verification barriers, and user experience risks.
              </p>
            </div>
            <button
              onClick={handleAnalyzeRisks}
              disabled={loadingAnalysis || !selectedCase}
              className="flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl bg-brand-600 hover:bg-brand-500 text-white shadow-md shadow-brand-500/20 disabled:opacity-50"
            >
              {loadingAnalysis ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              <span>Run Risk Audit</span>
            </button>
          </div>

          {analysis && (
            <div className="p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm space-y-6">
              <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-slate-800">
                <div>
                  <h3 className="text-base font-bold text-slate-900 dark:text-white">Analysis Findings</h3>
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
                  <h4 className="text-xs font-bold uppercase tracking-wider text-rose-500 mb-2 flex items-center gap-1.5">
                    <AlertTriangle className="w-4 h-4" />
                    <span>Identified Risks</span>
                  </h4>
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
            </div>
          )}
        </div>
      )}
    </div>
  );
}
