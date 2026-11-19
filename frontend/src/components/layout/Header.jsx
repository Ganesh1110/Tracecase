import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FolderKanban,
  Sun,
  Moon,
  Radio,
  Plus,
  Video,
  Play,
  Sparkles,
  ChevronDown,
} from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';
import { useProject } from '../../context/ProjectContext';
import { useWebSocket } from '../../context/WebSocketContext';

export function Header({ onOpenRecordModal, onOpenNewCaseModal }) {
  const { theme, toggleTheme } = useTheme();
  const { projects, currentProject, setCurrentProject } = useProject();
  const { connected } = useWebSocket();
  const [projectDropdownOpen, setProjectDropdownOpen] = useState(false);
  const navigate = useNavigate();

  return (
    <header className="h-16 border-b bg-white dark:bg-surface-panelDark border-slate-200 dark:border-surface-borderDark px-6 flex items-center justify-between shrink-0 z-20">
      {/* Workspace / Project Selector */}
      <div className="flex items-center gap-4">
        <div className="relative">
          <button
            onClick={() => setProjectDropdownOpen(!projectDropdownOpen)}
            className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-sm font-medium"
          >
            <FolderKanban className="w-4 h-4 text-brand-500" />
            <span className="text-slate-800 dark:text-slate-200 max-w-[160px] truncate">
              {currentProject?.name || 'Default Project'}
            </span>
            <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
          </button>

          {projectDropdownOpen && (
            <div className="absolute left-0 mt-1.5 w-60 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-surface-cardDark shadow-xl py-1.5 z-50 animate-in fade-in zoom-in-95">
              <div className="px-3 py-1.5 text-xs font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                Select Workspace
              </div>
              <div className="max-h-56 overflow-y-auto">
                {projects.map((proj) => (
                  <button
                    key={proj.id}
                    onClick={() => {
                      setCurrentProject(proj);
                      setProjectDropdownOpen(false);
                    }}
                    className={`w-full text-left px-3 py-2 text-sm flex items-center justify-between hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors ${
                      proj.id === currentProject?.id
                        ? 'text-brand-600 dark:text-brand-400 font-semibold bg-brand-50/50 dark:bg-brand-950/30'
                        : 'text-slate-700 dark:text-slate-300'
                    }`}
                  >
                    <span className="truncate">{proj.name}</span>
                    <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500">
                      {proj.testcase_count || 0} cases
                    </span>
                  </button>
                ))}
              </div>
              <div className="border-t border-slate-200 dark:border-slate-800 mt-1 pt-1">
                <button
                  onClick={() => {
                    setProjectDropdownOpen(false);
                    navigate('/projects');
                  }}
                  className="w-full text-left px-3 py-1.5 text-xs font-medium text-brand-600 dark:text-brand-400 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center gap-1.5"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Manage all projects
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Live WebSocket Connection Pill */}
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
            connected
              ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-400'
              : 'bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-400'
          }`}
          title={connected ? 'Connected to live engine' : 'Reconnecting to live engine...'}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              connected ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'
            }`}
          />
          <span>{connected ? 'Live Sync' : 'Connecting'}</span>
        </div>
      </div>

      {/* Action Buttons & Theme Controls */}
      <div className="flex items-center gap-3">
        {/* Quick Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => onOpenNewCaseModal?.() || navigate('/testcases')}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Case</span>
          </button>

          <button
            onClick={() => onOpenRecordModal?.() || navigate('/recorder')}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-rose-50 dark:bg-rose-950/50 hover:bg-rose-100 dark:hover:bg-rose-900/60 text-rose-600 dark:text-rose-300 border border-rose-200 dark:border-rose-800 transition-colors"
          >
            <Video className="w-3.5 h-3.5" />
            <span>Record Browser</span>
          </button>

          <button
            onClick={() => navigate('/suites')}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-50 dark:bg-indigo-950/50 hover:bg-indigo-100 dark:hover:bg-indigo-900/60 text-indigo-600 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 transition-colors"
          >
            <Play className="w-3.5 h-3.5" />
            <span>Run Suite</span>
          </button>

          <button
            onClick={() => navigate('/ai-assistant')}
            className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 text-white shadow-sm shadow-brand-500/25 transition-all"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>AI Assistant</span>
          </button>
        </div>

        <div className="h-5 w-px bg-slate-200 dark:bg-slate-800 mx-1" />

        {/* Theme Switcher */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-lg text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        >
          {theme === 'dark' ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4" />}
        </button>
      </div>
    </header>
  );
}
