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
      if (urls.length > 0 && !selectedNodeUrl) {
        setSelectedNodeUrl(urls[0]);
      } else if (urls.length > 0 && !g.nodes[selectedNodeUrl]) {
        setSelectedNodeUrl(urls[0]);
      }
    } catch (err) {
      showToast(err.message || 'Failed loading navigation graph', 'error');
    } finally {
      setLoadingGraph(false);
    }
  };

  useEffect(() => {
    loadRuns();
  }, []);

  useEffect(() => {
    if (selectedRunId) {
      loadGraph(selectedRunId);
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
      }
      loadRuns();
    } catch (err) {
      showToast(err.message || 'Failed to delete exploration run', 'error');
    }
  };

  const selectedNode = graphData?.nodes?.[selectedNodeUrl] || null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-200 dark:border-gray-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <Compass className="w-7 h-7 text-indigo-600 dark:text-indigo-400" />
            Autonomous Exploration
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Explore application state spaces, map interactive surfaces, and build navigation graphs.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              loadRuns();
              if (selectedRunId) loadGraph(selectedRunId);
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

      {/* Main Grid: Runs Selector & Graph Explorer */}
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

        {/* Right Column: Navigation Graph & Page Surface Inspector */}
        <div className="lg:col-span-3 space-y-6">
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
              {/* Summary Metrics Row */}
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

              {/* Page Nodes Selector Tabs */}
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

              {/* Selected Page Node Detail */}
              {selectedNode && (
                <div className="bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl p-6 space-y-6">
                  {/* Node Header */}
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

                            {form.is_destructive && (
                              <p className="text-xs text-red-600 dark:text-red-400 mb-2">
                                Guardrail: {form.destructive_reason}
                              </p>
                            )}

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

                  {/* Interactive Elements Surface */}
                  <div>
                    <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
                      <Layers className="w-4 h-4 text-indigo-500" />
                      Interactive DOM Elements ({selectedNode.interactive_elements?.length || 0})
                    </h4>
                    <div className="max-h-64 overflow-y-auto border border-gray-200 dark:border-gray-800 rounded-lg divide-y divide-gray-100 dark:divide-gray-800">
                      {(selectedNode.interactive_elements || []).map((el, elIdx) => (
                        <div
                          key={elIdx}
                          className="p-3 text-xs flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-800/40"
                        >
                          <div className="space-y-0.5 max-w-[70%]">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-indigo-600 dark:text-indigo-400 font-medium">
                                &lt;{el.tag_name}&gt;
                              </span>
                              <span className="text-gray-800 dark:text-gray-200 truncate">
                                {el.text || el.aria_label || el.name || 'unnamed'}
                              </span>
                            </div>
                            <div className="font-mono text-[11px] text-gray-400 truncate">
                              {el.selector}
                            </div>
                          </div>
                          <div>
                            {el.is_destructive ? (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-950 text-red-600 dark:text-red-300">
                                Destructive
                              </span>
                            ) : (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
                                Safe
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Outbound Transitions Table */}
                  <div>
                    <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
                      <ArrowRight className="w-4 h-4 text-indigo-500" />
                      State Transitions from this Page
                    </h4>
                    {(() => {
                      const transitions = (graphData.transitions || []).filter(
                        (t) => t.source_url === selectedNode.normalized_url
                      );
                      if (transitions.length === 0) {
                        return (
                          <div className="text-xs text-gray-400 bg-gray-50 dark:bg-gray-800/40 p-4 rounded-lg">
                            No outbound transitions recorded from this page.
                          </div>
                        );
                      }
                      return (
                        <div className="border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden">
                          <table className="w-full text-left text-xs">
                            <thead className="bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
                              <tr>
                                <th className="p-2.5 font-medium">Action</th>
                                <th className="p-2.5 font-medium">Target Page</th>
                                <th className="p-2.5 font-medium">Selector / Element</th>
                                <th className="p-2.5 font-medium">Latency</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100 dark:divide-gray-800 font-mono text-[11px]">
                              {transitions.map((t, idx) => (
                                <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-800/40">
                                  <td className="p-2.5 font-semibold text-indigo-600 dark:text-indigo-400">
                                    {t.action_type}
                                  </td>
                                  <td className="p-2.5 text-gray-900 dark:text-gray-200 truncate max-w-[200px]">
                                    {t.target_url}
                                  </td>
                                  <td className="p-2.5 text-gray-500 truncate max-w-[200px]">
                                    {t.selector || t.element_text || '-'}
                                  </td>
                                  <td className="p-2.5 text-gray-400">
                                    {Math.round(t.duration_ms)}ms
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      );
                    })()}
                  </div>
                </div>
              )}
            </>
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
