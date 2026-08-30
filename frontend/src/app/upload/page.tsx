'use client';

import React, { useState, useRef, useCallback } from 'react';
import {
  Upload, FileText, CheckCircle, AlertCircle,
  Database, RefreshCw, X, ArrowRight, Info,
  AlertTriangle, Table, Map
} from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type Stage = 'pick' | 'preview' | 'mapping' | 'processing' | 'done' | 'error';

interface PreviewData {
  filename: string;
  file_hash: string;
  total_rows_preview: number;
  headers: string[];
  inferred_mapping: Record<string, string | null>;
  sample_rows: Record<string, string>[];
  note: string;
}

interface MappingConfirmResult {
  job_id: string;
  status: string;
}

interface CommitResult {
  job_id: string;
  status: string;
  dataset_id: string;
  rows_received: number;
  rows_ingested: number;
  rows_quarantined: number;
  alerts_generated: number;
  message: string;
}

const REQUIRED_FIELDS = ['source_account_id', 'destination_account_id', 'amount'];
const OPTIONAL_FIELDS = ['transaction_id', 'currency', 'timestamp', 'transaction_type', 'channel', 'location', 'reference'];
const ALL_FIELDS = [...REQUIRED_FIELDS, ...OPTIONAL_FIELDS];

export default function UploadPage() {
  const [stage, setStage] = useState<Stage>('pick');
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [jobId, setJobId] = useState('');
  const [datasetName, setDatasetName] = useState('');
  const [result, setResult] = useState<CommitResult | null>(null);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setStage('pick');
    setFile(null);
    setPreview(null);
    setMapping({});
    setJobId('');
    setDatasetName('');
    setResult(null);
    setError('');
    setUploading(false);
  };

  const handleFile = useCallback(async (selectedFile: File) => {
    setFile(selectedFile);
    setStage('processing');
    setError('');
    setUploading(true);

    try {
      const formData = new FormData();
      formData.append('file', selectedFile);

      const res = await fetch(`${API}/api/v1/transactions/upload/preview`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data: PreviewData = await res.json();
      setPreview(data);
      setMapping(data.inferred_mapping || {});
      setDatasetName(selectedFile.name.replace(/\.[^.]+$/, ''));
      setStage('preview');
    } catch (e: any) {
      setError(e.message || 'Preview failed. Ensure file is a valid CSV or JSON.');
      setStage('error');
    } finally {
      setUploading(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, [handleFile]);

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setDragging(true); };
  const handleDragLeave = () => setDragging(false);

  const confirmMapping = async () => {
    if (!preview) return;
    setUploading(true);
    setError('');

    try {
      const res = await fetch(`${API}/api/v1/transactions/upload/mapping`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_hash: preview.file_hash,
          column_mapping: mapping,
          dataset_name: datasetName || undefined,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data: MappingConfirmResult = await res.json();
      setJobId(data.job_id);
      setStage('mapping');
    } catch (e: any) {
      setError(e.message || 'Mapping validation failed.');
    } finally {
      setUploading(false);
    }
  };

  const commitUpload = async () => {
    if (!file || !jobId) return;
    setStage('processing');
    setUploading(true);
    setError('');

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch(`${API}/api/v1/transactions/upload/commit?job_id=${jobId}`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data: CommitResult = await res.json();
      setResult(data);
      setStage('done');
    } catch (e: any) {
      setError(e.message || 'Commit failed.');
      setStage('error');
    } finally {
      setUploading(false);
    }
  };

  const missingRequired = REQUIRED_FIELDS.filter(f => !mapping[f]);

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      {/* Header */}
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h1 className="page-title">Upload Dataset</h1>
            <p className="page-subtitle">Ingest CSV or JSON transaction data for analysis</p>
          </div>
          {stage !== 'pick' && (
            <button className="btn btn-ghost btn-sm" onClick={reset} aria-label="Start over">
              <RefreshCw size={12} />
              Start Over
            </button>
          )}
        </div>
      </div>

      {/* Progress indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 28 }}>
        {[
          { id: 'pick', label: '1. Select File' },
          { id: 'preview', label: '2. Preview' },
          { id: 'mapping', label: '3. Map Columns' },
          { id: 'done', label: '4. Complete' },
        ].map((step, i, arr) => {
          const stageOrder: Record<Stage, number> = { pick: 0, preview: 1, mapping: 2, processing: 2, done: 3, error: -1 };
          const current = stageOrder[stage] || 0;
          const isActive = stageOrder[step.id as Stage] === current;
          const isDone = stageOrder[step.id as Stage] < current;
          return (
            <React.Fragment key={step.id}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 6,
                opacity: isDone ? 1 : isActive ? 1 : 0.4,
              }}>
                <div style={{
                  width: 22, height: 22, borderRadius: '50%',
                  background: isDone ? 'rgba(52, 211, 153, 0.2)' : isActive ? 'rgba(59, 130, 246, 0.2)' : 'rgba(30, 50, 80, 0.4)',
                  border: `2px solid ${isDone ? '#34d399' : isActive ? '#3b82f6' : 'var(--border-default)'}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 9, fontWeight: 800,
                  color: isDone ? '#34d399' : isActive ? '#60a5fa' : 'var(--text-tertiary)',
                  flexShrink: 0,
                }}>
                  {isDone ? '✓' : i + 1}
                </div>
                <span style={{ fontSize: 12, fontWeight: isActive ? 600 : 400, color: isActive ? 'var(--text-primary)' : 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
                  {step.label}
                </span>
              </div>
              {i < arr.length - 1 && <div style={{ flex: 1, height: 1, background: 'var(--border-subtle)', minWidth: 10 }} />}
            </React.Fragment>
          );
        })}
      </div>

      {/* Error */}
      {error && (
        <div style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 10, padding: '12px 16px', marginBottom: 20, fontSize: 13, color: '#f87171', display: 'flex', gap: 8, alignItems: 'center' }}>
          <AlertCircle size={14} />
          {error}
          <button className="btn btn-ghost btn-sm" style={{ marginLeft: 'auto' }} onClick={reset}>Try Again</button>
        </div>
      )}

      {/* ── Stage: Pick File ── */}
      {stage === 'pick' && (
        <div>
          <div
            className={`upload-zone ${dragging ? 'dragging' : ''}`}
            onClick={() => fileInputRef.current?.click()}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            role="button"
            tabIndex={0}
            onKeyDown={e => e.key === 'Enter' && fileInputRef.current?.click()}
            aria-label="Upload file drop zone"
          >
            <Upload size={40} style={{ color: 'var(--accent)', marginBottom: 16, opacity: 0.8 }} />
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
              Drop your file here
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 20 }}>
              or click to browse
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
              {['CSV', 'JSON'].map(fmt => (
                <span key={fmt} className="badge badge-info">{fmt}</span>
              ))}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 14 }}>
              Max 50 MB · 100,000 rows
            </div>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.json"
            style={{ display: 'none' }}
            onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
            aria-label="File input"
          />

          <div style={{ marginTop: 20, padding: '14px 18px', background: 'rgba(59, 130, 246, 0.05)', border: '1px solid rgba(59, 130, 246, 0.15)', borderRadius: 10 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <Info size={13} style={{ color: 'var(--accent)', flexShrink: 0, marginTop: 1 }} />
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>Expected CSV/JSON columns</div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                  Required: <code style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>source_account_id, destination_account_id, amount</code><br />
                  Optional: <code style={{ color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>timestamp, currency, transaction_type, channel, reference</code>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Stage: Processing ── */}
      {stage === 'processing' && (
        <div className="glass-card" style={{ padding: 60, textAlign: 'center' }}>
          <div style={{ width: 44, height: 44, margin: '0 auto 20px', border: '3px solid rgba(59,130,246,0.2)', borderTop: '3px solid #3b82f6', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>
            {uploading && !jobId ? 'Parsing and previewing file…' : 'Processing and detecting patterns…'}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            Running detection pipeline on uploaded transactions
          </div>
        </div>
      )}

      {/* ── Stage: Preview ── */}
      {stage === 'preview' && preview && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div className="glass-card" style={{ padding: 20 }}>
            <div className="section-label" style={{ marginBottom: 12 }}>
              <FileText size={10} />
              File Preview
            </div>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 16 }}>
              {[
                { label: 'Filename', value: preview.filename },
                { label: 'Rows', value: preview.total_rows_preview.toLocaleString() },
                { label: 'Columns', value: preview.headers.length },
              ].map(({ label, value }) => (
                <div key={label}>
                  <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-tertiary)', marginBottom: 3 }}>{label}</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>{value}</div>
                </div>
              ))}
            </div>
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', color: 'var(--text-tertiary)', marginBottom: 6 }}>DETECTED COLUMNS</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {preview.headers.map(h => (
                  <span key={h} style={{ fontFamily: 'var(--font-mono)', fontSize: 11, padding: '2px 8px', borderRadius: 20, background: 'rgba(59, 130, 246, 0.1)', border: '1px solid rgba(59, 130, 246, 0.2)', color: '#60a5fa' }}>
                    {h}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Dataset name */}
          <div className="glass-card" style={{ padding: 20 }}>
            <div className="section-label" style={{ marginBottom: 12 }}>
              <Database size={10} />
              Dataset Name (Optional)
            </div>
            <input
              className="input"
              value={datasetName}
              onChange={e => setDatasetName(e.target.value)}
              placeholder="my-dataset (defaults to filename)"
              aria-label="Dataset name"
            />
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 6 }}>
              Dataset will be accessible as: <code style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>UPLOAD:{datasetName || 'filename'}</code>
            </div>
          </div>

          {/* Column mapping */}
          <div className="glass-card" style={{ padding: 20 }}>
            <div className="section-label" style={{ marginBottom: 12 }}>
              <Map size={10} />
              Column Mapping
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 14 }}>
              {preview.note}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {ALL_FIELDS.map(field => {
                const isRequired = REQUIRED_FIELDS.includes(field);
                const hasMapping = !!mapping[field];
                return (
                  <div key={field} style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                    <div style={{ minWidth: 200, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{
                        fontFamily: 'var(--font-mono)', fontSize: 11,
                        color: hasMapping ? 'var(--accent-bright)' : isRequired ? '#f87171' : 'var(--text-tertiary)',
                      }}>
                        {field}
                      </span>
                      {isRequired && (
                        <span style={{ fontSize: 9, color: '#f87171', fontWeight: 700 }}>*</span>
                      )}
                    </div>
                    <select
                      className="select"
                      value={mapping[field] || ''}
                      onChange={e => setMapping(m => ({ ...m, [field]: e.target.value || null }))}
                      style={{ flex: 1, minWidth: 160 }}
                      aria-label={`Map column for ${field}`}
                    >
                      <option value="">— not mapped —</option>
                      {preview.headers.map(h => <option key={h} value={h}>{h}</option>)}
                    </select>
                    {hasMapping ? (
                      <CheckCircle size={14} style={{ color: '#34d399', flexShrink: 0 }} />
                    ) : isRequired ? (
                      <AlertCircle size={14} style={{ color: '#f87171', flexShrink: 0 }} />
                    ) : null}
                  </div>
                );
              })}
            </div>
            {missingRequired.length > 0 && (
              <div style={{ marginTop: 14, padding: '10px 14px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, fontSize: 12, color: '#f87171' }}>
                Required fields not mapped: {missingRequired.join(', ')}
              </div>
            )}
          </div>

          <button
            className="btn btn-primary"
            style={{ alignSelf: 'flex-start', minWidth: 200 }}
            onClick={confirmMapping}
            disabled={uploading || missingRequired.length > 0}
            aria-label="Confirm column mapping and proceed"
          >
            {uploading ? <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <ArrowRight size={14} />}
            {uploading ? 'Validating…' : 'Confirm Mapping'}
          </button>
        </div>
      )}

      {/* ── Stage: Mapping confirmed ── */}
      {stage === 'mapping' && (
        <div className="glass-card" style={{ padding: 32, textAlign: 'center' }}>
          <CheckCircle size={40} style={{ color: '#34d399', marginBottom: 16 }} />
          <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
            Mapping Validated
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 24, lineHeight: 1.6 }}>
            Column mapping confirmed. Click below to ingest the file through the detection pipeline.
            <br />
            Job ID: <code style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>{jobId}</code>
          </div>
          <button
            className="btn btn-primary"
            style={{ minWidth: 220 }}
            onClick={commitUpload}
            aria-label="Commit upload and run detection"
          >
            <Upload size={14} />
            Ingest & Run Detection
          </button>
        </div>
      )}

      {/* ── Stage: Done ── */}
      {stage === 'done' && result && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="glass-card-elevated anim-scale-in" style={{ padding: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
              <CheckCircle size={24} style={{ color: '#34d399' }} />
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>Upload Complete</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{result.message}</div>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 12 }}>
              {[
                { label: 'Rows Received', value: result.rows_received, color: '#60a5fa' },
                { label: 'Rows Ingested', value: result.rows_ingested, color: '#34d399' },
                { label: 'Quarantined', value: result.rows_quarantined, color: '#fbbf24' },
                { label: 'Alerts Generated', value: result.alerts_generated, color: '#f87171' },
              ].map(({ label, value, color }) => (
                <div key={label} style={{
                  textAlign: 'center', padding: '14px 10px',
                  background: `${color}0C`, border: `1px solid ${color}20`,
                  borderRadius: 10,
                }}>
                  <div style={{ fontSize: 28, fontWeight: 900, color }}>{value}</div>
                  <div style={{ fontSize: 9, color: 'var(--text-tertiary)', fontWeight: 700, letterSpacing: '0.08em', marginTop: 3 }}>{label}</div>
                </div>
              ))}
            </div>

            <div style={{ marginTop: 18, padding: '10px 14px', background: 'rgba(52, 211, 153, 0.06)', border: '1px solid rgba(52, 211, 153, 0.2)', borderRadius: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 3 }}>Dataset ID (use to filter views)</div>
              <code style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: '#34d399' }}>{result.dataset_id}</code>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <a href={`/alerts?dataset=${encodeURIComponent(result.dataset_id)}`} style={{ textDecoration: 'none' }}>
              <button className="btn btn-primary" aria-label="View generated alerts">
                <AlertTriangle size={14} />
                View Generated Alerts
              </button>
            </a>
            <button className="btn btn-secondary" onClick={reset} aria-label="Upload another file">
              <Upload size={14} />
              Upload Another
            </button>
          </div>
        </div>
      )}

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
