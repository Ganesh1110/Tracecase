import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  FolderKanban,
  Sun,
  Moon,
  Globe,
} from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';
import { useProject } from '../../context/ProjectContext';
import { useWebSocket } from '../../context/WebSocketContext';
import { api } from '../../services/api';

const formatBrowserName = (browser) => {
  if (!browser) return 'Google Chrome';
  const b = browser.toLowerCase();
  if (b.includes('chrome') || b.includes('chromium')) return 'Google Chrome';
  if (b.includes('firefox')) return 'Mozilla Firefox';
  if (b.includes('webkit') || b.includes('safari')) return 'WebKit (Safari)';
  if (b.includes('edge') || b.includes('msedge')) return 'Microsoft Edge';
  return browser.charAt(0).toUpperCase() + browser.slice(1);
};

export function Header() {
  const { theme, toggleTheme } = useTheme();
  const { currentProject } = useProject();
  const { connected } = useWebSocket();
  const navigate = useNavigate();

  const [currentBrowser, setCurrentBrowser] = useState(() => {
    try {
      return localStorage.getItem('tracecase_default_browser') || 'chromium';
    } catch {
      return 'chromium';
    }
  });

  useEffect(() => {
    // 1. Fetch default browser configured in Settings
    api.getSettings()
      .then((settings) => {
        if (settings?.default_browser) {
          setCurrentBrowser(settings.default_browser);
          localStorage.setItem('tracecase_default_browser', settings.default_browser);
        }
      })
      .catch((err) => {
        console.debug('Using cached browser setting:', err);
      });

    // 2. Listen for live changes from Settings or Test Case selection
    const handleBrowserChange = (e) => {
      if (e?.detail) {
        setCurrentBrowser(e.detail);
      }
    };

    const handleStorageChange = (e) => {
      if (e.key === 'tracecase_default_browser' && e.newValue) {
        setCurrentBrowser(e.newValue);
      }
    };

    window.addEventListener('tracecase:browser-changed', handleBrowserChange);
    window.addEventListener('storage', handleStorageChange);

    return () => {
      window.removeEventListener('tracecase:browser-changed', handleBrowserChange);
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  return (
    <header className="h-16 border-b bg-white dark:bg-surface-panelDark border-slate-200 dark:border-surface-borderDark px-4 sm:px-6 flex items-center justify-between shrink-0 z-30 overflow-x-auto scrollbar-none transition-colors">
      {/* Workspace & Browser Quick-Link Badges */}
      <div className="flex items-center gap-2 sm:gap-3 shrink-0">
        {/* Workspace Quick-Link -> Navigates to /projects */}
        <button
          onClick={() => navigate('/projects')}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-all text-xs sm:text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 cursor-pointer group"
          title="Click to manage Projects & Workspaces"
        >
          <FolderKanban className="w-4 h-4 text-brand-500 shrink-0 group-hover:scale-110 transition-transform" />
          <span className="text-slate-800 dark:text-slate-200 font-semibold max-w-[130px] sm:max-w-[180px] truncate">
            {currentProject?.name || 'Tracecase'}
          </span>
        </button>

        {/* Selected Browser Quick-Link -> Navigates to /settings */}
        <button
          onClick={() => navigate('/settings')}
          className="flex items-center gap-1.5 sm:gap-2 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-all text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 cursor-pointer group"
          title="Click to configure default browser in Settings"
        >
          <Globe className="w-3.5 h-3.5 text-brand-500 shrink-0 group-hover:scale-110 transition-transform" />
          <span className="text-slate-800 dark:text-slate-200 font-semibold max-w-[110px] sm:max-w-[160px] truncate">
            {formatBrowserName(currentBrowser)}
          </span>
          <span className="hidden sm:inline px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400 uppercase tracking-wider">
            LOCAL
          </span>
        </button>

        {/* Live WebSocket Connection Status Pill */}
        <div
          className={`hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border shrink-0 ${
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

      {/* Right: Theme Switcher */}
      <div className="flex items-center shrink-0 ml-2">
        <button
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          className="p-2 rounded-lg text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        >
          {theme === 'dark' ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4" />}
        </button>
      </div>
    </header>
  );
}
