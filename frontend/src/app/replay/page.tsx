'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Play, Pause, SkipBack, SkipForward, FastForward } from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface ReplayEvent {
  sequence: number;
  transaction_id: string;
  timestamp: string;
  source_entity_id: string;
  destination_entity_id: string;
  amount: number;
  currency: string;
  final_risk_score: number;
  signals_triggered: string[];
}

interface ReplayData {
  alert_id: string;
  alert_type: string;
  severity: string;
  start_time: string;
  end_time: string;
  total_events: number;
  events: ReplayEvent[];
}

export default function ReplayPage() {
  const [alertId, setAlertId] = useState('');
  const [inputId, setInputId] = useState('');
  const [replay, setReplay] = useState<ReplayData | null>(null);
  const [currentSeq, setCurrentSeq] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);

  // Auto-read alert ID from URL params
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('alert');
    if (id) { setAlertId(id); setInputId(id); }
  }, []);

  const fetchReplay = useCallback(async (id: string) => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API}/api/v1/replay/${id}`);
      if (!res.ok) throw new Error(`Not found: ${id}`);
      const data: ReplayData = await res.json();
      setReplay(data);
      setCurrentSeq(0);
      setPlaying(false);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (alertId) fetchReplay(alertId);
  }, [alertId, fetchReplay]);

  // Playback control
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (!playing || !replay) return;

    intervalRef.current = setInterval(() => {
      setCurrentSeq(s => {
        if (s >= replay.events.length - 1) {
          setPlaying(false);
          return s;
        }
        return s + 1;
      });
    }, 1500 / speed);

    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [playing, speed, replay]);

  const currentEvent = replay?.events[currentSeq];
  const progress = replay ? (currentSeq / Math.max(replay.events.length - 1, 1)) * 100 : 0;

  const RISK_COLORS: Record<string, string> = {
    CRITICAL: '#dc2626', HIGH: '#ea580c', MEDIUM: '#ca8a04', LOW: '#16a34a',
  };
  const getRiskColor = (score: number) =>
    score >= 80 ? '#dc2626' : score >= 60 ? '#ea580c' : score >= 30 ? '#ca8a04' : '#16a34a';

  // Build mini graph from events up to current
  const priorEvents = replay?.events.slice(0, currentSeq + 1) || [];
  const nodeSet: Set<string> = new Set();
  priorEvents.forEach(e => { nodeSet.add(e.source_entity_id); nodeSet.add(e.destination_entity_id); });
  const nodeList = Array.from(nodeSet);

  return (
    <div style={{ padding: 24, height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0', marginBottom: 4 }}>Crime Replay</h2>
        <p style={{ fontSize: 13, color: '#64748b' }}>
          Chronological reconstruction of transaction propagation for an alert.
          Frontend reconstructs graph state at each step without modifying stored data.
        </p>
      </div>

      {/* Alert selector */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        <input
          placeholder="Enter Alert ID (e.g. ALT-ABC123)"
          value={inputId}
          onChange={e => setInputId(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && setAlertId(inputId)}
          style={{
            flex: 1, background: '#1a2236', border: '1px solid #1e293b',
            color: '#e2e8f0', borderRadius: 8, padding: '8px 14px', fontSize: 13, outline: 'none',
          }}
        />
        <button className="btn-primary" onClick={() => setAlertId(inputId)}>
          Load Replay
        </button>
      </div>

      {loading && <div style={{ color: '#64748b', textAlign: 'center', padding: 40 }}>Loading replay…</div>}
      {error && <div style={{ color: '#ef4444', padding: 12, background: 'rgba(239,68,68,0.1)', borderRadius: 8 }}>{error}</div>}

      {replay && !loading && (
        <>
          {/* Info bar */}
          <div style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
            {[
              ['Alert', replay.alert_id],
              ['Type', replay.alert_type.replace(/_/g, ' ')],
              ['Severity', replay.severity],
              ['Events', String(replay.total_events)],
              ['Start', new Date(replay.start_time || '').toLocaleString()],
            ].map(([k, v]) => (
              <div key={k} style={{ background: '#1a2236', border: '1px solid #1e293b',
                borderRadius: 8, padding: '8px 14px' }}>
                <div style={{ fontSize: 10, color: '#64748b' }}>{k}</div>
                <div style={{ fontSize: 12, color: '#e2e8f0', marginTop: 2 }}>{v}</div>
              </div>
            ))}
          </div>

          {/* Main view: mini graph + event detail */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16, flex: 1, minHeight: 0 }}>
            {/* Mini graph */}
            <div style={{ background: '#080c12', border: '1px solid #1e293b',
              borderRadius: 12, padding: 20, overflow: 'hidden', position: 'relative' }}>
              <div style={{ fontSize: 11, color: '#64748b', marginBottom: 12 }}>
                TRANSACTION GRAPH (step {currentSeq + 1}/{replay.total_events})
              </div>
              <div style={{
                display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center',
                justifyContent: 'center', height: 'calc(100% - 40px)',
              }}>
                {priorEvents.map((ev, i) => {
                  const isActive = i === currentSeq;
                  const riskColor = getRiskColor(ev.final_risk_score);
                  return (
                    <div key={ev.transaction_id} style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      opacity: isActive ? 1 : 0.4,
                      transition: 'all 0.3s',
                      animation: isActive ? 'fadeIn 0.3s' : undefined,
                    }}>
                      <div style={{
                        width: 36, height: 36, borderRadius: '50%',
                        background: `${riskColor}22`, border: `2px solid ${riskColor}`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 9, color: riskColor, fontFamily: 'monospace',
                        boxShadow: isActive ? `0 0 12px ${riskColor}66` : 'none',
                      }}>
                        {ev.source_entity_id.slice(-4)}
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                        <div style={{ fontSize: 9, color: '#64748b' }}>
                          ₹{(ev.amount / 1000).toFixed(0)}K
                        </div>
                        <div style={{
                          width: 40, height: 2,
                          background: `linear-gradient(90deg, ${riskColor}, ${riskColor}44)`,
                          position: 'relative',
                        }}>
                          <div style={{
                            position: 'absolute', right: -4, top: -4,
                            width: 0, height: 0,
                            borderLeft: '6px solid ' + riskColor,
                            borderTop: '4px solid transparent',
                            borderBottom: '4px solid transparent',
                          }} />
                        </div>
                      </div>
                      <div style={{
                        width: 36, height: 36, borderRadius: '50%',
                        background: `${riskColor}22`, border: `2px solid ${riskColor}`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 9, color: riskColor, fontFamily: 'monospace',
                      }}>
                        {ev.destination_entity_id.slice(-4)}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Current event detail */}
            <div style={{ background: '#111827', border: '1px solid #1e293b', borderRadius: 12, padding: 16 }}>
              <div style={{ fontSize: 11, color: '#64748b', marginBottom: 12 }}>ACTIVE TRANSACTION</div>
              {currentEvent ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {[
                    ['Seq', String(currentEvent.sequence)],
                    ['TX ID', currentEvent.transaction_id.slice(-12)],
                    ['Amount', `₹${currentEvent.amount.toLocaleString()}`],
                    ['Currency', currentEvent.currency],
                    ['From', `...${currentEvent.source_entity_id.slice(-8)}`],
                    ['To', `...${currentEvent.destination_entity_id.slice(-8)}`],
                    ['Time', new Date(currentEvent.timestamp).toLocaleString()],
                    ['Risk', `${currentEvent.final_risk_score.toFixed(1)}/100`],
                  ].map(([k, v]) => (
                    <div key={k} style={{ display: 'flex', justifyContent: 'space-between',
                      paddingBottom: 8, borderBottom: '1px solid #1e293b' }}>
                      <span style={{ fontSize: 11, color: '#64748b' }}>{k}</span>
                      <span className="mono" style={{ fontSize: 11, color: '#e2e8f0' }}>{v}</span>
                    </div>
                  ))}

                  {currentEvent.signals_triggered.length > 0 && (
                    <div>
                      <div style={{ fontSize: 10, color: '#64748b', marginBottom: 6 }}>SIGNALS</div>
                      {currentEvent.signals_triggered.map(s => (
                        <div key={s} style={{
                          background: 'rgba(239, 68, 68, 0.1)',
                          border: '1px solid rgba(239, 68, 68, 0.2)',
                          borderRadius: 4, padding: '4px 8px',
                          fontSize: 10, color: '#ef4444', marginBottom: 4,
                        }}>⚡ {s}</div>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ color: '#64748b', fontSize: 12 }}>No active event</div>
              )}
            </div>
          </div>

          {/* Timeline scrubber */}
          <div style={{ marginTop: 16, background: '#111827', border: '1px solid #1e293b',
            borderRadius: 12, padding: 16 }}>
            {/* Progress bar */}
            <div style={{ marginBottom: 12, cursor: 'pointer' }}
              onClick={(e) => {
                const rect = e.currentTarget.getBoundingClientRect();
                const ratio = (e.clientX - rect.left) / rect.width;
                const seq = Math.round(ratio * (replay.total_events - 1));
                setCurrentSeq(Math.max(0, Math.min(seq, replay.total_events - 1)));
              }}>
              <div style={{ height: 6, background: '#1e293b', borderRadius: 4, position: 'relative' }}>
                <div style={{
                  height: '100%', width: `${progress}%`,
                  background: 'linear-gradient(90deg, #3b82f6, #60a5fa)',
                  borderRadius: 4, transition: 'width 0.2s',
                }} />
                <div style={{
                  position: 'absolute', top: -4, left: `${progress}%`,
                  width: 14, height: 14, borderRadius: '50%',
                  background: '#60a5fa', border: '2px solid #1a2236',
                  transform: 'translateX(-50%)',
                  boxShadow: '0 0 8px rgba(96, 165, 250, 0.6)',
                }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
                <span style={{ fontSize: 10, color: '#64748b' }}>
                  {replay.start_time ? new Date(replay.start_time).toLocaleDateString() : ''}
                </span>
                <span style={{ fontSize: 10, color: '#64748b' }}>
                  Step {currentSeq + 1} / {replay.total_events}
                </span>
                <span style={{ fontSize: 10, color: '#64748b' }}>
                  {replay.end_time ? new Date(replay.end_time).toLocaleDateString() : ''}
                </span>
              </div>
            </div>

            {/* Controls */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, justifyContent: 'center' }}>
              <button onClick={() => setCurrentSeq(0)}
                style={{ background: '#1a2236', border: '1px solid #1e293b',
                  color: '#94a3b8', borderRadius: 6, padding: '6px 10px', cursor: 'pointer' }}>
                <SkipBack size={16} />
              </button>
              <button onClick={() => setCurrentSeq(s => Math.max(0, s - 1))}
                style={{ background: '#1a2236', border: '1px solid #1e293b',
                  color: '#94a3b8', borderRadius: 6, padding: '6px 10px', cursor: 'pointer' }}>
                ‹
              </button>
              <button
                onClick={() => setPlaying(!playing)}
                style={{
                  background: playing ? 'rgba(239, 68, 68, 0.2)' : 'rgba(59, 130, 246, 0.2)',
                  border: `1px solid ${playing ? 'rgba(239, 68, 68, 0.4)' : 'rgba(59, 130, 246, 0.4)'}`,
                  color: playing ? '#ef4444' : '#3b82f6',
                  borderRadius: 8, padding: '8px 20px', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600,
                }}>
                {playing ? <Pause size={16} /> : <Play size={16} />}
                {playing ? 'Pause' : 'Play'}
              </button>
              <button onClick={() => setCurrentSeq(s => Math.min(replay.events.length - 1, s + 1))}
                style={{ background: '#1a2236', border: '1px solid #1e293b',
                  color: '#94a3b8', borderRadius: 6, padding: '6px 10px', cursor: 'pointer' }}>
                ›
              </button>
              <button onClick={() => setCurrentSeq(replay.events.length - 1)}
                style={{ background: '#1a2236', border: '1px solid #1e293b',
                  color: '#94a3b8', borderRadius: 6, padding: '6px 10px', cursor: 'pointer' }}>
                <SkipForward size={16} />
              </button>

              <div style={{ marginLeft: 16, display: 'flex', alignItems: 'center', gap: 6 }}>
                <FastForward size={12} style={{ color: '#64748b' }} />
                <span style={{ fontSize: 11, color: '#64748b' }}>Speed:</span>
                {[0.5, 1, 2, 4].map(s => (
                  <button key={s} onClick={() => setSpeed(s)}
                    style={{
                      background: speed === s ? 'rgba(59, 130, 246, 0.2)' : '#1a2236',
                      border: `1px solid ${speed === s ? 'rgba(59, 130, 246, 0.5)' : '#1e293b'}`,
                      color: speed === s ? '#3b82f6' : '#94a3b8',
                      borderRadius: 4, padding: '4px 8px', cursor: 'pointer', fontSize: 11,
                    }}>{s}x</button>
                ))}
              </div>
            </div>
          </div>
        </>
      )}

      {!replay && !loading && !error && (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexDirection: 'column', gap: 12, color: '#64748b' }}>
          <div style={{ fontSize: 48 }}>▶️</div>
          <div style={{ fontSize: 14 }}>Enter an Alert ID to load its transaction replay</div>
          <div style={{ fontSize: 12 }}>
            Find Alert IDs in the <a href="/alerts" style={{ color: '#3b82f6' }}>Alerts page</a>
          </div>
        </div>
      )}
    </div>
  );
}
