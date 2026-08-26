'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { BarChart3, RefreshCw, CheckCircle } from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface EvalResult {
  run_at: string;
  labeled_transactions: number;
  true_positives: number;
  false_positives: number;
  false_negatives: number;
  true_negatives: number;
  precision: number;
  recall: number;
  f1: number;
  false_positive_rate: number;
  per_scenario: Record<string, {
    precision: number; recall: number; f1: number;
    tp: number; fp: number; fn: number; tn: number;
  }>;
}

function Gauge({ value, label, color = '#3b82f6' }: { value: number; label: string; color?: string }) {
  const pct = (value * 100).toFixed(1);
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ position: 'relative', width: 100, height: 100, margin: '0 auto' }}>
        <svg viewBox="0 0 100 100" style={{ transform: 'rotate(-90deg)' }}>
          <circle cx="50" cy="50" r="40" fill="none" stroke="#1e293b" strokeWidth="10" />
          <circle cx="50" cy="50" r="40" fill="none"
            stroke={color} strokeWidth="10"
            strokeDasharray={`${value * 251.2} 251.2`}
            strokeLinecap="round" />
        </svg>
        <div style={{
          position: 'absolute', inset: 0, display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          flexDirection: 'column',
        }}>
          <span style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0' }}>{pct}%</span>
        </div>
      </div>
      <div style={{ fontSize: 12, color: '#64748b', marginTop: 6, fontWeight: 500 }}>{label}</div>
    </div>
  );
}

export default function EvaluationPage() {
  const [result, setResult] = useState<EvalResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');

  const fetchLatest = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/v1/evaluation/latest`);
      if (res.ok) setResult(await res.json());
    } catch {}
  }, []);

  useEffect(() => { fetchLatest(); }, [fetchLatest]);

  const runEvaluation = async () => {
    setRunning(true);
    setError('');
    try {
      const res = await fetch(`${API}/api/v1/evaluation/run`, { method: 'POST' });
      if (!res.ok) throw new Error('Evaluation failed');
      const data = await res.json();
      if (data.status === 'no_labeled_data') {
        setError(data.message);
      } else {
        setResult(data);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const confusionData = result ? [
    { label: 'TP', value: result.true_positives, color: '#10b981' },
    { label: 'FP', value: result.false_positives, color: '#ef4444' },
    { label: 'FN', value: result.false_negatives, color: '#f59e0b' },
    { label: 'TN', value: result.true_negatives, color: '#3b82f6' },
  ] : [];

  const scenarioData = result
    ? Object.entries(result.per_scenario).map(([name, m]) => ({
        name: name.replace(/_/g, ' ').slice(0, 15),
        precision: m.precision * 100,
        recall: m.recall * 100,
        f1: m.f1 * 100,
      }))
    : [];

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0', marginBottom: 4 }}>
            Detection Evaluation
          </h2>
          <p style={{ fontSize: 13, color: '#64748b' }}>
            Benchmark detection performance against synthetic ground-truth labels.
          </p>
        </div>
        <button
          onClick={runEvaluation}
          disabled={running}
          className="btn-primary"
          style={{ display: 'flex', alignItems: 'center', gap: 6 }}
        >
          {running ? <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <BarChart3 size={14} />}
          {running ? 'Running…' : 'Run Evaluation'}
        </button>
      </div>

      {error && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)',
          borderRadius: 8, padding: 12, marginBottom: 20, color: '#fca5a5', fontSize: 13 }}>
          {error}
        </div>
      )}

      {!result && !running && (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#64748b' }}>
          <BarChart3 size={40} style={{ marginBottom: 12, opacity: 0.3 }} />
          <div>No evaluation results yet.</div>
          <div style={{ fontSize: 12, marginTop: 4 }}>
            Run synthetic data first, then click "Run Evaluation"
          </div>
        </div>
      )}

      {result && (
        <>
          {/* Timestamp */}
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 20 }}>
            Last run: {new Date(result.run_at).toLocaleString()} · 
            {result.labeled_transactions} labeled transactions
          </div>

          {/* Gauges */}
          <div className="glass-card" style={{ padding: 24, marginBottom: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', marginBottom: 20 }}>
              Overall Detection Metrics
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-around', flexWrap: 'wrap', gap: 16 }}>
              <Gauge value={result.precision} label="Precision" color="#3b82f6" />
              <Gauge value={result.recall} label="Recall (TPR)" color="#10b981" />
              <Gauge value={result.f1} label="F1 Score" color="#8b5cf6" />
              <Gauge value={result.false_positive_rate} label="FPR" color="#ef4444" />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
            {/* Confusion Matrix */}
            <div className="glass-card" style={{ padding: 20 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', marginBottom: 16 }}>
                Confusion Matrix
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                {confusionData.map(({ label, value, color }) => (
                  <div key={label} style={{
                    background: `${color}11`, border: `1px solid ${color}33`,
                    borderRadius: 8, padding: 16, textAlign: 'center',
                  }}>
                    <div style={{ fontSize: 24, fontWeight: 700, color }}>{value}</div>
                    <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                      {label === 'TP' ? 'True Positives' :
                       label === 'FP' ? 'False Positives' :
                       label === 'FN' ? 'False Negatives' : 'True Negatives'}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Per-scenario */}
            <div className="glass-card" style={{ padding: 20 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', marginBottom: 16 }}>
                Per-Scenario F1
              </div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={scenarioData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                  <XAxis type="number" tick={{ fill: '#64748b', fontSize: 10 }} domain={[0, 100]} />
                  <YAxis type="category" dataKey="name" tick={{ fill: '#64748b', fontSize: 9 }} width={80} />
                  <Tooltip contentStyle={{ background: '#1a2236', border: '1px solid #1e293b' }} />
                  <Bar dataKey="f1" name="F1 (%)" fill="#3b82f6" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Scenario breakdown table */}
          <div className="glass-card" style={{ padding: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', marginBottom: 16 }}>
              Scenario Breakdown
            </div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Scenario</th>
                  <th>Precision</th>
                  <th>Recall</th>
                  <th>F1</th>
                  <th>TP</th>
                  <th>FP</th>
                  <th>FN</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(result.per_scenario).map(([scenario, m]) => (
                  <tr key={scenario}>
                    <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{scenario.replace(/_/g, ' ')}</td>
                    <td style={{ color: m.precision >= 0.8 ? '#10b981' : m.precision >= 0.6 ? '#f59e0b' : '#ef4444' }}>
                      {(m.precision * 100).toFixed(1)}%
                    </td>
                    <td style={{ color: m.recall >= 0.8 ? '#10b981' : m.recall >= 0.6 ? '#f59e0b' : '#ef4444' }}>
                      {(m.recall * 100).toFixed(1)}%
                    </td>
                    <td style={{ color: m.f1 >= 0.8 ? '#10b981' : m.f1 >= 0.6 ? '#f59e0b' : '#ef4444', fontWeight: 600 }}>
                      {(m.f1 * 100).toFixed(1)}%
                    </td>
                    <td style={{ color: '#10b981' }}>{m.tp}</td>
                    <td style={{ color: '#ef4444' }}>{m.fp}</td>
                    <td style={{ color: '#f59e0b' }}>{m.fn}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
