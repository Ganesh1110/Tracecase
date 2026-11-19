import React, { useEffect, useState } from 'react';
import { Settings as SettingsIcon, Save, Server, Monitor, Shield, Check } from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export function Settings() {
  const [settings, setSettings] = useState({
    default_browser: 'chromium',
    default_timeout: '30000',
    ai_provider: 'ollama',
    ai_model: 'llama3',
    ai_api_base: 'http://localhost:11434/v1',
    ai_api_key: '',
    theme: 'dark',
  });
  const [loading, setLoading] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    api.getSettings().then(setSettings).catch(console.error);
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    try {
      setLoading(true);
      await api.updateSettings(settings);
      showToast('Settings saved successfully!', 'success');
    } catch (err) {
      showToast('Failed to save settings: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-300 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
          <SettingsIcon className="w-6 h-6 text-brand-500" />
          <span>Platform Settings</span>
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Configure default test execution parameters, LLM providers, and workspace preferences.
        </p>
      </div>

      <form onSubmit={handleSave} className="space-y-6">
        {/* Browser & Execution */}
        <div className="p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm space-y-4">
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <Monitor className="w-4 h-4 text-brand-500" />
            <span>Browser & Replay Defaults</span>
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Default Browser
              </label>
              <select
                value={settings.default_browser}
                onChange={(e) => setSettings({ ...settings, default_browser: e.target.value })}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200"
              >
                <option value="chromium">Chromium</option>
                <option value="firefox">Firefox</option>
                <option value="webkit">WebKit (Safari)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Default Action Timeout (ms)
              </label>
              <input
                type="number"
                value={settings.default_timeout}
                onChange={(e) => setSettings({ ...settings, default_timeout: e.target.value })}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200"
              />
            </div>
          </div>
        </div>

        {/* AI Model Configuration */}
        <div className="p-6 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm space-y-4">
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <Server className="w-4 h-4 text-purple-500" />
            <span>AI Intelligence Provider</span>
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Provider Type
              </label>
              <select
                value={settings.ai_provider}
                onChange={(e) => setSettings({ ...settings, ai_provider: e.target.value })}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200"
              >
                <option value="ollama">Ollama (Local LLM)</option>
                <option value="openai">OpenAI / Compatible Endpoint (vLLM, LMStudio)</option>
                <option value="null">Deterministic Heuristics Only (Offline)</option>
              </select>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Model Identifier
                </label>
                <input
                  type="text"
                  placeholder="e.g. llama3, qwen2.5-coder, gpt-4o-mini"
                  value={settings.ai_model}
                  onChange={(e) => setSettings({ ...settings, ai_model: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  API Endpoint Base URL
                </label>
                <input
                  type="text"
                  placeholder="e.g. http://localhost:11434"
                  value={settings.ai_api_base}
                  onChange={(e) => setSettings({ ...settings, ai_api_base: e.target.value })}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200 font-mono text-xs"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                API Key (Optional for local servers)
              </label>
              <input
                type="password"
                placeholder="sk-..."
                value={settings.ai_api_key}
                onChange={(e) => setSettings({ ...settings, ai_api_key: e.target.value })}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900 text-slate-800 dark:text-slate-200 font-mono text-xs"
              />
            </div>
          </div>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={loading}
            className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-bold bg-brand-600 hover:bg-brand-500 text-white shadow-md shadow-brand-500/20 disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            <span>Save Settings</span>
          </button>
        </div>
      </form>
    </div>
  );
}
