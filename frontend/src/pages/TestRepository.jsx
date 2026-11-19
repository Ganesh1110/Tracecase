import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Database, Search, RefreshCw, Globe, CheckCircle2, FileCode2 } from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export function TestRepository() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [coverage, setCoverage] = useState(null);
  const [loading, setLoading] = useState(false);
  const { showToast } = useToast();
  const navigate = useNavigate();

  const loadCoverage = async () => {
    try {
      const data = await api.getCoverage();
      setCoverage(data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadCoverage();
  }, []);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    try {
      setLoading(true);
      const res = await api.searchRepository(query.trim());
      setResults(res);
    } catch (err) {
      showToast('Search failed: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleReindex = async () => {
    try {
      showToast('Reindexing corpus with SQLite FTS5...', 'info');
      const res = await api.reindexRepository();
      showToast(`Indexed ${res.indexed} testcases successfully!`, 'success');
      loadCoverage();
    } catch (err) {
      showToast('Reindexing failed: ' + err.message, 'error');
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            Test Repository & Coverage
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Full-text search indexed actions, selectors, and logs using SQLite FTS5 BM25 matching.
          </p>
        </div>
        <button
          onClick={handleReindex}
          className="flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Reindex Corpus</span>
        </button>
      </div>

      {/* Coverage KPI cards */}
      {coverage && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Total Indexed Cases
            </span>
            <div className="text-2xl font-bold text-slate-900 dark:text-white mt-2">
              {coverage.total_testcases || 0}
            </div>
          </div>
          <div className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Covered Domains
            </span>
            <div className="text-2xl font-bold text-brand-500 mt-2">
              {coverage.unique_domains || 0}
            </div>
          </div>
          <div className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Path Coverage
            </span>
            <div className="text-2xl font-bold text-emerald-500 mt-2">
              {Object.keys(coverage.path_coverage || {}).length} routes
            </div>
          </div>
        </div>
      )}

      {/* Search Bar */}
      <form onSubmit={handleSearch} className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3.5 top-2.5 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search selectors, endpoints, console logs, or keywords (e.g. login, #checkout-button, 404)..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
        </div>
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-5 py-2 text-xs font-bold rounded-xl bg-brand-600 hover:bg-brand-500 text-white shadow-md shadow-brand-500/20 disabled:opacity-50"
        >
          {loading ? 'Searching...' : 'Search Corpus'}
        </button>
      </form>

      {/* Results */}
      <div className="space-y-3">
        {results.map((r) => (
          <div
            key={r.id}
            onClick={() => navigate(`/testcases/${r.id}`)}
            className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark hover:border-brand-500/50 cursor-pointer transition-all shadow-sm"
          >
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-sm text-slate-900 dark:text-white">{r.name}</h3>
              <span className="text-xs font-mono text-slate-400">{r.id}</span>
            </div>
            <div className="text-xs font-mono text-slate-500 mt-0.5">{r.start_url}</div>
            {r.match_snippet && (
              <div
                className="mt-2 text-xs text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 p-2 rounded border border-slate-100 dark:border-slate-800"
                dangerouslySetInnerHTML={{
                  __html: r.match_snippet.replace(
                    /\[b\](.*?)\[\/b\]/g,
                    '<strong class="text-brand-500 font-bold">$1</strong>'
                  ),
                }}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
