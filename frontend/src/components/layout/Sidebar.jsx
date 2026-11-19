import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  FolderKanban,
  FileCode2,
  Layers,
  Video,
  PlayCircle,
  History,
  FileSpreadsheet,
  Images,
  Sparkles,
  Compass,
  BarChart3,
  Dna,
  Database,
  Terminal,
  Activity,
  Cpu,
  Settings,
  HardDrive,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
} from 'lucide-react';

const navSections = [
  {
    title: 'Workspace',
    items: [
      { name: 'Overview', to: '/', icon: LayoutDashboard },
      { name: 'Projects', to: '/projects', icon: FolderKanban },
    ],
  },
  {
    title: 'Testing',
    items: [
      { name: 'Test Cases', to: '/testcases', icon: FileCode2 },
      { name: 'Test Suites', to: '/suites', icon: Layers },
      { name: 'Browser Recorder', to: '/recorder', icon: Video, highlight: true },
      { name: 'Test Executions', to: '/executions', icon: PlayCircle },
      { name: 'Execution History', to: '/history', icon: History },
      { name: 'Reports', to: '/reports', icon: FileSpreadsheet },
      { name: 'Visual Regression', to: '/visual-diff', icon: Images },
    ],
  },
  {
    title: 'Intelligence',
    items: [
      { name: 'Autonomous Exploration', to: '/explore', icon: Compass, badge: 'New' },
      { name: 'AI Test Assistant', to: '/ai-assistant', icon: Sparkles, badge: 'AI' },
      { name: 'Test Analysis', to: '/test-analysis', icon: BarChart3 },
      { name: 'Negative Test Generation', to: '/mutations', icon: Dna },
      { name: 'Test Repository', to: '/repository', icon: Database },
    ],
  },
  {
    title: 'Developer Tools',
    items: [
      { name: 'Code Generator', to: '/codegen', icon: Terminal },
      { name: 'Network Inspector', to: '/network', icon: Activity },
      { name: 'MCP Integrations', to: '/mcp', icon: Cpu },
    ],
  },
  {
    title: 'Administration',
    items: [
      { name: 'Settings', to: '/settings', icon: Settings },
      { name: 'Storage Management', to: '/storage', icon: HardDrive },
    ],
  },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={`relative flex flex-col h-screen transition-all duration-300 border-r bg-white dark:bg-surface-panelDark border-slate-200 dark:border-surface-borderDark ${
        collapsed ? 'w-18' : 'w-64'
      } shrink-0 z-30 select-none`}
    >
      {/* Brand Header */}
      <div className="flex items-center justify-between h-16 px-4 border-b border-slate-200 dark:border-surface-borderDark">
        <NavLink to="/" className="flex items-center gap-3 overflow-hidden">
          <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-tr from-brand-600 to-indigo-500 text-white shadow-md shadow-brand-500/20 shrink-0">
            <ShieldCheck className="w-5 h-5" />
          </div>
          {!collapsed && (
            <div className="flex flex-col min-w-0">
              <span className="text-base font-bold tracking-tight text-slate-900 dark:text-white truncate">
                QA Auto
              </span>
              <span className="text-[10px] font-medium text-slate-400 dark:text-slate-500 uppercase tracking-widest truncate">
                Studio Platform
              </span>
            </div>
          )}
        </NavLink>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>

      {/* Navigation Sections */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
        {navSections.map((section) => (
          <div key={section.title} className="space-y-1">
            {!collapsed && (
              <h3 className="px-3 text-[11px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-2">
                {section.title}
              </h3>
            )}
            {section.items.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all group relative ${
                      isActive
                        ? 'bg-brand-50 dark:bg-brand-950/60 text-brand-600 dark:text-brand-300 font-semibold'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-100/70 dark:hover:bg-slate-800/60'
                    }`
                  }
                  title={collapsed ? item.name : undefined}
                >
                  <Icon
                    className={`w-4 h-4 shrink-0 transition-transform group-hover:scale-110 ${
                      item.highlight ? 'text-brand-500 animate-pulse' : ''
                    }`}
                  />
                  {!collapsed && (
                    <span className="flex-1 truncate">{item.name}</span>
                  )}
                  {!collapsed && item.badge && (
                    <span className="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-brand-100 dark:bg-brand-900/60 text-brand-600 dark:text-brand-300">
                      {item.badge}
                    </span>
                  )}
                </NavLink>
              );
            })}
          </div>
        ))}
      </div>

      {/* Tagline footer */}
      {!collapsed && (
        <div className="p-4 border-t border-slate-200 dark:border-surface-borderDark text-[11px] text-slate-400 dark:text-slate-500 text-center">
          Record once, test everywhere.
        </div>
      )}
    </aside>
  );
}
