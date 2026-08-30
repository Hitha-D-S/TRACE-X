'use client';

import React, { useState, useEffect, useCallback, useRef, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  FlaskConical, AlertTriangle, ArrowRight, X, Plus,
  Play, RefreshCw, Database, Shield, TrendingDown, TrendingUp,
  AlertCircle, CheckCircle
} from 'lucide-react';
import { datasetUploadedThisSession } from '../session-state';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface WhatIfResult {
  simulation: boolean;
  disclaimer: string;
  cluster_id: string;
  excluded_entities: string[];
  original_metrics: Record<string, number>;
  simulated_metrics: Record<string, number>;
  paths_removed: number;
  risk_score_change: number;
  entities_remaining: number;
  explanation: string;
}

interface AlertSummary {
  id: string;
  alert_type: string;
  severity: string;
  risk_components: { final_risk_score: number };
  entity_ids: string[];
}

// ── Animated diff metric ────────────────────────────────────────
function MetricDiff({
  label, original, simulated, reverse = false,
}: {
  label: string; original: number; simulated: number; reverse?: boolean;
}) {
  const diff = simulated - original;
  const changed = Math.abs(diff) > 0.0001;
  // "reverse=true" means decrease is good (e.g., risk)
  const isGood = reverse ? diff < 0 : diff > 0;
  const diffColor = !changed ? 'var(--text-tertiary)' : isGood ? '#34d399' : '#f87171';

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 4,
      padding: '12px 14px',
      background: 'rgba(10, 18, 35, 0.6)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 10,
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>
        {label}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 14, color: 'var(--text-tertiary)', fontWeight: 600 }}>
          {typeof original === 'number' ? (original < 10 ? original.toFixed(4) : original.toFixed(0)) : '—'}
        </span>
        <ArrowRight size={12} style={{ color: 'var(--text-tertiary)', flexShrink: 0 }} />
        <span style={{ fontSize: 16, color: 'var(--text-primary)', fontWeight: 800 }}>
          {typeof simulated === 'number' ? (simulated < 10 ? simulated.toFixed(4) : simulated.toFixed(0)) : '—'}
        </span>
        {changed && (
          <span style={{ fontSize: 12, fontWeight: 700, color: diffColor, marginLeft: 'auto' }}>
            {diff > 0 ? '+' : ''}{diff < 10 ? diff.toFixed(4) : diff.toFixed(0)}
          </span>
        )}
      </div>
    </div>
  );
}

