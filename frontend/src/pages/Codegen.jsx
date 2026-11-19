import React, { useEffect, useState } from 'react';
import { Terminal, Copy, Check, Download } from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export function Codegen() {
  const [testcases, setTestCases] = useState([]);
  const [selectedCase, setSelectedCase] = useState('');
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    api.getTestCases().then((cases) => {
      setTestCases(cases);
      if (cases.length > 0) {
        setSelectedCase(cases[0].id);
        loadCode(cases[0].id);
      }
    });
  }, []);

  const loadCode = async (caseId) => {
    try {
      setLoading(true);
      const res = await api.getCodegen(caseId);
      setCode(res.code);
    } catch (err) {
      showToast('Codegen failed: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = (e) => {
    const val = e.target.value;
    setSelectedCase(val);
    loadCode(val);
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
          <Terminal className="w-6 h-6 text-brand-500" />
          <span>Playwright Code Generator</span>
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Export recorded user sessions directly to executable, idiomatic Pytest + Playwright code.
        </p>
      </div>

      <div className="flex items-center justify-between p-4 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
        <div className="flex items-center gap-3">
          <label className="text-xs font-semibold text-slate-500">Test Case:</label>
          <select
            value={selectedCase}
            onChange={handleSelect}
            className="px-3 py-1.5 text-sm rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200 font-medium"
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
            navigator.clipboard.writeText(code);
            showToast('Code copied to clipboard!', 'success');
          }}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-brand-600 hover:bg-brand-500 text-white shadow-md shadow-brand-500/20 transition-all"
        >
          <Copy className="w-3.5 h-3.5" />
          <span>Copy Pytest Script</span>
        </button>
      </div>

      <div className="rounded-2xl border border-slate-800 bg-slate-950 text-slate-200 overflow-hidden shadow-xl">
        <pre className="p-6 font-mono text-xs leading-relaxed overflow-x-auto selection:bg-brand-600">
          {loading ? '# Generating code...' : code}
        </pre>
      </div>
    </div>
  );
}
