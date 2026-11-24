import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Play,
  FileCode2,
  Terminal,
  ShieldAlert,
  Sparkles,
  ChevronUp,
  ChevronDown,
  Trash2,
  Edit2,
  Check,
  X,
  Plus,
  Copy,
  ExternalLink,
  Camera,
  Settings2,
  Save,
  Sliders,
  Loader2,
  Crosshair,
  ArrowRight,
  Zap,
  RefreshCw,
} from "lucide-react";
import { api } from "../services/api";
import { useToast } from "../context/ToastContext";

export function TestCaseDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [testcase, setTestCase] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("steps"); // 'steps' | 'assertions' | 'codegen'
  const [codegen, setCodegen] = useState("");
  const [selectedScreenshot, setSelectedScreenshot] = useState(null);

  // Metadata editing
  const [isEditingMeta, setIsEditingMeta] = useState(false);
  const [metaName, setMetaName] = useState("");
  const [metaDesc, setMetaDesc] = useState("");
  const [metaUrl, setMetaUrl] = useState("");

  // Step editing
  const [editingStep, setEditingStep] = useState(null);
  const [editFormData, setEditFormData] = useState({});
  const [isAddingStep, setIsAddingStep] = useState(false);
  const [newStepData, setNewStepData] = useState({
    action_type: "click",
    selector: "",
    input_value: "",
    url: "",
    description_short: "",
  });

  // Assertion form
  const [newAssertionKind, setNewAssertionKind] = useState("visible");
  const [newAssertionTarget, setNewAssertionTarget] = useState("");
  const [newAssertionExpected, setNewAssertionExpected] = useState("");
  const [newAssertionStep, setNewAssertionStep] = useState(1);
  const [editingAssertionIndex, setEditingAssertionIndex] = useState(null);
  const [editAssertionData, setEditAssertionData] = useState({});

  // Replay Options Modal
  const [showReplayModal, setShowReplayModal] = useState(false);
  const [flakinessStats, setFlakinessStats] = useState(null);
  const [replayOptions, setReplayOptions] = useState({
    browser: "chromium",
    headed: false,
    heal: true,
    assertions: true,
    visual_diff: false,
    diff_threshold: 0.1,
    retries: 2,
  });

  // AI Features State
  const [suggestedAssertions, setSuggestedAssertions] = useState([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [selectorAudit, setSelectorAudit] = useState(null);
  const [loadingSelectorAudit, setLoadingSelectorAudit] = useState(false);

  const loadDetails = async () => {
    try {
      setLoading(true);
      const data = await api.getTestCase(id);
      setTestCase(data);
      setMetaName(data.name || "");
      setMetaDesc(data.description || "");
      setMetaUrl(data.start_url || "");
      if (data.browser) {
        setReplayOptions((prev) => ({ ...prev, browser: data.browser }));
      }
      api
        .getTestcaseFlakiness(id)
        .then(setFlakinessStats)
        .catch(() => {});
    } catch (err) {
      showToast("Failed to load test case: " + err.message, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDetails();
  }, [id]);

  const handleSuggestAssertions = async () => {
    try {
      setLoadingSuggestions(true);
      const res = await api.suggestAssertions(id);
      setSuggestedAssertions(res.suggestions || []);
      showToast(
        `Generated ${res.suggestions?.length || 0} assertions!`,
        "success",
      );
    } catch (err) {
      showToast("Failed to suggest assertions: " + err.message, "error");
    } finally {
      setLoadingSuggestions(false);
    }
  };

  const handleApplySingleSuggestion = async (suggestion) => {
    try {
      await api.applySuggestedAssertions(id, [suggestion]);
      setSuggestedAssertions((prev) => prev.filter((s) => s !== suggestion));
      showToast("Assertion attached!", "success");
      loadDetails();
    } catch (err) {
      showToast("Failed to attach: " + err.message, "error");
    }
  };

  const handleAuditSelectors = async () => {
    try {
      setLoadingSelectorAudit(true);
      const res = await api.auditSelectors(id);
      setSelectorAudit(res);
      showToast(
        `Audit: ${res.safe_count} resilient, ${res.fragile_count} fragile`,
        "info",
      );
    } catch (err) {
      showToast("Failed to audit: " + err.message, "error");
    } finally {
      setLoadingSelectorAudit(false);
    }
  };

  const handleApplySelectorFix = async (item) => {
    try {
      await api.applySelectorFix(
        id,
        item.step_number,
        item.recommended_locator,
      );
      showToast(
        `Step #${item.step_number} updated to resilient locator!`,
        "success",
      );
      loadDetails();
      const res = await api.auditSelectors(id);
      setSelectorAudit(res);
    } catch (err) {
      showToast("Failed to apply selector: " + err.message, "error");
    }
  };

  useEffect(() => {
    if (activeTab === "codegen" && !codegen && id) {
      api
        .getCodegen(id)
        .then((res) => setCodegen(res.code))
        .catch((err) =>
          showToast("Could not load code: " + err.message, "error"),
        );
    }
  }, [activeTab, id, codegen]);

  const handleSaveMeta = async () => {
    if (!metaName.trim()) {
      showToast("Test case name cannot be empty", "error");
      return;
    }
    try {
      const updated = await api.updateTestCase(id, {
        name: metaName.trim(),
        description: metaDesc.trim(),
        start_url: metaUrl.trim(),
      });
      setTestCase(updated);
      setIsEditingMeta(false);
      showToast("Metadata updated successfully!", "success");
    } catch (err) {
      showToast("Failed to update metadata: " + err.message, "error");
    }
  };

  const handleRunTest = async () => {
    try {
      showToast("Launching test execution...", "info");
      const run = await api.startExecution({
        testcase_id: id,
        browser: replayOptions.browser,
        headed: replayOptions.headed,
        heal: replayOptions.heal,
        assertions: replayOptions.assertions,
        visual_diff: replayOptions.visual_diff,
        diff_threshold: replayOptions.diff_threshold,
      });
      showToast("Execution launched!", "success");
      setShowReplayModal(false);
      navigate(`/executions?id=${run.id}`);
    } catch (err) {
      showToast("Execution failed: " + err.message, "error");
    }
  };

  const handleReorder = async (stepNumber, direction) => {
    try {
      const updated = await api.reorderStep(id, stepNumber, direction);
      setTestCase(updated);
      showToast(`Step moved ${direction}.`, "info");
    } catch (err) {
      showToast("Failed to reorder: " + err.message, "error");
    }
  };

  const handleDeleteTestCase = async () => {
    if (
      !confirm(
        `Are you sure you want to permanently delete "${testcase.name}"?`,
      )
    )
      return;
    try {
      await api.deleteTestCase(id);
      showToast("Test case deleted.", "success");
      navigate("/testcases");
    } catch (err) {
      showToast("Failed to delete: " + err.message, "error");
    }
  };

  const handleCreateStep = async (e) => {
    e.preventDefault();
    try {
      const updated = await api.createStep(id, newStepData);
      setTestCase(updated);
      setIsAddingStep(false);
      setNewStepData({
        action_type: "click",
        selector: "",
        input_value: "",
        url: "",
        description_short: "",
      });
      showToast("Step added successfully!", "success");
    } catch (err) {
      showToast("Failed to add step: " + err.message, "error");
    }
  };

  const handleDeleteStep = async (stepNumber) => {
    if (!confirm(`Are you sure you want to delete Step ${stepNumber}?`)) return;
    try {
      const updated = await api.deleteStep(id, stepNumber);
      setTestCase(updated);
      showToast(`Step ${stepNumber} deleted.`, "success");
    } catch (err) {
      showToast("Failed to delete step: " + err.message, "error");
    }
  };

  const startEditStep = (step) => {
    setEditingStep(step.number);
    setEditFormData({
      action_type: step.action_type,
      selector: step.element?.selector || "",
      input_value: step.input_value || "",
      description_short: step.description_short || "",
    });
  };

  const saveEditStep = async (stepNumber) => {
    try {
      const payload = {
        action_type: editFormData.action_type,
        input_value: editFormData.input_value,
        description_short: editFormData.description_short,
        element: { selector: editFormData.selector },
      };
      const updated = await api.updateStep(id, stepNumber, payload);
      setTestCase(updated);
      setEditingStep(null);
      showToast("Step updated successfully.", "success");
    } catch (err) {
      showToast("Failed to update step: " + err.message, "error");
    }
  };

  const handleAddAssertion = async (e) => {
    e.preventDefault();
    try {
      const payload = {
        kind: newAssertionKind,
        target: newAssertionTarget || null,
        expected: newAssertionExpected || null,
        step_number: parseInt(newAssertionStep, 10) || 1,
        enforced: true,
      };
      const updated = await api.addAssertion(id, payload);
      setTestCase(updated);
      setNewAssertionTarget("");
      setNewAssertionExpected("");
      showToast("Custom assertion added!", "success");
    } catch (err) {
      showToast("Failed to add assertion: " + err.message, "error");
    }
  };

  const handleStartEditAssertion = (index, assn) => {
    setEditingAssertionIndex(index);
    setEditAssertionData({
      kind: assn.kind,
      target: assn.target || "",
      expected: assn.expected || "",
      step_number: assn.step_number || 1,
      enforced: assn.enforced !== false,
    });
  };

  const handleSaveAssertion = async (index) => {
    try {
      const updated = await api.updateAssertion(id, index, editAssertionData);
      setTestCase(updated);
      setEditingAssertionIndex(null);
      showToast("Assertion updated successfully!", "success");
    } catch (err) {
      showToast("Failed to update assertion: " + err.message, "error");
    }
  };

  const handleDeleteAssertion = async (index) => {
    try {
      const updated = await api.deleteAssertion(id, index);
      setTestCase(updated);
      showToast("Assertion removed.", "info");
    } catch (err) {
      showToast("Failed to remove assertion: " + err.message, "error");
    }
  };

  if (loading) {
    return (
      <div className="p-12 text-center text-slate-500">
        Loading test case details...
      </div>
    );
  }

  if (!testcase) {
    return (
      <div className="p-12 text-center">
        <h3 className="text-base font-bold text-slate-800 dark:text-slate-200">
          Test Case Not Found
        </h3>
        <button
          onClick={() => navigate("/testcases")}
          className="mt-4 px-4 py-2 text-xs font-semibold rounded-lg bg-brand-600 text-white"
        >
          Return to Test Cases
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-200 dark:border-surface-borderDark">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <button
            onClick={() => navigate("/testcases")}
            className="p-2 rounded-xl border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 transition-colors mt-0.5"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>

          {isEditingMeta ? (
            <div className="space-y-2 flex-1 max-w-xl">
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase">
                  Test Case Name
                </label>
                <input
                  type="text"
                  value={metaName}
                  onChange={(e) => setMetaName(e.target.value)}
                  className="w-full px-3 py-1.5 text-sm font-semibold rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase">
                    Start URL
                  </label>
                  <input
                    type="text"
                    value={metaUrl}
                    onChange={(e) => setMetaUrl(e.target.value)}
                    className="w-full px-2.5 py-1 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                  />
                </div>
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase">
                    Description
                  </label>
                  <input
                    type="text"
                    value={metaDesc}
                    onChange={(e) => setMetaDesc(e.target.value)}
                    placeholder="Optional description"
                    className="w-full px-2.5 py-1 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                  />
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <button
                  onClick={handleSaveMeta}
                  className="px-3 py-1 text-xs font-semibold rounded-lg bg-brand-600 text-white flex items-center gap-1.5"
                >
                  <Check className="w-3.5 h-3.5" />
                  <span>Save Changes</span>
                </button>
                <button
                  onClick={() => setIsEditingMeta(false)}
                  className="px-2.5 py-1 text-xs text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white truncate">
                  {testcase.name}
                </h1>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 font-mono text-slate-500 uppercase">
                  {testcase.browser}
                </span>
                {flakinessStats && flakinessStats.total_runs > 0 && (
                  <span
                    className={`text-xs px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wider flex items-center gap-1.5 ${
                      flakinessStats.rating === "stable"
                        ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800"
                        : flakinessStats.rating === "low"
                          ? "bg-blue-50 text-blue-600 dark:bg-blue-950/60 dark:text-blue-400 border border-blue-200 dark:border-blue-800"
                          : flakinessStats.rating === "moderate"
                            ? "bg-amber-50 text-amber-600 dark:bg-amber-950/60 dark:text-amber-400 border border-amber-200 dark:border-amber-800"
                            : flakinessStats.rating === "failing"
                              ? "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300 border border-rose-300 dark:border-rose-800"
                              : "bg-rose-50 text-rose-600 dark:bg-rose-950/60 dark:text-rose-400 border border-rose-200 dark:border-rose-800"
                    }`}
                    title={`First-Attempt Pass: ${flakinessStats.first_attempt_pass_rate ?? 0}% | Final Pass: ${flakinessStats.final_pass_rate ?? 0}% | Flakiness: ${flakinessStats.flakiness_rate ?? flakinessStats.flakiness_score}% | Stability: ${flakinessStats.stability_score ?? 100}% | Failure Rate: ${flakinessStats.failure_rate ?? 0}%`}
                  >
                    <RefreshCw className="w-3 h-3" />
                    <span>
                      {flakinessStats.flakiness_rate ??
                        flakinessStats.flakiness_score}
                      % Flaky ({flakinessStats.rating})
                    </span>
                  </span>
                )}
                <button
                  onClick={() => setIsEditingMeta(true)}
                  className="p-1 text-slate-400 hover:text-brand-500 transition-colors"
                  title="Edit test case metadata"
                >
                  <Edit2 className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500 mt-1">
                <span className="font-mono truncate max-w-md">
                  {testcase.start_url}
                </span>
                {testcase.description && (
                  <span className="text-slate-400 border-l border-slate-200 dark:border-slate-800 pl-3">
                    {testcase.description}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          <button
            onClick={() => navigate(`/ai-assistant?caseId=${id}`)}
            className="flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-xl bg-purple-50 dark:bg-purple-950/50 hover:bg-purple-100 dark:hover:bg-purple-900 text-purple-600 dark:text-purple-300 border border-purple-200 dark:border-purple-800 transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>AI Analyze</span>
          </button>

          <button
            onClick={() => setShowReplayModal(true)}
            className="flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-600/25 transition-all"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>Execute Replay</span>
          </button>

          <button
            onClick={handleDeleteTestCase}
            className="p-2 rounded-xl border border-slate-200 dark:border-slate-800 text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors"
            title="Delete this test case"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Navigation Tabs (Test Summary, Code, Assertions, History) */}
      <div className="flex items-center gap-2 border-b border-slate-200 dark:border-surface-borderDark pb-px">
        <button
          onClick={() => setActiveTab("steps")}
          className={`px-4 py-2 text-xs font-bold transition-all border-b-2 flex items-center gap-2 ${
            activeTab === "steps"
              ? "border-brand-500 text-brand-600 dark:text-brand-400"
              : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          <FileCode2 className="w-4 h-4" />
          <span>Test Summary ({testcase.steps?.length || 0})</span>
        </button>

        <button
          onClick={() => setActiveTab("codegen")}
          className={`px-4 py-2 text-xs font-bold transition-all border-b-2 flex items-center gap-2 ${
            activeTab === "codegen"
              ? "border-brand-500 text-brand-600 dark:text-brand-400"
              : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          <Terminal className="w-4 h-4" />
          <span>Code ({codegen ? "Ready" : "Export"})</span>
        </button>

        <button
          onClick={() => setActiveTab("assertions")}
          className={`px-4 py-2 text-xs font-bold transition-all border-b-2 flex items-center gap-2 ${
            activeTab === "assertions"
              ? "border-brand-500 text-brand-600 dark:text-brand-400"
              : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          <ShieldAlert className="w-4 h-4" />
          <span>Assertions ({testcase.custom_assertions?.length || 0})</span>
        </button>
      </div>

      {/* Tab: Recorded Steps / Test Summary */}
      {activeTab === "steps" && (
        <div className="grid grid-cols-12 gap-5">
          {/* Main Column: Steps sequence and actions (8 cols) */}
          <div className="col-span-12 lg:col-span-8 space-y-4">
            {/* Steps Status Strip */}
            <div className="flex flex-wrap items-center justify-between p-3.5 rounded-2xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 text-xs font-semibold shadow-sm gap-3">
              <div className="flex items-center gap-3">
                <span className="text-slate-900 dark:text-white font-bold">
                  {testcase.steps?.length || 0} Total Steps
                </span>
                <span className="text-emerald-500 font-bold flex items-center gap-1">
                  ● {testcase.steps?.length || 0} passed
                </span>
                <span className="text-rose-500 font-bold flex items-center gap-1">
                  ● 0 failed
                </span>
                <span className="text-slate-400 flex items-center gap-1">
                  ● 0 skipped
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleAuditSelectors}
                  disabled={loadingSelectorAudit}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 hover:bg-brand-50 hover:text-brand-600 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-colors disabled:opacity-50"
                >
                  {loadingSelectorAudit ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Crosshair className="w-3.5 h-3.5" />
                  )}
                  <span>Audit Selectors</span>
                </button>
                <button
                  onClick={() => setIsAddingStep(!isAddingStep)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-brand-50 dark:bg-brand-950/50 text-brand-600 dark:text-brand-400 hover:bg-brand-100 transition-colors"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>{isAddingStep ? "Cancel" : "Add Step"}</span>
                </button>
              </div>
            </div>

          {/* Selector Audit Banner if performed */}
          {selectorAudit && (
            <div className="p-4 rounded-xl border border-brand-200 dark:border-brand-800 bg-brand-50/30 dark:bg-brand-950/20 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                  <Crosshair className="w-4 h-4 text-brand-500" />
                  <span>
                    Selector Fragility Audit: {selectorAudit.safe_count}{" "}
                    Resilient, {selectorAudit.fragile_count} Fragile
                  </span>
                </span>
                <button
                  onClick={() => setSelectorAudit(null)}
                  className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              {selectorAudit.fragile_count > 0 && (
                <div className="space-y-1.5 pt-1">
                  {selectorAudit.selectors
                    .filter((s) => s.is_fragile && s.recommended_locator)
                    .map((item, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between p-2 rounded-lg bg-white dark:bg-surface-cardDark border border-slate-200 dark:border-slate-800"
                      >
                        <span className="font-mono text-slate-700 dark:text-slate-300">
                          Step #{item.step_number}: Upgrade to{" "}
                          <strong className="text-brand-600 dark:text-brand-400">
                            {item.recommended_locator}
                          </strong>
                        </span>
                        <button
                          onClick={() => handleApplySelectorFix(item)}
                          className="px-2.5 py-1 text-[11px] font-bold rounded bg-brand-600 text-white hover:bg-brand-500 shadow-sm"
                        >
                          Apply Fix
                        </button>
                      </div>
                    ))}
                </div>
              )}
            </div>
          )}

          {/* Add Step Form */}
          {isAddingStep && (
            <form
              onSubmit={handleCreateStep}
              className="p-4 rounded-xl border border-brand-200 dark:border-brand-900 bg-brand-50/20 dark:bg-brand-950/20 space-y-3"
            >
              <h4 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider">
                Append New Step
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-500 uppercase mb-1">
                    Action Type
                  </label>
                  <select
                    value={newStepData.action_type}
                    onChange={(e) =>
                      setNewStepData({
                        ...newStepData,
                        action_type: e.target.value,
                      })
                    }
                    className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
                  >
                    <option value="click">click</option>
                    <option value="fill">fill</option>
                    <option value="navigate">navigate</option>
                    <option value="hover">hover</option>
                    <option value="press">press</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-500 uppercase mb-1">
                    Target Selector
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. #login-btn"
                    value={newStepData.selector}
                    onChange={(e) =>
                      setNewStepData({
                        ...newStepData,
                        selector: e.target.value,
                      })
                    }
                    className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-500 uppercase mb-1">
                    Input Value
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. user@example.com"
                    value={newStepData.input_value}
                    onChange={(e) =>
                      setNewStepData({
                        ...newStepData,
                        input_value: e.target.value,
                      })
                    }
                    className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-500 uppercase mb-1">
                    Short Description
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Click submit"
                    value={newStepData.description_short}
                    onChange={(e) =>
                      setNewStepData({
                        ...newStepData,
                        description_short: e.target.value,
                      })
                    }
                    className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <button
                  type="submit"
                  className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-brand-600 text-white"
                >
                  Append Step
                </button>
              </div>
            </form>
          )}

          {/* Steps List */}
          <div className="space-y-3">
            {testcase.steps?.map((step) => {
              const shotName = step.screenshot?.replace(/^.*[\\/]/, "");
              const isEditing = editingStep === step.number;

              return (
                <div
                  key={step.number}
                  className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4"
                >
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <span className="w-7 h-7 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-bold text-xs flex items-center justify-center shrink-0">
                      {step.number}
                    </span>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 text-[10px] font-bold rounded uppercase bg-brand-50 dark:bg-brand-950/60 text-brand-500 border border-brand-200 dark:border-brand-800">
                          {step.action_type}
                        </span>
                        <span className="text-xs font-semibold text-slate-900 dark:text-slate-100 truncate">
                          {step.description_short || step.action_type}
                        </span>
                      </div>

                      {isEditing ? (
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                          <input
                            type="text"
                            placeholder="Selector"
                            value={editFormData.selector}
                            onChange={(e) =>
                              setEditFormData({
                                ...editFormData,
                                selector: e.target.value,
                              })
                            }
                            className="px-2.5 py-1 text-xs rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                          />
                          <input
                            type="text"
                            placeholder="Description"
                            value={editFormData.description_short}
                            onChange={(e) =>
                              setEditFormData({
                                ...editFormData,
                                description_short: e.target.value,
                              })
                            }
                            className="px-2.5 py-1 text-xs rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                          />
                          <input
                            type="text"
                            placeholder="Input Value"
                            value={editFormData.input_value}
                            onChange={(e) =>
                              setEditFormData({
                                ...editFormData,
                                input_value: e.target.value,
                              })
                            }
                            className="px-2.5 py-1 text-xs rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                          />
                          <div className="col-span-full flex justify-end gap-2 mt-1">
                            <button
                              onClick={() => setEditingStep(null)}
                              className="px-2.5 py-1 text-xs text-slate-500"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={() => saveEditStep(step.number)}
                              className="px-3 py-1 text-xs font-semibold rounded bg-brand-600 text-white"
                            >
                              Save
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="space-y-1 mt-1 text-xs text-slate-500">
                          {step.element?.selector && (
                            <div className="flex items-center gap-1.5 font-mono">
                              <span className="text-slate-400">selector:</span>
                              <span className="text-slate-700 dark:text-slate-300 truncate max-w-md bg-slate-100 dark:bg-slate-800/80 px-1.5 py-0.5 rounded">
                                {step.element.selector}
                              </span>
                            </div>
                          )}
                          {step.input_value && (
                            <div className="flex items-center gap-1.5">
                              <span className="text-slate-400">value:</span>
                              <span className="font-semibold text-slate-800 dark:text-slate-200">
                                "{step.input_value}"
                              </span>
                            </div>
                          )}
                          {step.url && (
                            <div className="flex items-center gap-1.5 font-mono truncate">
                              <span className="text-slate-400">url:</span>
                              <span className="text-slate-700 dark:text-slate-300">
                                {step.url}
                              </span>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Screenshot & Actions */}
                  <div className="flex items-center gap-3 shrink-0 self-center md:self-auto">
                    {shotName && (
                      <button
                        onClick={() =>
                          setSelectedScreenshot(
                            `/api/testcases/${id}/screenshots/${shotName}`,
                          )
                        }
                        className="group/img relative w-20 h-12 rounded-lg border border-slate-200 dark:border-slate-800 overflow-hidden bg-slate-100 dark:bg-slate-900 shrink-0"
                        title="Click to view full screenshot"
                      >
                        <img
                          src={`/api/testcases/${id}/screenshots/${shotName}`}
                          alt={`Step ${step.number}`}
                          className="w-full h-full object-cover"
                          loading="lazy"
                        />
                        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover/img:opacity-100 flex items-center justify-center text-white transition-opacity">
                          <Camera className="w-4 h-4" />
                        </div>
                      </button>
                    )}

                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleReorder(step.number, "up")}
                        disabled={step.number === 1}
                        className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 disabled:opacity-20"
                        title="Move up"
                      >
                        <ChevronUp className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleReorder(step.number, "down")}
                        disabled={step.number === testcase.steps.length}
                        className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 disabled:opacity-20"
                        title="Move down"
                      >
                        <ChevronDown className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => startEditStep(step)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-brand-500 hover:bg-brand-50 dark:hover:bg-brand-950/40"
                        title="Edit step"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleDeleteStep(step.number)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40"
                        title="Delete step"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          </div>

          {/* Right Column: Metadata & Execution Sidebar (4 cols) */}
          <div className="col-span-12 lg:col-span-4 space-y-4">
            <div className="p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm space-y-4 lg:sticky lg:top-4">
              {/* Primary Execute Button */}
              <button
                type="button"
                onClick={() => setShowReplayModal(true)}
                aria-label="Execute test case"
                className="w-full py-3 px-4 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-600/25 flex items-center justify-center gap-2 transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
              >
                <Play className="w-4 h-4 fill-current" />
                <span>Execute test case</span>
              </button>
              <p className="text-[10px] text-slate-400 text-center font-mono">
                Executes locally on Playwright (0ms cloud latency)
              </p>

              <div className="space-y-3 pt-2 border-t border-slate-100 dark:border-slate-800 text-xs">
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                    Description
                  </label>
                  <p className="text-slate-600 dark:text-slate-300 text-xs leading-relaxed">
                    {testcase.description ||
                      "The user will execute the automated workflow validating page navigations, interactions, and assertions on local Chromium."}
                  </p>
                </div>

                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                    Preconditions
                  </label>
                  <span className="text-slate-500 italic text-[11px]">
                    Local application / target server running
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 pt-1">
                  <div>
                    <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                      Status
                    </label>
                    <span className="px-2.5 py-0.5 text-[11px] font-bold rounded-lg bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800 inline-block">
                      Ready
                    </span>
                  </div>
                  <div>
                    <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                      Priority
                    </label>
                    <span className="px-2.5 py-0.5 text-[11px] font-bold rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 inline-block">
                      Medium
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 pt-1">
                  <div>
                    <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                      Automation Status
                    </label>
                    <span className="px-2.5 py-0.5 text-[11px] font-bold rounded-lg bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 inline-block">
                      Automated
                    </span>
                  </div>
                  <div>
                    <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                      Engine
                    </label>
                    <span className="px-2.5 py-0.5 text-[11px] font-mono text-slate-500 uppercase bg-slate-100 dark:bg-slate-800 rounded inline-block">
                      {testcase.browser || "Chromium"}
                    </span>
                  </div>
                </div>

                {/* Variables and Secrets Used */}
                <div className="pt-2 border-t border-slate-100 dark:border-slate-800">
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1.5">
                    Variables & Secrets Used
                  </label>
                  <div className="flex flex-wrap gap-1.5">
                    <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-slate-100 dark:bg-slate-800 text-brand-600 dark:text-brand-400 font-semibold">
                      {"{{base_url}}"}
                    </span>
                    <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-slate-100 dark:bg-slate-800 text-indigo-500 font-semibold">
                      {"{{username}}"}
                    </span>
                    <span className="px-2 py-0.5 text-[10px] font-mono rounded bg-slate-100 dark:bg-slate-800 text-rose-500 font-semibold">
                      {"{{password}}"}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab: Assertions */}
      {activeTab === "assertions" && (
        <div className="space-y-6">
          {/* AI Suggest Assertions Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between p-4 rounded-2xl border border-brand-200 dark:border-brand-800 bg-brand-50/40 dark:bg-brand-950/20 gap-3">
            <div>
              <h3 className="text-xs font-bold text-slate-900 dark:text-white flex items-center gap-1.5 uppercase tracking-wider">
                <Sparkles className="w-4 h-4 text-brand-500" />
                <span>AI Automated Assertion Generation</span>
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Automatically synthesize URL, element visibility, and HTTP
                status verification assertions.
              </p>
            </div>
            <button
              onClick={handleSuggestAssertions}
              disabled={loadingSuggestions}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold rounded-xl bg-brand-600 hover:bg-brand-500 text-white shadow-sm disabled:opacity-50 shrink-0"
            >
              {loadingSuggestions ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Sparkles className="w-3.5 h-3.5" />
              )}
              <span>Suggest Assertions</span>
            </button>
          </div>

          {/* Suggested Assertions Cards */}
          {suggestedAssertions.length > 0 && (
            <div className="space-y-2 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark shadow-sm">
              <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
                <span className="text-xs font-bold text-slate-900 dark:text-white">
                  Recommended Assertions ({suggestedAssertions.length})
                </span>
                <button
                  onClick={() => setSuggestedAssertions([])}
                  className="text-xs text-slate-400 hover:text-slate-600"
                >
                  Dismiss
                </button>
              </div>
              <div className="grid grid-cols-1 gap-2 pt-1">
                {suggestedAssertions.map((s, idx) => (
                  <div
                    key={idx}
                    className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-100 dark:border-slate-800 gap-2 text-xs"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-brand-600 dark:text-brand-400">
                          Step #{s.step_number}
                        </span>
                        <span className="font-semibold text-slate-800 dark:text-slate-200">
                          {s.assertion_type}
                        </span>
                        <span className="text-[10px] text-slate-400">
                          ({Math.round(s.confidence * 100)}% conf)
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        {s.rationale}
                      </p>
                    </div>
                    <button
                      onClick={() => handleApplySingleSuggestion(s)}
                      className="px-3 py-1 rounded-lg text-xs font-bold bg-brand-600 hover:bg-brand-500 text-white shadow-sm shrink-0"
                    >
                      Attach
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <form
            onSubmit={handleAddAssertion}
            className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark space-y-4 shadow-sm"
          >
            <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Plus className="w-4 h-4 text-brand-500" />
              <span>Attach Custom Assertion</span>
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
              <div>
                <label className="block text-[11px] font-semibold text-slate-500 uppercase mb-1">
                  Step Number
                </label>
                <input
                  type="number"
                  min="1"
                  max={testcase.steps?.length || 1}
                  value={newAssertionStep}
                  onChange={(e) => setNewAssertionStep(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900"
                />
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-slate-500 uppercase mb-1">
                  Assertion Type
                </label>
                <select
                  value={newAssertionKind}
                  onChange={(e) => setNewAssertionKind(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900"
                >
                  <option value="visible">Element Visible</option>
                  <option value="text">Element Contains Text</option>
                  <option value="url">URL Path Matches</option>
                  <option value="status">HTTP Status Code</option>
                  <option value="no_page_error">No Console Errors</option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-slate-500 uppercase mb-1">
                  Target (Selector/URL)
                </label>
                <input
                  type="text"
                  placeholder="e.g. #submit-btn or /dashboard"
                  value={newAssertionTarget}
                  onChange={(e) => setNewAssertionTarget(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900"
                />
              </div>

              <div>
                <label className="block text-[11px] font-semibold text-slate-500 uppercase mb-1">
                  Expected Value
                </label>
                <input
                  type="text"
                  placeholder="e.g. Welcome or 200"
                  value={newAssertionExpected}
                  onChange={(e) => setNewAssertionExpected(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900"
                />
              </div>
            </div>

            <div className="flex justify-end">
              <button
                type="submit"
                className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-brand-600 hover:bg-brand-500 text-white shadow-sm"
              >
                Add Assertion
              </button>
            </div>
          </form>

          {/* List existing custom assertions */}
          <div className="space-y-3">
            {testcase.custom_assertions?.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-xs border border-dashed border-slate-200 dark:border-slate-800 rounded-xl">
                No custom assertions attached yet. Add assertions above to
                enforce validation rules during replays.
              </div>
            ) : (
              testcase.custom_assertions?.map((assn, idx) => {
                const isEditing = editingAssertionIndex === idx;

                return (
                  <div
                    key={idx}
                    className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm"
                  >
                    {isEditing ? (
                      <div className="space-y-3">
                        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                          <div>
                            <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">
                              Step Number
                            </label>
                            <input
                              type="number"
                              min="1"
                              value={editAssertionData.step_number}
                              onChange={(e) =>
                                setEditAssertionData({
                                  ...editAssertionData,
                                  step_number: parseInt(e.target.value, 10),
                                })
                              }
                              className="w-full px-2.5 py-1 text-xs rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">
                              Type
                            </label>
                            <select
                              value={editAssertionData.kind}
                              onChange={(e) =>
                                setEditAssertionData({
                                  ...editAssertionData,
                                  kind: e.target.value,
                                })
                              }
                              className="w-full px-2.5 py-1 text-xs rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                            >
                              <option value="visible">Element Visible</option>
                              <option value="text">
                                Element Contains Text
                              </option>
                              <option value="url">URL Path Matches</option>
                              <option value="status">HTTP Status Code</option>
                              <option value="no_page_error">
                                No Console Errors
                              </option>
                            </select>
                          </div>
                          <div>
                            <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">
                              Target
                            </label>
                            <input
                              type="text"
                              value={editAssertionData.target}
                              onChange={(e) =>
                                setEditAssertionData({
                                  ...editAssertionData,
                                  target: e.target.value,
                                })
                              }
                              className="w-full px-2.5 py-1 text-xs rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] font-bold text-slate-400 uppercase mb-1">
                              Expected
                            </label>
                            <input
                              type="text"
                              value={editAssertionData.expected}
                              onChange={(e) =>
                                setEditAssertionData({
                                  ...editAssertionData,
                                  expected: e.target.value,
                                })
                              }
                              className="w-full px-2.5 py-1 text-xs rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                            />
                          </div>
                        </div>
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => setEditingAssertionIndex(null)}
                            className="px-2.5 py-1 text-xs text-slate-500"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={() => handleSaveAssertion(idx)}
                            className="px-3 py-1 text-xs font-semibold rounded bg-brand-600 text-white"
                          >
                            Save
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between">
                        <div className="flex flex-wrap items-center gap-3">
                          <span className="w-6 h-6 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-500 font-mono text-xs flex items-center justify-center">
                            #{assn.step_number || 1}
                          </span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-brand-50 dark:bg-brand-950/60 text-brand-500 border border-brand-200 dark:border-brand-800">
                            {assn.kind}
                          </span>
                          <span className="text-xs text-slate-700 dark:text-slate-300 font-medium">
                            Target:{" "}
                            <span className="font-mono text-slate-500">
                              {assn.target || "None"}
                            </span>
                          </span>
                          {assn.expected && (
                            <span className="text-xs text-slate-700 dark:text-slate-300">
                              Expected:{" "}
                              <span className="font-bold text-slate-900 dark:text-white">
                                "{assn.expected}"
                              </span>
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleStartEditAssertion(idx, assn)}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-brand-500 hover:bg-brand-50 dark:hover:bg-brand-950/40"
                            title="Edit assertion"
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleDeleteAssertion(idx)}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40"
                            title="Delete assertion"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* Tab: Code Generation (Code View: AssertiveAction & AssertiveValidator) */}
      {activeTab === "codegen" && (
        <div className="space-y-4">
          {/* Code Artifacts Strip */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-950/20 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-emerald-400" />
                  <span className="font-bold text-xs text-white">AssertiveAction</span>
                  <span className="px-1.5 py-0.2 text-[9px] font-bold rounded bg-emerald-500/20 text-emerald-400">
                    Verified
                  </span>
                </div>
                <span className="text-[11px] text-slate-400 block mt-1">
                  v1 • Python • Playwright engine • Local Execution Ready
                </span>
              </div>
              <button
                type="button"
                onClick={() => setShowReplayModal(true)}
                className="px-3 py-1.5 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-1.5 shadow-sm"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Execute</span>
              </button>
            </div>

            <div className="p-4 rounded-xl border border-indigo-500/30 bg-indigo-950/20 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-indigo-400" />
                  <span className="font-bold text-xs text-white">AssertiveValidator</span>
                  <span className="px-1.5 py-0.2 text-[9px] font-bold rounded bg-indigo-500/20 text-indigo-400">
                    Verified
                  </span>
                </div>
                <span className="text-[11px] text-slate-400 block mt-1">
                  v1 • Python • Playwright engine • Contract & Visual Probes
                </span>
              </div>
              <button
                type="button"
                onClick={() => setShowReplayModal(true)}
                className="px-3 py-1.5 rounded-lg text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white flex items-center gap-1.5 shadow-sm"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Execute</span>
              </button>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-slate-950 text-slate-200 overflow-hidden shadow-xl">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-brand-400" />
                <span className="text-xs font-mono font-semibold text-slate-300">
                  test_{id.replace(/[^a-zA-Z0-9_]/g, "_")}.py
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const blob = new Blob([codegen || ""], { type: "text/plain" });
                    const downloadUrl = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = downloadUrl;
                    a.download = `test_${id.replace(/[^a-zA-Z0-9_]/g, "_")}.py`;
                    a.click();
                    showToast("Test script downloaded!", "success");
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download Script</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(codegen);
                    showToast("Code copied to clipboard!", "success");
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-brand-600 hover:bg-brand-500 text-white transition-colors"
                >
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copy Code</span>
                </button>
              </div>
            </div>
            <pre className="p-5 font-mono text-xs leading-relaxed overflow-x-auto selection:bg-brand-600">
              {codegen || "# Generating Pytest Playwright code..."}
            </pre>
          </div>
        </div>
      )}

      {/* Replay Execution Options Modal */}
      {showReplayModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-surface-cardDark border border-slate-200 dark:border-surface-borderDark rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
              <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Sliders className="w-5 h-5 text-emerald-500" />
                <span>Replay Configuration</span>
              </h3>
              <button
                onClick={() => setShowReplayModal(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Browser Engine
                </label>
                <select
                  value={replayOptions.browser}
                  onChange={(e) => {
                    const newBrowser = e.target.value;
                    setReplayOptions({
                      ...replayOptions,
                      browser: newBrowser,
                    });
                    localStorage.setItem("tracecase_default_browser", newBrowser);
                    window.dispatchEvent(
                      new CustomEvent("tracecase:browser-changed", {
                        detail: newBrowser,
                      })
                    );
                  }}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900"
                >
                  <option value="chromium">Chromium</option>
                  <option value="firefox">Firefox</option>
                  <option value="webkit">WebKit (Safari)</option>
                  <option value="msedge">Microsoft Edge</option>
                </select>
              </div>

              {/* Retries Slider */}
              <div className="space-y-1.5 p-2.5 rounded-lg bg-amber-50/50 dark:bg-amber-950/20 border border-amber-100 dark:border-amber-900/40">
                <div className="flex justify-between items-center text-xs font-semibold text-slate-700 dark:text-slate-300">
                  <span className="flex items-center gap-1.5">
                    <RefreshCw className="w-3.5 h-3.5 text-amber-500" />
                    <span>Flaky Retry Attempts</span>
                  </span>
                  <span className="font-mono text-amber-700 dark:text-amber-400 font-bold">
                    {replayOptions.retries === 0
                      ? "0 (None)"
                      : `${replayOptions.retries} Retries`}
                  </span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="3"
                  step="1"
                  value={replayOptions.retries ?? 2}
                  onChange={(e) =>
                    setReplayOptions({
                      ...replayOptions,
                      retries: parseInt(e.target.value, 10),
                    })
                  }
                  className="w-full h-1.5 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-amber-500"
                />
                <div className="flex justify-between text-[10px] text-slate-400">
                  <span>0 (None)</span>
                  <span>1</span>
                  <span className="text-amber-600 dark:text-amber-400 font-semibold">
                    2 (Default)
                  </span>
                  <span>3 (Max)</span>
                </div>
              </div>

              <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900/50">
                <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
                  Headed Window Mode
                </span>
                <input
                  type="checkbox"
                  checked={replayOptions.headed}
                  onChange={(e) =>
                    setReplayOptions({
                      ...replayOptions,
                      headed: e.target.checked,
                    })
                  }
                  className="rounded text-brand-600 focus:ring-brand-500"
                />
              </div>

              <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900/50">
                <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
                  Selector Self-Healing
                </span>
                <input
                  type="checkbox"
                  checked={replayOptions.heal}
                  onChange={(e) =>
                    setReplayOptions({
                      ...replayOptions,
                      heal: e.target.checked,
                    })
                  }
                  className="rounded text-brand-600 focus:ring-brand-500"
                />
              </div>

              <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900/50">
                <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
                  Evaluate Assertions
                </span>
                <input
                  type="checkbox"
                  checked={replayOptions.assertions}
                  onChange={(e) =>
                    setReplayOptions({
                      ...replayOptions,
                      assertions: e.target.checked,
                    })
                  }
                  className="rounded text-brand-600 focus:ring-brand-500"
                />
              </div>

              <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900/50">
                <span className="text-xs font-medium text-slate-700 dark:text-slate-300">
                  Visual Screenshot Diffing
                </span>
                <input
                  type="checkbox"
                  checked={replayOptions.visual_diff}
                  onChange={(e) =>
                    setReplayOptions({
                      ...replayOptions,
                      visual_diff: e.target.checked,
                    })
                  }
                  className="rounded text-brand-600 focus:ring-brand-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setShowReplayModal(false)}
                className="px-3.5 py-2 text-xs font-semibold text-slate-600 dark:text-slate-300"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleRunTest}
                className="px-5 py-2 text-xs font-bold rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-600/25 flex items-center gap-1.5"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Launch Replay</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Zoomed Screenshot Modal */}
      {selectedScreenshot && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 backdrop-blur-sm"
          onClick={() => setSelectedScreenshot(null)}
        >
          <div
            className="relative max-w-4xl max-h-[90vh] bg-slate-900 rounded-2xl overflow-hidden border border-slate-800 p-2 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setSelectedScreenshot(null)}
              className="absolute top-4 right-4 p-1.5 rounded-full bg-black/60 text-white hover:bg-black transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
            <img
              src={selectedScreenshot}
              alt="Screenshot preview"
              className="w-full h-auto max-h-[82vh] object-contain rounded-lg"
            />
          </div>
        </div>
      )}
    </div>
  );
}
