import React, { useEffect, useState } from 'react';
import { Activity, Download, Globe, Search, RefreshCw } from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export function NetworkInspector() {
  const [testcases, setTestCases] = useState([]);
  const [selectedCase, setSelectedCase] = useState('');
  const [harData, setHarData] = useState(null);
  const [loading, setLoading] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    api.getTestCases().then((cases) => {
      setTestCases(cases);
      if (cases.length > 0) {
        setSelectedCase(cases[0].id);
        loadHar(cases[0].id);
      }
    });
  }, []);

  const loadHar = async (caseId) => {
    try {
      setLoading(true);
      const data = await api.getHar(caseId);
      setHarData(data);
    } catch (err) {
      showToast('Failed to load HAR: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const entries = harData?.log?.entries || [];

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
          <Activity className="w-6 h-6 text-brand-500" />
          <span>Network Traffic & HAR Inspector</span>
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Inspect recorded HTTP requests, status codes, response bodies, and offline routing assets.
        </p>
      </div>

      <div className="flex items-center justify-between p-4 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
        <div className="flex items-center gap-3">
          <label className="text-xs font-semibold text-slate-500">Test Case:</label>
          <select
            value={selectedCase}
            onChange={(e) => {
              setSelectedCase(e.target.value);
              loadHar(e.target.value);
            }}
            className="px-3 py-1.5 text-sm rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900"
          >
            {testcases.map((tc) => (
              <option key={tc.id} value={tc.id}>
                {tc.name} ({tc.id})
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={() => {
            const blob = new Blob([JSON.stringify(harData, null, 2)], {
              type: 'application/json',
            });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${selectedCase}.har`;
            a.click();
            showToast('HAR file downloaded!', 'success');
          }}
          disabled={!harData}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 text-slate-700 dark:text-slate-300 disabled:opacity-50"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Export HAR</span>
        </button>
      </div>

      <div className="rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-slate-100 dark:border-surface-borderDark font-semibold text-slate-400 uppercase bg-slate-50/50 dark:bg-slate-900/30">
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3">Method</th>
                <th className="px-5 py-3">URL</th>
                <th className="px-5 py-3">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800 font-mono">
              {entries.length === 0 ? (
                <tr>
                  <td colSpan={4} className="p-8 text-center text-slate-500 italic">
                    No network entries recorded for this test case.
                  </td>
                </tr>
              ) : (
                entries.map((entry, idx) => (
                  <tr key={idx} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40">
                    <td className="px-5 py-3">
                      <span
                        className={`font-bold ${
                          entry.response?.status >= 200 && entry.response?.status < 300
                            ? 'text-emerald-500'
                            : entry.response?.status >= 400
                            ? 'text-rose-500'
                            : 'text-amber-500'
                        }`}
                      >
                        {entry.response?.status || '-'}
                      </span>
                    </td>
                    <td className="px-5 py-3 font-semibold text-slate-700 dark:text-slate-300">
                      {entry.request?.method}
                    </td>
                    <td className="px-5 py-3 text-slate-500 truncate max-w-md">
                      {entry.request?.url}
                    </td>
                    <td className="px-5 py-3 text-slate-400">{entry.time?.toFixed(0)}ms</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
