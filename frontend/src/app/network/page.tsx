'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  Search, RefreshCw, Maximize2, X, Database,
  Crosshair, Filter, Info, GitBranch, Shield,
  TrendingUp, Activity
} from 'lucide-react';
import { datasetUploadedThisSession } from '../session-state';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface GraphNode {
  id: string;
  label?: string;
  risk_score?: number;
  type?: string;
  dataset_id?: string;
  owner_name?: string;
  bank_name?: string;
  owner_type?: string;
}

interface GraphEdge {
  id: string;
  from: string;
  to: string;
  amount?: number;
  currency?: string;
  final_risk_score?: number;
  timestamp?: string;
  transaction_type?: string;
}

interface NodeDetail {
  id: string;
  risk_score: number;
  type: string;
  owner_name?: string;
  bank_name?: string;
  owner_type?: string;
  transactionCount?: number;
}

function getRiskLevel(score: number): string {
  if (score >= 80) return 'CRITICAL';
  if (score >= 60) return 'HIGH';
  if (score >= 30) return 'MEDIUM';
  if (score > 0) return 'LOW';
  return 'SAFE';
}

const RISK_COLORS: Record<string, string> = {
  CRITICAL: '#ef4444', HIGH: '#f97316', MEDIUM: '#f59e0b', LOW: '#10b981', SAFE: '#3b82f6',
};

function RiskBadge({ score }: { score: number }) {
  const level = getRiskLevel(score);
  const color = RISK_COLORS[level];
  return (
    <span className={`badge badge-${level.toLowerCase()}`}>
      {level} · {score.toFixed(0)}
    </span>
  );
}

