'use client';

import React, { useState, useEffect } from 'react';
import { FlaskConical, AlertCircle, ArrowRight, Minus, Plus } from 'lucide-react';

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

function MetricDiff({ label, original, simulated }: { label: string; original: number; simulated: number }) {
  const diff = simulated - original;
  const changed = Math.abs(diff) > 0.0001;
  const positive = diff > 0;

  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      paddingBottom: 10, borderBottom: '1px solid #1e293b', marginBottom: 10 }}>
      <span style={{ fontSize: 12, color: '#94a3b8' }}>{label}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 12, color: '#64748b' }}>{typeof original === 'number' ? original.toFixed(3) : original}</span>
        <ArrowRight size={12} style={{ color: '#334155' }} />
        <span style={{ fontSize: 12, color: '#e2e8f0', fontWeight: 600 }}>
          {typeof simulated === 'number' ? simulated.toFixed(3) : simulated}
        </span>
        {changed && (
          <span style={{
            fontSize: 11, fontWeight: 600,
            color: positive ? '#ef4444' : '#10b981',
          }}>
            {positive ? '+' : ''}{diff.toFixed(3)}
          </span>
        )}
      </div>
    </div>
  );
}

export default function WhatIfPage() {
  const [alertId, setAlertId] = useState('');
  const [inputId, setInputId] = useState('');
  const [alertData, setAlertData] = useState<any>(null);
  const [excludedEntities, setExcludedEntities] = useState<string[]>([]);
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('alert');
    if (id) { setAlertId(id); setInputId(id); }
  }, []);

  useEffect(() => {
    if (!alertId) return;
    fetch(`${API}/api/v1/alerts/${alertId}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setAlertData(d); })
      .catch(() => {});
  }, [alertId]);

  const runSimulation = async () => {
    if (!alertId) return;
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API}/api/v1/graph/what-if`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cluster_id: alertId,
          excluded_entity_ids: excludedEntities,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Simulation failed');
      }
      setResult(await res.json());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const toggleEntity = (entityId: string) => {
    setExcludedEntities(prev =>
      prev.includes(entityId) ? prev.filter(e => e !== entityId) : [...prev, entityId]
    );
    setResult(null);
  };

  return (
    <div style={{ padding: 24, maxWidth: '100%' }}>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0', marginBottom: 4 }}>
          What-If Sandbox
        </h2>
        <p style={{ fontSize: 13, color: '#64748b', maxWidth: 600 }}>
          Virtually exclude entities from the transaction network and observe the impact on 
          risk scores, cycle counts, and connectivity. <strong style={{ color: '#f59e0b' }}>
          No stored data is modified.</strong>
        </p>
      </div>

      {/* Simulation disclaimer */}
      <div style={{
        background: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.2)',
        borderRadius: 8, padding: 12, marginBottom: 20,
        display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <FlaskConical size={16} style={{ color: '#f59e0b', flexShrink: 0 }} />
        <div style={{ fontSize: 12, color: '#fbbf24' }}>
          <strong>Simulation Only</strong> — Results are virtual and do not affect stored graph data, 
          alerts, or any downstream processes. For investigative exploration only.
        </div>
      </div>

      {/* Alert selector */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        <input
          placeholder="Enter Alert/Cluster ID (e.g. ALT-ABC123)"
          value={inputId}
          onChange={e => setInputId(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && setAlertId(inputId)}
          style={{
            flex: 1, background: '#1a2236', border: '1px solid #1e293b',
            color: '#e2e8f0', borderRadius: 8, padding: '8px 14px', fontSize: 13, outline: 'none',
          }}
        />
        <button className="btn-primary" onClick={() => setAlertId(inputId)}>Load Alert</button>
      </div>

      {alertData && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
          {/* Entity selector */}
          <div style={{ background: '#111827', border: '1px solid #1e293b', borderRadius: 12, padding: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', marginBottom: 12 }}>
              Select Entities to Exclude
            </div>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 10 }}>
              Click an entity to toggle its exclusion from the simulation.
            </div>

            {alertData.entity_ids?.map((entityId: string) => {
              const excluded = excludedEntities.includes(entityId);
              return (
                <div
                  key={entityId}
                  onClick={() => toggleEntity(entityId)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '8px 12px', borderRadius: 8, marginBottom: 6, cursor: 'pointer',
                    background: excluded ? 'rgba(239, 68, 68, 0.1)' : '#1a2236',
                    border: `1px solid ${excluded ? 'rgba(239, 68, 68, 0.3)' : '#1e293b'}`,
                    transition: 'all 0.2s',
                  }}
                >
                  <div style={{
                    width: 20, height: 20, borderRadius: 4, border: '1px solid',
                    borderColor: excluded ? '#ef4444' : '#334155',
                    background: excluded ? 'rgba(239, 68, 68, 0.2)' : 'transparent',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    {excluded && <Minus size={12} style={{ color: '#ef4444' }} />}
                  </div>
                  <span className="mono" style={{
                    fontSize: 11,
                    color: excluded ? '#fca5a5' : '#94a3b8',
                    textDecoration: excluded ? 'line-through' : 'none',
                  }}>
                    ...{entityId.slice(-12)}
                  </span>
                  {excluded && (
                    <span style={{
                      marginLeft: 'auto', fontSize: 9,
                      color: '#ef4444', fontWeight: 600,
                    }}>EXCLUDED</span>
                  )}
                </div>
              );
            })}

            <button
              className="btn-primary"
              onClick={runSimulation}
              disabled={loading || excludedEntities.length === 0}
              style={{ width: '100%', marginTop: 12, opacity: excludedEntities.length === 0 ? 0.5 : 1 }}
            >
              {loading ? 'Running Simulation…' : `Run What-If (−${excludedEntities.length} entities)`}
            </button>

            {error && (
              <div style={{ color: '#ef4444', fontSize: 12, marginTop: 8,
                background: 'rgba(239,68,68,0.1)', borderRadius: 6, padding: 8 }}>
                {error}
              </div>
            )}
          </div>

          {/* Results */}
          <div style={{ background: '#111827', border: '1px solid #1e293b', borderRadius: 12, padding: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', marginBottom: 12 }}>
              Simulation Results
            </div>

            {!result && !loading && (
              <div style={{ color: '#64748b', fontSize: 12, padding: '40px 20px', textAlign: 'center' }}>
                Select entities and run simulation to see results
              </div>
            )}

            {loading && (
              <div style={{ color: '#64748b', fontSize: 12, padding: '40px 20px', textAlign: 'center' }}>
                Computing virtual exclusion…
              </div>
            )}

            {result && (
              <>
                {/* Summary */}
                <div style={{
                  background: 'rgba(139, 92, 246, 0.1)',
                  border: '1px solid rgba(139, 92, 246, 0.2)',
                  borderRadius: 8, padding: 12, marginBottom: 16,
                }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: '#a78bfa', marginBottom: 6 }}>
                    🔬 SIMULATION COMPLETE
                  </div>
                  <p style={{ fontSize: 12, color: '#c4b5fd', lineHeight: 1.5 }}>
                    {result.explanation}
                  </p>
                  <div style={{ marginTop: 8, fontSize: 12, color: '#94a3b8' }}>
                    Paths removed: <strong style={{ color: '#e2e8f0' }}>{result.paths_removed}</strong>
                    {' · '}
                    Risk change: <strong style={{
                      color: result.risk_score_change < 0 ? '#10b981' : '#ef4444'
                    }}>
                      {result.risk_score_change > 0 ? '+' : ''}{result.risk_score_change.toFixed(4)}
                    </strong>
                  </div>
                </div>

                {/* Metric comparison */}
                <div>
                  {Object.keys(result.original_metrics).map(key => (
                    <MetricDiff
                      key={key}
                      label={key.replace(/_/g, ' ')}
                      original={result.original_metrics[key]}
                      simulated={result.simulated_metrics[key] ?? 0}
                    />
                  ))}
                </div>

                <div style={{
                  marginTop: 12, fontSize: 10, color: '#64748b',
                  fontStyle: 'italic', borderTop: '1px solid #1e293b', paddingTop: 10,
                }}>
                  {result.disclaimer}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {!alertData && alertId && (
        <div style={{ color: '#64748b', textAlign: 'center', padding: 40 }}>
          Alert {alertId} not found. Check the ID and try again.
        </div>
      )}

      {!alertId && (
        <div style={{
          flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexDirection: 'column', gap: 12, color: '#64748b', padding: '60px 0',
        }}>
          <div style={{ fontSize: 48 }}>🧪</div>
          <div style={{ fontSize: 14 }}>Enter an Alert ID to explore What-If scenarios</div>
        </div>
      )}
    </div>
  );
}
