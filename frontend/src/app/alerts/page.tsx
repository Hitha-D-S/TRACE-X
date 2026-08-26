'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { AlertTriangle, Filter, Search, ChevronDown, Eye, MessageSquare, CheckCircle, X } from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const RISK_COLORS: Record<string, string> = {
  CRITICAL: '#dc2626', HIGH: '#ea580c', MEDIUM: '#ca8a04', LOW: '#16a34a',
};

const STATUS_COLORS: Record<string, string> = {
  NEW: '#f59e0b', INVESTIGATING: '#3b82f6', ESCALATED: '#8b5cf6',
  RESOLVED: '#10b981', FALSE_POSITIVE: '#64748b',
};

interface Alert {
  id: string;
  alert_type: string;
  severity: string;
  status: string;
  risk_components: { final_risk_score: number; risk_level: string; human_explanation: string };
  triggered_rules: Array<{ rule_id: string; score: number; explanation: string }>;
  entity_ids: string[];
  transaction_ids: string[];
  contributing_signals: Record<string, number>;
  created_at: string;
  assigned_to?: string;
  dataset_id: string;
}

function RiskBar({ score }: { score: number }) {
  const level = score >= 80 ? 'CRITICAL' : score >= 60 ? 'HIGH' : score >= 30 ? 'MEDIUM' : 'LOW';
  const color = RISK_COLORS[level];
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 4, background: '#1e293b', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${score}%`, background: color, borderRadius: 4 }} />
      </div>
      <span style={{ fontSize: 11, color, fontWeight: 600, minWidth: 28 }}>{score.toFixed(0)}</span>
    </div>
  );
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Alert | null>(null);
  const [filters, setFilters] = useState({ severity: '', status: '', minRisk: 0, search: '', datasetId: '' });
  const [datasets, setDatasets] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;

  useEffect(() => {
    fetch(`${API}/api/v1/datasets`)
      .then(res => res.json())
      .then(data => setDatasets(data.datasets || []))
      .catch(err => console.error("Error fetching datasets:", err));
  }, []);

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
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
      if (res.ok) {
        const data = await res.json();
        setAlerts(data.alerts || []);
        setTotal(data.total || 0);
      }
    } finally {
      setLoading(false);
    }
  }, [filters, page]);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);

  const filteredAlerts = alerts.filter(a =>
    !filters.search ||
    a.id.toLowerCase().includes(filters.search.toLowerCase()) ||
    a.alert_type.toLowerCase().includes(filters.search.toLowerCase())
  );

  const handleStatusChange = async (alertId: string, status: string) => {
    await fetch(`${API}/api/v1/alerts/${alertId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    fetchAlerts();
  };

  return (
    <div style={{ height: '100%', display: 'flex' }}>
      {/* Alert list */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header / filters */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #1e293b',
          background: '#0f1624', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <h2 style={{ fontSize: 15, fontWeight: 600, color: '#e2e8f0', marginRight: 8 }}>
            Alerts <span style={{ fontSize: 12, color: '#64748b' }}>({total})</span>
          </h2>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6,
            background: '#1a2236', border: '1px solid #1e293b', borderRadius: 8,
            padding: '5px 10px', flex: '1', maxWidth: 200 }}>
            <Search size={12} style={{ color: '#64748b' }} />
            <input placeholder="Search..." value={filters.search}
              onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
              style={{ background: 'none', border: 'none', outline: 'none',
                color: '#e2e8f0', fontSize: 12, width: '100%' }} />
          </div>

          {['severity', 'status'].map(f => (
            <select key={f}
              value={(filters as any)[f]}
              onChange={e => setFilters(prev => ({ ...prev, [f]: e.target.value }))}
              style={{ background: '#1a2236', border: '1px solid #1e293b', color: '#e2e8f0',
                borderRadius: 6, padding: '5px 8px', fontSize: 12, outline: 'none' }}>
              <option value="">All {f}</option>
              {f === 'severity'
                ? ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map(s => <option key={s}>{s}</option>)
                : ['NEW', 'INVESTIGATING', 'ESCALATED', 'RESOLVED'].map(s => <option key={s}>{s}</option>)
              }
            </select>
          ))}

          <select
            value={filters.datasetId}
            onChange={e => setFilters(prev => ({ ...prev, datasetId: e.target.value }))}
            style={{ background: '#1a2236', border: '1px solid #1e293b', color: '#e2e8f0',
              borderRadius: 6, padding: '5px 8px', fontSize: 12, outline: 'none' }}
          >
            <option value="">All Datasets (Demo)</option>
            {datasets.map(d => (
              <option key={d.dataset_id} value={d.dataset_id}>
                {d.dataset_id}
              </option>
            ))}
          </select>
        </div>

        {/* Table */}
        <div style={{ flex: 1, overflow: 'auto', padding: '0 20px 20px' }}>
          {loading ? (
            <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>Loading alerts…</div>
          ) : filteredAlerts.length === 0 ? (
            <div style={{ padding: '60px 40px', textAlign: 'center', color: '#64748b' }}>
              <AlertTriangle size={40} style={{ marginBottom: 12, opacity: 0.3 }} />
              <div>No alerts match your filters</div>
            </div>
          ) : (
            <table className="data-table" style={{ marginTop: 12 }}>
              <thead>
                <tr>
                  <th>Alert ID</th>
                  <th>Type</th>
                  <th>Severity</th>
                  <th>Risk Score</th>
                  <th>Entities</th>
                  <th>Status</th>
                  <th>Dataset</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {filteredAlerts.map(alert => (
                  <tr key={alert.id}
                    onClick={() => setSelected(alert)}
                    style={{ cursor: 'pointer',
                      background: selected?.id === alert.id ? 'rgba(59, 130, 246, 0.08)' : undefined }}>
                    <td className="mono" style={{ color: '#60a5fa', fontSize: 11 }}>{alert.id}</td>
                    <td style={{ fontSize: 11 }}>{alert.alert_type.replace(/_/g, ' ')}</td>
                    <td>
                      <span style={{ color: RISK_COLORS[alert.severity], fontWeight: 600, fontSize: 11 }}>
                        {alert.severity}
                      </span>
                    </td>
                    <td style={{ minWidth: 120 }}>
                      <RiskBar score={alert.risk_components?.final_risk_score || 0} />
                    </td>
                    <td style={{ fontSize: 12 }}>{alert.entity_ids?.length || 0}</td>
                    <td>
                      <span style={{ fontSize: 11, color: STATUS_COLORS[alert.status] || '#64748b',
                        background: `${STATUS_COLORS[alert.status]}22`, padding: '2px 7px', borderRadius: 5 }}>
                        {alert.status}
                      </span>
                    </td>
                    <td className="mono" style={{ fontSize: 10, color: '#64748b' }}>
                      {alert.dataset_id?.slice(0, 12)}
                    </td>
                    <td style={{ fontSize: 11, color: '#64748b' }}>
                      {new Date(alert.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Detail panel */}
      {selected && (
        <div style={{
          width: 380, borderLeft: '1px solid #1e293b',
          background: '#0f1624', overflow: 'auto', padding: 20,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>Alert Detail</span>
            <button onClick={() => setSelected(null)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b' }}>
              <X size={14} />
            </button>
          </div>

          <div className="mono" style={{ fontSize: 11, color: '#60a5fa', marginBottom: 12 }}>{selected.id}</div>

          {/* Risk breakdown */}
          <div style={{ background: '#1a2236', borderRadius: 8, padding: 14, marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8 }}>RISK BREAKDOWN</div>
            {Object.entries(selected.contributing_signals || {}).map(([signal, score]) => (
              <div key={signal} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 11, color: '#94a3b8', textTransform: 'capitalize' }}>{signal}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <div style={{ width: 60, height: 3, background: '#1e293b', borderRadius: 2 }}>
                    <div style={{ height: '100%', width: `${(score as number) * 100}%`,
                      background: '#3b82f6', borderRadius: 2 }} />
                  </div>
                  <span style={{ fontSize: 11, color: '#60a5fa' }}>{((score as number) * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>

          {/* Triggered rules */}
          {selected.triggered_rules?.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, color: '#64748b', marginBottom: 8 }}>TRIGGERED RULES</div>
              {selected.triggered_rules.map((rule, i) => (
                <div key={i} style={{
                  background: '#1a2236', borderRadius: 8, padding: 10, marginBottom: 6,
                  border: '1px solid #1e293b',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: '#f59e0b' }}>{rule.rule_id}</span>
                    <span style={{ fontSize: 10, color: '#64748b' }}>Score: {(rule.score * 100).toFixed(0)}%</span>
                  </div>
                  <p style={{ fontSize: 11, color: '#94a3b8', lineHeight: 1.5 }}>{rule.explanation}</p>
                </div>
              ))}
            </div>
          )}

          {/* Explanation */}
          <div style={{ background: '#1a2236', borderRadius: 8, padding: 12, marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 6 }}>EXPLANATION</div>
            <p style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6 }}>
              {selected.risk_components?.human_explanation}
            </p>
          </div>

          {/* Entities */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 6 }}>ENTITIES ({selected.entity_ids?.length})</div>
            {selected.entity_ids?.slice(0, 5).map(e => (
              <div key={e} className="mono" style={{
                fontSize: 10, color: '#60a5fa', padding: '4px 0',
                borderBottom: '1px solid #1e293b',
              }}>...{e.slice(-12)}</div>
            ))}
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>ACTIONS</div>
            {['INVESTIGATING', 'ESCALATED', 'RESOLVED', 'FALSE_POSITIVE'].map(status => (
              <button key={status}
                onClick={() => handleStatusChange(selected.id, status)}
                style={{
                  padding: '7px 12px', borderRadius: 6, cursor: 'pointer',
                  background: `${STATUS_COLORS[status]}22`,
                  border: `1px solid ${STATUS_COLORS[status]}44`,
                  color: STATUS_COLORS[status],
                  fontSize: 11, textAlign: 'left',
                }}>
                → Mark as {status.replace('_', ' ')}
              </button>
            ))}

            <a href={`/replay?alert=${selected.id}`} style={{
              display: 'block', padding: '7px 12px', borderRadius: 6,
              background: 'rgba(59, 130, 246, 0.1)',
              border: '1px solid rgba(59, 130, 246, 0.3)',
              color: '#3b82f6', fontSize: 11, textDecoration: 'none',
            }}>▶ Replay this alert</a>

            <a href={`/whatif?alert=${selected.id}`} style={{
              display: 'block', padding: '7px 12px', borderRadius: 6,
              background: 'rgba(139, 92, 246, 0.1)',
              border: '1px solid rgba(139, 92, 246, 0.3)',
              color: '#8b5cf6', fontSize: 11, textDecoration: 'none',
            }}>🧪 What-If Analysis</a>

            <a href={`/assistant?alert=${selected.id}`} style={{
              display: 'block', padding: '7px 12px', borderRadius: 6,
              background: 'rgba(16, 185, 129, 0.1)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              color: '#10b981', fontSize: 11, textDecoration: 'none',
            }}>🤖 AI Brief</a>
          </div>
        </div>
      )}
    </div>
  );
}
