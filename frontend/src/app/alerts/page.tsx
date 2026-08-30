'use client';

import React, { useState, useEffect, useCallback, useRef, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  AlertTriangle, Search, Filter, X, ChevronRight,
  CheckCircle, MessageSquare, Eye, ArrowLeft,
  Shield, Zap, Activity, GitBranch, Clock, RefreshCw,
  Send, Database, FileText
} from 'lucide-react';
import { datasetUploadedThisSession } from '../session-state';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface RiskComponents {
  final_risk_score: number;
  risk_level: string;
  human_explanation: string;
  rule_score?: number;
  anomaly_score?: number;
  graph_score?: number;
  temporal_score?: number;
  entity_score?: number;
  top_features?: string[];
}

interface TriggeredRule {
  rule_id: string;
  score: number;
  explanation: string;
}

interface Alert {
  id: string;
  alert_type: string;
  severity: string;
  status: string;
  risk_components: RiskComponents;
  contributing_signals: Record<string, number>;
  triggered_rules: TriggeredRule[];
  entity_ids: string[];
  transaction_ids: string[];
  created_at: string;
  updated_at?: string;
  assigned_to?: string;
  investigator_notes?: string;
  dataset_id: string;
}

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: '#ef4444', HIGH: '#f97316', MEDIUM: '#f59e0b', LOW: '#10b981',
};

const STATUS_OPTIONS = ['', 'NEW', 'INVESTIGATING', 'ESCALATED', 'RESOLVED', 'FALSE_POSITIVE'];
const SEVERITY_OPTIONS = ['', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];

function SeverityBadge({ s }: { s: string }) {
  return <span className={`badge badge-${s.toLowerCase()}`}>{s}</span>;
}

function StatusBadge({ s }: { s: string }) {
  const map: Record<string, string> = {
    NEW: 'badge-new', INVESTIGATING: 'badge-investigating', ESCALATED: 'badge-escalated',
    RESOLVED: 'badge-resolved', FALSE_POSITIVE: 'badge-false-positive',
  };
  return <span className={`badge ${map[s] || 'badge-neutral'}`}>{s.replace('_', ' ')}</span>;
}

function RiskBar({ score }: { score: number }) {
  const color = score >= 80 ? '#ef4444' : score >= 60 ? '#f97316' : score >= 30 ? '#f59e0b' : '#10b981';
  return (
    <div className="risk-bar">
      <div className="risk-bar-track">
        <div className="risk-bar-fill" style={{ width: `${Math.min(score, 100)}%`, background: color }} />
      </div>
      <span style={{ fontSize: 11, color, fontWeight: 700, minWidth: 26 }}>{score.toFixed(0)}</span>
    </div>
  );
}

// Signal labels with icons
const SIGNALS = [
  { key: 'rule_score', label: 'RULE ENGINE', icon: Shield, color: '#3b82f6' },
  { key: 'graph_score', label: 'GRAPH SIGNAL', icon: GitBranch, color: '#8b5cf6' },
  { key: 'anomaly_score', label: 'ML ANOMALY', icon: Activity, color: '#f97316' },
  { key: 'temporal_score', label: 'TEMPORAL', icon: Clock, color: '#06b6d4' },
  { key: 'entity_score', label: 'ENTITY RISK', icon: Eye, color: '#f59e0b' },
];

function SignalRow({ label, icon: Icon, color, score }: { label: string; icon: React.ElementType; color: string; score: number }) {
  const pct = Math.min((score / 1.0) * 100, 100); // score is 0–1 normalized
  const displayScore = Math.round(pct);
  return (
    <div className="signal-row">
      <Icon size={12} style={{ color, flexShrink: 0 }} />
      <span className="signal-label">{label}</span>
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8 }}>
        <div className="risk-bar-track" style={{ flex: 1 }}>
          <div className="risk-bar-fill" style={{ width: `${pct}%`, background: color, transition: 'width 0.8s ease' }} />
        </div>
        <span style={{ fontSize: 11, color, fontWeight: 700, minWidth: 28 }}>{displayScore}</span>
      </div>
    </div>
  );
}

