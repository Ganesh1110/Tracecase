import React, { useState } from 'react';
import { Images, ArrowLeftRight, Check, AlertTriangle, Loader2 } from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export function VisualRegression() {
  const [baseline, setBaseline] = useState('');
  const [candidate, setCandidate] = useState('');
  const [threshold, setThreshold] = useState(0.1);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const { showToast } = useToast();

  const handleCompare = async (e) => {
    e.preventDefault();
    if (!baseline || !candidate) {
      showToast('Please specify both baseline and candidate image paths.', 'error');
      return;
    }
    try {
      setLoading(true);
      const res = await api.compareVisual({
        baseline: baseline.trim(),
        candidate: candidate.trim(),
        threshold: parseFloat(threshold),
      });
      setResult(res);
      showToast('Visual diff comparison completed!', 'success');
    } catch (err) {
      showToast('Diff comparison failed: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          Visual Regression Studio
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Pixel-by-pixel visual diffing and tolerance validation across replay test runs.
        </p>
      </div>

      <form
        onSubmit={handleCompare}
        className="p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm space-y-4"
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Baseline Screenshot Path
            </label>
            <input
              type="text"
              placeholder="e.g. recordings/login/screenshots/001_click.png"
              value={baseline}
              onChange={(e) => setBaseline(e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 font-mono"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Candidate Screenshot Path
            </label>
            <input
              type="text"
              placeholder="e.g. recordings/login/replay_runs/.../001_click.png"
              value={candidate}
              onChange={(e) => setCandidate(e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 font-mono"
            />
          </div>
        </div>

        <div className="flex items-center justify-between pt-2">
          <div className="flex items-center gap-3">
            <label className="text-xs font-semibold text-slate-500">
              Diff Tolerance: {(threshold * 100).toFixed(0)}%
            </label>
            <input
              type="range"
              min="0.01"
              max="0.5"
              step="0.01"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              className="w-36"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="flex items-center gap-2 px-5 py-2 text-xs font-bold rounded-xl bg-brand-600 hover:bg-brand-500 text-white shadow-md shadow-brand-500/20 disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowLeftRight className="w-4 h-4" />}
            <span>Compare Screenshots</span>
          </button>
        </div>
      </form>

      {result && (
        <div className="p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm space-y-4">
          <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-slate-800">
            <div className="flex items-center gap-3">
              <span
                className={`px-3 py-1 rounded-full text-xs font-bold uppercase ${
                  result.passed
                    ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-500 border border-emerald-200'
                    : 'bg-rose-50 dark:bg-rose-950/60 text-rose-500 border border-rose-200'
                }`}
              >
                {result.passed ? 'Visual Match Passed' : 'Visual Mismatch Detected'}
              </span>
              <span className="text-xs text-slate-500 font-mono">
                Diff: {(result.diff_percent * 100).toFixed(2)}% (Tolerance: {(threshold * 100).toFixed(0)}%)
              </span>
            </div>
          </div>

          {result.diff_path && (
            <div className="rounded-xl overflow-hidden border border-slate-200 dark:border-slate-800 bg-black flex justify-center p-4">
              <img
                src={`/api/diff/image?path=${encodeURIComponent(result.diff_path)}`}
                alt="Visual Difference Overlay"
                className="max-h-[500px] object-contain"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
