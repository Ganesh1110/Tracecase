import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Video,
  Globe,
  Laptop,
  CheckCircle2,
  AlertCircle,
  Clock,
  ArrowRight,
  Loader2,
  FileCode2,
} from 'lucide-react';
import { api } from '../services/api';
import { useWebSocket } from '../context/WebSocketContext';
import { useToast } from '../context/ToastContext';

export function Recorder() {
  const [url, setUrl] = useState('');
  const [name, setName] = useState('');
  const [browser, setBrowser] = useState('chromium');
  const [headless, setHeadless] = useState(false);
  const [status, setStatus] = useState({ status: 'idle' });
  const [loading, setLoading] = useState(false);
  const { subscribe } = useWebSocket();
  const { showToast } = useToast();
  const navigate = useNavigate();

  const fetchStatus = async () => {
    try {
      const data = await api.getRecordingStatus();
      setStatus(data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const unsub = subscribe('recorder', (event) => {
      fetchStatus();
    });
    return unsub;
  }, [subscribe]);

  const handleStart = async (e) => {
    e.preventDefault();
    if (!url.trim()) {
      showToast('Please enter a target URL', 'error');
      return;
    }
    try {
      setLoading(true);
      const session = await api.startRecording({
        url: url.trim(),
        name: name.trim() || undefined,
        browser,
        headless,
        timeout: 30000,
      });
      setStatus(session);
      showToast('Recording session launched!', 'success');
    } catch (err) {
      showToast('Failed to start recorder: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const isRecording = status.status === 'recording';

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          Browser Recorder Workspace
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Launch a real browser instance, interact with elements, and generate structured test cases.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Configuration & Launch */}
        <div className="lg:col-span-2 p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm">
          <h2 className="text-base font-bold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
            <Video className="w-5 h-5 text-rose-500" />
            <span>Session Configuration</span>
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
                  disabled={isRecording}
                  className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                Test Case Name
              </label>
              <input
                type="text"
                placeholder="e.g. User Signup & Onboarding"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={isRecording}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                  Browser Engine
                </label>
                <select
                  value={browser}
                  onChange={(e) => setBrowser(e.target.value)}
                  disabled={isRecording}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                >
                  <option value="chromium">Chromium</option>
                  <option value="firefox">Firefox</option>
                  <option value="webkit">WebKit (Safari)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1.5">
                  Window Display
                </label>
                <select
                  value={headless ? 'headless' : 'headed'}
                  onChange={(e) => setHeadless(e.target.value === 'headless')}
                  disabled={isRecording}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                >
                  <option value="headed">Headed (Interactive Window)</option>
                  <option value="headless">Headless (Background)</option>
                </select>
              </div>
            </div>

            <div className="pt-2 flex items-center justify-end">
              <button
                type="submit"
                disabled={isRecording || loading}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-bold bg-rose-600 hover:bg-rose-500 text-white shadow-md shadow-rose-600/25 transition-all disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Launching Browser...</span>
                  </>
                ) : isRecording ? (
                  <>
                    <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
                    <span>Recording in Progress...</span>
                  </>
                ) : (
                  <>
                    <Video className="w-4 h-4" />
                    <span>Start Recording Session</span>
                  </>
                )}
              </button>
            </div>
          </form>
        </div>

        {/* Right: Live Session Status Monitor */}
        <div className="p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-4">
              Live Session Status
            </h3>

            <div className="p-4 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">Status:</span>
                <span
                  className={`px-2.5 py-0.5 rounded-full text-xs font-semibold capitalize ${
                    status.status === 'recording'
                      ? 'bg-rose-50 dark:bg-rose-950/60 text-rose-500 border border-rose-200 dark:border-rose-800 animate-pulse'
                      : status.status === 'completed'
                      ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-500 border border-emerald-200 dark:border-emerald-800'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-400'
                  }`}
                >
                  {status.status || 'idle'}
                </span>
              </div>

              {status.session_id && (
                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="text-slate-500">Session ID:</span>
                  <span className="text-slate-700 dark:text-slate-300">{status.session_id}</span>
                </div>
              )}

              {status.started_at && (
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500">Started:</span>
                  <span className="text-slate-700 dark:text-slate-300">
                    {new Date(status.started_at).toLocaleTimeString()}
                  </span>
                </div>
              )}

              {status.output_dir && (
                <div className="text-xs font-mono text-slate-400 truncate pt-1 border-t border-slate-200 dark:border-slate-800">
                  {status.output_dir}
                </div>
              )}
            </div>

            {isRecording && (
              <div className="mt-4 p-3 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300 text-xs leading-relaxed">
                Interact with the opened browser window. When finished, click <strong>Stop</strong> on
                the in-browser control panel to save your test case.
              </div>
            )}
          </div>

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
  );
}
