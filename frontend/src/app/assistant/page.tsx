'use client';

import React, { useState, useEffect, useRef, useCallback, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  Bot, Send, RefreshCw, AlertTriangle, Shield,
  ChevronRight, Sparkles, Database, X, Lightbulb,
  User, FileText
} from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  source?: string;
  timestamp: Date;
}

interface AlertSummary {
  id: string;
  alert_type: string;
  severity: string;
  risk_components: { final_risk_score: number };
}

const SUGGESTED_QUESTIONS = [
  'Who are the owners of the involved accounts?',
  'Which banks are involved in this case?',
  'What is the total transaction volume?',
  'Why is this alert suspicious?',
  'What are the recommended resolution steps?',
  'How should I resolve this alert?',
];

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', gap: 4 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
        {!isUser && (
          <>
            <div style={{
              width: 22, height: 22, borderRadius: '50%',
              background: 'rgba(59, 130, 246, 0.2)', border: '1px solid rgba(59, 130, 246, 0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Bot size={12} color="#60a5fa" />
            </div>
            <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', letterSpacing: '0.08em' }}>TRACE-X AI</span>
            {message.source && (
              <span style={{
                fontSize: 9, padding: '1px 6px', borderRadius: 20,
                background: message.source === 'gemini' ? 'rgba(139, 92, 246, 0.15)' : 'rgba(59, 130, 246, 0.12)',
                color: message.source === 'gemini' ? '#a78bfa' : '#60a5fa',
                border: `1px solid ${message.source === 'gemini' ? 'rgba(139, 92, 246, 0.3)' : 'rgba(59, 130, 246, 0.2)'}`,
                fontWeight: 700,
              }}>
                {message.source === 'gemini' ? '✦ Gemini' : 'Heuristic'}
              </span>
            )}
          </>
        )}
        {isUser && (
          <>
            <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', letterSpacing: '0.08em' }}>INVESTIGATOR</span>
            <div style={{
              width: 22, height: 22, borderRadius: '50%',
              background: 'rgba(30, 50, 90, 0.6)', border: '1px solid var(--border-default)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <User size={12} color="#94a3b8" />
            </div>
          </>
        )}
      </div>
      <div
        className={`chat-bubble ${message.role}`}
        style={{ maxWidth: '80%' }}
        dangerouslySetInnerHTML={{
          __html: message.content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/### (.*?)(\n|$)/g, '<h4 style="color:#e8eef8;font-size:13px;margin:8px 0 4px">$1</h4>')
            .replace(/## (.*?)(\n|$)/g, '<h3 style="color:#e8eef8;font-size:14px;margin:10px 0 6px">$1</h3>')
            .replace(/\n/g, '<br/>')
            .replace(/`(.*?)`/g, '<code style="font-family:monospace;background:rgba(0,0,0,0.3);padding:1px 4px;border-radius:3px;color:#93c5fd">$1</code>'),
        }}
      />
      <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
        {message.timestamp.toLocaleTimeString()}
      </span>
    </div>
  );
}

function AssistantPageContent() {
  const searchParams = useSearchParams();
  const urlAlertId = searchParams.get('alert');

  const [alerts, setAlerts] = useState<AlertSummary[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [selectedAlertId, setSelectedAlertId] = useState(urlAlertId || '');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [briefLoading, setBriefLoading] = useState(false);
  const [qaLoading, setQaLoading] = useState(false);
  const [error, setError] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, scrollToBottom]);

  // Load alerts
  useEffect(() => {
    fetch(`${API}/api/v1/alerts?limit=50`)
      .then(r => r.json())
      .then(d => {
        const list: AlertSummary[] = d.alerts || [];
        setAlerts(list);
        setAlertsLoading(false);
        const targetId = urlAlertId || (list.length > 0 ? list[0].id : '');
        if (targetId && !selectedAlertId) setSelectedAlertId(targetId);
      })
      .catch(() => setAlertsLoading(false));
  }, [urlAlertId, selectedAlertId]);

  // Generate brief when alert selected
  const generateBrief = useCallback(async (alertId: string) => {
    if (!alertId) return;
    setBriefLoading(true);
    setError('');
    setMessages([]);

    try {
      const res = await fetch(`${API}/api/v1/investigations/${alertId}/summary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      setMessages([{
        id: `brief-${Date.now()}`,
        role: 'assistant',
        content: data.summary,
        source: data.source,
        timestamp: new Date(),
      }]);
    } catch (e: any) {
      setError('Failed to generate investigation brief. Check backend connection.');
    } finally {
      setBriefLoading(false);
    }
  }, []);

  const handleAlertChange = (alertId: string) => {
    setSelectedAlertId(alertId);
    setMessages([]);
    setError('');
    if (alertId) generateBrief(alertId);
  };

  const sendQuestion = async (question: string) => {
    if (!question.trim() || !selectedAlertId) return;
    const trimmed = question.trim();
    setInput('');

    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMsg]);
    setQaLoading(true);
    setError('');

    try {
      const res = await fetch(`${API}/api/v1/investigations/${selectedAlertId}/questions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: trimmed }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      setMessages(prev => [...prev, {
        id: `ai-${Date.now()}`,
        role: 'assistant',
        content: data.answer,
        source: data.source,
        timestamp: new Date(),
      }]);
    } catch (e: any) {
      setMessages(prev => [...prev, {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: '⚠ Failed to get response. Please retry.',
        timestamp: new Date(),
      }]);
    } finally {
      setQaLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendQuestion(input);
    }
  };

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', height: 'calc(100vh - 120px)', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div className="page-header" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
              <h1 className="page-title">AI Investigation Assistant</h1>
              <span className="badge badge-info">
                <Sparkles size={9} />
                Evidence-Grounded
              </span>
            </div>
            <p className="page-subtitle">Answers limited to case evidence only. Does not make legal determinations.</p>
          </div>
        </div>
      </div>

      {/* Alert selector */}
      <div className="glass-card" style={{ padding: '12px 16px', marginBottom: 16, flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <Database size={13} style={{ color: 'var(--text-tertiary)', flexShrink: 0 }} />
          <select
            className="select"
            value={selectedAlertId}
            onChange={e => handleAlertChange(e.target.value)}
            style={{ flex: 1, minWidth: 200 }}
            aria-label="Select alert for investigation"
          >
            <option value="">— Select an alert to investigate —</option>
            {alerts.map(a => (
              <option key={a.id} value={a.id}>
                {a.severity} · {a.alert_type.replace(/_/g, ' ')} · Risk {a.risk_components?.final_risk_score?.toFixed(0) || '?'} · ···{a.id.slice(-10)}
              </option>
            ))}
          </select>
          {selectedAlertId && (
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => generateBrief(selectedAlertId)}
              disabled={briefLoading}
              aria-label="Regenerate investigation brief"
            >
              <RefreshCw size={12} style={{ transform: briefLoading ? 'rotate(360deg)' : 'none', transition: 'transform 0.5s' }} />
              Brief
            </button>
          )}
        </div>
      </div>

      {/* Disclaimer */}
      <div style={{
        padding: '8px 14px', marginBottom: 12, flexShrink: 0,
        background: 'rgba(245, 158, 11, 0.07)',
        border: '1px solid rgba(245, 158, 11, 0.18)',
        borderRadius: 8, fontSize: 11, color: 'var(--text-warning)',
        display: 'flex', gap: 6, alignItems: 'flex-start',
      }}>
        <Shield size={11} style={{ flexShrink: 0, marginTop: 1 }} />
        <span>
          TRACE-X is an investigator decision-support system. All data is SYNTHETIC. Responses are grounded
          in case evidence only. This tool does not determine criminal liability or make regulatory decisions.
        </span>
      </div>

      {/* Chat area */}
      <div
        className="glass-card"
        style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}
      >
        {/* Messages */}
        <div className="chat-messages" style={{ flex: 1, overflowY: 'auto' }}>
          {!selectedAlertId && (
            <div className="empty-state" style={{ flex: 1 }}>
              <Bot size={40} className="empty-state-icon" />
              <div className="empty-state-title">Select an alert to begin</div>
              <div className="empty-state-body">
                Choose an alert above and the AI assistant will generate an evidence-grounded investigation brief.
              </div>
            </div>
          )}

          {briefLoading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '20px 0', alignSelf: 'flex-start' }}>
              <div style={{
                width: 28, height: 28, borderRadius: '50%',
                background: 'rgba(59, 130, 246, 0.15)',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Bot size={14} color="#60a5fa" />
              </div>
              <div style={{ display: 'flex', gap: 4 }}>
                {[0, 1, 2].map(i => (
                  <div key={i} style={{
                    width: 6, height: 6, borderRadius: '50%',
                    background: 'var(--accent)',
                    animation: `dot-bounce 1.2s ease-in-out ${i * 0.2}s infinite`,
                  }} />
                ))}
              </div>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Generating investigation brief…</span>
            </div>
          )}

          {error && (
            <div style={{
              padding: '12px 16px', borderRadius: 10,
              background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
              fontSize: 13, color: '#f87171',
            }}>
              {error}
            </div>
          )}

          {messages.map(msg => <MessageBubble key={msg.id} message={msg} />)}

          {qaLoading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, alignSelf: 'flex-start' }}>
              <div style={{
                width: 28, height: 28, borderRadius: '50%',
                background: 'rgba(59, 130, 246, 0.15)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Bot size={14} color="#60a5fa" />
              </div>
              <div style={{ display: 'flex', gap: 4 }}>
                {[0, 1, 2].map(i => (
                  <div key={i} style={{
                    width: 6, height: 6, borderRadius: '50%',
                    background: 'var(--accent)',
                    animation: `dot-bounce 1.2s ease-in-out ${i * 0.2}s infinite`,
                  }} />
                ))}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Suggested questions */}
        {selectedAlertId && messages.length > 0 && !qaLoading && (
          <div style={{
            padding: '10px 16px',
            borderTop: '1px solid var(--border-subtle)',
            display: 'flex', flexWrap: 'wrap', gap: 6,
            flexShrink: 0,
          }}>
            <span style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 600, letterSpacing: '0.08em', width: '100%' }}>
              <Lightbulb size={9} style={{ marginRight: 4 }} />
              SUGGESTED QUESTIONS
            </span>
            {SUGGESTED_QUESTIONS.map(q => (
              <button
                key={q}
                className="btn btn-ghost btn-sm"
                style={{ fontSize: 11 }}
                onClick={() => sendQuestion(q)}
                aria-label={`Ask: ${q}`}
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {/* Input area */}
        <div style={{
          padding: '12px 16px',
          borderTop: '1px solid var(--border-subtle)',
          display: 'flex', gap: 10, alignItems: 'flex-end',
          flexShrink: 0,
          background: 'rgba(8, 14, 28, 0.5)',
        }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={selectedAlertId ? 'Ask a question about this case…' : 'Select an alert first'}
            disabled={!selectedAlertId || briefLoading || qaLoading}
            rows={2}
            className="input"
            style={{ flex: 1, resize: 'none', lineHeight: 1.5 }}
            aria-label="Ask a question about the case"
          />
          <button
            className="btn btn-primary btn-icon"
            onClick={() => sendQuestion(input)}
            disabled={!input.trim() || !selectedAlertId || qaLoading}
            aria-label="Send question"
          >
            <Send size={15} />
          </button>
        </div>
      </div>

      <style>{`
        @keyframes dot-bounce {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
          30% { transform: translateY(-6px); opacity: 1; }
        }
      `}</style>
    </div>
  );
}

export default function AssistantPage() {
  return (
    <Suspense fallback={<div className="glass-card" style={{ padding: 40, color: 'var(--text-secondary)', textAlign: 'center' }}>Loading AI Assistant…</div>}>
      <AssistantPageContent />
    </Suspense>
  );
}
