'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Bot, Send, FileText, AlertCircle, Loader2 } from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Message {
  role: 'system' | 'user' | 'assistant';
  content: string;
  source?: string;
}

const DISCLAIMER_MSG = `TRACE-X AI Assistant is evidence-grounded. All answers are based solely on the evidence packet for this alert. It does not assert guilt or make regulatory determinations. All data is SYNTHETIC.`;

export default function AssistantPage() {
  const [alertId, setAlertId] = useState('');
  const [inputId, setInputId] = useState('');
  const [messages, setMessages] = useState<Message[]>([{
    role: 'system',
    content: DISCLAIMER_MSG,
  }]);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [briefLoading, setBriefLoading] = useState(false);
  const [modelSource, setModelSource] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('alert');
    if (id) { setAlertId(id); setInputId(id); }
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadAlert = async (id: string) => {
    setAlertId(id);
    setMessages([{ role: 'system', content: DISCLAIMER_MSG }]);
  };

  const generateBrief = async () => {
    if (!alertId) return;
    setBriefLoading(true);
    try {
      const res = await fetch(`${API}/api/v1/investigations/${alertId}/summary`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error('Brief generation failed');
      const data = await res.json();
      setModelSource(data.source);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.summary,
        source: data.source,
      }]);
    } catch (e: any) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error generating brief: ${e.message}`,
      }]);
    } finally {
      setBriefLoading(false);
    }
  };

  const askQuestion = async () => {
    if (!question.trim() || !alertId) return;
    const userQuestion = question.trim();
    setQuestion('');
    setMessages(prev => [...prev, { role: 'user', content: userQuestion }]);
    setLoading(true);

    try {
      const res = await fetch(`${API}/api/v1/investigations/${alertId}/questions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: userQuestion }),
      });
      if (!res.ok) throw new Error('Question failed');
      const data = await res.json();
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.answer,
        source: data.source,
      }]);
    } catch (e: any) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${e.message}`,
      }]);
    } finally {
      setLoading(false);
    }
  };

  const SUGGESTED_QUESTIONS = [
    'What is the primary risk indicator in this alert?',
    'Which transactions should be investigated first?',
    'What AML typologies match this pattern?',
    'What evidence is missing to escalate this case?',
    'Summarize the financial flow between entities.',
  ];

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{ padding: '16px 24px', borderBottom: '1px solid #1e293b',
        background: '#0f1624', display: 'flex', alignItems: 'center', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: 'rgba(16, 185, 129, 0.15)',
            border: '1px solid rgba(16, 185, 129, 0.3)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Bot size={18} style={{ color: '#10b981' }} />
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0' }}>AI Investigation Assistant</div>
            <div style={{ fontSize: 11, color: '#64748b' }}>
              {modelSource ? `Model: ${modelSource}` : 'Evidence-grounded Q&A'}
            </div>
          </div>
        </div>

        {/* Alert selector */}
        <div style={{ display: 'flex', gap: 8, flex: 1, maxWidth: 400 }}>
          <input
            placeholder="Alert ID..."
            value={inputId}
            onChange={e => setInputId(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && loadAlert(inputId)}
            style={{
              flex: 1, background: '#1a2236', border: '1px solid #1e293b',
              color: '#e2e8f0', borderRadius: 8, padding: '6px 12px', fontSize: 12, outline: 'none',
            }}
          />
          <button className="btn-primary" onClick={() => loadAlert(inputId)} style={{ padding: '6px 14px', fontSize: 12 }}>
            Load
          </button>
        </div>

        {alertId && (
          <button
            onClick={generateBrief}
            disabled={briefLoading}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: 'rgba(59, 130, 246, 0.1)', border: '1px solid rgba(59, 130, 246, 0.3)',
              color: '#3b82f6', borderRadius: 8, padding: '7px 14px',
              cursor: 'pointer', fontSize: 12, fontWeight: 600,
            }}
          >
            {briefLoading ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <FileText size={14} />}
            {briefLoading ? 'Generating…' : 'Generate Brief'}
          </button>
        )}
      </div>

      {/* Disclaimer */}
      <div style={{ padding: '8px 24px', background: 'rgba(239, 68, 68, 0.05)',
        borderBottom: '1px solid rgba(239, 68, 68, 0.1)' }}>
        <div style={{ fontSize: 11, color: '#fca5a5', display: 'flex', alignItems: 'center', gap: 6 }}>
          <AlertCircle size={12} />
          {DISCLAIMER_MSG}
        </div>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflow: 'auto', padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
        {messages.filter(m => m.role !== 'system').map((msg, i) => (
          <div key={i} style={{
            display: 'flex', flexDirection: msg.role === 'user' ? 'row-reverse' : 'row', gap: 12,
          }}>
            {msg.role === 'assistant' && (
              <div style={{
                width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                background: 'rgba(16, 185, 129, 0.15)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Bot size={14} style={{ color: '#10b981' }} />
              </div>
            )}
            <div style={{
              maxWidth: '80%',
              background: msg.role === 'user' ? 'rgba(59, 130, 246, 0.15)' : '#1a2236',
              border: `1px solid ${msg.role === 'user' ? 'rgba(59, 130, 246, 0.3)' : '#1e293b'}`,
              borderRadius: msg.role === 'user' ? '12px 12px 4px 12px' : '12px 12px 12px 4px',
              padding: '12px 16px',
            }}>
              <pre style={{
                fontSize: 13, color: '#e2e8f0', lineHeight: 1.7,
                whiteSpace: 'pre-wrap', fontFamily: 'Inter, system-ui, sans-serif',
                margin: 0,
              }}>
                {msg.content}
              </pre>
              {msg.source && (
                <div style={{ fontSize: 10, color: '#64748b', marginTop: 6 }}>
                  Source: {msg.source}
                </div>
              )}
            </div>
          </div>
        ))}

        {(loading || briefLoading) && (
          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: 'rgba(16, 185, 129, 0.15)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Loader2 size={14} style={{ color: '#10b981', animation: 'spin 1s linear infinite' }} />
            </div>
            <div style={{
              background: '#1a2236', border: '1px solid #1e293b',
              borderRadius: '12px 12px 12px 4px', padding: '12px 16px',
            }}>
              <div style={{ display: 'flex', gap: 6 }}>
                {[0, 1, 2].map(i => (
                  <div key={i} style={{
                    width: 6, height: 6, borderRadius: '50%', background: '#64748b',
                    animation: `pulse 1.4s ease-in-out ${i * 0.2}s infinite`,
                  }} />
                ))}
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Suggested questions */}
      {alertId && messages.filter(m => m.role !== 'system').length === 0 && (
        <div style={{ padding: '0 24px 12px' }}>
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8 }}>SUGGESTED QUESTIONS</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {SUGGESTED_QUESTIONS.map(q => (
              <button key={q} onClick={() => { setQuestion(q); }}
                style={{
                  background: '#1a2236', border: '1px solid #1e293b',
                  color: '#94a3b8', borderRadius: 16, padding: '5px 12px',
                  cursor: 'pointer', fontSize: 11, transition: 'all 0.15s',
                }}
                onMouseOver={e => (e.currentTarget.style.borderColor = '#3b82f6')}
                onMouseOut={e => (e.currentTarget.style.borderColor = '#1e293b')}>
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div style={{ padding: '12px 24px', borderTop: '1px solid #1e293b', background: '#0f1624' }}>
        {!alertId ? (
          <div style={{ textAlign: 'center', color: '#64748b', fontSize: 12, padding: 8 }}>
            Load an alert to start the investigation Q&A
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 10 }}>
            <input
              placeholder="Ask about this alert's evidence… (Enter to send)"
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && askQuestion()}
              disabled={loading}
              style={{
                flex: 1, background: '#1a2236', border: '1px solid #1e293b',
                color: '#e2e8f0', borderRadius: 10, padding: '10px 14px',
                fontSize: 13, outline: 'none',
              }}
            />
            <button
              onClick={askQuestion}
              disabled={loading || !question.trim()}
              style={{
                background: 'linear-gradient(135deg, #10b981, #059669)',
                border: 'none', borderRadius: 10, padding: '10px 16px',
                cursor: 'pointer', color: 'white',
                display: 'flex', alignItems: 'center', gap: 6,
                opacity: loading || !question.trim() ? 0.5 : 1,
              }}
            >
              <Send size={16} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
