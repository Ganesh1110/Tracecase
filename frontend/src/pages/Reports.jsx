import React, { useEffect, useState } from 'react';
import { FileSpreadsheet, Eye, ExternalLink } from 'lucide-react';
import { api } from '../services/api';

export function Reports() {
  const [testcases, setTestCases] = useState([]);
  const [selectedCase, setSelectedCase] = useState(null);

  useEffect(() => {
    api.getTestCases().then((cases) => {
      setTestCases(cases);
      if (cases.length > 0) setSelectedCase(cases[0].id);
    });
  }, []);

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          Execution & Test Reports
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Detailed standalone HTML reports with action timelines and embedded network context.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <label className="text-xs font-semibold text-slate-500">Select Test Report:</label>
        <select
          value={selectedCase || ''}
          onChange={(e) => setSelectedCase(e.target.value)}
          className="px-3 py-1.5 text-sm rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark text-slate-800 dark:text-slate-200"
        >
          {testcases.map((tc) => (
            <option key={tc.id} value={tc.id}>
              {tc.name} ({tc.id})
            </option>
          ))}
        </select>
        {selectedCase && (
          <a
            href={`/api/testcases/${selectedCase}/html`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 text-slate-700 dark:text-slate-300"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            <span>Open in New Tab</span>
          </a>
        )}
      </div>

      {selectedCase && (
        <div className="rounded-2xl border border-slate-200 dark:border-surface-borderDark overflow-hidden bg-white shadow-sm h-[750px]">
          <iframe
            src={`/api/testcases/${selectedCase}/html`}
            title="HTML Report"
            className="w-full h-full border-none"
          />
        </div>
      )}
    </div>
  );
}
