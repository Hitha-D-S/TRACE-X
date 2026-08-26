'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Search, Filter, RefreshCw, ZoomIn, ZoomOut, Crosshair, X, Database } from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const RISK_NODE_COLORS: Record<string, string> = {
  CRITICAL: '#dc2626',
  HIGH: '#ea580c',
  MEDIUM: '#ca8a04',
  LOW: '#16a34a',
  DEFAULT: '#3b82f6',
};

function getRiskLevel(score: number): string {
  if (score >= 80) return 'CRITICAL';
  if (score >= 60) return 'HIGH';
  if (score >= 30) return 'MEDIUM';
  if (score > 0) return 'LOW';
  return 'DEFAULT';
}

interface GraphData {
  nodes: Array<{
    id: string;
    label?: string;
    risk_score?: number;
    type?: string;
    dataset_id?: string;
  }>;
  edges: Array<{
    id: string;
    from: string;
    to: string;
    amount?: number;
    final_risk_score?: number;
    timestamp?: string;
  }>;
}

interface NodeDetail {
  id: string;
  risk_score: number;
  type: string;
  transactionCount?: number;
  amount?: number;
  owner_name?: string;
  bank_name?: string;
  owner_type?: string;
}

export default function NetworkPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<any>(null);
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [] });
  const [loading, setLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<NodeDetail | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [minRisk, setMinRisk] = useState(0);
  const [datasetId, setDatasetId] = useState('');
  const [datasets, setDatasets] = useState<any[]>([]);
  const [nodeCount, setNodeCount] = useState(0);
  const [edgeCount, setEdgeCount] = useState(0);

  useEffect(() => {
    fetch(`${API}/api/v1/datasets`)
      .then(res => res.json())
      .then(data => setDatasets(data.datasets || []))
      .catch(err => console.error("Error fetching datasets:", err));
  }, []);



  const fetchGraph = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ 
        use_cache: 'false', 
        limit: '300',
        t: String(Date.now()) 
      });
      if (minRisk > 0) params.set('min_risk', String(minRisk));
      if (datasetId) params.set('dataset_id', datasetId);

      const res = await fetch(`${API}/api/v1/graph/network?${params}`);
      if (res.ok) {
        const data: GraphData = await res.json();
        setGraphData(data);
        setNodeCount(data.nodes.length);
        setEdgeCount(data.edges.length);
      }
    } catch (e) {
      console.error('Graph fetch failed:', e);
    } finally {
      setLoading(false);
    }
  }, [minRisk, datasetId]);

  useEffect(() => {
    fetchGraph();
    const interval = setInterval(fetchGraph, 15_000);
    return () => clearInterval(interval);
  }, [fetchGraph]);

  // Initialize Vis.js network
  useEffect(() => {
    if (!containerRef.current || graphData.nodes.length === 0) return;

    const initNetwork = async () => {
      try {
        const { Network, DataSet } = await import('vis-network/standalone');

        const visNodes = new DataSet(
          graphData.nodes.map(n => {
            const risk = n.risk_score || 0;
            const level = getRiskLevel(risk);
            const color = RISK_NODE_COLORS[level];
            const size = 12 + Math.min(risk / 5, 20);

            let tooltip = `${n.id}\nRisk: ${risk.toFixed(1)} (${level})`;
            if ((n as any).owner_name) tooltip += `\nOwner: ${(n as any).owner_name}`;
            if ((n as any).bank_name) tooltip += `\nBank: ${(n as any).bank_name}`;
            if ((n as any).owner_type) tooltip += `\nType: ${(n as any).owner_type}`;

            return {
              id: n.id,
              label: (n as any).owner_name 
                ? `${(n as any).owner_name}\n(...${n.id.slice(-4)})` 
                : (n.label || `...${n.id.slice(-6)}`),
              color: {
                background: `${color}33`,
                border: color,
                highlight: { background: `${color}66`, border: color },
              },
              size,
              font: { color: '#e2e8f0', size: 10, multi: true },
              title: tooltip,
              borderWidth: risk >= 60 ? 2 : 1,
              shadow: risk >= 60 ? { enabled: true, color: color, size: 10 } : { enabled: false },
            };
          })
        );

        const visEdges = new DataSet(
          graphData.edges.map(e => {
            const risk = e.final_risk_score || 0;
            const color = risk >= 60 ? '#ef4444' : risk >= 30 ? '#f59e0b' : '#334155';
            return {
              id: e.id,
              from: e.from,
              to: e.to,
              color: { color, highlight: '#60a5fa' },
              width: risk >= 60 ? 2.5 : 1,
              arrows: { to: { enabled: true, scaleFactor: 0.5 } },
              title: `Amount: ${(e.amount || 0).toLocaleString()} INR\nRisk: ${risk.toFixed(1)}`,
              dashes: risk < 30,
            };
          })
        );

        if (networkRef.current) {
          networkRef.current.setOptions({ physics: { enabled: true } });
          networkRef.current.setData({ nodes: visNodes, edges: visEdges });
          return;
        }

        const options = {
          nodes: { shape: 'dot', scaling: { min: 10, max: 40 } },
          edges: { smooth: { enabled: true, type: 'dynamic', roundness: 0.5 } },
          physics: {
            enabled: true,
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {
              gravitationalConstant: -180,
              centralGravity: 0.005,
              springLength: 150,
              springConstant: 0.05,
              avoidOverlap: 1,
            },
            stabilization: { iterations: 300 },
          },
          interaction: {
            hover: true,
            tooltipDelay: 200,
            zoomView: true,
            dragView: true,
            multiselect: true,
          },
          layout: { improvedLayout: true },
        };

        const network = new Network(
          containerRef.current!,
          { nodes: visNodes, edges: visEdges },
          options
        );

        network.on('click', (params) => {
          if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const node = graphData.nodes.find(n => n.id === nodeId);
            if (node) {
              const related = graphData.edges.filter(
                e => e.from === nodeId || e.to === nodeId
              );
              setSelectedNode({
                id: nodeId,
                risk_score: node.risk_score || 0,
                type: node.type || 'BankAccount',
                transactionCount: related.length,
                amount: related.reduce((s, e) => s + (e.amount || 0), 0),
                owner_name: (node as any).owner_name,
                bank_name: (node as any).bank_name,
                owner_type: (node as any).owner_type,
              });
            }
          } else {
            setSelectedNode(null);
          }
        });

        network.on('stabilized', () => {
          network.fit({ animation: { duration: 500 } as any });
          network.setOptions({ physics: { enabled: false } });
        });

        networkRef.current = network;
      } catch (e) {
        console.error('Vis.js init failed:', e);
      }
    };

    initNetwork();
  }, [graphData]);

  const handleSearch = () => {
    if (!networkRef.current || !searchQuery) return;
    const cleanQuery = searchQuery.replace(/^\.*|\.*$/g, '').trim().toLowerCase();
    if (!cleanQuery) return;

    const node = graphData.nodes.find(n => {
      const idMatch = n.id.toLowerCase().includes(cleanQuery);
      const labelMatch = (n.label || '').toLowerCase().includes(cleanQuery);
      const nameMatch = ((n as any).owner_name || '').toLowerCase().includes(cleanQuery);
      return idMatch || labelMatch || nameMatch;
    });

    if (node && networkRef.current) {
      networkRef.current.focus(node.id, { scale: 1.5, animation: { duration: 500 } as any });
      networkRef.current.selectNodes([node.id]);

      const related = graphData.edges.filter(
        e => e.from === node.id || e.to === node.id
      );
      setSelectedNode({
        id: node.id,
        risk_score: node.risk_score || 0,
        type: node.type || 'BankAccount',
        transactionCount: related.length,
        amount: related.reduce((s, e) => s + (e.amount || 0), 0),
        owner_name: (node as any).owner_name,
        bank_name: (node as any).bank_name,
        owner_type: (node as any).owner_type,
      });
    } else {
      alert(`No node matching "${searchQuery}" found in the network.`);
    }
  };

  const handleFitAll = () => {
    networkRef.current?.fit({ animation: { duration: 500 } as any });
  };

  const level = selectedNode ? getRiskLevel(selectedNode.risk_score) : 'DEFAULT';
  const riskColor = RISK_NODE_COLORS[level];

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Toolbar */}
      <div style={{
        padding: '12px 20px',
        background: '#0f1624',
        borderBottom: '1px solid #1e293b',
        display: 'flex', alignItems: 'center', gap: 12,
        flexWrap: 'wrap',
      }}>
        <h2 style={{ fontSize: 15, fontWeight: 600, color: '#e2e8f0', marginRight: 8 }}>
          Live Network
        </h2>

        {/* Search */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6,
          background: '#1a2236', border: '1px solid #1e293b', borderRadius: 8,
          padding: '6px 10px', flex: '1', maxWidth: 240 }}>
          <Search size={13} style={{ color: '#64748b', cursor: 'pointer' }} onClick={handleSearch} />
          <input
            placeholder="Search entity ID..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            style={{ background: 'none', border: 'none', outline: 'none',
              color: '#e2e8f0', fontSize: 12, width: '100%' }}
          />
        </div>

        {/* Min Risk Filter */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Filter size={13} style={{ color: '#64748b' }} />
          <span style={{ fontSize: 11, color: '#64748b' }}>Min Risk:</span>
          <select
            value={minRisk}
            onChange={e => setMinRisk(Number(e.target.value))}
            style={{
              background: '#1a2236', border: '1px solid #1e293b', color: '#e2e8f0',
              borderRadius: 6, padding: '4px 8px', fontSize: 12, outline: 'none',
            }}
          >
            <option value={0}>All</option>
            <option value={30}>Medium+</option>
            <option value={60}>High+</option>
            <option value={80}>Critical</option>
          </select>
        </div>

        {/* Dataset Filter */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Database size={13} style={{ color: '#64748b' }} />
          <span style={{ fontSize: 11, color: '#64748b' }}>Dataset:</span>
          <select
            value={datasetId}
            onChange={e => setDatasetId(e.target.value)}
            style={{
              background: '#1a2236', border: '1px solid #1e293b', color: '#e2e8f0',
              borderRadius: 6, padding: '4px 8px', fontSize: 12, outline: 'none',
            }}
          >
            <option value="">All (Demo)</option>
            {datasets.map(d => (
              <option key={d.dataset_id} value={d.dataset_id}>
                {d.dataset_id}
              </option>
            ))}
          </select>
        </div>

        <button onClick={fetchGraph} style={{
          display: 'flex', alignItems: 'center', gap: 4,
          background: '#1a2236', border: '1px solid #1e293b',
          color: '#94a3b8', borderRadius: 6, padding: '6px 10px',
          cursor: 'pointer', fontSize: 12,
        }}>
          <RefreshCw size={13} />
          Refresh
        </button>

        <button onClick={handleFitAll} style={{
          display: 'flex', alignItems: 'center', gap: 4,
          background: '#1a2236', border: '1px solid #1e293b',
          color: '#94a3b8', borderRadius: 6, padding: '6px 10px',
          cursor: 'pointer', fontSize: 12,
        }}>
          <Crosshair size={13} />
          Fit All
        </button>

        <div style={{ marginLeft: 'auto', fontSize: 11, color: '#64748b' }}>
          {nodeCount} nodes · {edgeCount} edges
          {loading && <span style={{ marginLeft: 8, color: '#3b82f6' }}>↻ Loading…</span>}
        </div>
      </div>

      {/* Graph + Detail Panel */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', position: 'relative' }}>
        {/* Graph canvas */}
        {graphData.nodes.length === 0 && !loading ? (
          <div style={{
            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexDirection: 'column', gap: 12, color: '#64748b',
          }}>
            <div style={{ fontSize: 48 }}>📊</div>
            <div style={{ fontSize: 15, fontWeight: 600 }}>No graph data yet</div>
            <div style={{ fontSize: 13 }}>
              Ingest transactions to populate the network graph.
            </div>
          </div>
        ) : (
          <div ref={containerRef} className="graph-container" style={{ flex: 1 }} />
        )}

        {/* Node detail panel */}
        {selectedNode && (
          <div style={{
            position: 'absolute', right: 12, top: 12,
            width: 280, background: 'rgba(17, 24, 39, 0.95)',
            border: `1px solid ${riskColor}44`,
            borderRadius: 12, padding: 16,
            backdropFilter: 'blur(12px)',
            boxShadow: `0 0 24px ${riskColor}22`,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <span style={{ fontSize: 12, fontWeight: 700, color: riskColor }}>
                ENTITY DETAIL
              </span>
              <button onClick={() => setSelectedNode(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b' }}>
                <X size={14} />
              </button>
            </div>

            <div className="mono" style={{ color: '#60a5fa', fontSize: 11, marginBottom: 12 }}>
              {selectedNode.id}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                ['Type', selectedNode.type],
                ...(selectedNode.owner_name ? [['Owner', selectedNode.owner_name]] : []),
                ...(selectedNode.bank_name ? [['Bank', selectedNode.bank_name]] : []),
                ...(selectedNode.owner_type ? [['Owner Type', selectedNode.owner_type]] : []),
                ['Risk Score', `${selectedNode.risk_score.toFixed(1)}/100`],
                ['Risk Level', level],
                ['Transactions', selectedNode.transactionCount?.toString() || '0'],
                ['Total Volume', `₹${(selectedNode.amount || 0).toLocaleString()}`],
              ].map(([k, v]) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 11, color: '#64748b' }}>{k}</span>
                  <span style={{ fontSize: 11, color: '#e2e8f0', fontWeight: 500 }}>{v}</span>
                </div>
              ))}
            </div>

            <div style={{ marginTop: 12 }}>
              <div style={{
                height: 4, background: '#1e293b', borderRadius: 4, overflow: 'hidden',
              }}>
                <div style={{
                  height: '100%', width: `${selectedNode.risk_score}%`,
                  background: riskColor, borderRadius: 4,
                  transition: 'width 0.5s ease',
                }} />
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
                <span style={{ fontSize: 9, color: '#64748b' }}>0</span>
                <span style={{ fontSize: 9, color: '#64748b' }}>100</span>
              </div>
            </div>

            <a
              href={`/alerts?entity=${selectedNode.id}`}
              style={{
                display: 'block', marginTop: 12, textAlign: 'center',
                padding: '8px', background: 'rgba(59, 130, 246, 0.15)',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                borderRadius: 6, fontSize: 12, color: '#3b82f6',
                textDecoration: 'none', cursor: 'pointer',
              }}
            >
              View Alerts →
            </a>
          </div>
        )}
      </div>

      {/* Legend */}
      <div style={{
        padding: '8px 20px', background: '#0f1624',
        borderTop: '1px solid #1e293b',
        display: 'flex', gap: 16, alignItems: 'center',
      }}>
        <span style={{ fontSize: 10, color: '#64748b' }}>RISK:</span>
        {Object.entries(RISK_NODE_COLORS).filter(([k]) => k !== 'DEFAULT').map(([level, color]) => (
          <div key={level} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%',
              background: `${color}33`, border: `2px solid ${color}` }} />
            <span style={{ fontSize: 10, color: '#94a3b8' }}>{level}</span>
          </div>
        ))}
        <span style={{ marginLeft: 'auto', fontSize: 10, color: '#64748b' }}>
          Click a node for details · Scroll to zoom · Drag to pan
        </span>
      </div>
    </div>
  );
}
