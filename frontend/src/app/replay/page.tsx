'use client';

import React, { useState, useEffect, useRef, useCallback, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  Play, Pause, SkipBack, SkipForward, Clock,
  AlertTriangle, Zap, Activity, GitBranch, ChevronRight,
  RefreshCw, ArrowRight, Search, Database, Shield
} from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface ReplayEvent {
  sequence: number;
  transaction_id: string;
  timestamp: string;
  source_entity_id: string;
  destination_entity_id: string;
  amount: number;
  currency: string;
  transaction_type: string;
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

interface AlertSummary {
  id: string;
  alert_type: string;
  severity: string;
  risk_components: { final_risk_score: number };
}

const SPEED_OPTIONS = [0.5, 1, 1.5, 2, 3];
const SIGNAL_ICONS: Record<string, { label: string; color: string }> = {
  RULE_TRIGGERED: { label: 'Rule', color: '#3b82f6' },
  ANOMALY_DETECTED: { label: 'Anomaly', color: '#f97316' },
  TEMPORAL_BURST: { label: 'Temporal', color: '#06b6d4' },
  HIGH_CENTRALITY: { label: 'Centrality', color: '#8b5cf6' },
};

function RiskBar({ score }: { score: number }) {
  const color = score >= 80 ? '#ef4444' : score >= 60 ? '#f97316' : score >= 30 ? '#f59e0b' : '#10b981';
  return (
    <div className="risk-bar">
      <div className="risk-bar-track" style={{ flex: 1 }}>
        <div className="risk-bar-fill" style={{ width: `${Math.min(score, 100)}%`, background: color }} />
      </div>
      <span style={{ fontSize: 11, color, fontWeight: 700, minWidth: 26 }}>{score.toFixed(0)}</span>
    </div>
  );
}

function EventCard({ event, isActive, onClick }: { event: ReplayEvent; isActive: boolean; onClick: () => void }) {
  const scoreColor = event.final_risk_score >= 80 ? '#ef4444' : event.final_risk_score >= 60 ? '#f97316' : event.final_risk_score >= 30 ? '#f59e0b' : '#10b981';
  return (
    <div
      onClick={onClick}
      style={{
        padding: '12px 14px',
        borderRadius: 10,
        border: `1px solid ${isActive ? 'rgba(59,130,246,0.5)' : 'var(--border-subtle)'}`,
        background: isActive ? 'rgba(59, 130, 246, 0.08)' : 'rgba(10, 18, 35, 0.6)',
        cursor: 'pointer',
        transition: 'all 0.2s',
        position: 'relative',
        overflow: 'hidden',
      }}
      role="button"
      tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && onClick()}
      aria-label={`Event ${event.sequence}, transaction ${event.transaction_id}`}
      aria-pressed={isActive}
    >
      {isActive && (
        <div style={{
          position: 'absolute', left: 0, top: 0, bottom: 0, width: 3,
          background: 'var(--accent)', borderRadius: '3px 0 0 3px',
        }} />
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
            color: isActive ? 'var(--accent-bright)' : 'var(--text-tertiary)',
          }}>
            #{event.sequence}
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)' }}>
            {event.transaction_type}
          </span>
        </div>
        <span style={{ fontSize: 11, fontWeight: 700, color: scoreColor }}>
          {event.final_risk_score.toFixed(0)}
        </span>
      </div>

      <div style={{ fontSize: 12, color: 'var(--text-primary)', marginBottom: 4, fontWeight: 500 }}>
        {event.amount.toLocaleString()} {event.currency}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: 'var(--text-tertiary)' }}>
        <span style={{ fontFamily: 'var(--font-mono)' }}>···{event.source_entity_id.slice(-6)}</span>
        <ArrowRight size={9} />
        <span style={{ fontFamily: 'var(--font-mono)' }}>···{event.destination_entity_id.slice(-6)}</span>
      </div>

      {event.signals_triggered.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
          {event.signals_triggered.map(sig => (
            <span key={sig} style={{
              fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 20,
              background: `${SIGNAL_ICONS[sig]?.color || '#64748b'}18`,
              color: SIGNAL_ICONS[sig]?.color || '#94a3b8',
              border: `1px solid ${SIGNAL_ICONS[sig]?.color || '#64748b'}30`,
            }}>
              {SIGNAL_ICONS[sig]?.label || sig}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ReplayPageContent() {
  const searchParams = useSearchParams();
  const urlAlertId = searchParams.get('alert');

  const [alerts, setAlerts] = useState<AlertSummary[]>([]);
  const [selectedAlertId, setSelectedAlertId] = useState(urlAlertId || '');
  const [replayData, setReplayData] = useState<ReplayData | null>(null);
  const [loading, setLoading] = useState(false);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [error, setError] = useState('');
  const [currentSeq, setCurrentSeq] = useState(1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const playRef = useRef<ReturnType<typeof setInterval>>();
  const eventListRef = useRef<HTMLDivElement>(null);

  // Fetch alert list
  useEffect(() => {
    fetch(`${API}/api/v1/alerts?limit=50`)
      .then(r => r.json())
      .then(d => {
        setAlerts(d.alerts || []);
        setAlertsLoading(false);
        // Auto-select first if no URL param
        if (!urlAlertId && (d.alerts || []).length > 0) {
          setSelectedAlertId(d.alerts[0].id);
        }
      })
      .catch(() => setAlertsLoading(false));
  }, [urlAlertId]);

  // Fetch replay data when alert is selected
  const fetchReplay = useCallback(async (alertId: string) => {
    if (!alertId) return;
    setLoading(true);
    setError('');
    setIsPlaying(false);
    setCurrentSeq(1);
    if (playRef.current) clearInterval(playRef.current);

    try {
      const res = await fetch(`${API}/api/v1/replay/${alertId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setReplayData(data);
    } catch (e: any) {
      setError('Failed to load replay data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedAlertId) fetchReplay(selectedAlertId);
  }, [selectedAlertId, fetchReplay]);

  // Playback engine
  useEffect(() => {
    if (!isPlaying || !replayData) return;
    const intervalMs = 1200 / speed;
    playRef.current = setInterval(() => {
      setCurrentSeq(seq => {
        if (seq >= replayData.total_events) {
          setIsPlaying(false);
          return seq;
        }
        return seq + 1;
      });
    }, intervalMs);
    return () => clearInterval(playRef.current);
  }, [isPlaying, speed, replayData]);

  // Auto-scroll event list to active event
  useEffect(() => {
    if (!eventListRef.current) return;
    const activeEl = eventListRef.current.querySelector('[aria-pressed="true"]');
    if (activeEl) {
      activeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [currentSeq]);

  const activeEvent = replayData?.events[currentSeq - 1];
  const totalEvents = replayData?.total_events || 0;
  const progress = totalEvents > 0 ? ((currentSeq - 1) / (totalEvents - 1)) * 100 : 0;

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!replayData || totalEvents === 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const newSeq = Math.max(1, Math.round(pct * (totalEvents - 1)) + 1);
    setCurrentSeq(newSeq);
    setIsPlaying(false);
  };

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div className="page-header" style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 className="page-title">Crime Replay</h1>
          <p className="page-subtitle">Chronological transaction sequence reconstruction</p>
        </div>
        {replayData && (
          <div className="live-chip offline">
            <Clock size={9} />
            {replayData.start_time ? new Date(replayData.start_time).toLocaleDateString() : 'N/A'}
            {' → '}
            {replayData.end_time ? new Date(replayData.end_time).toLocaleDateString() : 'N/A'}
          </div>
        )}
      </div>

      {/* Alert selector */}
      <div className="glass-card" style={{ padding: 16, marginBottom: 20 }}>
        <div className="section-label" style={{ marginBottom: 10 }}>
          <Database size={10} />
          Select Alert to Replay
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <select
            className="select"
            value={selectedAlertId}
            onChange={e => setSelectedAlertId(e.target.value)}
            style={{ flex: 1, minWidth: 200 }}
            aria-label="Select alert for replay"
          >
            <option value="">— Select an alert —</option>
            {alerts.map(a => (
              <option key={a.id} value={a.id}>
                {a.severity} · {a.alert_type.replace(/_/g, ' ')} · Risk {a.risk_components?.final_risk_score?.toFixed(0) || '?'} · {a.id.slice(-10)}
              </option>
            ))}
          </select>
          {selectedAlertId && (
            <button className="btn btn-secondary btn-sm" onClick={() => fetchReplay(selectedAlertId)} aria-label="Reload replay">
              <RefreshCw size={13} />
            </button>
          )}
        </div>
        {alertsLoading && <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 8 }}>Loading alerts…</div>}
      </div>

      {/* Error */}
      {error && (
        <div style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10, padding: '12px 16px', marginBottom: 16, fontSize: 13, color: '#f87171' }}>
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="glass-card" style={{ padding: 60, textAlign: 'center' }}>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Loading replay data…</div>
        </div>
      )}

      {/* Empty / not selected */}
      {!loading && !replayData && !error && (
        <div className="glass-card">
          <div className="empty-state">
            <Play size={36} className="empty-state-icon" />
            <div className="empty-state-title">Select an alert above</div>
            <div className="empty-state-body">Choose an alert to begin the chronological transaction replay</div>
          </div>
        </div>
      )}

      {/* Replay player */}
      {!loading && replayData && (
        <div style={{ display: 'flex', gap: 16, flexDirection: 'column' }}>
          {/* Active event spotlight */}
          {activeEvent && (
            <div className="glass-card-elevated anim-scale-in" style={{ padding: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-tertiary)' }}>
                      ACTIVE TRANSACTION — Event {currentSeq} of {totalEvents}
                    </div>
                    {currentSeq === totalEvents && !isPlaying && (
                      <span className="badge badge-low" style={{ fontSize: 9 }}>
                        REPLAY COMPLETE
                      </span>
                    )}
                  </div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-accent)' }}>
                    {activeEvent.transaction_id}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {activeEvent.signals_triggered.map(sig => (
                    <span key={sig} className="badge" style={{
                      background: `${SIGNAL_ICONS[sig]?.color || '#64748b'}18`,
                      color: SIGNAL_ICONS[sig]?.color || '#94a3b8',
                      borderColor: `${SIGNAL_ICONS[sig]?.color || '#64748b'}35`,
                    }}>
                      {SIGNAL_ICONS[sig]?.label || sig}
                    </span>
                  ))}
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 16 }}>
                {[
                  { label: 'AMOUNT', value: `${activeEvent.amount.toLocaleString()} ${activeEvent.currency}`, color: 'var(--text-primary)' },
                  { label: 'FROM', value: `···${activeEvent.source_entity_id.slice(-8)}`, color: 'var(--accent-bright)', mono: true },
                  { label: 'TO', value: `···${activeEvent.destination_entity_id.slice(-8)}`, color: 'var(--accent-bright)', mono: true },
                  { label: 'TYPE', value: activeEvent.transaction_type, color: 'var(--text-secondary)' },
                  { label: 'TIMESTAMP', value: new Date(activeEvent.timestamp).toLocaleString(), color: 'var(--text-secondary)' },
                ].map(({ label, value, color, mono }) => (
                  <div key={label}>
                    <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-tertiary)', marginBottom: 4 }}>{label}</div>
                    <div style={{ fontSize: 13, fontWeight: 600, color, fontFamily: mono ? 'var(--font-mono)' : 'inherit' }}>{value}</div>
                  </div>
                ))}
              </div>

              <div>
                <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-tertiary)', marginBottom: 6 }}>RISK SCORE</div>
                <RiskBar score={activeEvent.final_risk_score} />
              </div>
            </div>
          )}

          {/* Playback controls */}
          <div className="glass-card" style={{ padding: '16px 20px' }}>
            {/* Timeline scrubber */}
            <div
              className="timeline-track"
              style={{ marginBottom: 16, cursor: 'pointer' }}
              onClick={handleSeek}
              aria-label="Timeline scrubber"
              role="slider"
              aria-valuenow={currentSeq}
              aria-valuemin={1}
              aria-valuemax={totalEvents}
            >
              <div className="timeline-fill" style={{ width: `${progress}%` }} />
              <div className="timeline-thumb" style={{ left: `${progress}%` }} />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', justifyContent: 'center' }}>
              {/* Prev */}
              <button
                className="replay-control-btn"
                onClick={() => { setCurrentSeq(s => Math.max(1, s - 1)); setIsPlaying(false); }}
                disabled={currentSeq <= 1}
                aria-label="Previous event"
              >
                <SkipBack size={16} />
              </button>

              {/* Play/Pause */}
              <button
                className="replay-control-btn play"
                onClick={() => setIsPlaying(p => !p)}
                aria-label={isPlaying ? 'Pause' : 'Play'}
              >
                {isPlaying ? <Pause size={20} /> : <Play size={20} />}
              </button>

              {/* Next */}
              <button
                className="replay-control-btn"
                onClick={() => { setCurrentSeq(s => Math.min(totalEvents, s + 1)); setIsPlaying(false); }}
                disabled={currentSeq >= totalEvents}
                aria-label="Next event"
              >
                <SkipForward size={16} />
              </button>

              {/* Speed */}
              <div style={{ display: 'flex', gap: 4, marginLeft: 8 }}>
                {SPEED_OPTIONS.map(s => (
                  <button
                    key={s}
                    className={`btn btn-sm ${speed === s ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => setSpeed(s)}
                    aria-label={`Speed ${s}x`}
                    aria-pressed={speed === s}
                  >
                    {s}×
                  </button>
                ))}
              </div>

              <span style={{ fontSize: 12, color: 'var(--text-tertiary)', marginLeft: 'auto' }}>
                {currentSeq} / {totalEvents}
              </span>
            </div>
          </div>

          {/* Event list */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 8 }} ref={eventListRef}>
            {replayData.events.map(event => (
              <EventCard
                key={event.sequence}
                event={event}
                isActive={event.sequence === currentSeq}
                onClick={() => { setCurrentSeq(event.sequence); setIsPlaying(false); }}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function ReplayPage() {
  return (
    <Suspense fallback={<div className="glass-card" style={{ padding: 40, color: 'var(--text-secondary)', textAlign: 'center' }}>Loading Crime Replay…</div>}>
      <ReplayPageContent />
    </Suspense>
  );
}