function WhatIfPageContent() {
  const searchParams = useSearchParams();
  const urlAlertId = searchParams.get('alert');

  const [alerts, setAlerts] = useState<AlertSummary[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [selectedAlertId, setSelectedAlertId] = useState(urlAlertId || '');
  const [selectedAlert, setSelectedAlert] = useState<AlertSummary | null>(null);
  const [excludedEntities, setExcludedEntities] = useState<string[]>([]);
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [simulating, setSimulating] = useState(false);
  const [error, setError] = useState('');
  const [animateResult, setAnimateResult] = useState(false);

  // Load alerts
  useEffect(() => {
    if (!datasetUploadedThisSession) {
      setAlerts([]);
      setAlertsLoading(false);
      return;
    }
    fetch(`${API}/api/v1/alerts?limit=50`)
      .then(r => r.json())
      .then(d => {
        const list: AlertSummary[] = d.alerts || [];
        setAlerts(list);
        setAlertsLoading(false);
        // Auto-select from URL or first alert
        const targetId = urlAlertId || (list.length > 0 ? list[0].id : '');
        if (targetId) {
          setSelectedAlertId(targetId);
          const found = list.find(a => a.id === targetId);
          if (found) setSelectedAlert(found);
        }
      })
      .catch(() => setAlertsLoading(false));
  }, [urlAlertId]);

  // When alert changes, reset
  const handleAlertChange = (alertId: string) => {
    setSelectedAlertId(alertId);
    setExcludedEntities([]);
    setResult(null);
    setError('');
    const found = alerts.find(a => a.id === alertId);
    setSelectedAlert(found || null);
  };

  const toggleEntity = (entityId: string) => {
    setExcludedEntities(prev =>
      prev.includes(entityId)
        ? prev.filter(e => e !== entityId)
        : [...prev, entityId]
    );
  };

  const runSimulation = async () => {
    if (!selectedAlertId || excludedEntities.length === 0) return;
    setSimulating(true);
    setError('');
    setResult(null);
    setAnimateResult(false);

    try {
      const res = await fetch(`${API}/api/v1/graph/what-if`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cluster_id: selectedAlertId,
          excluded_entity_ids: excludedEntities,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setResult(data);
      setTimeout(() => setAnimateResult(true), 50);
    } catch (e: any) {
      setError('Simulation failed. Check backend connection.');
    } finally {
      setSimulating(false);
    }
  };

  const METRIC_LABELS: Record<string, { label: string; reverse: boolean }> = {
    node_count: { label: 'Node Count', reverse: true },
    edge_count: { label: 'Edge Count', reverse: true },
    cycle_count: { label: 'Cycle Count', reverse: true },
    max_pagerank: { label: 'Max PageRank', reverse: true },
    density: { label: 'Graph Density', reverse: true },
    total_amount: { label: 'Total Amount', reverse: true },
  };

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      {/* Header */}
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h1 className="page-title">What-If Sandbox</h1>
            <p className="page-subtitle">Virtual entity exclusion — counterfactual analysis</p>
          </div>
          <div className="sim-disclaimer">
            <FlaskConical size={13} />
            SIMULATION ONLY — No stored data is modified
          </div>
        </div>

        {/* Step progression indicator */}
        <div style={{
          display: 'flex', gap: 8, marginTop: 14, padding: '8px 12px',
          background: 'rgba(10, 18, 35, 0.6)', border: '1px solid var(--border-subtle)',
          borderRadius: 8, fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)',
          alignItems: 'center', flexWrap: 'wrap',
        }}>
          <span style={{ color: selectedAlertId ? 'var(--accent-bright)' : 'var(--text-tertiary)' }}>1. SELECT CLUSTER</span>
          <ArrowRight size={10} />
          <span style={{ color: excludedEntities.length > 0 ? 'var(--accent-bright)' : 'var(--text-tertiary)' }}>2. EXCLUDE ENTITIES</span>
          <ArrowRight size={10} />
          <span style={{ color: simulating ? 'var(--accent-bright)' : 'var(--text-tertiary)' }}>3. RUN SIMULATION</span>
          <ArrowRight size={10} />
          <span style={{ color: result ? '#34d399' : 'var(--text-tertiary)' }}>4. BEFORE vs AFTER</span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 20, marginBottom: 20 }}>
        {/* ── Left: Configuration ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Alert selector */}
          <div className="glass-card" style={{ padding: 20 }}>
            <div className="section-label" style={{ marginBottom: 12 }}>
              <AlertTriangle size={10} />
              Select Alert Cluster
            </div>
            <select
              className="select"
              value={selectedAlertId}
              onChange={e => handleAlertChange(e.target.value)}
              style={{ width: '100%' }}
              aria-label="Select alert for what-if analysis"
            >
              <option value="">— Choose an alert —</option>
              {alerts.map(a => (
                <option key={a.id} value={a.id}>
                  {a.severity} · {a.alert_type.replace(/_/g, ' ')} · Risk {a.risk_components?.final_risk_score?.toFixed(0) || '?'}
                </option>
              ))}
            </select>
            {alertsLoading && <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 8 }}>Loading alerts…</div>}
          </div>

          {/* Entity selection */}
          {selectedAlert && (
            <div className="glass-card" style={{ padding: 20 }} role="region" aria-label="Entity exclusion controls">
              <div className="section-label" style={{ marginBottom: 12 }}>
                <Database size={10} />
                Entities in Cluster — Click to Exclude
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
                {selectedAlert.entity_ids.map(eid => {
                  const isExcluded = excludedEntities.includes(eid);
                  return (
                    <button
                      key={eid}
                      onClick={() => toggleEntity(eid)}
                      className={`entity-tag ${isExcluded ? 'excluded' : ''}`}
                      aria-pressed={isExcluded}
                      aria-label={`${isExcluded ? 'Re-include' : 'Exclude'} entity ${eid}`}
                    >
                      {isExcluded ? <X size={10} /> : <Plus size={10} />}
                      ···{eid.slice(-8)}
                    </button>
                  );
                })}
              </div>

              {excludedEntities.length > 0 && (
                <div style={{
                  padding: '10px 14px', borderRadius: 8,
                  background: 'rgba(239, 68, 68, 0.08)',
                  border: '1px solid rgba(239, 68, 68, 0.2)',
                  fontSize: 12, color: '#f87171', marginBottom: 14,
                }}>
                  <strong>{excludedEntities.length}</strong> {excludedEntities.length === 1 ? 'entity' : 'entities'} marked for virtual exclusion
                </div>
              )}

              <button
                className="btn btn-primary"
                style={{ width: '100%' }}
                onClick={runSimulation}
                disabled={simulating || excludedEntities.length === 0 || !selectedAlertId}
                aria-label="Run what-if simulation"
              >
                {simulating ? (
                  <>
                    <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} />
                    Simulating…
                  </>
                ) : (
                  <>
                    <Play size={14} />
                    Run Simulation
                  </>
                )}
              </button>

              {excludedEntities.length === 0 && (
                <p style={{ fontSize: 11, color: 'var(--text-tertiary)', textAlign: 'center', marginTop: 8 }}>
                  Select at least one entity to exclude
                </p>
              )}
            </div>
          )}
        </div>

        {/* ── Right: Results ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {error && (
            <div style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10, padding: '12px 16px', fontSize: 13, color: '#f87171' }}>
              {error}
            </div>
          )}

          {/* Simulation loading */}
          {simulating && (
            <div className="glass-card" style={{ padding: 40, textAlign: 'center' }}>
              <div style={{
                width: 40, height: 40, margin: '0 auto 16px',
                border: '3px solid rgba(139, 92, 246, 0.2)',
                borderTop: '3px solid #8b5cf6',
                borderRadius: '50%',
                animation: 'spin 1s linear infinite',
              }} />
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Running virtual simulation…</div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>No data is being modified</div>
            </div>
          )}

          {/* Results */}
          {result && animateResult && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {/* Summary header */}
              <div className="glass-card-elevated anim-scale-in" style={{ padding: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                  <CheckCircle size={18} style={{ color: '#34d399' }} />
                  <h3 style={{ fontSize: 14, fontWeight: 700 }}>Simulation Complete</h3>
                  <span className="badge badge-neutral" style={{ marginLeft: 'auto', fontSize: 9 }}>
                    SIMULATION ONLY
                  </span>
                </div>

                <div style={{
                  display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 12,
                }}>
                  {[
                    { label: 'Paths Removed', value: result.paths_removed, color: '#34d399' },
                    { label: 'Entities Remaining', value: result.entities_remaining, color: '#fbbf24' },
                    {
                      label: 'PageRank Δ',
                      value: result.risk_score_change > 0
                        ? `+${result.risk_score_change.toFixed(4)}`
                        : result.risk_score_change.toFixed(4),
                      color: result.risk_score_change <= 0 ? '#34d399' : '#f87171',
                    },
                  ].map(({ label, value, color }) => (
                    <div key={label} style={{
                      textAlign: 'center', padding: '12px 8px',
                      background: `${color}0C`, border: `1px solid ${color}20`,
                      borderRadius: 10,
                    }}>
                      <div style={{ fontSize: 20, fontWeight: 900, color }}>{value}</div>
                      <div style={{ fontSize: 9, color: 'var(--text-tertiary)', fontWeight: 700, letterSpacing: '0.08em', marginTop: 3 }}>{label}</div>
                    </div>
                  ))}
                </div>

                <div style={{
                  fontSize: 12, color: 'var(--text-secondary)',
                  lineHeight: 1.6,
                  background: 'rgba(10, 18, 35, 0.5)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 8, padding: '10px 12px',
                }}>
                  {result.explanation}
                </div>
              </div>

              {/* Metric diffs */}
              <div className="glass-card" style={{ padding: 20 }}>
                <div className="section-label" style={{ marginBottom: 12 }}>
                  Before → After Metrics
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {Object.entries(result.original_metrics).map(([key, original]) => {
                    const simulated = result.simulated_metrics[key] ?? original;
                    const meta = METRIC_LABELS[key] || { label: key.replace(/_/g, ' '), reverse: false };
                    return (
                      <MetricDiff
                        key={key}
                        label={meta.label}
                        original={original}
                        simulated={simulated}
                        reverse={meta.reverse}
                      />
                    );
                  })}
                </div>
              </div>

              {/* Disclaimer */}
              <div className="sim-disclaimer">
                <Shield size={12} />
                {result.disclaimer}
              </div>
            </div>
          )}

          {/* No result yet */}
          {!result && !simulating && !error && (
            <div className="glass-card">
              <div className="empty-state">
                <FlaskConical size={36} className="empty-state-icon" />
                <div className="empty-state-title">Ready to simulate</div>
                <div className="empty-state-body">
                  Select an alert, choose entities to virtually exclude, and run the simulation to see counterfactual analysis
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}

export default function WhatIfPage() {
  return (
    <Suspense fallback={<div className="glass-card" style={{ padding: 40, color: 'var(--text-secondary)', textAlign: 'center' }}>Loading Sandbox…</div>}>
      <WhatIfPageContent />
    </Suspense>
  );
}
