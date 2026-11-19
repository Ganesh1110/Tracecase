import React from 'react';
import { Cpu, Terminal, CheckCircle2, Copy } from 'lucide-react';
import { useToast } from '../context/ToastContext';

export function MCPIntegrations() {
  const { showToast } = useToast();

  const mcpConfig = {
    mcpServers: {
      qa_auto: {
        command: "qa_auto",
        args: ["mcp"],
      },
    },
  };

  const copyConfig = () => {
    navigator.clipboard.writeText(JSON.stringify(mcpConfig, null, 2));
    showToast('MCP configuration JSON copied!', 'success');
  };

  const tools = [
    {
      name: 'search_testcases',
      description: 'Search indexed test cases by keyword, selector, URL, or action description using SQLite FTS5.',
    },
    {
      name: 'get_testcase',
      description: 'Retrieve full test case JSON with step-by-step actions and metadata.',
    },
    {
      name: 'run_replay',
      description: 'Execute automated replay with self-healing, visual diffing, and assertion checks.',
    },
    {
      name: 'get_coverage_report',
      description: 'Analyze URL and action coverage statistics across the recorded corpus.',
    },
  ];

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
          <Cpu className="w-6 h-6 text-brand-500" />
          <span>Model Context Protocol (MCP) Integrations</span>
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Connect external AI agents (Claude Code, Cursor, Antigravity) directly to your QA Auto test repository.
        </p>
      </div>

      <div className="p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-slate-900 dark:text-white">Agent Configuration</h2>
            <p className="text-xs text-slate-500">Add this to your agent's MCP configuration file</p>
          </div>
          <button
            onClick={copyConfig}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 text-slate-700 dark:text-slate-300"
          >
            <Copy className="w-3.5 h-3.5" />
            <span>Copy JSON</span>
          </button>
        </div>

        <pre className="p-4 rounded-xl bg-slate-950 text-slate-300 font-mono text-xs leading-relaxed overflow-x-auto">
          {JSON.stringify(mcpConfig, null, 2)}
        </pre>
      </div>

      <div>
        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-3">
          Exposed MCP Agent Tools
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {tools.map((t) => (
            <div
              key={t.name}
              className="p-4 rounded-xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm"
            >
              <div className="font-mono font-bold text-sm text-brand-600 dark:text-brand-400">
                {t.name}
              </div>
              <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">{t.description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
