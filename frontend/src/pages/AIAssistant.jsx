import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Sparkles, Send, Bot, User, Loader2, Database, ShieldAlert, Cpu } from 'lucide-react';
import { api } from '../services/api';
import { useToast } from '../context/ToastContext';

export function AIAssistant() {
  const [searchParams] = useSearchParams();
  const focusedCaseId = searchParams.get('caseId');
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        'Hello! I am your QA Auto AI Assistant. I can inspect your test repository, suggest missing edge-case assertions, analyze risk areas, and recommend negative test scenarios. How can I help you today?',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [contextMatches, setContextMatches] = useState([]);
  const messagesEndRef = useRef(null);
  const { showToast } = useToast();

  useEffect(() => {
    if (focusedCaseId) {
      setInput(`Can you analyze test case "${focusedCaseId}" and suggest resilient assertions?`);
    }
  }, [focusedCaseId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMsg = { role: 'user', content: input.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await api.sendAIChat({
        prompt: userMsg.content,
        testcase_id: focusedCaseId || undefined,
        conversation_history: messages.slice(-6),
      });

      setMessages((prev) => [...prev, { role: 'assistant', content: res.reply }]);
      if (res.context_matches?.length > 0) {
        setContextMatches(res.context_matches);
      }
    } catch (err) {
      showToast('AI request failed: ' + err.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  const samplePrompts = [
    'How do I test my checkout flow against slow networks?',
    'Suggest boundary and negative assertions for login inputs.',
    'Explain how heuristic selector self-healing works in QA Auto.',
    'What test coverage gaps exist across my recorded flows?',
  ];

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2.5">
          <Sparkles className="w-6 h-6 text-brand-500" />
          <span>AI Test Assistant</span>
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          Autonomous QA reasoning agent connected directly to your indexed test repository.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 h-[680px]">
        {/* Main Chat Pane */}
        <div className="lg:col-span-3 rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm flex flex-col overflow-hidden">
          {/* Chat Messages */}
          <div className="flex-1 overflow-y-auto p-5 space-y-4">
            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex gap-3 text-sm leading-relaxed ${
                  msg.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                {msg.role !== 'user' && (
                  <div className="w-8 h-8 rounded-xl bg-brand-50 dark:bg-brand-950/60 text-brand-500 flex items-center justify-center shrink-0 mt-0.5">
                    <Bot className="w-4 h-4" />
                  </div>
                )}
                <div
                  className={`p-4 rounded-2xl max-w-2xl whitespace-pre-wrap ${
                    msg.role === 'user'
                      ? 'bg-brand-600 text-white shadow-md shadow-brand-600/20'
                      : 'bg-slate-100 dark:bg-slate-800/80 text-slate-800 dark:text-slate-100 border border-slate-200 dark:border-slate-700/60'
                  }`}
                >
                  {msg.content}
                </div>
                {msg.role === 'user' && (
                  <div className="w-8 h-8 rounded-xl bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-200 flex items-center justify-center shrink-0 mt-0.5">
                    <User className="w-4 h-4" />
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div className="flex gap-3 text-sm">
                <div className="w-8 h-8 rounded-xl bg-brand-50 dark:bg-brand-950/60 text-brand-500 flex items-center justify-center shrink-0">
                  <Bot className="w-4 h-4" />
                </div>
                <div className="p-4 rounded-2xl bg-slate-100 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700/60 flex items-center gap-2 text-slate-500 text-xs">
                  <Loader2 className="w-4 h-4 animate-spin text-brand-500" />
                  <span>Consulting test repository & synthesizing insights...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Suggestion Pills */}
          <div className="px-5 py-2.5 border-t border-slate-100 dark:border-slate-800 flex gap-2 overflow-x-auto">
            {samplePrompts.map((p, i) => (
              <button
                key={i}
                onClick={() => setInput(p)}
                className="px-3 py-1 text-xs rounded-full bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 whitespace-nowrap transition-colors"
              >
                {p}
              </button>
            ))}
          </div>

          {/* Input Form */}
          <form
            onSubmit={handleSend}
            className="p-4 border-t border-slate-200 dark:border-surface-borderDark flex items-center gap-3 bg-slate-50/50 dark:bg-slate-900/30"
          >
            <input
              type="text"
              placeholder="Ask QA Auto Assistant anything about your tests or coverage..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              className="flex-1 px-4 py-2.5 text-sm rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-brand-500"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="px-4 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs flex items-center gap-2 shadow-md shadow-brand-500/20 disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
              <span>Send</span>
            </button>
          </form>
        </div>

        {/* Right: Retrieved Context & Insights */}
        <div className="rounded-2xl border border-slate-200 dark:border-surface-borderDark bg-white dark:bg-surface-cardDark shadow-sm p-5 flex flex-col overflow-hidden">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3 flex items-center gap-2">
            <Database className="w-4 h-4 text-brand-500" />
            <span>Repository Context</span>
          </h3>

          <div className="flex-1 overflow-y-auto space-y-3 text-xs text-slate-600 dark:text-slate-400">
            {contextMatches.length === 0 ? (
              <p className="italic text-slate-400">
                Relevant indexed test cases and step snippets matched from your queries will be referenced here.
              </p>
            ) : (
              contextMatches.map((m, i) => (
                <div
                  key={i}
                  className="p-3 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50"
                >
                  <div className="font-bold text-slate-900 dark:text-white truncate">{m.name}</div>
                  <div className="text-[11px] font-mono text-slate-400 truncate mt-0.5">{m.start_url}</div>
                  {m.match_snippet && (
                    <div className="mt-2 text-[11px] text-slate-500 line-clamp-3 bg-white dark:bg-slate-900 p-2 rounded border border-slate-200 dark:border-slate-800">
                      {m.match_snippet.replace(/\[\/?b\]/g, '')}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
