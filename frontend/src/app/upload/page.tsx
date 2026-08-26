'use client';

import React, { useState } from 'react';
import { Upload, FileText, Check, AlertCircle, ChevronRight, Loader2 } from 'lucide-react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface MappingField {
  field: string;
  label: string;
  required: boolean;
}

const MAPPING_FIELDS: MappingField[] = [
  { field: 'source_account_id', label: 'Source Account', required: true },
  { field: 'destination_account_id', label: 'Destination Account', required: true },
  { field: 'amount', label: 'Amount', required: true },
  { field: 'transaction_id', label: 'Transaction ID', required: false },
  { field: 'currency', label: 'Currency', required: false },
  { field: 'timestamp', label: 'Timestamp', required: false },
  { field: 'transaction_type', label: 'Transaction Type', required: false },
  { field: 'channel', label: 'Channel', required: false },
  { field: 'location', label: 'Location', required: false },
  { field: 'reference', label: 'Reference', required: false },
];

type Step = 'upload' | 'mapping' | 'confirm' | 'done';

export default function UploadPage() {
  const [step, setStep] = useState<Step>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<any | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [jobId, setJobId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [commitResult, setCommitResult] = useState<any>(null);
  const [datasetName, setDatasetName] = useState('');
  const [dragOver, setDragOver] = useState(false);

  const handleFile = async (f: File) => {
    setFile(f);
    setError('');
    setLoading(true);
    try {
      const form = new FormData();
      form.append('file', f);
      const res = await fetch(`${API}/api/v1/transactions/upload/preview`, {
        method: 'POST',
        body: form,
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Preview failed');
      const data = await res.json();
      setPreview(data);
      setMapping(data.inferred_mapping || {});
      setStep('mapping');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmMapping = async () => {
    if (!preview) return;
    setLoading(true);
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
      if (!res.ok) throw new Error((await res.json()).detail || 'Mapping failed');
      const data = await res.json();
      setJobId(data.job_id);
      setStep('confirm');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCommit = async () => {
    if (!file || !jobId) return;
    setLoading(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(`${API}/api/v1/transactions/upload/commit?job_id=${jobId}`, {
        method: 'POST',
        body: form,
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Commit failed');
      setCommitResult(await res.json());
      setStep('done');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setStep('upload');
    setFile(null);
    setPreview(null);
    setMapping({});
    setJobId('');
    setCommitResult(null);
    setError('');
    setDatasetName('');
  };

  const STEPS = ['upload', 'mapping', 'confirm', 'done'];
  const stepIdx = STEPS.indexOf(step);

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: '0 auto' }}>
      <h2 style={{ fontSize: 18, fontWeight: 700, color: '#e2e8f0', marginBottom: 4 }}>
        Upload Dataset
      </h2>
      <p style={{ fontSize: 13, color: '#64748b', marginBottom: 24 }}>
        Upload CSV or JSON transaction data for analysis. Automatic column mapping with manual correction.
      </p>

      {/* Step indicator */}
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 32 }}>
        {['Upload', 'Mapping', 'Confirm', 'Done'].map((label, i) => (
          <React.Fragment key={label}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{
                width: 28, height: 28, borderRadius: '50%', display: 'flex',
                alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 600,
                background: i <= stepIdx ? '#3b82f6' : '#1a2236',
                color: i <= stepIdx ? 'white' : '#64748b',
                border: `1px solid ${i <= stepIdx ? '#3b82f6' : '#1e293b'}`,
              }}>
                {i < stepIdx ? <Check size={14} /> : i + 1}
              </div>
              <span style={{ fontSize: 12, color: i === stepIdx ? '#e2e8f0' : '#64748b' }}>{label}</span>
            </div>
            {i < 3 && (
              <div style={{ flex: 1, height: 1, background: i < stepIdx ? '#3b82f6' : '#1e293b', margin: '0 12px' }} />
            )}
          </React.Fragment>
        ))}
      </div>

      {error && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)',
          borderRadius: 8, padding: 12, marginBottom: 16, color: '#fca5a5', fontSize: 13,
          display: 'flex', alignItems: 'center', gap: 8 }}>
          <AlertCircle size={14} />
          {error}
        </div>
      )}

      {/* Step: Upload */}
      {step === 'upload' && (
        <div
          onDrop={e => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          style={{
            border: `2px dashed ${dragOver ? '#3b82f6' : '#1e293b'}`,
            borderRadius: 16, padding: '60px 40px', textAlign: 'center',
            background: dragOver ? 'rgba(59, 130, 246, 0.05)' : '#111827',
            transition: 'all 0.2s', cursor: 'pointer',
          }}
          onClick={() => document.getElementById('fileInput')?.click()}
        >
          <input id="fileInput" type="file" accept=".csv,.json"
            style={{ display: 'none' }} onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />
          {loading ? (
            <Loader2 size={32} style={{ color: '#3b82f6', animation: 'spin 1s linear infinite', margin: '0 auto 12px' }} />
          ) : (
            <Upload size={32} style={{ color: '#64748b', margin: '0 auto 12px' }} />
          )}
          <div style={{ fontSize: 14, color: '#94a3b8', marginBottom: 4 }}>
            {loading ? 'Parsing file…' : 'Drop CSV or JSON here, or click to browse'}
          </div>
          <div style={{ fontSize: 12, color: '#64748b' }}>Max 50MB · Up to 100,000 rows</div>
        </div>
      )}

      {/* Step: Mapping */}
      {step === 'mapping' && preview && (
        <div>
          <div className="glass-card" style={{ padding: 20, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', marginBottom: 12 }}>
              File Preview — {preview.filename} ({preview.total_rows_preview} rows)
            </div>
            <div style={{ overflow: 'auto', maxHeight: 180 }}>
              <table className="data-table">
                <thead>
                  <tr>{preview.headers?.map((h: string) => <th key={h}>{h}</th>)}</tr>
                </thead>
                <tbody>
                  {preview.sample_rows?.slice(0, 3).map((row: any, i: number) => (
                    <tr key={i}>
                      {preview.headers?.map((h: string) => (
                        <td key={h} className="mono" style={{ fontSize: 10 }}>
                          {String(row[h] || '').slice(0, 30)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="glass-card" style={{ padding: 20, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', marginBottom: 12 }}>
              Column Mapping
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {MAPPING_FIELDS.map(({ field, label, required }) => (
                <div key={field} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ minWidth: 150, fontSize: 12, color: required ? '#e2e8f0' : '#94a3b8' }}>
                    {label}
                    {required && <span style={{ color: '#ef4444' }}> *</span>}
                  </div>
                  <select
                    value={mapping[field] || ''}
                    onChange={e => setMapping(m => ({ ...m, [field]: e.target.value }))}
                    style={{
                      flex: 1, background: '#1a2236', border: `1px solid ${mapping[field] ? '#3b82f6' : '#1e293b'}`,
                      color: '#e2e8f0', borderRadius: 6, padding: '5px 8px', fontSize: 12, outline: 'none',
                    }}
                  >
                    <option value="">-- Not Mapped --</option>
                    {preview.headers?.map((h: string) => <option key={h} value={h}>{h}</option>)}
                  </select>
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <input
              placeholder="Dataset name (optional)"
              value={datasetName}
              onChange={e => setDatasetName(e.target.value)}
              style={{
                background: '#1a2236', border: '1px solid #1e293b',
                color: '#e2e8f0', borderRadius: 8, padding: '8px 14px', fontSize: 13, outline: 'none', flex: 1,
              }}
            />
            <button className="btn-primary" onClick={handleConfirmMapping} disabled={loading}>
              {loading ? 'Validating…' : 'Confirm Mapping →'}
            </button>
          </div>
        </div>
      )}

      {/* Step: Confirm */}
      {step === 'confirm' && (
        <div className="glass-card" style={{ padding: 32, textAlign: 'center' }}>
          <FileText size={40} style={{ color: '#3b82f6', margin: '0 auto 16px' }} />
          <div style={{ fontSize: 16, fontWeight: 600, color: '#e2e8f0', marginBottom: 8 }}>
            Ready to Ingest
          </div>
          <div style={{ fontSize: 13, color: '#64748b', marginBottom: 4 }}>
            File: {file?.name} · Job ID: {jobId.slice(0, 12)}...
          </div>
          <div style={{ fontSize: 12, color: '#64748b', marginBottom: 24 }}>
            {preview?.total_rows_preview} rows will be processed through the detection pipeline.
          </div>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
            <button onClick={reset} style={{
              background: '#1a2236', border: '1px solid #1e293b', color: '#94a3b8',
              borderRadius: 8, padding: '8px 20px', cursor: 'pointer', fontSize: 13,
            }}>
              Cancel
            </button>
            <button className="btn-primary" onClick={handleCommit} disabled={loading}>
              {loading ? <><Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Ingesting…</> : '✓ Commit & Ingest'}
            </button>
          </div>
        </div>
      )}

      {/* Step: Done */}
      {step === 'done' && commitResult && (
        <div className="glass-card" style={{ padding: 32, textAlign: 'center' }}>
          <div style={{
            width: 64, height: 64, borderRadius: '50%',
            background: 'rgba(16, 185, 129, 0.15)', border: '2px solid rgba(16, 185, 129, 0.4)',
            margin: '0 auto 16px', display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Check size={28} style={{ color: '#10b981' }} />
          </div>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#10b981', marginBottom: 8 }}>
            Ingestion Complete!
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, margin: '20px 0', maxWidth: 400, marginLeft: 'auto', marginRight: 'auto' }}>
            {[
              ['Rows Ingested', commitResult.rows_ingested],
              ['Quarantined', commitResult.rows_quarantined],
              ['Alerts Generated', commitResult.alerts_generated],
            ].map(([k, v]) => (
              <div key={k} style={{ background: '#1a2236', border: '1px solid #1e293b', borderRadius: 8, padding: 12 }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: '#e2e8f0' }}>{v}</div>
                <div style={{ fontSize: 11, color: '#64748b' }}>{k}</div>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 12, color: '#64748b', marginBottom: 20 }}>
            Dataset ID: <code style={{ color: '#3b82f6' }}>{commitResult.dataset_id}</code>
          </div>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
            <a href="/alerts" className="btn-primary">View Alerts →</a>
            <button onClick={reset} style={{
              background: '#1a2236', border: '1px solid #1e293b', color: '#94a3b8',
              borderRadius: 8, padding: '8px 20px', cursor: 'pointer', fontSize: 13,
            }}>Upload Another</button>
          </div>
        </div>
      )}
    </div>
  );
}