export default function NetworkPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<any>(null);
  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] }>({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedNode, setSelectedNode] = useState<NodeDetail | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [minRisk, setMinRisk] = useState(0);
  const [datasetId, setDatasetId] = useState('');
  const [datasets, setDatasets] = useState<any[]>([]);
  const [nodeCount, setNodeCount] = useState(0);
  const [edgeCount, setEdgeCount] = useState(0);
  const [showPanel, setShowPanel] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/v1/datasets`)
      .then(r => r.json())
      .then(d => setDatasets(d.datasets || []))
      .catch(() => {});
  }, []);

  const fetchGraph = useCallback(async () => {
    if (!datasetUploadedThisSession) {
      setGraphData({ nodes: [], edges: [] });
      setNodeCount(0);
      setEdgeCount(0);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ use_cache: 'false', limit: '300' });
      if (minRisk > 0) params.set('min_risk', String(minRisk));
      if (datasetId) params.set('dataset_id', datasetId);

      const res = await fetch(`${API}/api/v1/graph/network?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setGraphData({ nodes: data.nodes || [], edges: data.edges || [] });
      setNodeCount(data.total_nodes || 0);
      setEdgeCount(data.total_edges || 0);
    } catch (e: any) {
      setError('Failed to load graph data. Check backend connection.');
    } finally {
      setLoading(false);
    }
  }, [minRisk, datasetId]);

  useEffect(() => { fetchGraph(); }, [fetchGraph]);

  // Keyboard Escape listener to close entity detail panel
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedNode(null);
        setShowPanel(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Initialize vis-network
  useEffect(() => {
    if (loading || !containerRef.current || graphData.nodes.length === 0) return;

    let mounted = true;
    const importVis = async () => {
      try {
        const { Network, DataSet } = await import('vis-network/standalone');

        if (!mounted || !containerRef.current) return;

        // Destroy old network
        if (networkRef.current) {
          networkRef.current.destroy();
          networkRef.current = null;
        }

        const visNodes = new DataSet(
          graphData.nodes.map(n => {
            const risk = n.risk_score || 0;
            const level = getRiskLevel(risk);
            const nodeColor = RISK_COLORS[level];
            return {
              id: n.id,
              label: n.label || `···${n.id.slice(-6)}`,
              title: `${n.owner_name || n.id}\nBank: ${n.bank_name || 'Unknown'}\nRisk: ${risk.toFixed(0)}`,
              color: {
                background: `${nodeColor}20`,
                border: nodeColor,
                highlight: { background: `${nodeColor}35`, border: nodeColor },
                hover: { background: `${nodeColor}30`, border: nodeColor },
              },
              font: { color: '#e8eef8', size: 11, face: 'JetBrains Mono, monospace' },
              borderWidth: risk >= 60 ? 2 : 1.5,
              borderWidthSelected: 3,
              size: 14 + Math.min(risk / 10, 12),
              shape: n.owner_type === 'COMPANY' ? 'box' : 'dot',
            };
          })
        );

        const visEdges = new DataSet(
          graphData.edges.map(e => {
            const risk = e.final_risk_score || 0;
            const edgeColor = risk >= 60 ? `${RISK_COLORS['HIGH']}90` : risk >= 30 ? `${RISK_COLORS['MEDIUM']}70` : 'rgba(59, 130, 246, 0.3)';
            return {
              id: e.id,
              from: e.from,
              to: e.to,
              title: `Amount: ${e.amount?.toLocaleString()} ${e.currency || 'INR'}\nRisk: ${risk.toFixed(0)}\nType: ${e.transaction_type || 'OTHER'}`,
              color: { color: edgeColor, highlight: '#60a5fa', hover: '#93c5fd' },
              width: 1 + Math.min(risk / 40, 3),
              arrows: { to: { enabled: true, scaleFactor: 0.6 } },
              smooth: { enabled: true, type: 'curvedCW', roundness: 0.15 },
            };
          })
        );

        const options = {
          nodes: {
            shape: 'dot',
            shadow: { enabled: true, size: 8, color: 'rgba(0,0,0,0.4)' },
          },
          edges: {
            smooth: { enabled: true, type: 'curvedCW', roundness: 0.15 },
            shadow: false,
          },
          physics: {
            enabled: true,
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {
              gravitationalConstant: -50,
              centralGravity: 0.01,
              springLength: 120,
              springConstant: 0.06,
              damping: 0.5,
            },
            stabilization: { iterations: 200, fit: true },
          },
          interaction: {
            hover: true,
            tooltipDelay: 200,
            navigationButtons: false,
            keyboard: false,
            zoomView: true,
          },
          background: { color: 'transparent' },
        };

        const network = new Network(containerRef.current, { nodes: visNodes, edges: visEdges }, options);
        networkRef.current = network;

        network.on('click', (params: any) => {
          if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const node = graphData.nodes.find(n => n.id === nodeId);
            if (node) {
              // Count transactions
              const txCount = graphData.edges.filter(e => e.from === nodeId || e.to === nodeId).length;
              setSelectedNode({
                id: node.id,
                risk_score: node.risk_score || 0,
                type: node.type || 'BankAccount',
                owner_name: node.owner_name,
                bank_name: node.bank_name,
                owner_type: node.owner_type,
                transactionCount: txCount,
              });
              setShowPanel(true);
            }
          } else {
            setSelectedNode(null);
            setShowPanel(false);
          }
        });

        // Stabilize then disable physics
        network.on('stabilizationIterationsDone', () => {
          network.setOptions({ physics: { enabled: false } });
        });

      } catch (err) {
        setError('Failed to initialize graph visualization.');
      }
    };

    importVis();
    return () => { mounted = false; };
  }, [graphData, loading]);

  // Search highlight
  const handleSearch = () => {
    if (!networkRef.current || !searchQuery.trim()) return;
    const matchNode = graphData.nodes.find(n =>
      n.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (n.owner_name || '').toLowerCase().includes(searchQuery.toLowerCase())
    );
    if (matchNode) {
      networkRef.current.focus(matchNode.id, { animation: { duration: 600, easingFunction: 'easeInOutQuad' }, scale: 1.5 });
      networkRef.current.selectNodes([matchNode.id]);
    }
  };

  const handleFitGraph = () => {
    networkRef.current?.fit({ animation: { duration: 600, easingFunction: 'easeInOutQuad' } });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 120px)', maxWidth: 1400, margin: '0 auto' }}>
      {/* Page header */}
      <div className="page-header" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h1 className="page-title">Live Transaction Network</h1>
            <p className="page-subtitle">
              {nodeCount} entities · {edgeCount} transactions · Follow the money
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn btn-secondary btn-sm" onClick={handleFitGraph} aria-label="Fit graph to view">
              <Maximize2 size={13} />
              Fit
            </button>
            <button className="btn btn-secondary btn-sm" onClick={fetchGraph} aria-label="Refresh graph">
              <RefreshCw size={13} />
              Refresh
            </button>
          </div>
        </div>

        {/* Controls */}
        <div style={{ display: 'flex', gap: 10, marginTop: 16, flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: 1, minWidth: 200, maxWidth: 320 }}>
            <Search size={13} style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)', pointerEvents: 'none' }} />
            <input
              className="input input-search"
              placeholder="Search entity or owner…"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              aria-label="Search graph node"
            />
          </div>
          <button className="btn btn-secondary btn-sm" onClick={handleSearch} aria-label="Find node">
            <Crosshair size={13} />
            Find
          </button>

          <select className="select" value={minRisk} onChange={e => setMinRisk(Number(e.target.value))} aria-label="Minimum risk filter">
            <option value={0}>All Risk Levels</option>
            <option value={30}>Medium+ (≥30)</option>
            <option value={60}>High+ (≥60)</option>
            <option value={80}>Critical (≥80)</option>
          </select>

          <select className="select" value={datasetId} onChange={e => setDatasetId(e.target.value)} aria-label="Dataset filter">
            <option value="">All Datasets</option>
            {datasets.map(d => <option key={d.dataset_id} value={d.dataset_id}>{d.dataset_id}</option>)}
          </select>
        </div>
      </div>

      {/* Graph area */}
      <div style={{ flex: 1, position: 'relative', minHeight: 0, display: 'flex', gap: 16 }}>
        {/* Graph canvas */}
        <div style={{ flex: 1, position: 'relative', minWidth: 0 }}>
          <div ref={containerRef} className="graph-container" style={{ width: '100%', height: '100%', minHeight: 400 }} />

          {/* Loading overlay */}
          {loading && (
            <div style={{
              position: 'absolute', inset: 0,
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              background: 'rgba(5, 8, 16, 0.85)', borderRadius: 14,
              gap: 14,
            }}>
              <div style={{
                width: 36, height: 36,
                border: '3px solid rgba(59, 130, 246, 0.2)',
                borderTop: '3px solid #3b82f6',
                borderRadius: '50%',
                animation: 'spin 1s linear infinite',
              }} />
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Loading transaction network…</div>
            </div>
          )}

          {/* Error overlay */}
          {error && !loading && (
            <div style={{
              position: 'absolute', inset: 0,
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              background: 'rgba(5, 8, 16, 0.85)', borderRadius: 14,
              gap: 10,
            }}>
              <Shield size={28} style={{ color: 'var(--critical)', opacity: 0.7 }} />
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{error}</div>
              <button className="btn btn-secondary btn-sm" onClick={fetchGraph}>Retry</button>
            </div>
          )}

          {/* Empty overlay */}
          {!loading && !error && graphData.nodes.length === 0 && (
            <div style={{
              position: 'absolute', inset: 0,
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              background: 'rgba(5, 8, 16, 0.7)', borderRadius: 14,
              gap: 10,
            }}>
              <GitBranch size={32} style={{ color: 'var(--text-tertiary)', opacity: 0.4 }} />
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>No transaction data yet</div>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Run the stream producer to populate the network</div>
            </div>
          )}

          {/* Graph legend */}
          {!loading && graphData.nodes.length > 0 && (
            <div style={{
              position: 'absolute', bottom: 16, left: 16,
              background: 'rgba(9, 14, 26, 0.9)', backdropFilter: 'blur(10px)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 8, padding: '8px 12px',
              display: 'flex', gap: 12, flexWrap: 'wrap',
            }}>
              {Object.entries(RISK_COLORS).map(([level, color]) => (
                <div key={level} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />
                  <span style={{ fontSize: 9, color: 'var(--text-tertiary)', fontWeight: 600, letterSpacing: '0.06em' }}>{level}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Node detail panel (desktop) */}
        {selectedNode && (
          <div className="hide-mobile glass-card anim-slide-right" style={{
            width: 280, flexShrink: 0, padding: 20,
            display: 'flex', flexDirection: 'column', gap: 14,
            alignSelf: 'flex-start',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ fontSize: 13, fontWeight: 700 }}>Entity Detail</h3>
              <button className="btn btn-ghost btn-icon btn-sm" onClick={() => { setSelectedNode(null); setShowPanel(false); }} aria-label="Close detail">
                <X size={14} />
              </button>
            </div>

            <div>
              <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 600, letterSpacing: '0.1em', marginBottom: 4 }}>ACCOUNT ID</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-accent)', wordBreak: 'break-all' }}>
                ···{selectedNode.id.slice(-10)}
              </div>
            </div>

            <div>
              <RiskBadge score={selectedNode.risk_score} />
            </div>

            {selectedNode.owner_name && (
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 600, letterSpacing: '0.1em', marginBottom: 4 }}>OWNER</div>
                <div style={{ fontSize: 12, color: 'var(--text-primary)' }}>{selectedNode.owner_name}</div>
              </div>
            )}

            {selectedNode.bank_name && (
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 600, letterSpacing: '0.1em', marginBottom: 4 }}>BANK</div>
                <div style={{ fontSize: 12, color: 'var(--text-primary)' }}>{selectedNode.bank_name}</div>
              </div>
            )}

            {selectedNode.owner_type && (
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 600, letterSpacing: '0.1em', marginBottom: 4 }}>TYPE</div>
                <div style={{ fontSize: 12, color: 'var(--text-primary)' }}>{selectedNode.owner_type}</div>
              </div>
            )}

            <div>
              <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontWeight: 600, letterSpacing: '0.1em', marginBottom: 4 }}>TRANSACTIONS</div>
              <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--text-primary)' }}>{selectedNode.transactionCount}</div>
            </div>

            <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: 12 }}>
              <a href={`/alerts?search=${selectedNode.id}`} style={{ textDecoration: 'none' }}>
                <button className="btn btn-secondary btn-sm" style={{ width: '100%' }}>
                  <Shield size={12} />
                  View Alerts
                </button>
              </a>
            </div>
          </div>
        )}
      </div>

      {/* Mobile node detail bottom sheet */}
      {selectedNode && showPanel && (
        <div className="show-mobile" style={{
          position: 'fixed', bottom: 64, left: 0, right: 0,
          background: 'rgba(9, 14, 26, 0.97)', backdropFilter: 'blur(16px)',
          border: '1px solid var(--border-default)', borderRadius: '20px 20px 0 0',
          padding: 20, zIndex: 150,
          animation: 'fadeInUp 0.3s ease',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <h3 style={{ fontSize: 14, fontWeight: 700 }}>Entity Detail</h3>
            <button className="btn btn-ghost btn-icon btn-sm" onClick={() => setShowPanel(false)} aria-label="Close">
              <X size={14} />
            </button>
          </div>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-accent)', marginBottom: 6 }}>···{selectedNode.id.slice(-10)}</div>
              <RiskBadge score={selectedNode.risk_score} />
              {selectedNode.owner_name && <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>{selectedNode.owner_name}</div>}
              {selectedNode.bank_name && <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{selectedNode.bank_name}</div>}
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 28, fontWeight: 900, color: RISK_COLORS[getRiskLevel(selectedNode.risk_score)] }}>{selectedNode.risk_score.toFixed(0)}</div>
              <div style={{ fontSize: 9, color: 'var(--text-tertiary)', fontWeight: 700 }}>RISK SCORE</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginTop: 4 }}>{selectedNode.transactionCount}</div>
              <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>txns</div>
            </div>
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
