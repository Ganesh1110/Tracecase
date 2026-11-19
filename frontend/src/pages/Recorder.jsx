import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Video,
  Globe,
  CheckCircle2,
  AlertCircle,
  Clock,
  ArrowRight,
  Loader2,
  StopCircle,
  Pause,
  Play,
  FolderKanban,
  Activity,
  Layers,
  Bug,
  Radio,
} from 'lucide-react';
import { api } from '../services/api';
import { useWebSocket } from '../context/WebSocketContext';
import { useToast } from '../context/ToastContext';
import { useProject } from '../context/ProjectContext';

export function Recorder() {
  const [url, setUrl] = useState('');
  const [name, setName] = useState('');
  const [browser, setBrowser] = useState('chromium');
  const [headless, setHeadless] = useState(false);
  const [status, setStatus] = useState({ status: 'idle' });
  const [liveSteps, setLiveSteps] = useState([]);
  const [loading, setLoading] = useState(false);
  const [pauseLoading, setPauseLoading] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const { subscribe } = useWebSocket();
  const { showToast } = useToast();
  const { projects, currentProject } = useProject();
  const [selectedProjectId, setSelectedProjectId] = useState(currentProject?.id || 'default_project');
  const navigate = useNavigate();
  const timerRef = useRef(null);

  useEffect(() => {
    if (currentProject?.id && !selectedProjectId) {
      setSelectedProjectId(currentProject.id);
    }
  }, [currentProject]);

  const fetchStatus = async () => {
    try {
      const data = await api.getRecordingStatus();
      setStatus(data);
      if (data.steps && Array.isArray(data.steps)) {
        setLiveSteps(data.steps);
      }
      if (data.elapsed_seconds !== undefined) {
        setElapsedSeconds(data.elapsed_seconds);
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 2500);
    return () => clearInterval(interval);
  }, []);

  // Timer loop when actively recording
  useEffect(() => {
    if (status.status === 'recording') {
      timerRef.current = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [status.status]);

  useEffect(() => {
    const unsubRecorder = subscribe('recorder', (event) => {
      fetchStatus();
    });
    const unsubStep = subscribe('recording_step', (event) => {
      if (event?.data?.step) {
        setLiveSteps((prev) => {
          const exists = prev.some((s) => s.number === event.data.step.number);
          if (exists) return prev;
          return [...prev, event.data.step];
        });
      }
      fetchStatus();
    });
    return () => {
      unsubRecorder();
      unsubStep();
    };
  }, [subscribe]);

  const handleStart = async (e) => {
    e.preventDefault();
    if (!url.trim()) {
      showToast('Please enter a target URL', 'error');
      return;
    }
    try {
      setLoading(true);
      setLiveSteps([]);
      setElapsedSeconds(0);
      const session = await api.startRecording({
        url: url.trim(),
        name: name.trim() || undefined,
        browser,
        headless,
        timeout: 30000,
        project_id: selectedProjectId || 'default_project',
      });
      setStatus(session);
      showToast('Recording session launched!', 'success');
    } catch (err) {
      showToast('Failed to start recorder: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async () => {
    try {
      setPauseLoading(true);
      const res = await api.pauseRecording();
      setStatus(res);
      showToast('Recording paused', 'info');
    } catch (err) {
      showToast('Failed to pause recording: ' + err.message, 'error');
    } finally {
      setPauseLoading(false);
    }
  };

  const handleResume = async () => {
    try {
      setPauseLoading(true);
      const res = await api.resumeRecording();
      setStatus(res);
      showToast('Recording resumed', 'success');
    } catch (err) {
      showToast('Failed to resume recording: ' + err.message, 'error');
    } finally {
      setPauseLoading(false);
    }
  };

  const handleStop = async () => {
    try {
      setLoading(true);
      showToast('Finalizing recording and saving test case...', 'info');
      const res = await api.stopRecording();
      setStatus(res);
      showToast('Recording finalized and test case generated!', 'success');
      if (res.testcase_id) {
        navigate(`/testcases/${res.testcase_id}`);
      }
    } catch (err) {
      showToast('Failed to stop recording: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const isRecording = status.status === 'recording';
  const isPaused = status.status === 'paused';
  const isActive = isRecording || isPaused;

  const formatTimer = (secs) => {
    const mins = Math.floor(secs / 60);
    const remainderSecs = secs % 60;
    return `${mins.toString().padStart(2, '0')}:${remainderSecs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2.5">
            <Video className="w-6 h-6 text-rose-500" />
            <span>Browser Recorder Workspace</span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Launch a real browser instance, interact with elements, and record reproducible test cases.
          </p>
        </div>

        {/* Live Active Pill Indicator */}
        {isActive && (
          <div className="flex items-center gap-3 bg-white dark:bg-surface-cardDark px-4 py-2 rounded-xl border border-slate-200 dark:border-surface-borderDark shadow-sm">
            <span className="relative flex h-3 w-3">
              {isRecording && (
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
              )}
              <span
                className={`relative inline-flex rounded-full h-3 w-3 ${
                  isRecording ? 'bg-rose-500' : 'bg-amber-500'
                }`}
              ></span>
            </span>
            <div className="text-xs">
              <span className="font-semibold text-slate-800 dark:text-slate-200 uppercase tracking-wider">
                {isRecording ? 'Recording Live' : 'Paused'}
              </span>
              <span className="text-slate-400 ml-2 font-mono">
                {formatTimer(elapsedSeconds)}
              </span>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Configuration & Controls */}
        <div className="lg:col-span-2 space-y-6">
          <div className="p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
            <h2 className="text-base font-bold text-slate-900 dark:text-white mb-4 flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Radio className="w-5 h-5 text-rose-500" />
                <span>Session Configuration</span>
              </span>
              {isActive && (
                <span className="text-xs font-mono text-slate-400">
                  Session: {status.session_id}
                </span>
              )}
            </h2>

            <form onSubmit={handleStart} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                  Target Application URL <span className="text-rose-500">*</span>
                </label>
                <div className="relative">
                  <Globe className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
                  <input
                    type="text"
                    placeholder="https://example.com or http://localhost:3000"
                    value={url}
                    onChange={(e) => setUrl(e.target.value)}
                    disabled={isActive}
                    className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                    Test Case Name
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. User Signup & Onboarding"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    disabled={isActive}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
                    <FolderKanban className="w-3.5 h-3.5 text-slate-400" />
                    <span>Target Project</span>
                  </label>
                  <select
                    value={selectedProjectId}
                    onChange={(e) => setSelectedProjectId(e.target.value)}
                    disabled={isActive}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                  >
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                    Browser Engine
                  </label>
                  <select
                    value={browser}
                    onChange={(e) => setBrowser(e.target.value)}
                    disabled={isActive}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                  >
                    <option value="chromium">Chromium</option>
                    <option value="firefox">Firefox</option>
                    <option value="webkit">WebKit (Safari)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                    Window Mode
                  </label>
                  <select
                    value={headless ? 'headless' : 'headed'}
                    onChange={(e) => setHeadless(e.target.value === 'headless')}
                    disabled={isActive}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                  >
                    <option value="headed">Headed (Interactive Window)</option>
                    <option value="headless">Headless (Background)</option>
                  </select>
                </div>
              </div>

              <div className="pt-3 flex flex-wrap items-center justify-end gap-3 border-t border-slate-100 dark:border-slate-800">
                {isActive ? (
                  <>
                    {isRecording ? (
                      <button
                        type="button"
                        onClick={handlePause}
                        disabled={pauseLoading}
                        className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold bg-amber-500 hover:bg-amber-400 text-white transition-all shadow-sm"
                      >
                        <Pause className="w-4 h-4" />
                        <span>Pause Recording</span>
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={handleResume}
                        disabled={pauseLoading}
                        className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition-all shadow-sm"
                      >
                        <Play className="w-4 h-4" />
                        <span>Resume Recording</span>
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={handleStop}
                      disabled={loading}
                      className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-bold bg-rose-600 hover:bg-rose-500 text-white shadow-md shadow-rose-600/25 transition-all"
                    >
                      {loading ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          <span>Finalizing...</span>
                        </>
                      ) : (
                        <>
                          <StopCircle className="w-4 h-4" />
                          <span>Stop & Save Test Case</span>
                        </>
                      )}
                    </button>
                  </>
                ) : (
                  <button
                    type="submit"
                    disabled={loading}
                    className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-bold bg-rose-600 hover:bg-rose-500 text-white shadow-md shadow-rose-600/25 transition-all disabled:opacity-50"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Launching Browser...</span>
                      </>
                    ) : (
                      <>
                        <Video className="w-4 h-4" />
                        <span>Start Recording Session</span>
                      </>
                    )}
                  </button>
                )}
              </div>
            </form>
          </div>

          {/* Live Action Stream Panel */}
          <div className="p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Layers className="w-5 h-5 text-brand-500" />
                <span>Captured Action Stream</span>
              </h3>
              <span className="text-xs px-2.5 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-semibold">
                {liveSteps.length} {liveSteps.length === 1 ? 'Step' : 'Steps'}
              </span>
            </div>

            {liveSteps.length === 0 ? (
              <div className="text-center py-10 px-4 border border-dashed border-slate-200 dark:border-slate-800 rounded-xl">
                <Activity className="w-8 h-8 text-slate-400 mx-auto mb-2 opacity-50" />
                <p className="text-sm font-medium text-slate-600 dark:text-slate-400">
                  {isActive
                    ? 'Browser open. Interact with the page to record actions.'
                    : 'Start a session to stream user actions in real-time.'}
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  Clicks, inputs, navigations, and hover events are captured automatically.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5 max-h-[420px] overflow-y-auto pr-1">
                {liveSteps.map((step, idx) => (
                  <div
                    key={step.number || idx}
                    className="p-3 rounded-xl border border-slate-100 dark:border-slate-800/80 bg-slate-50/50 dark:bg-slate-900/40 flex items-start gap-3 hover:border-slate-200 transition-all"
                  >
                    <span className="w-6 h-6 rounded-full bg-brand-500/10 text-brand-600 dark:text-brand-400 font-bold text-xs flex items-center justify-center shrink-0 mt-0.5">
                      {step.number || idx + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 text-[10px] font-bold rounded uppercase bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                          {step.action_type || 'action'}
                        </span>
                        <span className="text-xs font-medium text-slate-900 dark:text-slate-100 truncate">
                          {step.description_short || step.action_type}
                        </span>
                      </div>
                      {(step.element?.selector || step.selector) && (
                        <p className="text-[11px] font-mono text-slate-500 dark:text-slate-400 truncate mt-1">
                          {step.element?.selector || step.selector}
                        </p>
                      )}
                      {step.input_value && (
                        <p className="text-[11px] text-slate-600 dark:text-slate-300 mt-0.5">
                          Value: <span className="font-mono bg-white dark:bg-slate-800 px-1 py-0.5 rounded border border-slate-200 dark:border-slate-700">{step.input_value}</span>
                        </p>
                      )}
                      {step.url && (
                        <p className="text-[11px] text-brand-500 dark:text-brand-400 truncate mt-0.5">
                          {step.url}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: Live Session Status & Metrics */}
        <div className="space-y-6">
          <div className="p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
            <h3 className="text-base font-bold text-slate-900 dark:text-white mb-4">
              Session Metrics
            </h3>

            <div className="space-y-3">
              <div className="p-3.5 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 flex items-center justify-between">
                <span className="text-xs text-slate-500 flex items-center gap-1.5">
                  <Activity className="w-4 h-4 text-brand-500" />
                  Status
                </span>
                <span
                  className={`px-2.5 py-0.5 rounded-full text-xs font-semibold capitalize ${
                    status.status === 'recording'
                      ? 'bg-rose-50 dark:bg-rose-950/60 text-rose-500 border border-rose-200 dark:border-rose-800 animate-pulse'
                      : status.status === 'paused'
                      ? 'bg-amber-50 dark:bg-amber-950/60 text-amber-500 border border-amber-200 dark:border-amber-800'
                      : status.status === 'completed'
                      ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-500 border border-emerald-200 dark:border-emerald-800'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-400'
                  }`}
                >
                  {status.status || 'idle'}
                </span>
              </div>

              <div className="p-3.5 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 flex items-center justify-between">
                <span className="text-xs text-slate-500 flex items-center gap-1.5">
                  <Clock className="w-4 h-4 text-blue-500" />
                  Elapsed Time
                </span>
                <span className="text-xs font-mono font-semibold text-slate-800 dark:text-slate-200">
                  {formatTimer(elapsedSeconds)}
                </span>
              </div>

              <div className="p-3.5 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 flex items-center justify-between">
                <span className="text-xs text-slate-500 flex items-center gap-1.5">
                  <Layers className="w-4 h-4 text-purple-500" />
                  Captured Steps
                </span>
                <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
                  {liveSteps.length || status.steps_count || 0}
                </span>
              </div>

              <div className="p-3.5 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 flex items-center justify-between">
                <span className="text-xs text-slate-500 flex items-center gap-1.5">
                  <Bug className="w-4 h-4 text-rose-500" />
                  Console Errors
                </span>
                <span className={`text-xs font-semibold ${status.console_errors_count ? 'text-rose-500' : 'text-slate-400'}`}>
                  {status.console_errors_count || 0}
                </span>
              </div>

              <div className="p-3.5 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 flex items-center justify-between">
                <span className="text-xs text-slate-500 flex items-center gap-1.5">
                  <Globe className="w-4 h-4 text-indigo-500" />
                  Network Requests
                </span>
                <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  {status.network_requests_count || 0}
                </span>
              </div>
            </div>

            {isActive && (
              <div className="mt-4 p-3.5 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300 text-xs leading-relaxed">
                Interact with the browser window to record actions. When done, click <strong>Stop & Save</strong> to generate the test case.
              </div>
            )}

            {status.status === 'completed' && status.testcase_id && (
              <button
                onClick={() => navigate(`/testcases/${status.testcase_id}`)}
                className="mt-4 flex items-center justify-center gap-2 w-full py-2.5 text-xs font-bold rounded-xl bg-brand-600 hover:bg-brand-500 text-white shadow-md shadow-brand-500/20 transition-all"
              >
                <span>View Recorded Test Case</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
