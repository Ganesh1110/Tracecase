import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
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
} from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export function TestCaseDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const [testcase, setTestCase] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('steps'); // 'steps' | 'assertions' | 'codegen' | 'analysis'
  const [codegen, setCodegen] = useState('');
  const [selectedScreenshot, setSelectedScreenshot] = useState(null);
  const [editingStep, setEditingStep] = useState(null);
  const [editFormData, setEditFormData] = useState({});
  const [isAddingStep, setIsAddingStep] = useState(false);
  const [newStepData, setNewStepData] = useState({
    action_type: 'click',
    selector: '',
    input_value: '',
    url: '',
    description_short: '',
  });

  // Assertion form
  const [newAssertionKind, setNewAssertionKind] = useState('visible');
  const [newAssertionTarget, setNewAssertionTarget] = useState('');
  const [newAssertionExpected, setNewAssertionExpected] = useState('');
  const [newAssertionStep, setNewAssertionStep] = useState(1);

  const loadDetails = async () => {
    try {
      setLoading(true);
      const data = await api.getTestCase(id);
      setTestCase(data);
    } catch (err) {
      showToast('Failed to load test case: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDetails();
  }, [id]);

  useEffect(() => {
    if (activeTab === 'codegen' && !codegen && id) {
      api
        .getCodegen(id)
        .then((res) => setCodegen(res.code))
        .catch((err) => showToast('Could not load code: ' + err.message, 'error'));
    }
  }, [activeTab, id, codegen]);

  const handleRunTest = async () => {
    try {
      showToast('Starting test execution...', 'info');
      const run = await api.startExecution({ testcase_id: id });
      showToast('Execution launched!', 'success');
      navigate(`/executions?id=${run.id}`);
    } catch (err) {
      showToast('Execution failed: ' + err.message, 'error');
    }
  };

  const handleReorder = async (stepNumber, direction) => {
    try {
      const updated = await api.reorderStep(id, stepNumber, direction);
      setTestCase(updated);
      showToast(`Step moved ${direction}.`, 'info');
    } catch (err) {
      showToast('Failed to reorder: ' + err.message, 'error');
    }
  };

  const handleDeleteTestCase = async () => {
    if (!confirm(`Are you sure you want to permanently delete "${testcase.name}"?`)) return;
    try {
      await api.deleteTestCase(id);
      showToast('Test case deleted.', 'success');
      navigate('/testcases');
    } catch (err) {
      showToast('Failed to delete: ' + err.message, 'error');
    }
  };

  const handleCreateStep = async (e) => {
    e.preventDefault();
    try {
      const updated = await api.createStep(id, newStepData);
      setTestCase(updated);
      setIsAddingStep(false);
      setNewStepData({
        action_type: 'click',
        selector: '',
        input_value: '',
        url: '',
        description_short: '',
      });
      showToast('Step added successfully!', 'success');
    } catch (err) {
      showToast('Failed to add step: ' + err.message, 'error');
    }
  };

  const handleDeleteStep = async (stepNumber) => {
    if (!confirm(`Are you sure you want to delete Step ${stepNumber}?`)) return;
    try {
      const updated = await api.deleteStep(id, stepNumber);
      setTestCase(updated);
      showToast(`Step ${stepNumber} deleted.`, 'success');
    } catch (err) {
      showToast('Failed to delete step: ' + err.message, 'error');
    }
  };

  const startEditStep = (step) => {
    setEditingStep(step.number);
    setEditFormData({
      action_type: step.action_type,
      selector: step.element?.selector || '',
      input_value: step.input_value || '',
      description_short: step.description_short || '',
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
      showToast('Step updated successfully.', 'success');
    } catch (err) {
      showToast('Failed to update step: ' + err.message, 'error');
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
      setNewAssertionTarget('');
      setNewAssertionExpected('');
      showToast('Custom assertion added!', 'success');
    } catch (err) {
      showToast('Failed to add assertion: ' + err.message, 'error');
    }
  };

  const handleDeleteAssertion = async (index) => {
    try {
      const updated = await api.deleteAssertion(id, index);
      setTestCase(updated);
      showToast('Assertion removed.', 'info');
    } catch (err) {
      showToast('Failed to remove assertion: ' + err.message, 'error');
    }
  };

  if (loading) {
    return <div className="p-12 text-center text-slate-500">Loading test case details...</div>;
  }

  if (!testcase) {
    return (
      <div className="p-12 text-center">
        <h3 className="text-base font-bold text-slate-800 dark:text-slate-200">Test Case Not Found</h3>
        <button
          onClick={() => navigate('/testcases')}
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
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/testcases')}
            className="p-2 rounded-xl border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">
                {testcase.name}
              </h1>
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 font-mono text-slate-500">
                {testcase.browser}
              </span>
            </div>
            <p className="text-xs font-mono text-slate-500 mt-0.5">{testcase.start_url}</p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => navigate(`/ai-assistant?caseId=${id}`)}
            className="flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-xl bg-purple-50 dark:bg-purple-950/50 hover:bg-purple-100 dark:hover:bg-purple-900 text-purple-600 dark:text-purple-300 border border-purple-200 dark:border-purple-800 transition-colors"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Analyze with AI</span>
          </button>

          <button
            onClick={handleRunTest}
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

      {/* Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-200 dark:border-surface-borderDark pb-px">
        <button
          onClick={() => setActiveTab('steps')}
          className={`px-4 py-2 text-xs font-bold transition-all border-b-2 flex items-center gap-2 ${
            activeTab === 'steps'
              ? 'border-brand-500 text-brand-600 dark:text-brand-400'
              : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
          }`}
        >
          <FileCode2 className="w-4 h-4" />
          <span>Recorded Steps ({testcase.steps?.length || 0})</span>
        </button>

        <button
          onClick={() => setActiveTab('assertions')}
          className={`px-4 py-2 text-xs font-bold transition-all border-b-2 flex items-center gap-2 ${
            activeTab === 'assertions'
              ? 'border-brand-500 text-brand-600 dark:text-brand-400'
              : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
          }`}
        >
          <ShieldAlert className="w-4 h-4" />
          <span>Assertions ({testcase.custom_assertions?.length || 0})</span>
        </button>

        <button
          onClick={() => setActiveTab('codegen')}
          className={`px-4 py-2 text-xs font-bold transition-all border-b-2 flex items-center gap-2 ${
            activeTab === 'codegen'
              ? 'border-brand-500 text-brand-600 dark:text-brand-400'
              : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
          }`}
        >
          <Terminal className="w-4 h-4" />
          <span>Pytest Code</span>
        </button>
      </div>

      {/* Tab: Recorded Steps */}
      {activeTab === 'steps' && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <span className="text-xs text-slate-500">
              Total {testcase.steps?.length || 0} user actions in sequence
            </span>
            <button
              onClick={() => setIsAddingStep(!isAddingStep)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-brand-50 dark:bg-brand-950/60 hover:bg-brand-100 dark:hover:bg-brand-900 text-brand-600 dark:text-brand-400 border border-brand-200 dark:border-brand-800 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>{isAddingStep ? 'Cancel' : 'Add Step'}</span>
            </button>
          </div>

          {isAddingStep && (
            <form
              onSubmit={handleCreateStep}
              className="p-4 rounded-xl border border-brand-500/40 bg-brand-50/20 dark:bg-brand-950/20 space-y-3"
            >
              <h4 className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider">
                Insert New Step
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                <div>
                  <label className="block text-[10px] font-semibold text-slate-500 uppercase mb-1">
                    Action
                  </label>
                  <select
                    value={newStepData.action_type}
                    onChange={(e) =>
                      setNewStepData({ ...newStepData, action_type: e.target.value })
                    }
                    className="w-full px-2.5 py-1.5 text-xs rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                  >
                    <option value="click">click</option>
                    <option value="input">input</option>
                    <option value="navigate">navigate</option>
                    <option value="scroll">scroll</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] font-semibold text-slate-500 uppercase mb-1">
                    Selector
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. #submit or button.primary"
                    value={newStepData.selector}
                    onChange={(e) =>
                      setNewStepData({ ...newStepData, selector: e.target.value })
                    }
                    className="w-full px-2.5 py-1.5 text-xs rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-semibold text-slate-500 uppercase mb-1">
                    Input Value / URL
                  </label>
                  <input
                    type="text"
                    placeholder="Text or URL"
                    value={newStepData.input_value || newStepData.url}
                    onChange={(e) =>
                      setNewStepData({
                        ...newStepData,
                        input_value: e.target.value,
                        url: e.target.value,
                      })
                    }
                    className="w-full px-2.5 py-1.5 text-xs rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-semibold text-slate-500 uppercase mb-1">
                    Description
                  </label>
                  <input
                    type="text"
                    placeholder="Short description"
                    value={newStepData.description_short}
                    onChange={(e) =>
                      setNewStepData({ ...newStepData, description_short: e.target.value })
                    }
                    className="w-full px-2.5 py-1.5 text-xs rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setIsAddingStep(false)}
                  className="px-3 py-1 text-xs text-slate-500"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1 text-xs font-semibold rounded bg-brand-600 text-white"
                >
                  Append Step
                </button>
              </div>
            </form>
          )}

          {testcase.steps?.map((step) => {
            const isEditing = editingStep === step.number;
            const shotPath = step.screenshot_with_highlight || step.screenshot_path;
            const shotName = shotPath ? shotPath.split(/[/\\]/).pop() : null;

            return (
              <div
                key={step.number}
                className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm flex flex-col md:flex-row gap-4 items-start justify-between group"
              >
                <div className="flex items-start gap-3.5 flex-1 min-w-0">
                  <div className="w-7 h-7 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 flex items-center justify-center font-mono font-bold text-xs shrink-0 mt-0.5">
                    {step.number}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="px-2 py-0.5 text-[10px] font-bold uppercase rounded-md bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400 border border-brand-200 dark:border-brand-800">
                        {step.action_type}
                      </span>
                      <span className="text-sm font-semibold text-slate-900 dark:text-white truncate">
                        {step.description_short || `${step.action_type} action`}
                      </span>
                    </div>

                    {isEditing ? (
                      <div className="mt-3 p-3 rounded-lg bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 space-y-2">
                        <div className="grid grid-cols-2 gap-2">
                          <input
                            type="text"
                            placeholder="Selector"
                            value={editFormData.selector}
                            onChange={(e) =>
                              setEditFormData({ ...editFormData, selector: e.target.value })
                            }
                            className="px-2.5 py-1.5 text-xs rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 font-mono"
                          />
                          <input
                            type="text"
                            placeholder="Input value (if any)"
                            value={editFormData.input_value}
                            onChange={(e) =>
                              setEditFormData({ ...editFormData, input_value: e.target.value })
                            }
                            className="px-2.5 py-1.5 text-xs rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                          />
                        </div>
                        <div className="flex justify-end gap-2 mt-2">
                          <button
                            onClick={() => setEditingStep(null)}
                            className="px-2 py-1 text-xs text-slate-500"
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
                            <span className="text-slate-700 dark:text-slate-300">{step.url}</span>
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
                        setSelectedScreenshot(`/api/testcases/${id}/screenshots/${shotName}`)
                      }
                      className="group/img relative w-20 h-12 rounded-lg border border-slate-200 dark:border-slate-800 overflow-hidden bg-slate-100 dark:bg-slate-900 shrink-0"
                      title="Click to zoom screenshot"
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
                      onClick={() => handleReorder(step.number, 'up')}
                      disabled={step.number === 1}
                      className="p-1 rounded text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 disabled:opacity-20"
                      title="Move up"
                    >
                      <ChevronUp className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleReorder(step.number, 'down')}
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
      )}

      {/* Tab: Assertions */}
      {activeTab === 'assertions' && (
        <div className="space-y-6">
          <form
            onSubmit={handleAddAssertion}
            className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark space-y-4"
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
          <div className="space-y-2">
            {testcase.custom_assertions?.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-xs">
                No custom assertions added yet. Add assertions above to enforce validation rules during replays.
              </div>
            ) : (
              testcase.custom_assertions?.map((assn, idx) => (
                <div
                  key={idx}
                  className="p-3.5 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark flex items-center justify-between"
                >
                  <div className="flex items-center gap-3">
                    <span className="w-6 h-6 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-500 font-mono text-xs flex items-center justify-center">
                      #{assn.step_number || 1}
                    </span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-brand-50 dark:bg-brand-950/60 text-brand-500 border border-brand-200 dark:border-brand-800">
                      {assn.kind}
                    </span>
                    <span className="text-xs text-slate-700 dark:text-slate-300 font-medium">
                      Target: <span className="font-mono text-slate-500">{assn.target || 'None'}</span>
                    </span>
                    {assn.expected && (
                      <span className="text-xs text-slate-700 dark:text-slate-300">
                        Expected: <span className="font-bold text-slate-900 dark:text-white">"{assn.expected}"</span>
                      </span>
                    )}
                  </div>

                  <button
                    onClick={() => handleDeleteAssertion(idx)}
                    className="p-1 rounded text-slate-400 hover:text-rose-500"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Tab: Pytest Codegen */}
      {activeTab === 'codegen' && (
        <div className="rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-slate-950 text-slate-200 overflow-hidden shadow-xl">
          <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/60">
            <span className="text-xs font-mono font-semibold text-slate-400">
              test_{id.replace(/[^a-zA-Z0-9_]/g, '_')}.py
            </span>
            <button
              onClick={() => {
                navigator.clipboard.writeText(codegen);
                showToast('Code copied to clipboard!', 'success');
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
            >
              <Copy className="w-3.5 h-3.5" />
              <span>Copy Pytest</span>
            </button>
          </div>
          <pre className="p-5 font-mono text-xs leading-relaxed overflow-x-auto selection:bg-brand-600">
            {codegen || '# Generating Pytest Playwright code...'}
          </pre>
        </div>
      )}

      {/* Zoomed Screenshot Modal */}
      {selectedScreenshot && (
        <div
          onClick={() => setSelectedScreenshot(null)}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in cursor-zoom-out"
        >
          <div className="relative max-w-4xl max-h-[85vh] rounded-2xl overflow-hidden border border-slate-700 shadow-2xl bg-black">
            <img
              src={selectedScreenshot}
              alt="Screenshot Preview"
              className="w-full h-full object-contain"
            />
          </div>
        </div>
      )}
    </div>
  );
}
