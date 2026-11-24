import React, { useState, useEffect } from 'react';
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
  Globe,
  Smartphone,
  Tablet,
  Laptop,
  Check,
  RefreshCw,
  Cpu,
  Bot,
} from 'lucide-react';
import { useTheme } from '../../context/ThemeContext';
import { useProject } from '../../context/ProjectContext';
import { useWebSocket } from '../../context/WebSocketContext';
import { api } from '../../services/api';

export function Header({ onOpenRecordModal, onOpenNewCaseModal }) {
  const { theme, toggleTheme } = useTheme();
  const { projects, currentProject, setCurrentProject } = useProject();
  const { connected } = useWebSocket();
  const [projectDropdownOpen, setProjectDropdownOpen] = useState(false);
  const [deviceDropdownOpen, setDeviceDropdownOpen] = useState(false);
  const [deviceTab, setDeviceTab] = useState('desktop'); // 'desktop' | 'emulation' | 'adb' | 'simulator'
  const [availableDevices, setAvailableDevices] = useState(null);
  const [selectedTarget, setSelectedTarget] = useState({
    id: 'desktop_chrome',
    name: 'Google Chrome',
    type: 'desktop',
    engine: 'chrome',
  });
  const navigate = useNavigate();

  useEffect(() => {
    loadDevices();
  }, []);

  const loadDevices = async () => {
    try {
      const data = await api.getAvailableDevices();
      setAvailableDevices(data);
      if (data?.browsers?.length > 0 && !selectedTarget) {
        setSelectedTarget(data.browsers[0]);
      }
    } catch (err) {
      console.error('Failed to load available devices:', err);
    }
  };

  return (
    <header className="h-16 border-b bg-white dark:bg-surface-panelDark border-slate-200 dark:border-surface-borderDark px-6 flex items-center justify-between shrink-0 z-20">
      {/* Workspace & Device Selector */}
      <div className="flex items-center gap-3">
        {/* Workspace Dropdown */}
        <div className="relative">
          <button
            onClick={() => setProjectDropdownOpen(!projectDropdownOpen)}
            className="flex items-center gap-2.5 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-sm font-medium"
          >
            <FolderKanban className="w-4 h-4 text-brand-500" />
            <span className="text-slate-800 dark:text-slate-200 max-w-[140px] truncate">
              {currentProject?.name || 'Tracecase'}
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

        {/* Local Device & Browser Discovery Hub Picker */}
        <div className="relative">
          <button
            onClick={() => setDeviceDropdownOpen(!deviceDropdownOpen)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-xs font-medium"
            title="Select target browser or mobile device for test execution"
          >
            {selectedTarget?.type === 'emulation' ? (
              <Smartphone className="w-3.5 h-3.5 text-indigo-500" />
            ) : selectedTarget?.platform === 'android' ? (
              <Smartphone className="w-3.5 h-3.5 text-emerald-500" />
            ) : selectedTarget?.platform === 'ios' ? (
              <Tablet className="w-3.5 h-3.5 text-sky-500" />
            ) : (
              <Globe className="w-3.5 h-3.5 text-brand-500" />
            )}
            <span className="text-slate-800 dark:text-slate-200 font-semibold max-w-[150px] truncate">
              {selectedTarget?.name || 'Local Browser'}
            </span>
            <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400 uppercase">
              {selectedTarget?.type === 'desktop' ? 'LOCAL' : selectedTarget?.type || 'EMU'}
            </span>
            <ChevronDown className="w-3 h-3 text-slate-400" />
          </button>

          {deviceDropdownOpen && (
            <div className="absolute left-0 mt-1.5 w-80 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xl p-2 z-50 animate-in fade-in zoom-in-95">
              <div className="px-3 py-1.5 flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2">
                <span className="text-xs font-bold text-slate-900 dark:text-slate-100">
                  Target Device & Browser Hub
                </span>
                <button
                  onClick={loadDevices}
                  className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-slate-600"
                  title="Rescan local hardware"
                >
                  <RefreshCw className="w-3 h-3" />
                </button>
              </div>

              {/* Sub-tabs */}
              <div className="grid grid-cols-4 gap-1 p-1 bg-slate-100 dark:bg-slate-800/60 rounded-xl my-2 text-[10px] font-bold">
                <button
                  onClick={() => setDeviceTab('desktop')}
                  className={`py-1 rounded-lg transition-all ${
                    deviceTab === 'desktop'
                      ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-xs'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  Desktop
                </button>
                <button
                  onClick={() => setDeviceTab('emulation')}
                  className={`py-1 rounded-lg transition-all ${
                    deviceTab === 'emulation'
                      ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-xs'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  Mobile Emu
                </button>
                <button
                  onClick={() => setDeviceTab('adb')}
                  className={`py-1 rounded-lg transition-all ${
                    deviceTab === 'adb'
                      ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-xs'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  ADB ({availableDevices?.adb?.devices?.length || 0})
                </button>
                <button
                  onClick={() => setDeviceTab('simulator')}
                  className={`py-1 rounded-lg transition-all ${
                    deviceTab === 'simulator'
                      ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-xs'
                      : 'text-slate-500 hover:text-slate-800'
                  }`}
                >
                  iOS Sim
                </button>
              </div>

              {/* Tab Contents */}
              <div className="max-h-56 overflow-y-auto space-y-1 p-1">
                {deviceTab === 'desktop' &&
                  availableDevices?.browsers?.map((b) => (
                    <button
                      key={b.id}
                      onClick={() => {
                        setSelectedTarget(b);
                        setDeviceDropdownOpen(false);
                      }}
                      className={`w-full text-left p-2 rounded-xl text-xs flex items-center justify-between transition-colors ${
                        selectedTarget?.id === b.id
                          ? 'bg-brand-50 dark:bg-brand-950/40 text-brand-700 dark:text-brand-300 font-semibold'
                          : 'hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <Globe className="w-3.5 h-3.5 text-brand-500" />
                        <div>
                          <div>{b.name}</div>
                          <div className="text-[10px] text-slate-400 font-normal">{b.engine}</div>
                        </div>
                      </div>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 font-semibold">
                        Ready
                      </span>
                    </button>
                  ))}

                {deviceTab === 'emulation' &&
                  availableDevices?.mobile_emulation_presets?.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => {
                        setSelectedTarget({ ...p, type: 'emulation' });
                        setDeviceDropdownOpen(false);
                      }}
                      className={`w-full text-left p-2 rounded-xl text-xs flex items-center justify-between transition-colors ${
                        selectedTarget?.id === p.id
                          ? 'bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 font-semibold'
                          : 'hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300'
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <Smartphone className="w-3.5 h-3.5 text-indigo-500" />
                        <div>
                          <div>{p.name}</div>
                          <div className="text-[10px] text-slate-400 font-normal">
                            {p.viewport.width}x{p.viewport.height} ({p.platform})
                          </div>
                        </div>
                      </div>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 font-semibold">
                        Preset
                      </span>
                    </button>
                  ))}

                {deviceTab === 'adb' && (
                  <div>
                    {availableDevices?.adb?.devices?.length > 0 ? (
                      availableDevices.adb.devices.map((d) => (
                        <button
                          key={d.id}
                          onClick={() => {
                            setSelectedTarget(d);
                            setDeviceDropdownOpen(false);
                          }}
                          className={`w-full text-left p-2 rounded-xl text-xs flex items-center justify-between transition-colors ${
                            selectedTarget?.id === d.id
                              ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 font-semibold'
                              : 'hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300'
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <Smartphone className="w-3.5 h-3.5 text-emerald-500" />
                            <div>
                              <div>{d.name}</div>
                              <div className="text-[10px] text-slate-400 font-normal">{d.id}</div>
                            </div>
                          </div>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 font-semibold">
                            {d.status}
                          </span>
                        </button>
                      ))
                    ) : (
                      <div className="p-4 text-center text-slate-400 text-xs">
                        No physical Android devices connected via ADB.
                      </div>
                    )}
                  </div>
                )}

                {deviceTab === 'simulator' && (
                  <div>
                    {availableDevices?.simulators?.simulators?.length > 0 ? (
                      availableDevices.simulators.simulators.map((s) => (
                        <button
                          key={s.id}
                          onClick={() => {
                            setSelectedTarget(s);
                            setDeviceDropdownOpen(false);
                          }}
                          className={`w-full text-left p-2 rounded-xl text-xs flex items-center justify-between transition-colors ${
                            selectedTarget?.id === s.id
                              ? 'bg-sky-50 dark:bg-sky-950/40 text-sky-700 dark:text-sky-300 font-semibold'
                              : 'hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300'
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <Tablet className="w-3.5 h-3.5 text-sky-500" />
                            <div>
                              <div>{s.name}</div>
                              <div className="text-[10px] text-slate-400 font-normal">{s.os}</div>
                            </div>
                          </div>
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-50 dark:bg-sky-950 text-sky-600 dark:text-sky-400 font-semibold">
                            {s.status}
                          </span>
                        </button>
                      ))
                    ) : (
                      <div className="p-4 text-center text-slate-400 text-xs">
                        No active iOS Simulators booted.
                      </div>
                    )}
                  </div>
                )}
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
