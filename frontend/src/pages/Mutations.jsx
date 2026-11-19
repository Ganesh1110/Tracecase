import React, { useEffect, useState } from 'react';
import { Dna, Play, Sparkles, Loader2, ShieldAlert } from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export function Mutations() {
  const [testcases, setTestCases] = useState([]);
  const [selectedCase, setSelectedCase] = useState('');
  const [mutants, setMutants] = useState([]);
  const [loading, setLoading] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    api.getTestCases().then((cases) => {
      setTestCases(cases);
      if (cases.length > 0) setSelectedCase(cases[0].id);
    });
  }, []);

  const handleGenerate = async () => {
    if (!selectedCase) return;
    try {
      setLoading(true);
      const res = await api.generateMutations({
        testcase_id: selectedCase,
        strategies: ['inputs', 'actions', 'network'],
        limit: 12,
      });
      setMutants(res);
      showToast(`Synthesized ${res.length} negative test cases!`, 'success');
    } catch (err) {
      showToast('Mutation generation failed: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
          <Dna className="w-6 h-6 text-indigo-500" />
          <span>Negative Test Generation</span>
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Synthesize robust negative test variations by mutating inputs (SQLi/XSS/boundaries), dropping actions, and simulating network faults.
        </p>
      </div>

      <div className="flex items-center gap-3 p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
        <label className="text-xs font-semibold text-slate-500">Seed Test Case:</label>
        <select
          value={selectedCase}
          onChange={(e) => setSelectedCase(e.target.value)}
          className="flex-1 max-w-md px-3 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900"
        >
          {testcases.map((tc) => (
            <option key={tc.id} value={tc.id}>
              {tc.name} ({tc.id})
            </option>
          ))}
        </select>
        <button
          onClick={handleGenerate}
          disabled={loading || !selectedCase}
          className="flex items-center gap-2 px-5 py-2 text-xs font-bold rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/20 disabled:opacity-50"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Dna className="w-4 h-4" />}
          <span>Synthesize Negative Tests</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {mutants.map((m, idx) => (
          <div
            key={idx}
            className="p-5 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm flex flex-col justify-between"
          >
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-indigo-50 dark:bg-indigo-950/60 text-indigo-500 border border-indigo-200 dark:border-indigo-800">
                  {m.strategy}
                </span>
                <span className="text-[11px] font-mono text-slate-400">Step #{m.target_step}</span>
              </div>
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">{m.name}</h3>
              <p className="text-xs text-slate-500 mt-2 line-clamp-3 leading-relaxed">
                {m.description}
              </p>
              {m.mutated_value && (
                <div className="mt-3 p-2 rounded-lg bg-slate-100 dark:bg-slate-900 font-mono text-[11px] text-slate-700 dark:text-slate-300 truncate">
                  <span className="text-slate-400">Payload: </span>
                  {m.mutated_value}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
