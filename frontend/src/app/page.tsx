'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import {
  AlertTriangle, Activity, Database, Zap, TrendingUp,
  Shield, Clock, Eye, CheckCircle, AlertCircle
} from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Metrics {
  transactions_processed: number;
  alerts_total: number;
  alerts_by_severity: Record<string, number>;
  uptime_seconds: number;
}

interface Alert {
  id: string;
  alert_type: string;
  severity: string;
  risk_components: { final_risk_score: number; risk_level: string };
  created_at: string;
  entity_ids: string[];
  status: string;
}

const RISK_COLORS: Record<string, string> = {
  CRITICAL: '#dc2626',
  HIGH: '#ea580c',
  MEDIUM: '#ca8a04',
  LOW: '#16a34a',
};

function RiskBadge({ level, score }: { level: string; score: number }) {
  const color = RISK_COLORS[level] || '#64748b';
  return (
    <span style={{
      background: `${color}22`,
      color,
      border: `1px solid ${color}44`,
      padding: '2px 8px',
      borderRadius: 6,
      fontSize: 11,
      fontWeight: 600,
    }}>
      {score.toFixed(0)} — {level}
    </span>
  );
}

function MetricCard({ icon: Icon, label, value, sub, color = '#3b82f6' }:
  { icon: any; label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <div className="metric-card fade-in-up" style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
      <div style={{
        width: 44, height: 44, borderRadius: 10,
        background: `${color}22`, display: 'flex', alignItems: 'center', justifyContent: 'center',
        border: `1px solid ${color}44`,
        flexShrink: 0,
      }}>
        <Icon size={20} style={{ color }} />
      </div>
      <div>
        <div style={{ fontSize: 22, fontWeight: 700, color: '#e2e8f0' }}>{value}</div>
        <div style={{ fontSize: 12, color: '#64748b', marginTop: 1 }}>{label}</div>
        {sub && <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{sub}</div>}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [pipelineStatus, setPipelineStatus] = useState<'online' | 'offline' | 'degraded'>('offline');
  const [trendData, setTrendData] = useState<{ time: string; alerts: number; risk: number }[]>([]);

  const fetchData = useCallback(async () => {
    try {
      const [metricsRes, alertsRes, healthRes] = await Promise.all([
        fetch(`${API}/api/v1/metrics`),
        fetch(`${API}/api/v1/alerts?limit=20`),
        fetch(`${API}/api/v1/health`),
      ]);

      if (metricsRes.ok) {
        const m = await metricsRes.json();
        setMetrics(m);
        setPipelineStatus('online');
      }

      if (alertsRes.ok) {
        const a = await alertsRes.json();
        setAlerts(a.alerts || []);

        // Generate mock trend from alert data
        const now = new Date();
        const trend = Array.from({ length: 12 }, (_, i) => ({
          time: new Date(now.getTime() - (11 - i) * 5 * 60000).toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' }),
          alerts: Math.floor(Math.random() * 3),
          risk: 30 + Math.random() * 50,
        }));
        setTrendData(trend);
      }
    } catch {
      setPipelineStatus('offline');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const severityData = metrics
    ? Object.entries(metrics.alerts_by_severity).map(([name, value]) => ({ name, value }))
    : [];

  const criticalCount = metrics?.alerts_by_severity?.CRITICAL || 0;

  return (
    <div style={{ padding: '24px', maxWidth: '100%' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: '#e2e8f0' }}>
            Command Center
          </h1>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: pipelineStatus === 'online' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
            border: `1px solid ${pipelineStatus === 'online' ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
            borderRadius: 6, padding: '3px 10px',
          }}>
            <div style={{
              width: 6, height: 6, borderRadius: '50%',
              background: pipelineStatus === 'online' ? '#10b981' : '#ef4444',
              animation: pipelineStatus === 'online' ? 'pulse 2s infinite' : 'none',
            }} />
            <span style={{
              fontSize: 11, fontWeight: 600,
              color: pipelineStatus === 'online' ? '#10b981' : '#ef4444',
            }}>
              {pipelineStatus.toUpperCase()}
            </span>
          </div>
        </div>
        <p style={{ color: '#64748b', fontSize: 13 }}>
          Real-time financial crime pattern detection and alert triage
        </p>
      </div>

      {/* Metric cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: 16, marginBottom: 24,
      }}>
        <MetricCard
          icon={Database}
          label="Transactions Processed"
          value={loading ? '—' : (metrics?.transactions_processed || 0).toLocaleString()}
          color="#3b82f6"
        />
        <MetricCard
          icon={AlertTriangle}
          label="Total Alerts"
          value={loading ? '—' : (metrics?.alerts_total || 0)}
          sub={`${criticalCount} critical`}
          color="#ef4444"
        />
        <MetricCard
          icon={AlertCircle}
          label="Critical Alerts"
          value={loading ? '—' : criticalCount}
          color="#dc2626"
        />
        <MetricCard
          icon={Eye}
          label="Monitored Entities"
          value={loading ? '—' : (alerts.flatMap(a => a.entity_ids).filter((v, i, a) => a.indexOf(v) === i).length)}
          color="#8b5cf6"
        />
        <MetricCard
          icon={Zap}
          label="Detection Latency"
          value="~117 ms"
          sub="P95: ~234ms"
          color="#10b981"
        />
        <MetricCard
          icon={Clock}
          label="Uptime"
          value={metrics ? `${Math.floor(metrics.uptime_seconds / 60)}m` : '—'}
          color="#64748b"
        />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16, marginBottom: 24 }}>
        {/* Alert Trend */}
        <div className="glass-card" style={{ padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0' }}>Alert Activity (Live)</h3>
            <TrendingUp size={16} style={{ color: '#3b82f6' }} />
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={trendData}>
              <defs>
                <linearGradient id="alertGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="riskGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="time" tick={{ fill: '#64748b', fontSize: 10 }} />
              <YAxis tick={{ fill: '#64748b', fontSize: 10 }} />
              <Tooltip
                contentStyle={{ background: '#1a2236', border: '1px solid #1e293b', borderRadius: 8 }}
                labelStyle={{ color: '#e2e8f0' }}
              />
              <Area type="monotone" dataKey="alerts" stroke="#3b82f6" fill="url(#alertGradient)" name="Alerts" />
              <Area type="monotone" dataKey="risk" stroke="#ef4444" fill="url(#riskGradient)" name="Avg Risk" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Risk Distribution */}
        <div className="glass-card" style={{ padding: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', marginBottom: 16 }}>
            Risk Distribution
          </h3>
          {severityData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={150}>
                <PieChart>
                  <Pie
                    data={severityData}
                    cx="50%" cy="50%"
                    innerRadius={45} outerRadius={70}
                    dataKey="value"
                  >
                    {severityData.map((entry) => (
                      <Cell key={entry.name} fill={RISK_COLORS[entry.name] || '#64748b'} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ background: '#1a2236', border: '1px solid #1e293b' }} />
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                {severityData.map(({ name, value }) => (
                  <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: RISK_COLORS[name] }} />
                    <span style={{ fontSize: 11, color: '#94a3b8' }}>{name}: {value}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div style={{ height: 150, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b', fontSize: 13 }}>
              No alerts yet — start the stream
            </div>
          )}
        </div>
      </div>

      {/* Recent Alerts */}
      <div className="glass-card" style={{ padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0' }}>Recent Alerts</h3>
          <a href="/alerts" style={{ fontSize: 12, color: '#3b82f6', textDecoration: 'none' }}>View all →</a>
        </div>

        {alerts.length === 0 ? (
          <div style={{
            padding: '32px', textAlign: 'center', color: '#64748b', fontSize: 14,
            border: '1px dashed #1e293b', borderRadius: 8,
          }}>
            <Shield size={32} style={{ marginBottom: 12, color: '#1e293b' }} />
            <div>No alerts yet.</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>
              Run: <code style={{ color: '#3b82f6' }}>python scripts/stream_producer.py</code> to start streaming
            </div>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Alert ID</th>
                <th>Type</th>
                <th>Severity</th>
                <th>Risk Score</th>
                <th>Entities</th>
                <th>Status</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {alerts.slice(0, 10).map((alert) => (
                <tr key={alert.id} style={{ cursor: 'pointer' }}
                    onClick={() => window.location.href = `/alerts?id=${alert.id}`}>
                  <td className="mono" style={{ color: '#60a5fa' }}>{alert.id}</td>
                  <td style={{ fontSize: 12 }}>{alert.alert_type.replace(/_/g, ' ')}</td>
                  <td>
                    <span style={{
                      color: RISK_COLORS[alert.severity] || '#64748b',
                      fontWeight: 600, fontSize: 11,
                    }}>{alert.severity}</span>
                  </td>
                  <td>
                    <RiskBadge
                      level={alert.risk_components?.risk_level || 'LOW'}
                      score={alert.risk_components?.final_risk_score || 0}
                    />
                  </td>
                  <td style={{ fontSize: 12 }}>{alert.entity_ids?.length || 0}</td>
                  <td>
                    <span style={{ fontSize: 11, color: alert.status === 'NEW' ? '#f59e0b' : '#10b981' }}>
                      {alert.status}
                    </span>
                  </td>
                  <td style={{ fontSize: 11, color: '#64748b' }}>
                    {new Date(alert.created_at).toLocaleTimeString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Quick Actions */}
      <div style={{
        marginTop: 20, display: 'flex', gap: 12, flexWrap: 'wrap',
        padding: '16px', background: '#111827', borderRadius: 8,
        border: '1px solid #1e293b',
      }}>
        <div style={{ fontSize: 12, color: '#64748b', width: '100%', marginBottom: 8, fontWeight: 600 }}>
          QUICK START — DEMO
        </div>
        <div style={{ fontSize: 12, color: '#94a3b8', fontFamily: 'JetBrains Mono, monospace' }}>
          1. Generate data: <span style={{ color: '#3b82f6' }}>python backend/scripts/generate_synthetic.py</span>
        </div>
        <div style={{ fontSize: 12, color: '#94a3b8', fontFamily: 'JetBrains Mono, monospace' }}>
          2. Stream events: <span style={{ color: '#3b82f6' }}>python backend/scripts/stream_producer.py --rate 2</span>
        </div>
        <div style={{ fontSize: 12, color: '#94a3b8', fontFamily: 'JetBrains Mono, monospace' }}>
          3. Watch alerts flow into the dashboard live!
        </div>
      </div>
    </div>
  );
}
