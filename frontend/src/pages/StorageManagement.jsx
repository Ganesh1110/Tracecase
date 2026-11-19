import React, { useEffect, useState } from 'react';
import { HardDrive, Trash2, RefreshCw, Database } from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export function StorageManagement() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const { showToast } = useToast();

  const loadStats = async () => {
    try {
      const data = await api.getStorageStats();
      setStats(data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadStats();
  }, []);

  const handleCleanDiffs = async () => {
    try {
      setLoading(true);
      const res = await api.cleanStorage({ clean_diffs: true, clean_old_runs: false });
      showToast(`Cleaned ${res.deleted_files} files, freed ${res.freed_mb} MB!`, 'success');
      loadStats();
    } catch (err) {
      showToast('Cleanup failed: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleCleanOldRuns = async () => {
    if (!confirm('Are you sure you want to prune old replay runs?')) return;
    try {
      setLoading(true);
      const res = await api.cleanStorage({ clean_diffs: true, clean_old_runs: true });
      showToast(`Cleaned ${res.deleted_files} files, freed ${res.freed_mb} MB!`, 'success');
      loadStats();
    } catch (err) {
      showToast('Cleanup failed: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
          <HardDrive className="w-6 h-6 text-brand-500" />
          <span>Storage Management</span>
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Monitor disk usage for recordings, screenshot artifacts, and visual diffs.
        </p>
      </div>

      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
          <div className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Total Storage Used
            </span>
            <div className="text-3xl font-bold text-slate-900 dark:text-white mt-2">
              {stats.total_size_mb} MB
            </div>
            <p className="text-xs text-slate-500 mt-1">Across all projects & runs</p>
          </div>

          <div className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Screenshot Artifacts
            </span>
            <div className="text-3xl font-bold text-brand-500 mt-2">
              {stats.screenshots_count}
            </div>
            <p className="text-xs text-slate-500 mt-1">{stats.screenshots_size_mb} MB on disk</p>
          </div>

          <div className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Recorded Test Cases
            </span>
            <div className="text-3xl font-bold text-emerald-500 mt-2">
              {stats.recordings_count}
            </div>
            <p className="text-xs text-slate-500 mt-1 font-mono truncate">{stats.database_path}</p>
          </div>
        </div>
      )}

      <div className="p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm space-y-4">
        <h2 className="text-base font-bold text-slate-900 dark:text-white">Artifact Pruning Actions</h2>
        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={handleCleanDiffs}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition-colors disabled:opacity-50"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Clean Old Visual Diff Images</span>
          </button>
          <button
            onClick={handleCleanOldRuns}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold bg-rose-50 dark:bg-rose-950/60 hover:bg-rose-100 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-800 transition-colors disabled:opacity-50"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Prune Replay Run Outputs</span>
          </button>
        </div>
      </div>
    </div>
  );
}
