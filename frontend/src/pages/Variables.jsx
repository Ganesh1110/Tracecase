import React, { useEffect, useState, useRef } from 'react';
import {
  Variable,
  Lock,
  Eye,
  EyeOff,
  Copy,
  Plus,
  Trash2,
  Database,
  FileCode,
  Layers,
  Sparkles,
  ShieldCheck,
  RefreshCw,
  Clock,
  Play,
  Terminal,
  Check,
  Loader2,
  X,
  Search,
  KeyRound,
  FileJson,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';
import { useProject } from '../context/ProjectContext';

export function Variables() {
  const { currentProject } = useProject();
  const { showToast } = useToast();

  const [activeTab, setActiveTab] = useState('variables'); // 'variables' | 'totp' | 'db' | 'schemas'
  const [selectedEnv, setSelectedEnv] = useState('all'); // 'all' | 'global' | 'local' | 'staging' | 'production'
  const [search, setSearch] = useState('');

  // Variables State
  const [variables, setVariables] = useState([]);
  const [loadingVars, setLoadingVars] = useState(true);
  const [showSecrets, setShowSecrets] = useState({});

  // New Variable Modal / Form
  const [isNewVarOpen, setIsNewVarOpen] = useState(false);
  const [varKey, setVarKey] = useState('');
  const [varValue, setVarValue] = useState('');
  const [varType, setVarType] = useState('string'); // 'string' | 'secret' | 'totp'
  const [varEnv, setVarEnv] = useState('global');
  const [varDesc, setVarDesc] = useState('');

  // TOTP Live Generator
  const [liveTotpCodes, setLiveTotpCodes] = useState({});
  const [totpRemaining, setTotpRemaining] = useState(30);

  // Database Connections State
  const [dbConnections, setDbConnections] = useState([]);
  const [loadingDb, setLoadingDb] = useState(false);
  const [isNewDbOpen, setIsNewDbOpen] = useState(false);
  const [dbName, setDbName] = useState('');
  const [dbType, setDbType] = useState('sqlite');
  const [dbConnStr, setDbConnStr] = useState('');
  const [dbDesc, setDbDesc] = useState('');

  // DB Query Playground
  const [selectedConnId, setSelectedConnId] = useState('');
  const [testQuery, setTestQuery] = useState('SELECT * FROM projects LIMIT 5;');
  const [queryResult, setQueryResult] = useState(null);
  const [queryLoading, setQueryLoading] = useState(false);

  // Schemas State
  const [schemas, setSchemas] = useState([]);
  const [loadingSchemas, setLoadingSchemas] = useState(false);
  const [isNewSchemaOpen, setIsNewSchemaOpen] = useState(false);
  const [schemaName, setSchemaName] = useState('');
  const [schemaJson, setSchemaJson] = useState('{\n  "type": "object",\n  "required": ["id", "status"],\n  "properties": {\n    "id": { "type": "string" },\n    "status": { "type": "string" }\n  }\n}');
  const [schemaDesc, setSchemaDesc] = useState('');

  // Load data
  const loadVariables = async () => {
    try {
      setLoadingVars(true);
      const data = await api.getVariables({
        project_id: currentProject?.id || 'default_project',
        environment: selectedEnv !== 'all' ? selectedEnv : undefined,
      });
      setVariables(data || []);
      // Pre-populate TOTP codes
      const map = {};
      data.forEach((v) => {
        if (v.var_type === 'totp' && v.current_totp) {
          map[v.id] = v.current_totp;
        }
      });
      setLiveTotpCodes(map);
    } catch (err) {
      showToast('Failed to load variables: ' + err.message, 'error');
    } finally {
      setLoadingVars(false);
    }
  };

  const loadDbConnections = async () => {
    try {
      setLoadingDb(true);
      const data = await api.getDbConnections(currentProject?.id || 'default_project');
      setDbConnections(data || []);
      if (data && data.length > 0 && !selectedConnId) {
        setSelectedConnId(data[0].id);
      }
    } catch (err) {
      showToast('Failed to load database connections: ' + err.message, 'error');
    } finally {
      setLoadingDb(false);
    }
  };

  const loadSchemas = async () => {
    try {
      setLoadingSchemas(true);
      const data = await api.getResponseSchemas(currentProject?.id || 'default_project');
      setSchemas(data || []);
    } catch (err) {
      showToast('Failed to load schemas: ' + err.message, 'error');
    } finally {
      setLoadingSchemas(false);
    }
  };

  useEffect(() => {
    loadVariables();
    loadDbConnections();
    loadSchemas();
  }, [currentProject?.id, selectedEnv]);

  // Live TOTP Refresh Clock (30s interval)
  useEffect(() => {
    const timer = setInterval(() => {
      const now = Math.floor(Date.now() / 1000);
      const rem = 30 - (now % 30);
      setTotpRemaining(rem);
      if (rem === 30 || rem === 1) {
        loadVariables();
      }
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const handleSaveVariable = async (e) => {
    e.preventDefault();
    if (!varKey.trim() || !varValue.trim()) return;
    try {
      await api.saveVariable({
        key: varKey.trim(),
        value: varValue.trim(),
        var_type: varType,
        environment: varEnv,
        is_secret: varType === 'secret' || varType === 'totp',
        description: varDesc.trim(),
        project_id: currentProject?.id || 'default_project',
      });
      showToast(`Variable {{${varKey.trim()}}} saved to vault!`, 'success');
      setVarKey('');
      setVarValue('');
      setVarDesc('');
      setIsNewVarOpen(false);
      loadVariables();
    } catch (err) {
      showToast('Failed to save variable: ' + err.message, 'error');
    }
  };

  const handleDeleteVariable = async (varId, keyName) => {
    if (!confirm(`Delete variable "{{${keyName}}}"?`)) return;
    try {
      await api.deleteVariable(varId);
      showToast('Variable deleted', 'info');
      loadVariables();
    } catch (err) {
      showToast('Failed to delete: ' + err.message, 'error');
    }
  };

  const handleSaveDb = async (e) => {
    e.preventDefault();
    if (!dbName.trim() || !dbConnStr.trim()) return;
    try {
      await api.saveDbConnection({
        name: dbName.trim(),
        db_type: dbType,
        connection_string: dbConnStr.trim(),
        description: dbDesc.trim(),
        project_id: currentProject?.id || 'default_project',
      });
      showToast('Database connection saved', 'success');
      setDbName('');
      setDbConnStr('');
      setDbDesc('');
      setIsNewDbOpen(false);
      loadDbConnections();
    } catch (err) {
      showToast('Failed to save connection: ' + err.message, 'error');
    }
  };

  const handleDeleteDb = async (connId) => {
    if (!confirm('Delete this database connection?')) return;
    try {
      await api.deleteDbConnection(connId);
      showToast('Connection deleted', 'info');
      loadDbConnections();
    } catch (err) {
      showToast('Failed to delete: ' + err.message, 'error');
    }
  };

  const handleExecuteQuery = async (e) => {
    e.preventDefault();
    if (!selectedConnId || !testQuery.trim()) return;
    try {
      setQueryLoading(true);
      const res = await api.executeDbQuery(selectedConnId, testQuery.trim());
      setQueryResult(res);
      showToast(`Query executed: ${res.row_count} rows returned`, 'success');
    } catch (err) {
      showToast('Query error: ' + err.message, 'error');
      setQueryResult({ error: err.message });
    } finally {
      setQueryLoading(false);
    }
  };

  const handleSaveSchema = async (e) => {
    e.preventDefault();
    if (!schemaName.trim()) return;
    try {
      await api.saveResponseSchema({
        name: schemaName.trim(),
        schema_json: schemaJson,
        description: schemaDesc.trim(),
        project_id: currentProject?.id || 'default_project',
      });
      showToast('Response schema saved for contract testing', 'success');
      setSchemaName('');
      setSchemaDesc('');
      setIsNewSchemaOpen(false);
      loadSchemas();
    } catch (err) {
      showToast('Failed to save schema: ' + err.message, 'error');
    }
  };

  const handleDeleteSchema = async (schemaId) => {
    if (!confirm('Delete this schema?')) return;
    try {
      await api.deleteResponseSchema(schemaId);
      showToast('Schema deleted', 'info');
      loadSchemas();
    } catch (err) {
      showToast('Failed to delete: ' + err.message, 'error');
    }
  };

  const filteredVars = variables.filter((v) => {
    if (activeTab === 'totp' && v.var_type !== 'totp') return false;
    if (activeTab === 'variables' && v.var_type === 'totp') return false;
    if (search.trim()) {
      const q = search.toLowerCase();
      return v.key.toLowerCase().includes(q) || (v.description || '').toLowerCase().includes(q);
    }
    return true;
  });

  return (
    <div className="space-y-4 animate-in fade-in duration-200 select-none">
      {/* ──────────────────────────────────────────────────────────────────────────
          TOP HEADER
          ────────────────────────────────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-3 border-b border-slate-200 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-400">Test Manager</span>
            <span className="text-xs text-slate-500">/</span>
            <h1 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <KeyRound className="w-5 h-5 text-brand-500" />
              Variables &amp; Vault
            </h1>
            <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              100% Local Encrypted
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Manage environment variables, automated 2FA/TOTP seeds, database connections, and response schemas.
          </p>
        </div>

        {/* Global Tabs: Global Variables, TOTP 2FA, DB Connections, Schemas */}
        <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-900 p-1 rounded-xl border border-slate-200 dark:border-slate-800 text-xs font-semibold">
          <button
            type="button"
            onClick={() => setActiveTab('variables')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
              activeTab === 'variables'
                ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm font-bold'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <Variable className="w-3.5 h-3.5 text-brand-500" />
            <span>Variables ({variables.filter((v) => v.var_type !== 'totp').length})</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('totp')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
              activeTab === 'totp'
                ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm font-bold'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <Clock className="w-3.5 h-3.5 text-indigo-400" />
            <span>TOTP 2FA Tokens</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('db')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
              activeTab === 'db'
                ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm font-bold'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <Database className="w-3.5 h-3.5 text-amber-500" />
            <span>DB Connections ({dbConnections.length})</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('schemas')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
              activeTab === 'schemas'
                ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm font-bold'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <FileJson className="w-3.5 h-3.5 text-emerald-500" />
            <span>Schemas ({schemas.length})</span>
          </button>
        </div>
      </div>

      {/* ──────────────────────────────────────────────────────────────────────────
          TAB 1: GLOBAL & ENVIRONMENT VARIABLES
          ────────────────────────────────────────────────────────────────────────── */}
      {activeTab === 'variables' && (
        <div className="space-y-3">
          {/* Action Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm">
            <div className="flex items-center gap-2 flex-1 min-w-[280px]">
              <div className="relative flex-1">
                <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search variables..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full pl-9 pr-3 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:border-brand-500"
                />
              </div>

              {/* Environment Filter */}
              <select
                value={selectedEnv}
                onChange={(e) => setSelectedEnv(e.target.value)}
                className="px-2.5 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-300 font-medium"
              >
                <option value="all">Environment: All</option>
                <option value="global">Global</option>
                <option value="local">Local</option>
                <option value="staging">Staging</option>
                <option value="production">Production</option>
              </select>
            </div>

            <button
              type="button"
              onClick={() => {
                setVarType('string');
                setIsNewVarOpen(true);
              }}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl text-xs font-bold bg-brand-600 hover:bg-brand-500 text-white shadow-sm shadow-brand-600/30 transition-all"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Create Variable</span>
            </button>
          </div>

          {/* Variables Table */}
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm overflow-hidden">
            <div className="grid grid-cols-12 px-4 py-2.5 bg-slate-50 dark:bg-slate-950 border-b border-slate-200 dark:border-slate-800 text-xs font-bold text-slate-500">
              <span className="col-span-3">Variable Key</span>
              <span className="col-span-4">Value</span>
              <span className="col-span-2">Environment</span>
              <span className="col-span-2">Type</span>
              <span className="col-span-1 text-right">Actions</span>
            </div>

            {loadingVars ? (
              <div className="p-8 text-center text-xs text-slate-400">Loading vault...</div>
            ) : filteredVars.length === 0 ? (
              <div className="p-12 text-center text-slate-500 space-y-2">
                <Variable className="w-8 h-8 mx-auto text-slate-400 opacity-50" />
                <p className="text-xs font-medium">No variables match the selected filter.</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {filteredVars.map((v) => {
                  const isMasked = v.is_secret && !showSecrets[v.id];
                  return (
                    <div
                      key={v.id}
                      className="grid grid-cols-12 items-center px-4 py-3 text-xs hover:bg-slate-50 dark:hover:bg-slate-850/50 transition-colors"
                    >
                      {/* Key */}
                      <div className="col-span-3 flex items-center gap-2">
                        <span className="font-mono font-bold text-brand-600 dark:text-brand-400">
                          {`{{${v.key}}}`}
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            navigator.clipboard.writeText(`{{${v.key}}}`);
                            showToast(`Copied {{${v.key}}}`, 'info');
                          }}
                          className="text-slate-400 hover:text-white"
                          title="Copy Token"
                        >
                          <Copy className="w-3 h-3" />
                        </button>
                      </div>

                      {/* Value */}
                      <div className="col-span-4 flex items-center gap-2 min-w-0 pr-3 font-mono">
                        <span className="truncate text-slate-800 dark:text-slate-200">
                          {isMasked ? '••••••••••••••••' : v.value}
                        </span>
                        {v.is_secret && (
                          <button
                            type="button"
                            onClick={() =>
                              setShowSecrets((prev) => ({ ...prev, [v.id]: !prev[v.id] }))
                            }
                            className="text-slate-400 hover:text-white shrink-0"
                          >
                            {isMasked ? <Eye className="w-3 h-3" /> : <EyeOff className="w-3 h-3" />}
                          </button>
                        )}
                      </div>

                      {/* Environment */}
                      <div className="col-span-2">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                          {v.environment || 'global'}
                        </span>
                      </div>

                      {/* Type */}
                      <div className="col-span-2">
                        <span
                          className={`px-2 py-0.5 rounded-lg text-[10px] font-bold uppercase ${
                            v.var_type === 'secret'
                              ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                              : 'bg-brand-500/10 text-brand-400 border border-brand-500/20'
                          }`}
                        >
                          {v.var_type}
                        </span>
                      </div>

                      {/* Actions */}
                      <div className="col-span-1 flex items-center justify-end">
                        <button
                          type="button"
                          onClick={() => handleDeleteVariable(v.id, v.key)}
                          className="p-1 rounded text-slate-400 hover:text-rose-400 hover:bg-slate-800"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          TAB 2: TOTP 2FA LIVE VAULT (Automated MFA Testing)
          ────────────────────────────────────────────────────────────────────────── */}
      {activeTab === 'totp' && (
        <div className="space-y-4">
          <div className="p-4 rounded-2xl border border-indigo-500/30 bg-gradient-to-r from-indigo-950/30 to-slate-900/60 shadow-sm flex items-center justify-between">
            <div className="space-y-1">
              <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider flex items-center gap-1.5">
                <Clock className="w-4 h-4" />
                Automated 2FA / TOTP Authenticator Engine
              </span>
              <p className="text-xs text-slate-300 max-w-2xl leading-relaxed">
                Generates live RFC 6238 time-based one-time passwords entirely on this machine. Test steps can reference{' '}
                <code className="text-indigo-300 font-mono">{'{{totp:variable_name}}'}</code> to automatically inject valid 2FA tokens.
              </p>
            </div>

            {/* Countdown Clock */}
            <div className="flex items-center gap-3 bg-slate-950/80 px-4 py-2 rounded-2xl border border-slate-800 shrink-0">
              <div className="flex flex-col items-center">
                <span className="text-[10px] text-slate-400 uppercase font-mono">Window</span>
                <span className="text-sm font-mono font-bold text-indigo-400">{totpRemaining}s</span>
              </div>
              <button
                type="button"
                onClick={loadVariables}
                className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-white"
                title="Refresh Codes"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {variables
              .filter((v) => v.var_type === 'totp')
              .map((v) => (
                <div
                  key={v.id}
                  className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-xs font-bold text-slate-900 dark:text-white font-mono block">
                        {`{{totp:${v.key}}}`}
                      </span>
                      <span className="text-[11px] text-slate-400">{v.description || '2FA Seed'}</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteVariable(v.id, v.key)}
                      className="text-slate-400 hover:text-rose-400 p-1"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {/* Big Live TOTP Display */}
                  <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 flex items-center justify-between">
                    <span className="text-2xl font-mono font-black tracking-widest text-emerald-400">
                      {v.current_totp || '------'}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(v.current_totp || '');
                        showToast(`Copied 2FA Code: ${v.current_totp}`, 'success');
                      }}
                      className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-1.5 shadow-sm"
                    >
                      <Copy className="w-3 h-3" />
                      <span>Copy Code</span>
                    </button>
                  </div>
                </div>
              ))}

            {/* Create TOTP Seed Card */}
            <div className="p-4 rounded-2xl border border-dashed border-slate-300 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/20 flex flex-col items-center justify-center min-h-[140px] space-y-2">
              <Clock className="w-6 h-6 text-indigo-400 opacity-60" />
              <button
                type="button"
                onClick={() => {
                  setVarType('totp');
                  setIsNewVarOpen(true);
                }}
                className="text-xs font-bold text-indigo-500 hover:underline"
              >
                + Register New 2FA / TOTP Seed
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          TAB 3: DATABASE CONNECTIONS & LOCAL QUERY RUNNER
          ────────────────────────────────────────────────────────────────────────── */}
      {activeTab === 'db' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm">
            <div>
              <h3 className="text-xs font-bold text-slate-900 dark:text-white">
                Stored Database Connections
              </h3>
              <p className="text-[11px] text-slate-500">
                Connect to local SQLite files or databases to query test state during automation assertions.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setIsNewDbOpen(true)}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold bg-amber-600 hover:bg-amber-500 text-white shadow-sm"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Create Connection</span>
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
            {/* Connections List (5 cols) */}
            <div className="lg:col-span-5 space-y-2.5">
              {dbConnections.length === 0 ? (
                <div className="p-8 text-center text-xs text-slate-500 border border-dashed border-slate-200 dark:border-slate-800 rounded-xl">
                  No database connections added yet.
                </div>
              ) : (
                dbConnections.map((conn) => (
                  <div
                    key={conn.id}
                    onClick={() => setSelectedConnId(conn.id)}
                    className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                      selectedConnId === conn.id
                        ? 'border-amber-500 bg-amber-500/10'
                        : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Database className="w-4 h-4 text-amber-500" />
                        <span className="text-xs font-bold text-slate-900 dark:text-white">
                          {conn.name}
                        </span>
                        <span className="px-1.5 py-0.2 text-[9px] font-mono rounded bg-slate-200 dark:bg-slate-800 text-slate-400 uppercase">
                          {conn.db_type}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteDb(conn.id);
                        }}
                        className="text-slate-400 hover:text-rose-400 p-1"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                    <p className="text-[11px] font-mono text-slate-400 truncate mt-1">
                      {conn.connection_string}
                    </p>
                  </div>
                ))
              )}
            </div>

            {/* Query Playground (7 cols) */}
            <div className="lg:col-span-7 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm space-y-3">
              <span className="text-xs font-bold text-slate-900 dark:text-white flex items-center gap-1.5">
                <Terminal className="w-4 h-4 text-brand-500" />
                Query Assertion Playground (Read-Only)
              </span>

              <form onSubmit={handleExecuteQuery} className="space-y-2">
                <textarea
                  rows={3}
                  value={testQuery}
                  onChange={(e) => setTestQuery(e.target.value)}
                  placeholder="SELECT * FROM users WHERE active = 1;"
                  className="w-full p-2.5 text-xs font-mono rounded-xl bg-slate-950 border border-slate-800 text-slate-200 focus:outline-none focus:border-brand-500"
                />
                <div className="flex justify-end">
                  <button
                    type="submit"
                    disabled={queryLoading || !selectedConnId}
                    className="px-3.5 py-1.5 text-xs font-bold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-1.5 disabled:opacity-50"
                  >
                    {queryLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-current" />}
                    <span>Run Query</span>
                  </button>
                </div>
              </form>

              {queryResult && (
                <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-[11px] font-mono space-y-1.5 overflow-x-auto max-h-48">
                  {queryResult.error ? (
                    <span className="text-rose-400">{queryResult.error}</span>
                  ) : (
                    <>
                      <span className="text-emerald-400 block font-bold">
                        &check; {queryResult.row_count} rows returned from &quot;{queryResult.connection_name}&quot;
                      </span>
                      <pre className="text-slate-300">{JSON.stringify(queryResult.rows, null, 2)}</pre>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          TAB 4: RESPONSE SCHEMAS FOR CONTRACT TESTING
          ────────────────────────────────────────────────────────────────────────── */}
      {activeTab === 'schemas' && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm">
            <div>
              <h3 className="text-xs font-bold text-slate-900 dark:text-white">
                API Response Schemas ({schemas.length})
              </h3>
              <p className="text-[11px] text-slate-500">
                Store JSON response schemas once and re-use them for contract assertions across tests.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setIsNewSchemaOpen(true)}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Create Schema</span>
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {schemas.map((s) => (
              <div
                key={s.id}
                className="p-4 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 shadow-sm space-y-2"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <FileJson className="w-4 h-4 text-emerald-500" />
                    {s.name}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleDeleteSchema(s.id)}
                    className="text-slate-400 hover:text-rose-400 p-1"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
                <pre className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-[10px] font-mono text-slate-300 max-h-36 overflow-y-auto">
                  {s.schema_json}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          MODAL: CREATE NEW VARIABLE
          ────────────────────────────────────────────────────────────────────────── */}
      {isNewVarOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-in fade-in">
          <form
            onSubmit={handleSaveVariable}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4"
          >
            <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                {varType === 'totp' ? 'Register TOTP 2FA Seed' : 'Create Variable'}
              </h3>
              <button
                type="button"
                onClick={() => setIsNewVarOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                  Key Name
                </label>
                <input
                  type="text"
                  placeholder="e.g. base_url or my_auth_totp"
                  value={varKey}
                  onChange={(e) => setVarKey(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 font-mono"
                  autoFocus
                />
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                  {varType === 'totp' ? 'Base32 Authenticator Seed' : 'Value'}
                </label>
                <input
                  type="text"
                  placeholder={varType === 'totp' ? 'JBSWY3DPEHPK3PXP' : 'value...'}
                  value={varValue}
                  onChange={(e) => setVarValue(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 font-mono"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                    Environment
                  </label>
                  <select
                    value={varEnv}
                    onChange={(e) => setVarEnv(e.target.value)}
                    className="w-full px-2.5 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800"
                  >
                    <option value="global">Global</option>
                    <option value="local">Local</option>
                    <option value="staging">Staging</option>
                    <option value="production">Production</option>
                  </select>
                </div>
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                    Type
                  </label>
                  <select
                    value={varType}
                    onChange={(e) => setVarType(e.target.value)}
                    className="w-full px-2.5 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800"
                  >
                    <option value="string">String</option>
                    <option value="secret">Secret</option>
                    <option value="totp">TOTP 2FA Seed</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                  Description
                </label>
                <input
                  type="text"
                  placeholder="Optional context"
                  value={varDesc}
                  onChange={(e) => setVarDesc(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setIsNewVarOpen(false)}
                className="px-3 py-1.5 text-xs text-slate-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 text-xs font-bold rounded-lg bg-brand-600 text-white"
              >
                Save Variable
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          MODAL: CREATE DB CONNECTION
          ────────────────────────────────────────────────────────────────────────── */}
      {isNewDbOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-in fade-in">
          <form
            onSubmit={handleSaveDb}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4"
          >
            <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                New Database Connection
              </h3>
              <button
                type="button"
                onClick={() => setIsNewDbOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                  Connection Name
                </label>
                <input
                  type="text"
                  placeholder="e.g. Local Studio SQLite"
                  value={dbName}
                  onChange={(e) => setDbName(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800"
                  autoFocus
                />
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                  Database Type
                </label>
                <select
                  value={dbType}
                  onChange={(e) => setDbType(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800"
                >
                  <option value="sqlite">SQLite (.db / .sqlite file)</option>
                  <option value="postgres">PostgreSQL</option>
                  <option value="mysql">MySQL</option>
                </select>
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                  File Path or Connection String
                </label>
                <input
                  type="text"
                  placeholder={dbType === 'sqlite' ? '.tracecase/studio.db' : 'postgresql://user:pass@localhost:5432/app'}
                  value={dbConnStr}
                  onChange={(e) => setDbConnStr(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 font-mono"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setIsNewDbOpen(false)}
                className="px-3 py-1.5 text-xs text-slate-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 text-xs font-bold rounded-lg bg-amber-600 text-white"
              >
                Save Connection
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          MODAL: CREATE SCHEMA
          ────────────────────────────────────────────────────────────────────────── */}
      {isNewSchemaOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-in fade-in">
          <form
            onSubmit={handleSaveSchema}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4"
          >
            <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                New Response Schema
              </h3>
              <button
                type="button"
                onClick={() => setIsNewSchemaOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                  Schema Name
                </label>
                <input
                  type="text"
                  placeholder="e.g. AuthLoginResponseSchema"
                  value={schemaName}
                  onChange={(e) => setSchemaName(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800"
                  autoFocus
                />
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1">
                  JSON Schema
                </label>
                <textarea
                  rows={6}
                  value={schemaJson}
                  onChange={(e) => setSchemaJson(e.target.value)}
                  className="w-full p-2.5 text-xs font-mono rounded-xl bg-slate-950 border border-slate-800 text-slate-200"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setIsNewSchemaOpen(false)}
                className="px-3 py-1.5 text-xs text-slate-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 text-xs font-bold rounded-lg bg-emerald-600 text-white"
              >
                Save Schema
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