// ── Investigation Panel ──────────────────────────────────────────
function InvestigationPanel({
  alert,
  onClose,
  onStatusChange,
  onAddNote,
}: {
  alert: Alert;
  onClose: () => void;
  onStatusChange: (id: string, status: string) => Promise<void>;
  onAddNote: (id: string, note: string) => Promise<void>;
}) {
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [activeTab, setActiveTab] = useState<'evidence' | 'signals' | 'notes'>('evidence');

  const score = alert.risk_components?.final_risk_score || 0;
  const scoreColor = score >= 80 ? '#ef4444' : score >= 60 ? '#f97316' : score >= 30 ? '#f59e0b' : '#10b981';

  // Keyboard Escape key handler to close drawer
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleStatusChange = async (newStatus: string) => {
    setSubmitting(true);
    await onStatusChange(alert.id, newStatus);
    setSubmitting(false);
  };

  const handleAddNote = async () => {
    if (!note.trim()) return;
    setSubmitting(true);
    await onAddNote(alert.id, note.trim());
    setNote('');
    setSubmitting(false);
  };

  return (
    <>
      {/* Backdrop (mobile) */}
      <div className="investigation-panel-backdrop open" onClick={onClose} />

      <div className="investigation-panel open">
        {/* Panel header */}
        <div style={{
          padding: '16px 20px',
          borderBottom: '1px solid var(--border-subtle)',
          display: 'flex', alignItems: 'flex-start', gap: 12, flexShrink: 0,
        }}>
          <button className="btn btn-ghost btn-icon btn-sm" onClick={onClose} aria-label="Close panel">
            <X size={15} />
          </button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
              <SeverityBadge s={alert.severity} />
              <StatusBadge s={alert.status} />
            </div>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 2 }}>
              {alert.alert_type.replace(/_/g, ' ')}
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-tertiary)' }}>
              {alert.id}
            </div>
          </div>
          {/* Final risk score display */}
          <div style={{
            textAlign: 'center', background: `${scoreColor}12`,
            border: `1px solid ${scoreColor}30`,
            borderRadius: 10, padding: '8px 14px', flexShrink: 0,
          }}>
            <div style={{ fontSize: 24, fontWeight: 900, color: scoreColor, lineHeight: 1 }}>
              {score.toFixed(0)}
            </div>
            <div style={{ fontSize: 9, color: scoreColor, fontWeight: 700, letterSpacing: '0.1em', marginTop: 2 }}>
              RISK
            </div>
          </div>
        </div>

        {/* Risk explanation */}
        {alert.risk_components?.human_explanation && (
          <div style={{
            padding: '12px 20px',
            background: 'rgba(59, 130, 246, 0.05)',
            borderBottom: '1px solid var(--border-subtle)',
            fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6, flexShrink: 0,
          }}>
            {alert.risk_components.human_explanation}
          </div>
        )}

        {/* Tabs */}
        <div style={{
          display: 'flex', gap: 2, padding: '12px 20px 0',
          borderBottom: '1px solid var(--border-subtle)', flexShrink: 0,
        }}>
          {(['evidence', 'signals', 'notes'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: '7px 14px',
                fontSize: 12, fontWeight: 600,
                color: activeTab === tab ? 'var(--accent-bright)' : 'var(--text-tertiary)',
                background: 'none', border: 'none',
                borderBottom: activeTab === tab ? '2px solid var(--accent)' : '2px solid transparent',
                cursor: 'pointer', textTransform: 'capitalize', transition: 'all 0.15s',
                marginBottom: -1,
              }}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>

          {/* ── Evidence tab ── */}
          {activeTab === 'evidence' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div className="section-label">Triggered Detection Rules</div>

              {alert.triggered_rules?.length === 0 ? (
                <div style={{ fontSize: 12, color: 'var(--text-tertiary)', padding: '12px 0' }}>
                  No rules triggered for this alert.
                </div>
              ) : (
                alert.triggered_rules?.map((rule, i) => (
                  <div key={i} className="evidence-card anim-fade-up" style={{ animationDelay: `${i * 60}ms` }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <div className="evidence-rule-id">{rule.rule_id}</div>
                      <div style={{
                        fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
                        background: rule.score >= 0.8 ? 'rgba(239,68,68,0.15)' : rule.score >= 0.5 ? 'rgba(249,115,22,0.15)' : 'rgba(245,158,11,0.15)',
                        color: rule.score >= 0.8 ? '#f87171' : rule.score >= 0.5 ? '#fb923c' : '#fbbf24',
                      }}>
                        Score: {(rule.score * 100).toFixed(0)}
                      </div>
                    </div>
                    <div className="evidence-explanation">{rule.explanation}</div>
                  </div>
                ))
              )}

              <div className="section-label" style={{ marginTop: 8 }}>Entities Involved</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {alert.entity_ids?.map(eid => (
                  <span key={eid} style={{
                    fontFamily: 'var(--font-mono)', fontSize: 10,
                    background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.25)',
                    color: '#a78bfa', padding: '3px 8px', borderRadius: 20,
                  }}>
                    ···{eid.slice(-8)}
                  </span>
                ))}
              </div>

              <div className="section-label" style={{ marginTop: 4 }}>Dataset</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Database size={12} style={{ color: 'var(--text-tertiary)' }} />
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)' }}>
                  {alert.dataset_id}
                </span>
              </div>

              <div className="section-label" style={{ marginTop: 4 }}>Navigate</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {[
                  { href: `/replay?alert=${alert.id}`, label: 'Crime Replay' },
                  { href: `/whatif?alert=${alert.id}`, label: 'What-If Analysis' },
                  { href: `/assistant?alert=${alert.id}`, label: 'AI Assistant' },
                ].map(({ href, label }) => (
                  <a key={href} href={href} style={{ textDecoration: 'none' }}>
                    <button className="btn btn-secondary btn-sm">
                      <ChevronRight size={12} />
                      {label}
                    </button>
                  </a>
                ))}
              </div>
            </div>
          )}

          {/* ── Signals tab ── */}
          {activeTab === 'signals' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div className="section-label">Risk Signal Breakdown</div>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 14 }}>
                Scores are normalized 0–100. Final risk fuses all signals.
              </div>

              {SIGNALS.map(({ key, label, icon, color }) => {
                const rawScore = (alert.contributing_signals?.[key] || alert.risk_components?.[key as keyof RiskComponents] || 0) as number;
                return (
                  <SignalRow
                    key={key}
                    label={label}
                    icon={icon}
                    color={color}
                    score={typeof rawScore === 'number' ? rawScore : 0}
                  />
                );
              })}

              <div style={{
                marginTop: 16,
                padding: '14px 16px',
                background: `${scoreColor}0A`,
                border: `1px solid ${scoreColor}25`,
                borderRadius: 10,
              }}>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', color: scoreColor, marginBottom: 4 }}>
                  FINAL COMPOSITE RISK
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div className="risk-bar-track" style={{ flex: 1, height: 8 }}>
                    <div className="risk-bar-fill" style={{ width: `${score}%`, background: scoreColor, transition: 'width 1s ease' }} />
                  </div>
                  <span style={{ fontSize: 22, fontWeight: 900, color: scoreColor }}>{score.toFixed(0)}</span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 6 }}>
                  {alert.risk_components?.risk_level} — Weights: Rule 30% · Anomaly 25% · Graph 25% · Temporal 20%
                </div>
              </div>

              {alert.risk_components?.top_features && alert.risk_components.top_features.length > 0 && (
                <>
                  <div className="section-label" style={{ marginTop: 12 }}>Top ML Features</div>
                  {alert.risk_components.top_features.map((f, i) => (
                    <div key={i} style={{ fontSize: 12, color: 'var(--text-secondary)', padding: '4px 0' }}>
                      • {f}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}

          {/* ── Notes tab ── */}
          {activeTab === 'notes' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div className="section-label">Update Status</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {['INVESTIGATING', 'ESCALATED', 'RESOLVED', 'FALSE_POSITIVE'].map(s => (
                  <button
                    key={s}
                    className="btn btn-secondary btn-sm"
                    disabled={submitting || alert.status === s}
                    onClick={() => handleStatusChange(s)}
                    style={alert.status === s ? { opacity: 0.5, cursor: 'not-allowed' } : {}}
                  >
                    {s.replace('_', ' ')}
                  </button>
                ))}
              </div>

              {alert.investigator_notes && (
                <>
                  <div className="section-label" style={{ marginTop: 4 }}>Investigation Notes</div>
                  <div style={{
                    background: 'rgba(10, 18, 35, 0.7)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 8, padding: '12px 14px',
                    fontSize: 12, color: 'var(--text-secondary)',
                    lineHeight: 1.7, whiteSpace: 'pre-wrap',
                    maxHeight: 200, overflowY: 'auto',
                  }}>
                    {alert.investigator_notes}
                  </div>
                </>
              )}

              <div className="section-label" style={{ marginTop: 4 }}>Add Note</div>
              <textarea
                value={note}
                onChange={e => setNote(e.target.value)}
                placeholder="Add investigation notes…"
                rows={4}
                className="input"
                style={{ resize: 'vertical', lineHeight: 1.6 }}
                aria-label="Investigation notes"
              />
              <button
                className="btn btn-primary btn-sm"
                onClick={handleAddNote}
                disabled={!note.trim() || submitting}
              >
                <Send size={12} />
                {submitting ? 'Saving…' : 'Add Note'}
              </button>

              {alert.assigned_to && (
                <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                  Assigned to: <strong style={{ color: 'var(--text-secondary)' }}>{alert.assigned_to}</strong>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ── Main Alerts Page ─────────────────────────────────────────────
function AlertsPageContent() {
  const searchParams = useSearchParams();
  const initialAlertId = searchParams.get('id');

  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<Alert | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [datasets, setDatasets] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const PAGE_SIZE = 20;

  const [filters, setFilters] = useState({
    severity: '', status: '', minRisk: 0, search: '', datasetId: '',
  });

  // Fetch datasets for filter
  useEffect(() => {
    fetch(`${API}/api/v1/datasets`)
      .then(r => r.json())
      .then(d => setDatasets(d.datasets || []))
      .catch(() => {});
  }, []);

  const fetchAlerts = useCallback(async (showRefresh = false) => {
    if (!datasetUploadedThisSession) {
      setAlerts([]);
      setTotal(0);
      setLoading(false);
      return;
    }
    if (showRefresh) setRefreshing(true);
    else setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String((page - 1) * PAGE_SIZE),
      });
      if (filters.severity) params.set('severity', filters.severity);
      if (filters.status) params.set('status', filters.status);
      if (filters.minRisk > 0) params.set('min_risk', String(filters.minRisk));
      if (filters.datasetId) params.set('dataset_id', filters.datasetId);

      const res = await fetch(`${API}/api/v1/alerts?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const list: Alert[] = data.alerts || [];
      setAlerts(list);
      setTotal(data.total || 0);

      // If URL contains alert id, auto-select it
      if (initialAlertId && !selected) {
        const found = list.find(a => a.id === initialAlertId);
        if (found) setSelected(found);
      }
    } catch (e: any) {
      setError('Failed to load alerts. Check backend connection.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [filters, page, initialAlertId, selected]);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);

  // Client-side search filter
  const filteredAlerts = filters.search
    ? alerts.filter(a =>
        a.id.toLowerCase().includes(filters.search.toLowerCase()) ||
        a.alert_type.toLowerCase().includes(filters.search.toLowerCase()) ||
        a.severity.toLowerCase().includes(filters.search.toLowerCase())
      )
    : alerts;

  const handleStatusChange = async (alertId: string, status: string) => {
    await fetch(`${API}/api/v1/alerts/${alertId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    await fetchAlerts();
    // Refresh selected alert
    if (selected?.id === alertId) {
      const res = await fetch(`${API}/api/v1/alerts/${alertId}`);
      if (res.ok) setSelected(await res.json());
    }
  };

  const handleAddNote = async (alertId: string, content: string) => {
    await fetch(`${API}/api/v1/alerts/${alertId}/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    // Refresh selected
    const res = await fetch(`${API}/api/v1/alerts/${alertId}`);
    if (res.ok) setSelected(await res.json());
  };

  const handleSelectAlert = async (alert: Alert) => {
    // Fetch full detail
    try {
      const res = await fetch(`${API}/api/v1/alerts/${alert.id}`);
      if (res.ok) {
        setSelected(await res.json());
      } else {
        setSelected(alert);
      }
    } catch {
      setSelected(alert);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div className="page-header" style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 className="page-title">Alert Investigation</h1>
          <p className="page-subtitle">{total} alerts • Select an alert to investigate</p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={() => fetchAlerts(true)} disabled={refreshing} aria-label="Refresh alerts">
          <RefreshCw size={13} style={{ transform: refreshing ? 'rotate(360deg)' : 'none', transition: 'transform 0.5s' }} />
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {/* Filters row */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
        {/* Search */}
        <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
          <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)', pointerEvents: 'none' }} />
          <input
            className="input input-search"
            placeholder="Search by ID, type…"
            value={filters.search}
            onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
            aria-label="Search alerts"
          />
        </div>

        <select className="select" value={filters.severity} onChange={e => setFilters(f => ({ ...f, severity: e.target.value }))} aria-label="Filter by severity">
          <option value="">All Severities</option>
          {SEVERITY_OPTIONS.filter(Boolean).map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        <select className="select" value={filters.status} onChange={e => setFilters(f => ({ ...f, status: e.target.value }))} aria-label="Filter by status">
          <option value="">All Statuses</option>
          {STATUS_OPTIONS.filter(Boolean).map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
        </select>

        <select className="select" value={filters.datasetId} onChange={e => setFilters(f => ({ ...f, datasetId: e.target.value }))} aria-label="Filter by dataset">
          <option value="">All Datasets</option>
          {datasets.map(d => <option key={d.dataset_id} value={d.dataset_id}>{d.dataset_id}</option>)}
        </select>

        {(filters.severity || filters.status || filters.search || filters.datasetId) && (
          <button className="btn btn-ghost btn-sm" onClick={() => setFilters({ severity: '', status: '', minRisk: 0, search: '', datasetId: '' })}>
            <X size={12} />
            Clear
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10, padding: '12px 16px', marginBottom: 20, fontSize: 13, color: '#f87171', display: 'flex', alignItems: 'center', gap: 8 }}>
          <AlertTriangle size={14} />
          {error}
          <button className="btn btn-danger btn-sm" style={{ marginLeft: 'auto' }} onClick={() => fetchAlerts()}>Retry</button>
        </div>
      )}

      {/* Main content */}
      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="skeleton" style={{ height: 52, borderRadius: 10 }} />
          ))}
        </div>
      ) : filteredAlerts.length === 0 ? (
        <div className="glass-card">
          <div className="empty-state">
            <Shield size={40} className="empty-state-icon" />
            <div className="empty-state-title">No alerts found</div>
            <div className="empty-state-body">
              {filters.severity || filters.status || filters.search
                ? 'Try adjusting your filters'
                : 'Run the stream producer to generate alerts'}
            </div>
          </div>
        </div>
      ) : (
        <>
          {/* Desktop table */}
          <div className="glass-card hide-mobile" style={{ overflow: 'hidden' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Alert ID</th>
                  <th>Type</th>
                  <th>Severity</th>
                  <th style={{ minWidth: 140 }}>Risk Score</th>
                  <th>Status</th>
                  <th>Entities</th>
                  <th>Dataset</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredAlerts.map(alert => {
                  const score = alert.risk_components?.final_risk_score || 0;
                  const isSelected = selected?.id === alert.id;
                  return (
                    <tr
                      key={alert.id}
                      onClick={() => handleSelectAlert(alert)}
                      className={isSelected ? 'selected' : ''}
                      style={{ cursor: 'pointer' }}
                      tabIndex={0}
                      onKeyDown={e => e.key === 'Enter' && handleSelectAlert(alert)}
                      aria-selected={isSelected}
                      aria-label={`Alert ${alert.id}, ${alert.severity} severity`}
                    >
                      <td>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-accent)' }}>
                          {alert.id.slice(-14)}
                        </span>
                      </td>
                      <td style={{ fontSize: 12, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {alert.alert_type.replace(/_/g, ' ')}
                      </td>
                      <td><SeverityBadge s={alert.severity} /></td>
                      <td><RiskBar score={score} /></td>
                      <td><StatusBadge s={alert.status} /></td>
                      <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{alert.entity_ids?.length || 0}</td>
                      <td style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {alert.dataset_id}
                      </td>
                      <td style={{ fontSize: 11, color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
                        {new Date(alert.created_at).toLocaleString()}
                      </td>
                      <td>
                        <Eye size={13} style={{ color: isSelected ? 'var(--accent)' : 'var(--text-tertiary)', opacity: 0.7 }} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="show-mobile" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {filteredAlerts.map(alert => {
              const score = alert.risk_components?.final_risk_score || 0;
              const scoreColor = score >= 80 ? '#ef4444' : score >= 60 ? '#f97316' : score >= 30 ? '#f59e0b' : '#10b981';
              return (
                <div
                  key={alert.id}
                  className={`alert-card ${alert.severity.toLowerCase()}`}
                  onClick={() => handleSelectAlert(alert)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => e.key === 'Enter' && handleSelectAlert(alert)}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <div>
                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-accent)', marginBottom: 4 }}>
                        {alert.id.slice(-12)}
                      </div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                        {alert.alert_type.replace(/_/g, ' ')}
                      </div>
                    </div>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: 20, fontWeight: 900, color: scoreColor }}>{score.toFixed(0)}</div>
                      <div style={{ fontSize: 8, color: scoreColor, fontWeight: 700 }}>RISK</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      <SeverityBadge s={alert.severity} />
                      <StatusBadge s={alert.status} />
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                      {new Date(alert.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 10, marginTop: 20 }}>
              <button
                className="btn btn-secondary btn-sm"
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
                aria-label="Previous page"
              >
                Previous
              </button>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                Page {page} of {totalPages}
              </span>
              <button
                className="btn btn-secondary btn-sm"
                disabled={page === totalPages}
                onClick={() => setPage(p => p + 1)}
                aria-label="Next page"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}

      {/* Investigation Panel */}
      {selected && (
        <InvestigationPanel
          alert={selected}
          onClose={() => setSelected(null)}
          onStatusChange={handleStatusChange}
          onAddNote={handleAddNote}
        />
      )}
    </div>
  );
}

export default function AlertsPage() {
  return (
    <Suspense fallback={<div className="glass-card" style={{ padding: 40, color: 'var(--text-secondary)', textAlign: 'center' }}>Loading Alerts Workspace…</div>}>
      <AlertsPageContent />
    </Suspense>
  );
}
