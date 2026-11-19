import React, { useEffect, useState, useRef } from 'react';
import {
  Compass,
  Play,
  Square,
  AlertTriangle,
  ShieldCheck,
  Globe,
  Layers,
  ArrowRight,
  FileText,
  Search,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  Trash2,
  ExternalLink,
  Lock,
  Eye,
  RefreshCw,
  Sparkles,
  ListChecks,
  UserCheck,
  AlertCircle,
  Check,
  X,
  FileCode2,
  Target,
  GitBranch,
  Flame,
  Filter,
} from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export function AutonomousExploration() {
  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [graphData, setGraphData] = useState(null);
  const [selectedNodeUrl, setSelectedNodeUrl] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadingGraph, setLoadingGraph] = useState(false);

  // Active view tab: 'graph' | 'review' | 'planner' | 'regression'
  const [viewTab, setViewTab] = useState('graph');

  // Drafts & Synthesis State
  const [drafts, setDrafts] = useState([]);
  const [selectedDraftId, setSelectedDraftId] = useState(null);
  const [loadingDrafts, setLoadingDrafts] = useState(false);
  const [synthesizing, setSynthesizing] = useState(false);
  const [processingDraftId, setProcessingDraftId] = useState(null);

  // Requirements Planner State
  const [requirementText, setRequirementText] = useState('As a user, I want to open settings and update my profile email');
  const [planningRequirement, setPlanningRequirement] = useState(false);
  const [planResult, setPlanResult] = useState(null);

  // Intelligent Regression State
  const [changedRoutesInput, setChangedRoutesInput] = useState('/settings, /dashboard');
  const [changedSelectorsInput, setChangedSelectorsInput] = useState('#input-email, #btn-save-profile');
  const [analyzingRegression, setAnalyzingRegression] = useState(false);
  const [regressionResult, setRegressionResult] = useState(null);

  // New exploration dialog state
  const [showNewModal, setShowNewModal] = useState(false);
  const [startUrl, setStartUrl] = useState('http://127.0.0.1:8000/');
  const [maxDepth, setMaxDepth] = useState(3);
  const [maxPages, setMaxPages] = useState(20);
  const [maxInteractions, setMaxInteractions] = useState(50);
  const [timeoutSecs, setTimeoutSecs] = useState(120);
  const [browserType, setBrowserType] = useState('chromium');
  const [starting, setStarting] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  // Active running exploration
  const [activeRun, setActiveRun] = useState(null);

  const { showToast } = useToast();
  const pollingRef = useRef(null);

  // Load exploration runs
  const loadRuns = async () => {
    try {
      const data = await api.listExplorationRuns();
      setRuns(data);
      const running = data.find((r) => r.status === 'running');
      setActiveRun(running || null);

      if (!selectedRunId && data.length > 0) {
        setSelectedRunId(data[0].id);
      }
    } catch (err) {
      showToast(err.message || 'Failed loading exploration runs', 'error');
    } finally {
      setLoading(false);
    }
  };

  // Load graph for selected run
  const loadGraph = async (runId) => {
    if (!runId) return;
    setLoadingGraph(true);
    try {
      const g = await api.getExplorationGraph(runId);
      setGraphData(g);
      const urls = Object.keys(g.nodes || {});
      if (urls.length > 0 && (!selectedNodeUrl || !g.nodes[selectedNodeUrl])) {
        setSelectedNodeUrl(urls[0]);
      }
    } catch (err) {
      showToast(err.message || 'Failed loading navigation graph', 'error');
    } finally {
      setLoadingGraph(false);
    }
  };

  // Load drafts for selected exploration run
  const loadDrafts = async (runId) => {
    if (!runId) return;
    setLoadingDrafts(true);
    try {
      const dList = await api.listDrafts({ exploration_id: runId });
      setDrafts(dList);
      if (dList.length > 0 && (!selectedDraftId || !dList.some((d) => d.id === selectedDraftId))) {
        setSelectedDraftId(dList[0].id);
      }
    } catch (err) {
      showToast(err.message || 'Failed loading test drafts', 'error');
    } finally {
      setLoadingDrafts(false);
    }
  };

  useEffect(() => {
    loadRuns();
  }, []);

  useEffect(() => {
    if (selectedRunId) {
      loadGraph(selectedRunId);
      loadDrafts(selectedRunId);
    }
  }, [selectedRunId]);

  // Polling while an exploration is active
  useEffect(() => {
    if (activeRun) {
      pollingRef.current = setInterval(async () => {
        try {
          const runDetail = await api.getExplorationRun(activeRun.id);
          if (runDetail.status !== 'running') {
            setActiveRun(null);
            loadRuns();
            if (selectedRunId === activeRun.id) {
              loadGraph(activeRun.id);
              loadDrafts(activeRun.id);
            }
          } else {
            setActiveRun(runDetail);
            if (selectedRunId === activeRun.id) {
              loadGraph(activeRun.id);
            }
          }
        } catch {
          // ignore transient poll error
        }
      }, 3000);
    } else {
      if (pollingRef.current) clearInterval(pollingRef.current);
    }

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [activeRun, selectedRunId]);

  const handleStartExploration = async (e) => {
    e.preventDefault();
    if (!startUrl) {
      showToast('Start URL is required', 'error');
      return;
    }

    setStarting(true);
    try {
      const config = {
        start_url: startUrl.trim(),
        max_depth: parseInt(maxDepth, 10),
        max_pages: parseInt(maxPages, 10),
        max_interactions: parseInt(maxInteractions, 10),
        execution_timeout: parseFloat(timeoutSecs),
        browser: browserType,
        headless: true,
      };

      const result = await api.startExploration(config);
      showToast('Autonomous exploration started', 'success');
      setShowNewModal(false);
      setActiveRun(result);
      setSelectedRunId(result.id);
      loadRuns();
    } catch (err) {
      showToast(err.message || 'Failed to start exploration', 'error');
    } finally {
      setStarting(false);
    }
  };

  const handleCancelExploration = async (runId) => {
    setCancelling(true);
    try {
      await api.cancelExploration(runId);
      showToast('Exploration cancellation requested', 'info');
      setActiveRun(null);
      loadRuns();
      if (selectedRunId === runId) {
        loadGraph(runId);
      }
    } catch (err) {
      showToast(err.message || 'Failed to cancel exploration', 'error');
    } finally {
      setCancelling(false);
    }
  };

  const handleDeleteRun = async (runId) => {
    if (!window.confirm('Delete this exploration run and its navigation graph?')) return;
    try {
      await api.deleteExplorationRun(runId);
      showToast('Exploration run deleted', 'success');
      if (selectedRunId === runId) {
        setSelectedRunId(null);
        setGraphData(null);
        setDrafts([]);
      }
      loadRuns();
    } catch (err) {
      showToast(err.message || 'Failed to delete exploration run', 'error');
    }
  };

  const handleSynthesizeJourneys = async () => {
    if (!selectedRunId) return;
    setSynthesizing(true);
    try {
      const generated = await api.synthesizeJourneys(selectedRunId, { max_journeys: 6 });
      showToast(`Synthesized ${generated.length} test journeys from graph`, 'success');
      setDrafts(generated);
      if (generated.length > 0) {
        setSelectedDraftId(generated[0].id);
        setViewTab('review');
      }
    } catch (err) {
      showToast(err.message || 'Failed synthesizing journeys', 'error');
    } finally {
      setSynthesizing(false);
    }
  };

  const handleApproveDraft = async (draftId) => {
    setProcessingDraftId(draftId);
    try {
      const result = await api.approveDraft(draftId);
      showToast(`Approved! Test case '${result.testcase_id}' created and ready for execution.`, 'success');
      loadDrafts(selectedRunId);
    } catch (err) {
      showToast(err.message || 'Failed approving draft', 'error');
    } finally {
      setProcessingDraftId(null);
    }
  };

  const handleRejectDraft = async (draftId) => {
    const reason = window.prompt('Reason for rejecting draft (optional):', 'Not aligned with requirements');
    if (reason === null) return;

    setProcessingDraftId(draftId);
    try {
      await api.rejectDraft(draftId, { reason });
      showToast('Draft rejected', 'info');
      loadDrafts(selectedRunId);
    } catch (err) {
      showToast(err.message || 'Failed rejecting draft', 'error');
    } finally {
      setProcessingDraftId(null);
    }
  };

  const handlePlanRequirement = async (e) => {
    e.preventDefault();
    if (!selectedRunId) {
      showToast('Please select an exploration run first', 'error');
      return;
    }
    if (!requirementText.trim()) {
      showToast('Please enter a requirement or user story', 'error');
      return;
    }

    setPlanningRequirement(true);
    try {
      const result = await api.planRequirement({
        requirement: requirementText.trim(),
        exploration_id: selectedRunId,
      });
      setPlanResult(result);
      if (result.synthesized_draft) {
        showToast('Requirement mapped to graph! Test draft generated.', 'success');
        loadDrafts(selectedRunId);
      } else {
        showToast('Requirement analyzed. Missing evidence identified.', 'info');
      }
    } catch (err) {
      showToast(err.message || 'Failed planning requirement', 'error');
    } finally {
      setPlanningRequirement(false);
    }
  };

  const handleSelectRegression = async (e) => {
    e.preventDefault();
    setAnalyzingRegression(true);
    try {
      const routes = changedRoutesInput
        .split(',')
        .map((r) => r.trim())
        .filter(Boolean);
      const selectors = changedSelectorsInput
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);

      const res = await api.selectRegression({
        changed_routes: routes,
        changed_selectors: selectors,
      });
      setRegressionResult(res);
      showToast(`Regression impact analyzed: ${res.recommended_count} tests prioritized.`, 'success');
    } catch (err) {
      showToast(err.message || 'Failed selecting regression tests', 'error');
    } finally {
      setAnalyzingRegression(false);
    }
  };

  const selectedNode = graphData?.nodes?.[selectedNodeUrl] || null;
  const selectedDraft = drafts.find((d) => d.id === selectedDraftId) || null;
  const pendingDraftsCount = drafts.filter((d) => d.status === 'pending').length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-200 dark:border-gray-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <Compass className="w-7 h-7 text-indigo-600 dark:text-indigo-400" />
            Autonomous Exploration & Intelligence
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Explore state spaces, map requirements to navigation graphs, review drafts, and select intelligent regression suites.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              loadRuns();
              if (selectedRunId) {
                loadGraph(selectedRunId);
                loadDrafts(selectedRunId);
              }
            }}
            className="p-2 border border-gray-300 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-300 transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={() => setShowNewModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium shadow-sm transition-colors"
          >
            <Play className="w-4 h-4" />
            Start Exploration
          </button>
        </div>
      </div>

      {/* Active Run Banner */}
      {activeRun && (
        <div className="bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-800/60 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="relative flex items-center justify-center">
              <Loader2 className="w-6 h-6 text-indigo-600 dark:text-indigo-400 animate-spin" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-gray-900 dark:text-gray-100 text-sm">
                  Active Exploration:
                </span>
                <span className="font-mono text-xs px-2 py-0.5 bg-indigo-100 dark:bg-indigo-900/60 text-indigo-700 dark:text-indigo-300 rounded">
                  {activeRun.start_url}
                </span>
              </div>
              <div className="flex items-center gap-4 text-xs text-gray-600 dark:text-gray-400 mt-1">
                <span>Pages: <strong>{activeRun.pages_discovered}</strong></span>
                <span>Transitions: <strong>{activeRun.transitions_discovered}</strong></span>
                <span>Forms: <strong>{activeRun.forms_discovered}</strong></span>
              </div>
            </div>
          </div>
          <button
            onClick={() => handleCancelExploration(activeRun.id)}
            disabled={cancelling}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-medium transition-colors"
          >
            <Square className="w-3.5 h-3.5" />
            {cancelling ? 'Cancelling...' : 'Stop Exploration'}
          </button>
        </div>
      )}

      {/* Main Grid: Runs Selector & Content Area */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left Column: Runs List */}
        <div className="lg:col-span-1 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-1.5">
              <Layers className="w-4 h-4 text-gray-500" />
              Exploration Runs
            </h2>
            <span className="text-xs text-gray-500">{runs.length}</span>
          </div>

          {loading ? (
            <div className="py-8 text-center text-gray-500 text-sm">Loading runs...</div>
          ) : runs.length === 0 ? (
            <div className="py-8 text-center text-gray-500 text-xs">
              No exploration runs yet. Click "Start Exploration" to begin.
            </div>
          ) : (
            <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
              {runs.map((r) => {
                const isSelected = r.id === selectedRunId;
                return (
                  <div
                    key={r.id}
                    onClick={() => setSelectedRunId(r.id)}
                    className={`p-3 rounded-lg border text-left cursor-pointer transition-all ${
                      isSelected
                        ? 'border-indigo-500 bg-indigo-50/50 dark:bg-indigo-950/30'
                        : 'border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/60'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1 mb-1">
                      <span className="text-xs font-mono truncate max-w-[170px] text-gray-900 dark:text-gray-200 font-medium">
                        {r.start_url}
                      </span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                          r.status === 'completed'
                            ? 'bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-300'
                            : r.status === 'running'
                            ? 'bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 animate-pulse'
                            : r.status === 'cancelled'
                            ? 'bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300'
                            : 'bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-300'
                        }`}
                      >
                        {r.status}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-gray-500 mt-2">
                      <span>{r.pages_discovered} pages · {r.transitions_discovered} edges</span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteRun(r.id);
                        }}
                        className="text-gray-400 hover:text-red-500 p-1 transition-colors"
                        title="Delete run"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Column: 4 View Modes */}
        <div className="lg:col-span-3 space-y-6">
          {/* View Mode Tabs & Action Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-3">
            <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
              <button
                onClick={() => setViewTab('graph')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  viewTab === 'graph'
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}
              >
                <Globe className="w-3.5 h-3.5" />
                Navigation Graph
              </button>

              <button
                onClick={() => setViewTab('planner')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  viewTab === 'planner'
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}
              >
                <Target className="w-3.5 h-3.5" />
                Requirements Planner
              </button>

              <button
                onClick={() => setViewTab('review')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  viewTab === 'review'
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}
              >
                <ListChecks className="w-3.5 h-3.5" />
                Review Queue
                {pendingDraftsCount > 0 && (
                  <span className="px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-amber-500 text-white">
                    {pendingDraftsCount}
                  </span>
                )}
              </button>

              <button
                onClick={() => setViewTab('regression')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  viewTab === 'regression'
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}
              >
                <GitBranch className="w-3.5 h-3.5" />
                Intelligent Regression
              </button>
            </div>

            {/* Synthesize Button */}
            {selectedRunId && viewTab !== 'regression' && (
              <button
                onClick={handleSynthesizeJourneys}
                disabled={synthesizing || !graphData || graphData.total_pages === 0}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg text-xs font-medium shadow-sm transition-colors"
              >
                {synthesizing ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Sparkles className="w-3.5 h-3.5" />
                )}
                {synthesizing ? 'Synthesizing...' : 'Synthesize Journeys'}
              </button>
            )}
          </div>

          {/* TAB 1: NAVIGATION GRAPH */}
          {viewTab === 'graph' && (
            <>
              {loadingGraph ? (
                <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-12 text-center text-gray-500">
                  <Loader2 className="w-8 h-8 mx-auto animate-spin text-indigo-600 mb-2" />
                  Loading Application Navigation Graph...
                </div>
              ) : !graphData || Object.keys(graphData.nodes || {}).length === 0 ? (
                <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-12 text-center">
                  <Globe className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                  <h3 className="text-base font-medium text-gray-900 dark:text-gray-100">
                    No Navigation Graph Data
                  </h3>
                  <p className="text-sm text-gray-500 mt-1 max-w-sm mx-auto">
                    Select an exploration run or start a new exploration to view discovered pages and state transitions.
                  </p>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
                      <div className="text-xs text-gray-500 uppercase tracking-wider font-medium">Pages Discovered</div>
                      <div className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-1">
                        {graphData.total_pages}
                      </div>
                    </div>
                    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
                      <div className="text-xs text-gray-500 uppercase tracking-wider font-medium">Transitions / Edges</div>
                      <div className="text-2xl font-bold text-indigo-600 dark:text-indigo-400 mt-1">
                        {graphData.total_transitions}
                      </div>
                    </div>
                    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
                      <div className="text-xs text-gray-500 uppercase tracking-wider font-medium">Forms Detected</div>
                      <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-1">
                        {Object.values(graphData.nodes || {}).reduce((acc, n) => acc + (n.forms?.length || 0), 0)}
                      </div>
                    </div>
                    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
                      <div className="text-xs text-gray-500 uppercase tracking-wider font-medium">Interactive Elements</div>
                      <div className="text-2xl font-bold text-amber-600 dark:text-amber-400 mt-1">
                        {Object.values(graphData.nodes || {}).reduce((acc, n) => acc + (n.interactive_elements?.length || 0), 0)}
                      </div>
                    </div>
                  </div>

                  <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
                    <div className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-3">
                      Discovered Pages & Route Nodes
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {Object.values(graphData.nodes).map((node) => {
                        const isSelected = node.normalized_url === selectedNodeUrl;
                        const pathOnly = new URL(node.url, 'http://localhost').pathname;
                        return (
                          <button
                            key={node.id}
                            onClick={() => setSelectedNodeUrl(node.normalized_url)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all flex items-center gap-1.5 ${
                              isSelected
                                ? 'bg-indigo-600 text-white font-medium shadow-sm'
                                : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
                            }`}
                          >
                            <span>{pathOnly || '/'}</span>
                            <span className={`text-[10px] px-1 py-0.2 rounded ${isSelected ? 'bg-indigo-700 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400'}`}>
                              d:{node.depth}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {selectedNode && (
                    <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-6 space-y-6">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-gray-200 dark:border-gray-800 pb-4">
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100">
                              {selectedNode.title || 'Untitled Page'}
                            </h3>
                            <span className="text-xs px-2 py-0.5 rounded font-mono bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-300">
                              HTTP {selectedNode.status_code || 200}
                            </span>
                          </div>
                          <div className="text-xs text-gray-500 font-mono mt-1 flex items-center gap-1.5">
                            <Globe className="w-3.5 h-3.5" />
                            {selectedNode.url}
                          </div>
                        </div>
                        <div className="text-xs text-gray-500 font-mono">
                          Fingerprint: {selectedNode.state_fingerprint}
                        </div>
                      </div>

                      {/* Forms Breakdown */}
                      <div>
                        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
                          <FileText className="w-4 h-4 text-emerald-500" />
                          Discovered Form Schemas ({selectedNode.forms?.length || 0})
                        </h4>
                        {(!selectedNode.forms || selectedNode.forms.length === 0) ? (
                          <div className="text-xs text-gray-400 bg-gray-50 dark:bg-gray-800/40 p-4 rounded-lg">
                            No forms detected on this page.
                          </div>
                        ) : (
                          <div className="space-y-3">
                            {selectedNode.forms.map((form, idx) => (
                              <div
                                key={idx}
                                className="border border-gray-200 dark:border-gray-800 rounded-lg p-4 bg-gray-50/50 dark:bg-gray-800/30"
                              >
                                <div className="flex items-center justify-between mb-2">
                                  <span className="font-mono text-xs font-semibold text-gray-800 dark:text-gray-200">
                                    {form.form_id} ({form.method} {form.action || ''})
                                  </span>
                                  {form.is_destructive ? (
                                    <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-300 font-medium">
                                      <AlertTriangle className="w-3 h-3" />
                                      Destructive Form (Skipped)
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-300 font-medium">
                                      <ShieldCheck className="w-3 h-3" />
                                      Safe Form
                                    </span>
                                  )}
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 mt-2">
                                  {form.fields.map((f, fIdx) => (
                                    <div
                                      key={fIdx}
                                      className="text-xs bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-2 rounded"
                                    >
                                      <div className="font-medium text-gray-800 dark:text-gray-200 truncate">
                                        {f.name || f.selector}
                                      </div>
                                      <div className="text-[10px] text-gray-400 mt-0.5">
                                        Type: {f.field_type} {f.required ? '· Required' : ''}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}
            </>
          )}

          {/* TAB 2: REQUIREMENTS PLANNER */}
          {viewTab === 'planner' && (
            <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-6 space-y-6">
              <div>
                <h3 className="text-base font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                  <Target className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                  Requirements-Driven Test Planner
                </h3>
                <p className="text-xs text-gray-500 mt-1">
                  Enter natural language user stories or requirements. Tracecase maps intent to discovered navigation graph nodes, identifies coverage gaps, and generates verified test drafts.
                </p>
              </div>

              <form onSubmit={handlePlanRequirement} className="space-y-3">
                <textarea
                  rows={3}
                  value={requirementText}
                  onChange={(e) => setRequirementText(e.target.value)}
                  placeholder="e.g. As a user, I want to open settings and update my profile display name"
                  className="w-full px-3.5 py-2.5 border border-gray-300 dark:border-gray-700 rounded-lg bg-transparent text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />

                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-1.5 text-xs text-gray-500">
                    <span className="font-medium">Quick examples:</span>
                    <button
                      type="button"
                      onClick={() => setRequirementText('As a user, I want to open settings and update my profile email')}
                      className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-gray-700 dark:text-gray-300 hover:bg-gray-200"
                    >
                      Update Profile
                    </button>
                    <button
                      type="button"
                      onClick={() => setRequirementText('As a user, I want to navigate to dashboard and refresh metrics')}
                      className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-gray-700 dark:text-gray-300 hover:bg-gray-200"
                    >
                      Dashboard Flow
                    </button>
                    <button
                      type="button"
                      onClick={() => setRequirementText('As a user, I want to search catalog for items and complete checkout')}
                      className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-gray-700 dark:text-gray-300 hover:bg-gray-200"
                    >
                      Search & Checkout (Gap Demo)
                    </button>
                  </div>

                  <button
                    type="submit"
                    disabled={planningRequirement || !selectedRunId}
                    className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors"
                  >
                    {planningRequirement ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                    {planningRequirement ? 'Mapping to Graph...' : 'Map & Plan Test'}
                  </button>
                </div>
              </form>

              {/* Plan Results Display */}
              {planResult && (
                <div className="border border-gray-200 dark:border-gray-800 rounded-xl p-5 space-y-5 bg-gray-50/40 dark:bg-gray-800/20">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-gray-200 dark:border-gray-800 pb-3">
                    <div>
                      <span className="text-xs uppercase tracking-wider text-gray-500 font-semibold">Requirement Coverage Score</span>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
                          {Math.round(planResult.coverage_score * 100)}%
                        </span>
                        <div className="w-36 bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                          <div
                            className="bg-indigo-600 h-2 rounded-full transition-all"
                            style={{ width: `${Math.round(planResult.coverage_score * 100)}%` }}
                          />
                        </div>
                      </div>
                    </div>
                    <div className="text-right text-xs text-gray-500 font-mono">
                      Engine: {planResult.provider_used}
                    </div>
                  </div>

                  {/* Covered vs Missing Concepts */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    <div>
                      <span className="font-semibold text-green-700 dark:text-green-300 flex items-center gap-1.5 mb-2">
                        <CheckCircle2 className="w-4 h-4 text-green-500" />
                        Verified In Graph ({planResult.covered_concepts?.length || 0})
                      </span>
                      {planResult.covered_concepts?.length === 0 ? (
                        <div className="text-gray-400">No concepts matched directly in graph.</div>
                      ) : (
                        <div className="flex flex-wrap gap-1.5">
                          {planResult.covered_concepts.map((c, i) => (
                            <span key={i} className="px-2 py-0.5 rounded bg-green-100 dark:bg-green-950 text-green-800 dark:text-green-300 font-mono">
                              ✓ {c}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    <div>
                      <span className="font-semibold text-amber-700 dark:text-amber-300 flex items-center gap-1.5 mb-2">
                        <AlertTriangle className="w-4 h-4 text-amber-500" />
                        Coverage Gaps & Missing Evidence ({planResult.missing_concepts?.length || 0})
                      </span>
                      {planResult.missing_concepts?.length === 0 ? (
                        <div className="text-gray-400">All requirement concepts are covered!</div>
                      ) : (
                        <div className="space-y-1.5">
                          {planResult.missing_concepts.map((g, i) => (
                            <div key={i} className="p-2 rounded bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/60">
                              <span className="font-mono font-semibold text-amber-800 dark:text-amber-300">
                                {g.concept}
                              </span>
                              <p className="text-[11px] text-amber-700 dark:text-amber-400 mt-0.5">{g.reason}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Generated Draft Link */}
                  {planResult.synthesized_draft && (
                    <div className="bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-800/60 rounded-lg p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div>
                        <div className="font-semibold text-sm text-gray-900 dark:text-gray-100">
                          {planResult.synthesized_draft.name}
                        </div>
                        <div className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">
                          {planResult.synthesized_draft.steps?.length || 0} steps synthesized from observed routes
                        </div>
                      </div>
                      <button
                        onClick={() => {
                          setSelectedDraftId(planResult.synthesized_draft.id);
                          setViewTab('review');
                        }}
                        className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold transition-colors"
                      >
                        Inspect in Review Queue <ArrowRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* TAB 3: HUMAN REVIEW QUEUE */}
          {viewTab === 'review' && (
            <div className="space-y-6">
              {loadingDrafts ? (
                <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-12 text-center text-gray-500">
                  <Loader2 className="w-8 h-8 mx-auto animate-spin text-indigo-600 mb-2" />
                  Loading synthesized test drafts...
                </div>
              ) : drafts.length === 0 ? (
                <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-12 text-center">
                  <Sparkles className="w-12 h-12 text-purple-400 mx-auto mb-3" />
                  <h3 className="text-base font-medium text-gray-900 dark:text-gray-100">
                    No Test Journey Drafts in Queue
                  </h3>
                  <p className="text-sm text-gray-500 mt-1 max-w-sm mx-auto mb-4">
                    Synthesize deterministic user journeys from the navigation graph or map a requirement to generate review drafts.
                  </p>
                  <button
                    onClick={handleSynthesizeJourneys}
                    disabled={synthesizing}
                    className="inline-flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium shadow-sm transition-colors"
                  >
                    {synthesizing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                    {synthesizing ? 'Synthesizing...' : 'Synthesize Test Journeys Now'}
                  </button>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {/* Drafts List Column */}
                  <div className="md:col-span-1 space-y-2">
                    <div className="text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
                      Synthesized Journeys ({drafts.length})
                    </div>
                    {drafts.map((d) => {
                      const isSelected = d.id === selectedDraftId;
                      return (
                        <div
                          key={d.id}
                          onClick={() => setSelectedDraftId(d.id)}
                          className={`p-3 rounded-lg border text-left cursor-pointer transition-all ${
                            isSelected
                              ? 'border-indigo-500 bg-indigo-50/50 dark:bg-indigo-950/30'
                              : 'border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/60'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-1 mb-1">
                            <span className="text-xs font-semibold text-gray-900 dark:text-gray-100 truncate">
                              {d.name}
                            </span>
                            <span
                              className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                                d.status === 'approved'
                                  ? 'bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-300'
                                  : d.status === 'rejected'
                                  ? 'bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-300'
                                  : 'bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300'
                              }`}
                            >
                              {d.status === 'approved' ? '✓ Approved' : d.status === 'rejected' ? '✗ Rejected' : 'Draft'}
                            </span>
                          </div>
                          <div className="text-[11px] text-gray-500 flex items-center justify-between mt-1">
                            <span className="capitalize">{d.journey_type.replace('_', ' ')}</span>
                            <span>{d.steps?.length || 0} steps</span>
                          </div>
                          {d.requires_human_input && d.status === 'pending' && (
                            <div className="text-[10px] text-amber-600 dark:text-amber-400 mt-1 flex items-center gap-1 font-medium">
                              <AlertCircle className="w-3 h-3" /> Needs Human Review
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {/* Draft Detail & Approval Column */}
                  <div className="md:col-span-2">
                    {selectedDraft ? (
                      <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-6 space-y-6">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-gray-200 dark:border-gray-800 pb-4">
                          <div>
                            <div className="flex items-center gap-2">
                              <h3 className="text-base font-bold text-gray-900 dark:text-gray-100">
                                {selectedDraft.name}
                              </h3>
                              <span className="text-[11px] px-2 py-0.5 rounded font-medium bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 uppercase">
                                {selectedDraft.journey_type}
                              </span>
                            </div>
                            <p className="text-xs text-gray-500 mt-1">{selectedDraft.description}</p>
                          </div>

                          {/* Approval Actions */}
                          {selectedDraft.status === 'pending' ? (
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => handleRejectDraft(selectedDraft.id)}
                                disabled={processingDraftId === selectedDraft.id}
                                className="px-3 py-1.5 border border-red-300 dark:border-red-800 text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40 rounded-lg text-xs font-medium transition-colors"
                              >
                                Reject
                              </button>
                              <button
                                onClick={() => handleApproveDraft(selectedDraft.id)}
                                disabled={processingDraftId === selectedDraft.id}
                                className="flex items-center gap-1.5 px-4 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded-lg text-xs font-medium shadow-sm transition-colors"
                              >
                                {processingDraftId === selectedDraft.id ? (
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                ) : (
                                  <Check className="w-3.5 h-3.5" />
                                )}
                                Approve Test Case
                              </button>
                            </div>
                          ) : selectedDraft.status === 'approved' ? (
                            <div className="flex items-center gap-1.5 px-3 py-1 bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-300 rounded-lg text-xs font-medium">
                              <CheckCircle2 className="w-4 h-4" />
                              Approved into Suite
                            </div>
                          ) : (
                            <div className="flex items-center gap-1.5 px-3 py-1 bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-300 rounded-lg text-xs font-medium">
                              <XCircle className="w-4 h-4" />
                              Rejected: {selectedDraft.rejection_reason || 'Rejected'}
                            </div>
                          )}
                        </div>

                        {selectedDraft.requires_human_input && (
                          <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/60 rounded-lg p-3 text-xs text-amber-800 dark:text-amber-300 flex items-start gap-2">
                            <AlertCircle className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
                            <div>
                              <strong>Evidence Guardrail:</strong> This journey contains form submission or state changes where the final outcome cannot be proven from exploration evidence alone. Review the flagged assertions before approval.
                            </div>
                          </div>
                        )}

                        {/* Steps Timeline & Assertions */}
                        <div className="space-y-4">
                          <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                            Synthesized Steps & Provenance Evidence ({selectedDraft.steps?.length || 0})
                          </h4>

                          <div className="space-y-3">
                            {(selectedDraft.steps || []).map((step) => (
                              <div
                                key={step.number}
                                className="border border-gray-200 dark:border-gray-800 rounded-lg p-3.5 bg-gray-50/40 dark:bg-gray-800/20 space-y-2"
                              >
                                <div className="flex items-center justify-between text-xs">
                                  <div className="flex items-center gap-2">
                                    <span className="w-5 h-5 rounded-full bg-indigo-100 dark:bg-indigo-900 text-indigo-700 dark:text-indigo-300 flex items-center justify-center font-bold text-[11px]">
                                      {step.number}
                                    </span>
                                    <span className="font-semibold text-gray-900 dark:text-gray-100">
                                      {step.description_short}
                                    </span>
                                    <span className="font-mono text-[11px] px-1.5 py-0.2 bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded">
                                      {step.action_type}
                                    </span>
                                  </div>
                                </div>

                                <div className="text-[11px] text-gray-500 font-mono">
                                  {step.url || step.selector}
                                  {step.input_value && ` · Value: "${step.input_value}"`}
                                </div>

                                {/* Step Assertions */}
                                {step.assertions && step.assertions.length > 0 && (
                                  <div className="pt-2 border-t border-gray-200 dark:border-gray-800 space-y-1.5">
                                    <div className="text-[10px] uppercase font-semibold text-gray-400">
                                      Attached Assertions:
                                    </div>
                                    {step.assertions.map((ast, aIdx) => (
                                      <div
                                        key={aIdx}
                                        className={`text-xs p-2 rounded flex items-center justify-between ${
                                          ast.requires_human_input
                                            ? 'bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300'
                                            : 'bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800 text-green-800 dark:text-green-300'
                                        }`}
                                      >
                                        <div className="flex items-center gap-2">
                                          {ast.requires_human_input ? (
                                            <AlertCircle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
                                          ) : (
                                            <CheckCircle2 className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
                                          )}
                                          <div>
                                            <span className="font-mono font-medium">{ast.assertion_type}</span>
                                            {ast.expected_value !== null && ast.expected_value !== undefined && (
                                              <span className="font-mono text-[11px] ml-1.5 text-gray-600 dark:text-gray-300">
                                                == "{ast.expected_value}"
                                              </span>
                                            )}
                                            {ast.review_prompt && (
                                              <div className="text-[10px] text-amber-700 dark:text-amber-400 mt-0.5">
                                                Prompt: {ast.review_prompt}
                                              </div>
                                            )}
                                          </div>
                                        </div>
                                        <span className="text-[10px] uppercase tracking-wider font-semibold">
                                          {ast.requires_human_input ? 'Review Req' : 'Evidence'}
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="text-center py-12 text-gray-400">
                        Select a synthesized journey draft to inspect steps and evidence.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 4: INTELLIGENT REGRESSION SELECTOR */}
          {viewTab === 'regression' && (
            <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-6 space-y-6">
              <div>
                <h3 className="text-base font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                  <GitBranch className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                  Intelligent Regression Test Selection
                </h3>
                <p className="text-xs text-gray-500 mt-1">
                  Specify changed page routes and modified DOM selectors. Tracecase analyzes step interactions and recent failure history to prioritize the most critical regression tests.
                </p>
              </div>

              <form onSubmit={handleSelectRegression} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                    Changed Routes (comma-separated)
                  </label>
                  <input
                    type="text"
                    value={changedRoutesInput}
                    onChange={(e) => setChangedRoutesInput(e.target.value)}
                    placeholder="/settings, /profile, /dashboard"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-transparent text-sm font-mono"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                    Changed Selectors (comma-separated)
                  </label>
                  <input
                    type="text"
                    value={changedSelectorsInput}
                    onChange={(e) => setChangedSelectorsInput(e.target.value)}
                    placeholder="#input-email, #btn-save-profile"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-transparent text-sm font-mono"
                  />
                </div>

                <div className="sm:col-span-2 flex justify-end">
                  <button
                    type="submit"
                    disabled={analyzingRegression}
                    className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors"
                  >
                    {analyzingRegression ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Filter className="w-3.5 h-3.5" />}
                    {analyzingRegression ? 'Analyzing Impact...' : 'Select Regression Tests'}
                  </button>
                </div>
              </form>

              {/* Regression Results Table */}
              {regressionResult && (
                <div className="space-y-4">
                  <div className="bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-800/60 rounded-lg p-3.5 flex items-center justify-between text-xs text-indigo-900 dark:text-indigo-200">
                    <span>{regressionResult.explanation}</span>
                    <span className="font-bold text-sm">
                      {regressionResult.recommended_count} Recommended Tests
                    </span>
                  </div>

                  <div className="border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
                        <tr>
                          <th className="p-3 font-medium">Priority</th>
                          <th className="p-3 font-medium">Test Case</th>
                          <th className="p-3 font-medium">Risk Score</th>
                          <th className="p-3 font-medium">Impact Reasons</th>
                          <th className="p-3 font-medium">Affected Steps</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100 dark:divide-gray-800 text-xs">
                        {regressionResult.ranked_testcases?.map((c) => (
                          <tr key={c.testcase_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/40">
                            <td className="p-3">
                              <span
                                className={`text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider ${
                                  c.priority === 'critical'
                                    ? 'bg-red-100 dark:bg-red-950 text-red-700 dark:text-red-300'
                                    : c.priority === 'high'
                                    ? 'bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-300'
                                    : 'bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300'
                                }`}
                              >
                                {c.priority}
                              </span>
                            </td>
                            <td className="p-3 font-semibold text-gray-900 dark:text-gray-100">
                              {c.testcase_name}
                            </td>
                            <td className="p-3 font-mono font-bold text-indigo-600 dark:text-indigo-400">
                              {c.risk_score}
                            </td>
                            <td className="p-3 text-gray-600 dark:text-gray-400 max-w-xs">
                              {c.reasons?.length > 0 ? c.reasons.join(' · ') : 'General regression candidate'}
                            </td>
                            <td className="p-3 font-mono text-gray-500">
                              {c.affected_steps?.length > 0 ? `Steps ${c.affected_steps.join(', ')}` : '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* New Exploration Modal */}
      {showNewModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-gray-200 dark:border-gray-800 pb-3">
              <h3 className="text-base font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
                <Compass className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                Configure Autonomous Exploration
              </h3>
              <button
                onClick={() => setShowNewModal(false)}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleStartExploration} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                  Start URL
                </label>
                <input
                  type="url"
                  required
                  value={startUrl}
                  onChange={(e) => setStartUrl(e.target.value)}
                  placeholder="http://localhost:8000/"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-transparent text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                    Max Depth
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="8"
                    value={maxDepth}
                    onChange={(e) => setMaxDepth(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-transparent text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                    Max Pages
                  </label>
                  <input
                    type="number"
                    min="2"
                    max="100"
                    value={maxPages}
                    onChange={(e) => setMaxPages(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-transparent text-sm"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                    Max Interactions
                  </label>
                  <input
                    type="number"
                    min="5"
                    max="200"
                    value={maxInteractions}
                    onChange={(e) => setMaxInteractions(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-transparent text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                    Timeout (Seconds)
                  </label>
                  <input
                    type="number"
                    min="10"
                    max="600"
                    value={timeoutSecs}
                    onChange={(e) => setTimeoutSecs(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-transparent text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                  Browser Engine
                </label>
                <select
                  value={browserType}
                  onChange={(e) => setBrowserType(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-sm"
                >
                  <option value="chromium">Chromium</option>
                  <option value="firefox">Firefox</option>
                  <option value="webkit">WebKit</option>
                </select>
              </div>

              {/* Safety notice */}
              <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/60 rounded-lg p-3 text-xs text-amber-800 dark:text-amber-300 flex items-start gap-2">
                <ShieldCheck className="w-4 h-4 text-amber-600 mt-0.5 flex-shrink-0" />
                <span>
                  <strong>Safety Guardrails Active:</strong> Navigation is constrained strictly to the target origin. Destructive actions (payment, delete, purchase, publish) are automatically flagged and skipped.
                </span>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-gray-200 dark:border-gray-800">
                <button
                  type="button"
                  onClick={() => setShowNewModal(false)}
                  className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={starting}
                  className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium shadow-sm transition-colors"
                >
                  {starting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                  {starting ? 'Launching...' : 'Start Exploring'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
export default AutonomousExploration;
