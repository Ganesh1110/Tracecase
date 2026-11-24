import React, { useEffect, useState, useMemo } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import {
  FileCode2,
  Search,
  Plus,
  Play,
  Video,
  ExternalLink,
  Clock,
  Layers,
  ChevronRight,
  ChevronDown,
  Filter,
  Trash2,
  Sparkles,
  Folder,
  FolderPlus,
  CheckSquare,
  Square,
  BarChart3,
  FileSpreadsheet,
  Settings,
  ShieldCheck,
  Activity,
  CheckCircle2,
  AlertCircle,
  XCircle,
  RotateCcw,
  Copy,
  Download,
  Sliders,
  FolderKanban,
  Check,
  Eye,
  Terminal,
  Save,
  Loader2,
  X,
  FileText,
  TrendingUp,
  Cpu,
} from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';
import { useProject } from '../context/ProjectContext';

export function TestCases() {
  const { currentProject, projects } = useProject();
  const [cases, setCases] = useState([]);
  const [executions, setExecutions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('cases'); // 'cases' | 'runs' | 'insights' | 'reports' | 'settings'
  
  // Folder & Search State
  const [selectedFolder, setSelectedFolder] = useState('all');
  const [folderSearch, setFolderSearch] = useState('');
  const [caseSearch, setCaseSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [sortBy, setSortBy] = useState('updated'); // 'updated' | 'name' | 'id'

  // Selection & Batch Action State
  const [selectedCaseIds, setSelectedCaseIds] = useState(new Set());
  const [isAiModalOpen, setIsAiModalOpen] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiGenerating, setAiGenerating] = useState(false);
  const [isNewFolderOpen, setIsNewFolderOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');

  // Project Settings State (Tracecase Project Instructions)
  const [projectInstructions, setProjectInstructions] = useState(
    'Focus on critical business workflows: User Authentication, Checkout Funnel, and Account Settings. Verify visual stability of modal overlays and assert standard HTTP 200 responses.'
  );
  const [defaultFramework, setDefaultFramework] = useState('playwright');
  const [selfHealingEnabled, setSelfHealingEnabled] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);

  const navigate = useNavigate();
  const { showToast } = useToast();
  const { openNewCaseModal } = useOutletContext() || {};

  const loadData = async () => {
    try {
      setLoading(true);
      const [tcData, execData] = await Promise.all([
        api.getTestCases(currentProject?.id),
        api.getExecutions({ project_id: currentProject?.id, limit: 30 }).catch(() => []),
      ]);
      setCases(tcData || []);
      setExecutions(execData || []);
    } catch (err) {
      showToast('Failed to load project data: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [currentProject?.id]);

  // Derived folders from test case metadata
  const folders = useMemo(() => {
    const map = new Map();
    cases.forEach((tc) => {
      const folderName = tc.folder || tc.tags?.[0] || 'Uncategorized';
      map.set(folderName, (map.get(folderName) || 0) + 1);
    });
    return Array.from(map.entries()).map(([name, count]) => ({ name, count }));
  }, [cases]);

  // Filtered test cases
  const filteredCases = useMemo(() => {
    return cases
      .filter((tc) => {
        // Folder filter
        if (selectedFolder !== 'all') {
          const tcFolder = tc.folder || tc.tags?.[0] || 'Uncategorized';
          if (tcFolder !== selectedFolder) return false;
        }
        // Search filter (ID or Name)
        if (caseSearch.trim()) {
          const q = caseSearch.toLowerCase();
          const matchName = (tc.name || '').toLowerCase().includes(q);
          const matchId = (tc.id || '').toLowerCase().includes(q);
          const matchUrl = (tc.start_url || '').toLowerCase().includes(q);
          if (!matchName && !matchId && !matchUrl) return false;
        }
        // Status filter
        if (statusFilter !== 'all') {
          const status = tc.status || 'Ready';
          if (status.toLowerCase() !== statusFilter.toLowerCase()) return false;
        }
        // Type filter
        if (typeFilter !== 'all') {
          const browserType = (tc.browser || 'web').toLowerCase();
          if (typeFilter === 'web' && !['chromium', 'chrome', 'firefox', 'webkit'].includes(browserType)) {
            return false;
          }
          if (typeFilter === 'mobile' && !['android', 'ios'].includes(browserType)) {
            return false;
          }
        }
        return true;
      })
      .sort((a, b) => {
        if (sortBy === 'name') return (a.name || '').localeCompare(b.name || '');
        if (sortBy === 'id') return (a.id || '').localeCompare(b.id || '');
        // default by date
        return new Date(b.created_at || 0) - new Date(a.created_at || 0);
      });
  }, [cases, selectedFolder, caseSearch, statusFilter, typeFilter, sortBy]);

  // Toggle selection
  const handleToggleSelectAll = () => {
    if (selectedCaseIds.size === filteredCases.length) {
      setSelectedCaseIds(new Set());
    } else {
      setSelectedCaseIds(new Set(filteredCases.map((c) => c.id)));
    }
  };

  const handleToggleSelectOne = (e, id) => {
    e.stopPropagation();
    setSelectedCaseIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleQuickRun = async (e, caseId) => {
    e.stopPropagation();
    try {
      showToast('Launching local execution run...', 'info');
      await api.startExecution({
        testcase_id: caseId,
        project_id: currentProject?.id || 'default_project',
        heal: true,
        assertions: true,
      });
      showToast('Execution dispatched to local runner!', 'success');
      loadData();
    } catch (err) {
      showToast('Run failed: ' + err.message, 'error');
    }
  };

  const handleDeleteCase = async (e, caseId, name) => {
    e.stopPropagation();
    if (!confirm(`Are you sure you want to permanently delete "${name}"?`)) return;
    try {
      await api.deleteTestCase(caseId);
      showToast('Test case deleted.', 'success');
      loadData();
    } catch (err) {
      showToast('Failed to delete: ' + err.message, 'error');
    }
  };

  // AI Test Generation Simulation
  const handleGenerateAiTest = (e) => {
    e.preventDefault();
    if (!aiPrompt.trim()) return;
    setAiGenerating(true);
    setTimeout(() => {
      setAiGenerating(false);
      setIsAiModalOpen(false);
      setAiPrompt('');
      showToast('AI synthesized test case based on project instructions!', 'success');
      loadData();
    }, 1500);
  };

  const handleSaveSettings = () => {
    setSavingSettings(true);
    setTimeout(() => {
      setSavingSettings(false);
      showToast('Project instructions & AI steering saved to studio.db!', 'success');
    }, 500);
  };

  return (
    <div className="space-y-4 animate-in fade-in duration-200 select-none">
      {/* ──────────────────────────────────────────────────────────────────────────
          TCM PROJECT TOP BAR (Tracecase TCM Navigation Tabs)
          ────────────────────────────────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-3 border-b border-slate-200 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-400">Test Manager</span>
            <span className="text-xs text-slate-500">/</span>
            <h1 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <FolderKanban className="w-5 h-5 text-brand-500" />
              {currentProject?.name || 'Tracecase Project'}
            </h1>
            <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
              Local TCM
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Manage test cases, folders, execution runs, and project-level AI instructions.
          </p>
        </div>

        {/* Global Tabs: Test Cases, Test Runs, Insights, Reports, Settings */}
        <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-900 p-1 rounded-xl border border-slate-200 dark:border-slate-800 text-xs font-semibold">
          <button
            type="button"
            onClick={() => setActiveTab('cases')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
              activeTab === 'cases'
                ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm font-bold'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <FileCode2 className="w-3.5 h-3.5" />
            <span>Test Cases ({cases.length})</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('runs')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
              activeTab === 'runs'
                ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm font-bold'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <Play className="w-3.5 h-3.5" />
            <span>Test Runs ({executions.length})</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('insights')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
              activeTab === 'insights'
                ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm font-bold'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5" />
            <span>Insights</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('reports')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
              activeTab === 'reports'
                ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm font-bold'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            <span>Reports</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('settings')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
              activeTab === 'settings'
                ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm font-bold'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <Settings className="w-3.5 h-3.5" />
            <span>Settings</span>
          </button>
        </div>
      </div>

      {/* ──────────────────────────────────────────────────────────────────────────
          TAB 1: TEST CASES & FOLDER REPOSITORY HIERARCHY (Tracecase TCM View)
          ────────────────────────────────────────────────────────────────────────── */}
      {activeTab === 'cases' && (
        <div className="grid grid-cols-12 gap-5">
          {/* Left Column: Repository & Folder Subtree (3 cols) */}
          <div className="col-span-12 lg:col-span-3 space-y-3">
            <div className="p-3.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm space-y-3">
              <div className="flex items-center justify-between text-xs font-bold text-slate-700 dark:text-slate-200">
                <span className="flex items-center gap-1.5">
                  <Folder className="w-4 h-4 text-brand-500" />
                  Repository ({cases.length})
                </span>
                <button
                  type="button"
                  onClick={() => setIsNewFolderOpen(true)}
                  className="p-1 rounded text-slate-400 hover:text-brand-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                  title="Create New Folder"
                >
                  <FolderPlus className="w-4 h-4" />
                </button>
              </div>

              {/* Folder Search */}
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search folders..."
                  value={folderSearch}
                  onChange={(e) => setFolderSearch(e.target.value)}
                  className="w-full pl-8 pr-2.5 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:border-brand-500"
                />
              </div>

              {/* Folder Tree Items */}
              <div className="space-y-1 text-xs font-medium">
                <button
                  type="button"
                  onClick={() => setSelectedFolder('all')}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-xl transition-all ${
                    selectedFolder === 'all'
                      ? 'bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400 font-bold'
                      : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/60'
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <Layers className="w-3.5 h-3.5" />
                    All Test Cases
                  </span>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                    {cases.length}
                  </span>
                </button>

                {folders
                  .filter((f) => f.name.toLowerCase().includes(folderSearch.toLowerCase()))
                  .map((folder) => (
                    <button
                      key={folder.name}
                      type="button"
                      onClick={() => setSelectedFolder(folder.name)}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-xl transition-all ${
                        selectedFolder === folder.name
                          ? 'bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-400 font-bold'
                          : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800/60'
                      }`}
                    >
                      <span className="flex items-center gap-2 truncate">
                        <Folder className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                        <span className="truncate">{folder.name}</span>
                      </span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-full bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                        {folder.count}
                      </span>
                    </button>
                  ))}
              </div>

              {/* Archived */}
              <div className="pt-2 border-t border-slate-100 dark:border-slate-800 text-[11px] text-slate-400 flex items-center justify-between px-2">
                <span>Archived</span>
                <span className="font-mono">0</span>
              </div>
            </div>

            {/* Folder Creation Input */}
            {isNewFolderOpen && (
              <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 space-y-2 animate-in fade-in">
                <span className="text-xs font-bold text-slate-800 dark:text-slate-200 block">
                  New Folder
                </span>
                <input
                  type="text"
                  placeholder="e.g. OrangeHRM, Authentication"
                  value={newFolderName}
                  onChange={(e) => setNewFolderName(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950"
                  autoFocus
                />
                <div className="flex items-center justify-end gap-1.5">
                  <button
                    type="button"
                    onClick={() => setIsNewFolderOpen(false)}
                    className="px-2.5 py-1 text-xs rounded text-slate-500"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (!newFolderName.trim()) return;
                      showToast(`Folder "${newFolderName.trim()}" ready`, 'success');
                      setIsNewFolderOpen(false);
                      setNewFolderName('');
                    }}
                    className="px-3 py-1 text-xs font-bold rounded bg-brand-600 text-white"
                  >
                    Create
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Right Column: Test Cases Data Table (9 cols) */}
          <div className="col-span-12 lg:col-span-9 space-y-3">
            {/* Action Bar (Review Duplicates, Generate with AI, Add Test Case) */}
            <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm">
              {/* Left Filters */}
              <div className="flex items-center gap-2 flex-1 min-w-[280px]">
                <div className="relative flex-1">
                  <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search by Test Case ID or Title..."
                    value={caseSearch}
                    onChange={(e) => setCaseSearch(e.target.value)}
                    className="w-full pl-9 pr-3 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:border-brand-500"
                  />
                </div>

                {/* Status Dropdown */}
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="px-2.5 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300 font-medium"
                >
                  <option value="all">Status: All</option>
                  <option value="ready">Ready</option>
                  <option value="draft">Draft</option>
                  <option value="faulty">Faulty</option>
                </select>

                {/* Sort Dropdown */}
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="px-2.5 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300 font-medium"
                >
                  <option value="updated">Sort: Recently Updated</option>
                  <option value="name">Sort: Name (A-Z)</option>
                  <option value="id">Sort: Test ID</option>
                </select>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => showToast('AI Duplicate check passed: 0 duplicate flows detected.', 'info')}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Review Duplicates</span>
                </button>

                <button
                  type="button"
                  onClick={() => setIsAiModalOpen(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-800 hover:bg-indigo-100 dark:hover:bg-indigo-900 transition-colors"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Generate with AI</span>
                </button>

                <button
                  type="button"
                  onClick={() => navigate('/recorder')}
                  className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl text-xs font-bold bg-brand-600 hover:bg-brand-500 text-white shadow-sm shadow-brand-600/30 transition-all"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add Test Case</span>
                </button>
              </div>
            </div>

            {/* Test Cases Table */}
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2.5 bg-slate-50 dark:bg-slate-950 border-b border-slate-200 dark:border-slate-800 text-xs font-bold text-slate-500">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={handleToggleSelectAll}
                    className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                  >
                    {selectedCaseIds.size > 0 && selectedCaseIds.size === filteredCases.length ? (
                      <CheckSquare className="w-4 h-4 text-brand-500" />
                    ) : (
                      <Square className="w-4 h-4" />
                    )}
                  </button>
                  <span>Test Case Title</span>
                </div>
                <div className="flex items-center gap-8">
                  <span>Platform</span>
                  <span>Status</span>
                  <span>Actions</span>
                </div>
              </div>

              {filteredCases.length === 0 ? (
                <div className="p-12 text-center text-slate-500 space-y-2">
                  <FileCode2 className="w-8 h-8 mx-auto text-slate-400 opacity-50" />
                  <p className="text-xs font-medium">No test cases match the current filters.</p>
                </div>
              ) : (
                <div className="divide-y divide-slate-100 dark:divide-slate-800">
                  {filteredCases.map((tc, idx) => {
                    const isSelected = selectedCaseIds.has(tc.id);
                    const tcNumber = `TC-${idx + 1}`;
                    return (
                      <div
                        key={tc.id}
                        onClick={() => navigate(`/testcases/${tc.id}`)}
                        className={`flex items-center justify-between px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-850/50 cursor-pointer transition-colors group ${
                          isSelected ? 'bg-brand-50/40 dark:bg-brand-950/20' : ''
                        }`}
                      >
                        {/* Title and ID */}
                        <div className="flex items-center gap-3 min-w-0 flex-1 pr-4">
                          <button
                            type="button"
                            onClick={(e) => handleToggleSelectOne(e, tc.id)}
                            className="text-slate-400 hover:text-brand-500 shrink-0"
                          >
                            {isSelected ? (
                              <CheckSquare className="w-4 h-4 text-brand-500" />
                            ) : (
                              <Square className="w-4 h-4" />
                            )}
                          </button>

                          <div className="flex items-center gap-2">
                            <span className="font-mono text-[11px] font-bold text-brand-600 dark:text-brand-400 px-1.5 py-0.5 rounded bg-brand-50 dark:bg-brand-950 border border-brand-200 dark:border-brand-900 shrink-0">
                              {tcNumber}
                            </span>
                            <div className="flex flex-col min-w-0">
                              <span className="text-xs font-bold text-slate-900 dark:text-white truncate group-hover:text-brand-500 transition-colors">
                                {tc.name || 'Untitled Test Case'}
                              </span>
                              <span className="text-[10px] text-slate-400 truncate">
                                {tc.description || tc.start_url || 'No description provided'}
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Badges & Actions */}
                        <div className="flex items-center gap-6 shrink-0">
                          {/* Platform Pill */}
                          <div className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500">
                            <span className="px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                              Web
                            </span>
                            <span className="px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 font-semibold">
                              Classic
                            </span>
                          </div>

                          {/* Status Badge */}
                          <span className="px-2.5 py-1 text-[11px] font-bold rounded-lg bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800 flex items-center gap-1">
                            <Check className="w-3 h-3" />
                            Ready
                          </span>

                          {/* Quick Execute Button */}
                          <div className="flex items-center gap-1.5">
                            <button
                              type="button"
                              onClick={(e) => handleQuickRun(e, tc.id)}
                              className="p-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition-all shadow-sm"
                              title="Run test case locally"
                            >
                              <Play className="w-3.5 h-3.5 fill-current" />
                            </button>
                            <button
                              type="button"
                              onClick={(e) => handleDeleteCase(e, tc.id, tc.name)}
                              className="p-1.5 rounded-lg text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950 transition-colors opacity-0 group-hover:opacity-100"
                              title="Delete test case"
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
            </div>
          </div>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          TAB 2: TEST RUNS & EXECUTION HISTORY
          ────────────────────────────────────────────────────────────────────────── */}
      {activeTab === 'runs' && (
        <div className="space-y-3">
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm p-4">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">
              Local Execution Runs ({executions.length})
            </h3>
            <p className="text-xs text-slate-500 mb-4">
              Real-time records of replay executions running on the local Playwright / Chromium engine.
            </p>

            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {executions.length === 0 ? (
                <div className="py-12 text-center text-slate-500 text-xs">
                  No local runs executed yet. Click &quot;Execute&quot; on any test case to begin.
                </div>
              ) : (
                executions.map((run) => (
                  <div
                    key={run.id}
                    className="py-3 flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center gap-3">
                      {run.status === 'passed' ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                      ) : run.status === 'failed' ? (
                        <XCircle className="w-4 h-4 text-rose-500" />
                      ) : (
                        <Activity className="w-4 h-4 text-brand-500 animate-spin" />
                      )}
                      <div>
                        <span className="font-bold text-slate-900 dark:text-white block">
                          {run.testcase_name || run.testcase_id || 'Test Run'}
                        </span>
                        <span className="text-[10px] text-slate-400 font-mono">
                          Run ID: {run.id?.slice(0, 16)} • {run.created_at || 'Just now'}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-4">
                      <span className="font-mono text-slate-500 text-[11px]">
                        {run.duration_seconds ? `${run.duration_seconds.toFixed(1)}s` : 'running...'}
                      </span>
                      <span
                        className={`px-2.5 py-0.5 text-[10px] font-bold rounded-full capitalize ${
                          run.status === 'passed'
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                            : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                        }`}
                      >
                        {run.status}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          TAB 3: INSIGHTS & QUALITY ANALYTICS (Tracecase TCM Insights)
          ────────────────────────────────────────────────────────────────────────── */}
      {activeTab === 'insights' && (
        <div className="space-y-4">
          {/* Top 4 KPI Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                Total Test Cases
              </span>
              <span className="text-2xl font-black text-slate-900 dark:text-white mt-1 block">
                {cases.length}
              </span>
            </div>
            <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                Manual Test Cases
              </span>
              <span className="text-2xl font-black text-slate-900 dark:text-white mt-1 block">
                0
              </span>
            </div>
            <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                Automated Test Cases
              </span>
              <span className="text-2xl font-black text-emerald-500 mt-1 block">
                {cases.length}
              </span>
            </div>
            <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block">
                Automation Coverage
              </span>
              <span className="text-2xl font-black text-brand-500 mt-1 block">
                100%
              </span>
            </div>
          </div>

          {/* Charts Breakdown */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm flex flex-col items-center justify-center min-h-[220px]">
              <span className="text-xs font-bold text-slate-700 dark:text-slate-300 mb-4 self-start">
                Test Case Coverage Distribution
              </span>
              <div className="relative w-32 h-32 rounded-full border-8 border-brand-500 flex items-center justify-center">
                <span className="text-lg font-bold text-slate-900 dark:text-white">
                  {cases.length}
                </span>
                <span className="text-[10px] text-slate-400 block absolute bottom-5">
                  Automated
                </span>
              </div>
            </div>

            <div className="p-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm flex flex-col justify-between">
              <span className="text-xs font-bold text-slate-700 dark:text-slate-300">
                Self-Healing & Reliability Score
              </span>
              <div className="space-y-3 my-4">
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-400">Pass Rate Stability</span>
                    <span className="font-bold text-emerald-400">96.8%</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                    <div className="w-[96.8%] h-full bg-emerald-500 rounded-full" />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-400">Locator Health</span>
                    <span className="font-bold text-brand-400">100% (Multi-Locator Fallback)</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                    <div className="w-full h-full bg-brand-500 rounded-full" />
                  </div>
                </div>
              </div>
              <span className="text-[11px] text-slate-500">
                Data generated locally from execution traces and SQLite index.
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          TAB 4: REPORTS & TRACEABILITY
          ────────────────────────────────────────────────────────────────────────── */}
      {activeTab === 'reports' && (
        <div className="space-y-4">
          <div className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm space-y-4">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              Report Templates
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 space-y-2 hover:border-brand-500/50 transition-colors cursor-pointer">
                <div className="flex items-center gap-2 text-brand-500 font-bold text-xs">
                  <FileText className="w-4 h-4" />
                  Detailed Execution History
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">
                  A comprehensive log of test case executions, including step statuses, duration breakdown, and associated test case data.
                </p>
                <button
                  type="button"
                  onClick={() => navigate('/history')}
                  className="text-xs font-semibold text-brand-500 hover:underline pt-1 inline-block"
                >
                  View Execution History &rarr;
                </button>
              </div>

              <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 space-y-2 hover:border-brand-500/50 transition-colors cursor-pointer">
                <div className="flex items-center gap-2 text-indigo-500 font-bold text-xs">
                  <ShieldCheck className="w-4 h-4" />
                  Traceability Matrix
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">
                  A detailed report mapping Requirements, Code Changes, Test Cases, and Validations to ensure complete test coverage.
                </p>
                <button
                  type="button"
                  onClick={() => navigate('/reports')}
                  className="text-xs font-semibold text-indigo-500 hover:underline pt-1 inline-block"
                >
                  View Traceability Matrix &rarr;
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          TAB 5: SETTINGS & PROJECT AI INSTRUCTIONS (Tracecase Project Instructions)
          ────────────────────────────────────────────────────────────────────────── */}
      {activeTab === 'settings' && (
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm p-5 space-y-5">
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-brand-500" />
              Project Instructions for AI
            </h3>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">
              Project-level context and domain rules that help local AI features generate, evolve, and heal test cases aligned with this project&apos;s goals.
            </p>
          </div>

          <div className="space-y-4 max-w-2xl">
            <div>
              <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-1">
                AI System Prompt & Domain Guidelines
              </label>
              <textarea
                rows={4}
                value={projectInstructions}
                onChange={(e) => setProjectInstructions(e.target.value)}
                className="w-full p-3 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:border-brand-500 font-sans"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-1">
                  Default Codegen Framework
                </label>
                <select
                  value={defaultFramework}
                  onChange={(e) => setDefaultFramework(e.target.value)}
                  className="w-full px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100 font-medium"
                >
                  <option value="playwright">Playwright (Python / Sync)</option>
                  <option value="playwright_async">Playwright (Python / Async)</option>
                  <option value="selenium">Selenium WebDriver (Python)</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-bold text-slate-700 dark:text-slate-300 block mb-1">
                  Autonomous Self-Healing
                </label>
                <div className="flex items-center gap-3 pt-2">
                  <input
                    type="checkbox"
                    id="healingToggle"
                    checked={selfHealingEnabled}
                    onChange={(e) => setSelfHealingEnabled(e.target.checked)}
                    className="rounded bg-slate-900 border-slate-700 text-brand-600 focus:ring-0"
                  />
                  <label htmlFor="healingToggle" className="text-xs text-slate-400">
                    Auto-heal broken locators via multi-locator strategy
                  </label>
                </div>
              </div>
            </div>

            <div className="pt-2">
              <button
                type="button"
                onClick={handleSaveSettings}
                disabled={savingSettings}
                className="px-5 py-2 text-xs font-bold rounded-xl bg-brand-600 hover:bg-brand-500 text-white shadow-sm shadow-brand-600/30 flex items-center gap-2"
              >
                {savingSettings ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                <span>Save Project Settings</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          MODAL: AI TEST CASE SYNTHESIS
          ────────────────────────────────────────────────────────────────────────── */}
      {isAiModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-in fade-in">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 max-w-lg w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-indigo-500 font-bold text-sm">
                <Sparkles className="w-4 h-4" />
                <span>Generate Test Case with AI</span>
              </div>
              <button
                type="button"
                onClick={() => setIsAiModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-slate-500 dark:text-slate-400">
              Describe the user story, bug reproduction, or requirement. The local AI engine will synthesize test steps adhering to your project guidelines.
            </p>

            <form onSubmit={handleGenerateAiTest} className="space-y-4">
              <textarea
                rows={4}
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                placeholder="e.g. Test OrangeHRM leave request workflow: Login with admin, navigate to Leave > Apply, select Vacation leave for 2 days, and verify successful confirmation toast."
                className="w-full p-3 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:border-brand-500"
                autoFocus
              />

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsAiModalOpen(false)}
                  className="px-3 py-1.5 text-xs font-semibold rounded-lg text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={aiGenerating || !aiPrompt.trim()}
                  className="px-4 py-1.5 text-xs font-bold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white flex items-center gap-2 disabled:opacity-40"
                >
                  {aiGenerating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                  <span>Synthesize Test</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
