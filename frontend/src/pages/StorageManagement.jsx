import React, { useEffect, useState } from 'react';
import {
  HardDrive,
  Trash2,
  RefreshCw,
  Database,
  ShieldAlert,
  Clock,
  Layers,
  FileImage,
  CheckCircle2,
  Settings,
  Sliders,
  AlertTriangle,
  FolderOpen,
} from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export function StorageManagement() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [dryRun, setDryRun] = useState(false);
  const [lastPruneResult, setLastPruneResult] = useState(null);
  const { showToast } = useToast();

  const [policyForm, setPolicyForm] = useState({
    retention_mode: 'all',
    keep_latest_runs: 10,
    max_age_days: 14,
    max_storage_mb: 500,
    auto_prune_on_complete: true,
  });

  const loadSummary = async () => {
    try {
      setLoading(true);
      const data = await api.getStorageSummary();
      setSummary(data);
      if (data.retention_policy) {
        setPolicyForm({
          retention_mode: data.retention_policy.retention_mode || 'all',
          keep_latest_runs: data.retention_policy.keep_latest_runs ?? 10,
          max_age_days: data.retention_policy.max_age_days ?? 14,
          max_storage_mb: data.retention_policy.max_storage_mb ?? 500,
          auto_prune_on_complete: data.retention_policy.auto_prune_on_complete ?? true,
        });
      }
    } catch (err) {
      console.error(err);
      showToast('Failed to load storage summary: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSummary();
  }, []);

  const handleSavePolicy = async (e) => {
    e.preventDefault();
    try {
      setSavingPolicy(true);
      const updated = await api.updateRetentionPolicy({
        retention_mode: policyForm.retention_mode,
        keep_latest_runs: parseInt(policyForm.keep_latest_runs, 10) || 0,
        max_age_days: parseInt(policyForm.max_age_days, 10) || 0,
        max_storage_mb: parseInt(policyForm.max_storage_mb, 10) || 0,
        auto_prune_on_complete: Boolean(policyForm.auto_prune_on_complete),
      });
      showToast('Retention policy saved successfully!', 'success');
      setPolicyForm({
        retention_mode: updated.retention_mode,
        keep_latest_runs: updated.keep_latest_runs,
        max_age_days: updated.max_age_days,
        max_storage_mb: updated.max_storage_mb,
        auto_prune_on_complete: updated.auto_prune_on_complete,
      });
      loadSummary();
    } catch (err) {
      showToast('Failed to save policy: ' + err.message, 'error');
    } finally {
      setSavingPolicy(false);
    }
  };

  const handlePrune = async (pruneOptions, description) => {
    try {
      setLoading(true);
      const payload = {
        ...pruneOptions,
        dry_run: dryRun,
      };
      const res = await api.pruneStorage(payload);
      setLastPruneResult(res);
      const prefix = dryRun ? '[Dry Run Preview] Would free' : 'Successfully freed';
      showToast(
        `${prefix} ${res.freed_mb} MB (${res.deleted_files} files, ${res.deleted_runs} runs)!`,
        'success'
      );
      if (!dryRun) {
        loadSummary();
      }
    } catch (err) {
      showToast(`Pruning failed: ${err.message}`, 'error');
    } finally {
      setLoading(false);
    }
  };

  // Percentages for storage allocation
  const totalMb = summary ? Math.max(summary.total_size_mb, 0.01) : 1;
  const runsPct = summary ? ((summary.replay_runs_size_mb / totalMb) * 100).toFixed(1) : 0;
  const diffsPct = summary ? ((summary.diffs_size_mb / totalMb) * 100).toFixed(1) : 0;
  const recPct = summary ? ((summary.recordings_size_mb / totalMb) * 100).toFixed(1) : 0;
  const dbPct = summary ? ((summary.database_size_mb / totalMb) * 100).toFixed(1) : 0;

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <HardDrive className="w-6 h-6 text-brand-500" />
            <span>Artifact & Storage Optimization</span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Fine-grained disk allocation, automated retention rules, and safe artifact pruning.
          </p>
        </div>
        <button
          onClick={loadSummary}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 transition-colors shadow-sm disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-brand-500' : ''}`} />
          <span>Refresh Metrics</span>
        </button>
      </div>

      {/* Storage Breakdown Cards */}
      {summary && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Total Disk Usage
              </span>
              <HardDrive className="w-4 h-4 text-brand-500" />
            </div>
            <div className="text-3xl font-bold text-slate-900 dark:text-white mt-2">
              {summary.total_size_mb} MB
            </div>
            <p className="text-xs text-slate-500 mt-1">Across all workspaces & assets</p>
          </div>

          <div className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Replay Runs & Shots
              </span>
              <FileImage className="w-4 h-4 text-indigo-500" />
            </div>
            <div className="text-3xl font-bold text-indigo-600 dark:text-indigo-400 mt-2">
              {summary.replay_runs_size_mb} MB
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {summary.replay_runs_count} runs ({summary.replay_screenshots_count} screenshots)
            </p>
          </div>

          <div className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Visual Regression Diffs
              </span>
              <Layers className="w-4 h-4 text-amber-500" />
            </div>
            <div className="text-3xl font-bold text-amber-600 dark:text-amber-400 mt-2">
              {summary.diffs_size_mb} MB
            </div>
            <p className="text-xs text-slate-500 mt-1">{summary.diffs_count} diff images stored</p>
          </div>

          <div className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Baseline Corpus & DB
              </span>
              <Database className="w-4 h-4 text-emerald-500" />
            </div>
            <div className="text-3xl font-bold text-emerald-600 dark:text-emerald-400 mt-2">
              {(summary.recordings_size_mb + summary.database_size_mb).toFixed(2)} MB
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {summary.recordings_count} test cases ({summary.database_size_mb} MB DB)
            </p>
          </div>
        </div>
      )}

      {/* Storage Allocation Visual Bar */}
      {summary && (
        <div className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm space-y-3">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-600 dark:text-slate-400">
            <span>Storage Allocation Ratio</span>
            <span>{summary.total_size_mb} MB total</span>
          </div>
          <div className="w-full h-3.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden flex">
            <div
              style={{ width: `${runsPct}%` }}
              className="bg-indigo-500 transition-all duration-500"
              title={`Replay Runs: ${runsPct}% (${summary.replay_runs_size_mb} MB)`}
            />
            <div
              style={{ width: `${diffsPct}%` }}
              className="bg-amber-500 transition-all duration-500"
              title={`Visual Diffs: ${diffsPct}% (${summary.diffs_size_mb} MB)`}
            />
            <div
              style={{ width: `${recPct}%` }}
              className="bg-emerald-500 transition-all duration-500"
              title={`Baseline Corpus: ${recPct}% (${summary.recordings_size_mb} MB)`}
            />
            <div
              style={{ width: `${dbPct}%` }}
              className="bg-sky-500 transition-all duration-500"
              title={`Database: ${dbPct}% (${summary.database_size_mb} MB)`}
            />
          </div>
          <div className="flex flex-wrap items-center gap-4 text-[11px] text-slate-500 pt-1">
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-indigo-500" />
              <span>Replay Runs ({runsPct}%)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
              <span>Visual Diffs ({diffsPct}%)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
              <span>Baseline Corpus ({recPct}%)</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-sky-500" />
              <span>Studio DB ({dbPct}%)</span>
            </div>
          </div>
        </div>
      )}

      {/* Grid: Retention Policy & Pruning Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Retention Policy Form */}
        <div className="p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm space-y-5">
          <div className="flex items-center gap-2">
            <Sliders className="w-5 h-5 text-brand-500" />
            <h2 className="text-base font-bold text-slate-900 dark:text-white">
              Artifact Retention Policy
            </h2>
          </div>
          <p className="text-xs text-slate-500">
            Configure automated rules applied during test execution and maintenance cycles.
          </p>

          <form onSubmit={handleSavePolicy} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Artifact Retention Strategy
              </label>
              <select
                value={policyForm.retention_mode}
                onChange={(e) =>
                  setPolicyForm({ ...policyForm, retention_mode: e.target.value })
                }
                className="w-full text-xs rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 px-3 py-2 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="all">Keep All Artifacts (Default)</option>
                <option value="failures_only">
                  Failures & Flaky Runs Only (Prune screenshots on pass)
                </option>
                <option value="none">Discard All Replay Outputs (Minimal footprint)</option>
              </select>
              <p className="text-[11px] text-slate-400 mt-1">
                {policyForm.retention_mode === 'failures_only'
                  ? 'Screenshots are automatically pruned for passing runs, saving ~95% disk space while keeping failure diagnostics.'
                  : policyForm.retention_mode === 'none'
                  ? 'Replay runs are discarded immediately upon execution completion.'
                  : 'Full step screenshots, traces, and reports are preserved for all runs.'}
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Keep Latest Runs (per test case)
                </label>
                <input
                  type="number"
                  min="0"
                  max="1000"
                  value={policyForm.keep_latest_runs}
                  onChange={(e) =>
                    setPolicyForm({ ...policyForm, keep_latest_runs: e.target.value })
                  }
                  className="w-full text-xs rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 px-3 py-2 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
                <span className="text-[10px] text-slate-400">0 = keep all runs</span>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Max Age (Days)
                </label>
                <input
                  type="number"
                  min="0"
                  max="365"
                  value={policyForm.max_age_days}
                  onChange={(e) =>
                    setPolicyForm({ ...policyForm, max_age_days: e.target.value })
                  }
                  className="w-full text-xs rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 px-3 py-2 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
                />
                <span className="text-[10px] text-slate-400">0 = no age pruning</span>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Target Replay Quota (MB)
              </label>
              <input
                type="number"
                min="0"
                max="100000"
                value={policyForm.max_storage_mb}
                onChange={(e) =>
                  setPolicyForm({ ...policyForm, max_storage_mb: e.target.value })
                }
                className="w-full text-xs rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 px-3 py-2 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
              <span className="text-[10px] text-slate-400">
                Oldest runs are purged when quota is exceeded (0 = unlimited)
              </span>
            </div>

            <div className="flex items-center gap-2 pt-1">
              <input
                type="checkbox"
                id="auto_prune"
                checked={policyForm.auto_prune_on_complete}
                onChange={(e) =>
                  setPolicyForm({ ...policyForm, auto_prune_on_complete: e.target.checked })
                }
                className="rounded border-slate-300 text-brand-600 focus:ring-brand-500"
              />
              <label
                htmlFor="auto_prune"
                className="text-xs font-medium text-slate-700 dark:text-slate-300 cursor-pointer"
              >
                Enforce retention rules automatically on execution completion
              </label>
            </div>

            <button
              type="submit"
              disabled={savingPolicy}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold bg-brand-600 hover:bg-brand-700 text-white transition-colors shadow-sm disabled:opacity-50"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{savingPolicy ? 'Saving Policy...' : 'Save Retention Policy'}</span>
            </button>
          </form>
        </div>

        {/* Artifact Pruning Controls */}
        <div className="p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm space-y-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Trash2 className="w-5 h-5 text-rose-500" />
              <h2 className="text-base font-bold text-slate-900 dark:text-white">
                Pruning & Storage Actions
              </h2>
            </div>
            {/* Dry Run Toggle */}
            <label className="flex items-center gap-2 cursor-pointer bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 px-3 py-1.5 rounded-xl">
              <input
                type="checkbox"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
                className="rounded border-slate-300 text-amber-500 focus:ring-amber-400"
              />
              <span className="text-[11px] font-semibold text-slate-700 dark:text-slate-300">
                Dry Run Simulation
              </span>
            </label>
          </div>

          {dryRun && (
            <div className="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300 text-xs flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>Dry run active: simulates deletion and reports freed bytes without deleting files.</span>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <button
              onClick={() => handlePrune({ clean_diffs: true }, 'Clean Visual Diffs')}
              disabled={loading}
              className="flex items-center gap-2 p-3 rounded-xl text-xs font-semibold bg-slate-50 dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200 transition-colors disabled:opacity-50 text-left"
            >
              <Trash2 className="w-4 h-4 text-amber-500 shrink-0" />
              <div>
                <div>Prune Visual Diffs</div>
                <div className="text-[10px] text-slate-400 font-normal">
                  Delete diff_{'{...}'}.png comparison images
                </div>
              </div>
            </button>

            <button
              onClick={() =>
                handlePrune(
                  { failures_only: true },
                  'Prune Passing Run Screenshots'
                )
              }
              disabled={loading}
              className="flex items-center gap-2 p-3 rounded-xl text-xs font-semibold bg-slate-50 dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200 transition-colors disabled:opacity-50 text-left"
            >
              <ShieldAlert className="w-4 h-4 text-emerald-500 shrink-0" />
              <div>
                <div>Failures-Only Retention</div>
                <div className="text-[10px] text-slate-400 font-normal">
                  Prune screenshots for passed runs
                </div>
              </div>
            </button>

            <button
              onClick={() =>
                handlePrune(
                  { older_than_days: policyForm.max_age_days || 14 },
                  `Prune Runs Older Than ${policyForm.max_age_days}d`
                )
              }
              disabled={loading}
              className="flex items-center gap-2 p-3 rounded-xl text-xs font-semibold bg-slate-50 dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200 transition-colors disabled:opacity-50 text-left"
            >
              <Clock className="w-4 h-4 text-indigo-500 shrink-0" />
              <div>
                <div>Prune by Max Age</div>
                <div className="text-[10px] text-slate-400 font-normal">
                  Remove runs older than {policyForm.max_age_days || 14} days
                </div>
              </div>
            </button>

            <button
              onClick={() =>
                handlePrune(
                  { keep_latest_runs: policyForm.keep_latest_runs || 10 },
                  `Keep Latest ${policyForm.keep_latest_runs || 10} Runs`
                )
              }
              disabled={loading}
              className="flex items-center gap-2 p-3 rounded-xl text-xs font-semibold bg-slate-50 dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200 transition-colors disabled:opacity-50 text-left"
            >
              <Layers className="w-4 h-4 text-brand-500 shrink-0" />
              <div>
                <div>Prune Excess Runs</div>
                <div className="text-[10px] text-slate-400 font-normal">
                  Retain latest {policyForm.keep_latest_runs || 10} per test case
                </div>
              </div>
            </button>

            <button
              onClick={() =>
                handlePrune(
                  { max_storage_mb: policyForm.max_storage_mb || 500 },
                  'Enforce Storage Quota'
                )
              }
              disabled={loading}
              className="flex items-center gap-2 p-3 rounded-xl text-xs font-semibold bg-slate-50 dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200 transition-colors disabled:opacity-50 text-left"
            >
              <HardDrive className="w-4 h-4 text-rose-500 shrink-0" />
              <div>
                <div>Enforce Quota</div>
                <div className="text-[10px] text-slate-400 font-normal">
                  FIFO purge oldest runs to {policyForm.max_storage_mb || 500} MB
                </div>
              </div>
            </button>

            <button
              onClick={() => {
                if (!dryRun && !confirm('Are you sure you want to prune ALL old replay runs?')) return;
                handlePrune({ clean_old_runs: true }, 'Prune All Old Replay Runs');
              }}
              disabled={loading}
              className="flex items-center gap-2 p-3 rounded-xl text-xs font-semibold bg-rose-50 dark:bg-rose-950/40 hover:bg-rose-100 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-800 transition-colors disabled:opacity-50 text-left"
            >
              <Trash2 className="w-4 h-4 shrink-0" />
              <div>
                <div>Wipe All Replay Runs</div>
                <div className="text-[10px] text-rose-500/80 font-normal">
                  Delete all replay run directories
                </div>
              </div>
            </button>
          </div>

          {/* Pruning Result Panel */}
          {lastPruneResult && (
            <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 space-y-2 animate-in fade-in">
              <div className="flex items-center justify-between text-xs font-bold text-slate-800 dark:text-slate-200">
                <span className="flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                  <span>
                    {lastPruneResult.dry_run ? 'Simulation Report' : 'Pruning Execution Report'}
                  </span>
                </span>
                <span className="font-mono text-emerald-600 dark:text-emerald-400">
                  {lastPruneResult.dry_run ? 'Would Free ' : 'Freed '}
                  {lastPruneResult.freed_mb} MB
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-[11px] text-slate-600 dark:text-slate-400 font-medium">
                <div>Runs: {lastPruneResult.deleted_runs}</div>
                <div>Files: {lastPruneResult.deleted_files}</div>
                <div>Remaining: {lastPruneResult.remaining_storage_mb} MB</div>
              </div>
              {lastPruneResult.pruned_paths && lastPruneResult.pruned_paths.length > 0 && (
                <div className="pt-2 text-[10px] text-slate-500">
                  <span className="font-semibold">Sample Paths ({lastPruneResult.pruned_paths.length}):</span>
                  <div className="mt-1 max-h-24 overflow-y-auto space-y-1 font-mono text-[9px] bg-white dark:bg-slate-950 p-2 rounded border border-slate-200 dark:border-slate-800">
                    {lastPruneResult.pruned_paths.slice(0, 10).map((p, idx) => (
                      <div key={idx} className="truncate">{p}</div>
                    ))}
                    {lastPruneResult.pruned_paths.length > 10 && (
                      <div className="text-slate-400">
                        ...and {lastPruneResult.pruned_paths.length - 10} more
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
