'use client';

import React, { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard, Network, AlertTriangle, PlayCircle,
  FlaskConical, Bot, BarChart3, Upload, Shield,
  Wifi, WifiOff, Bell, X, Activity, Cpu
} from 'lucide-react';
import './globals.css';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// In-memory flag — resets every time the JS bundle loads fresh (new tab / hard reload).
// Using sessionStorage here would incorrectly skip the boot screen when a user restores
// a closed tab, because browsers preserve sessionStorage across tab restores.
let hasBooted = false;

const NAV_ITEMS = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/network', label: 'Live Network', icon: Network },
  { href: '/alerts', label: 'Alerts', icon: AlertTriangle },
  { href: '/replay', label: 'Crime Replay', icon: PlayCircle },
  { href: '/whatif', label: 'What-If Sandbox', icon: FlaskConical },
  { href: '/assistant', label: 'AI Assistant', icon: Bot },
  { href: '/evaluation', label: 'Evaluation', icon: BarChart3 },
  { href: '/upload', label: 'Upload Dataset', icon: Upload },
];

const BOTTOM_NAV_ITEMS = [
  { href: '/', label: 'Home', icon: LayoutDashboard },
  { href: '/upload', label: 'Upload', icon: Upload },
  { href: '/alerts', label: 'Alerts', icon: AlertTriangle },
  { href: '/network', label: 'Network', icon: Network },
  { href: '/assistant', label: 'AI', icon: Bot },
  { href: '/evaluation', label: 'Eval', icon: BarChart3 },
];

interface Toast {
  id: string;
  alertType: string;
  riskScore: number;
}

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [liveAlerts, setLiveAlerts] = useState(0);
  const [connected, setConnected] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [booting, setBooting] = useState(false);
  const [bootStep, setBootStep] = useState(0);

  // Boot sequence check — runs once per fresh page load (in-memory flag resets on load)
  useEffect(() => {
    if (!hasBooted) {
      hasBooted = true;
      setBooting(true);
      const t1 = setTimeout(() => setBootStep(1), 400);
      const t2 = setTimeout(() => setBootStep(2), 800);
      const t3 = setTimeout(() => setBootStep(3), 1200);
      const t4 = setTimeout(() => setBooting(false), 1600);

      return () => {
        clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); clearTimeout(t4);
      };
    }
  }, []);

  // Reset backend pipeline when window/tab is closed
  useEffect(() => {
    const handleUnload = () => {
      try {
        if (navigator.sendBeacon) {
          navigator.sendBeacon(`${API}/api/v1/reset`);
        } else {
          fetch(`${API}/api/v1/reset`, { method: 'POST', keepalive: true }).catch(() => {});
        }
      } catch {}
    };
    window.addEventListener('beforeunload', handleUnload);
    return () => window.removeEventListener('beforeunload', handleUnload);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  useEffect(() => {
    let source: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      try {
        source = new EventSource(`${API}/api/v1/events/alerts`);
        source.onopen = () => setConnected(true);
        source.onmessage = (evt) => {
          try {
            const data = JSON.parse(evt.data);
            if (data.type !== 'connected') {
              setLiveAlerts(n => n + 1);
              const toast: Toast = {
                id: `${Date.now()}-${Math.random()}`,
                alertType: data.alert_type || 'Alert Detected',
                riskScore: data.final_risk_score || 0,
              };
              setToasts(prev => [toast, ...prev].slice(0, 5));
              setTimeout(() => dismissToast(toast.id), 6000);
            }
          } catch { /* keep-alive ping */ }
        };
        source.onerror = () => {
          setConnected(false);
          source?.close();
          retryTimer = setTimeout(connect, 10000);
        };
      } catch { setConnected(false); }
    };

    connect();
    return () => { source?.close(); clearTimeout(retryTimer); };
  }, [dismissToast]);

  const statusClass = connected ? 'online' : 'offline';

  return (
    <>
      {/* ── CINEMATIC INITIALIZATION BOOT OVERLAY ───────────────── */}
      {booting && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 99999,
          background: '#03060d',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          gap: 20, animation: 'fadeIn 0.2s ease',
        }}>
          <div style={{
            width: 54, height: 54, borderRadius: 14,
            background: 'linear-gradient(135deg, rgba(59,130,246,0.3), rgba(6,182,212,0.15))',
            border: '1px solid rgba(59,130,246,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 0 40px rgba(59,130,246,0.4)',
          }}>
            <Shield size={28} color="#60a5fa" />
          </div>

          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 20, fontWeight: 900, letterSpacing: '0.14em', color: '#f0f4fc' }}>
              TRACE-X
            </div>
            <div style={{ fontSize: 10, letterSpacing: '0.18em', color: '#60a5fa', fontWeight: 700, marginTop: 2, textTransform: 'uppercase' }}>
              Financial Crime Intelligence
            </div>
          </div>

          <div style={{
            width: 260, height: 3, background: 'rgba(30, 50, 90, 0.5)',
            borderRadius: 10, overflow: 'hidden', position: 'relative',
          }}>
            <div style={{
              height: '100%',
              width: bootStep === 0 ? '25%' : bootStep === 1 ? '55%' : bootStep === 2 ? '85%' : '100%',
              background: 'linear-gradient(90deg, #3b82f6, #06b6d4)',
              transition: 'width 0.35s ease',
            }} />
          </div>

          <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)', letterSpacing: '0.08em' }}>
            {bootStep === 0 && '[+] INITIALIZING GRAPH INTELLIGENCE...'}
            {bootStep === 1 && '[+] CONNECTING TO TRANSACTION STREAM...'}
            {bootStep === 2 && '[+] LOADING ANOMALY DETECTION ENGINE...'}
            {bootStep === 3 && '[+] SYSTEM OPERATIONAL'}
          </div>
        </div>
      )}

      {/* Synthetic data disclaimer banner */}
      <div className="synthetic-banner">
        ⚠ SYNTHETIC DATA DEMONSTRATION ONLY — All entities, accounts and transactions are artificially generated.
        TRACE-X is an investigator decision-support tool. Not a legal determination system.
      </div>

      <div className="app-shell">
        {/* Sidebar */}
        <aside className="sidebar">
          <div className="sidebar-logo">
            <div className="sidebar-logo-icon">
              <Shield size={18} color="#3b82f6" />
            </div>
            <div>
              <div className="sidebar-title">TRACE-X</div>
              <div className="sidebar-subtitle">Crime Intelligence</div>
            </div>
          </div>

          <div className="sidebar-status">
            <div className={`status-dot ${statusClass}`} />
            <span style={{ fontSize: 11, fontWeight: 600, color: connected ? 'var(--text-success)' : 'var(--text-tertiary)' }}>
              {connected ? 'OPERATIONAL' : 'OFFLINE'}
            </span>
            {liveAlerts > 0 && (
              <span className="nav-badge" style={{ marginLeft: 'auto' }}>
                {liveAlerts > 99 ? '99+' : liveAlerts}
              </span>
            )}
            {connected
              ? <Wifi size={12} style={{ marginLeft: liveAlerts > 0 ? 0 : 'auto', color: 'var(--text-success)', opacity: 0.8 }} />
              : <WifiOff size={12} style={{ marginLeft: 'auto', color: 'var(--text-tertiary)', opacity: 0.5 }} />
            }
          </div>

          <nav className="sidebar-nav" aria-label="Main navigation">
            {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
              const isActive = href === '/' ? pathname === '/' : pathname.startsWith(href);
              const isAlerts = href === '/alerts';
              return (
                <Link key={href} href={href} style={{ textDecoration: 'none' }}>
                  <div className={`nav-item ${isActive ? 'active' : ''}`} aria-current={isActive ? 'page' : undefined}>
                    <Icon size={16} style={{ flexShrink: 0 }} />
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
                    {isAlerts && liveAlerts > 0 && (
                      <span className="nav-badge">{liveAlerts > 99 ? '99+' : liveAlerts}</span>
                    )}
                  </div>
                </Link>
              );
            })}
          </nav>

          <div className="sidebar-footer">
            <div style={{ fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 2 }}>Team BrainBytes</div>
            <div>Omnikon National Hackathon 2026</div>
            <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 5 }}>
              <Cpu size={10} style={{ color: 'var(--accent)', opacity: 0.7 }} />
              <span style={{ color: 'var(--accent)', opacity: 0.7, fontWeight: 600 }}>Synthetic Intelligence</span>
            </div>
          </div>
        </aside>

        {/* Main content */}
        <main className="main-content" id="main-content">
          <div className="page-scroll">
            {children}
          </div>
        </main>
      </div>

      {/* Bottom nav (Mobile) */}
      <nav className="bottom-nav" aria-label="Mobile navigation">
        {BOTTOM_NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const isActive = href === '/' ? pathname === '/' : pathname.startsWith(href);
          const isAlerts = href === '/alerts';
          return (
            <Link key={href} href={href} style={{ textDecoration: 'none' }}>
              <div className={`bottom-nav-item ${isActive ? 'active' : ''}`} aria-current={isActive ? 'page' : undefined}>
                <div style={{ position: 'relative' }}>
                  <Icon size={20} />
                  {isAlerts && liveAlerts > 0 && (
                    <span style={{
                      position: 'absolute', top: -6, right: -6,
                      background: 'var(--critical)', color: 'white',
                      fontSize: 8, fontWeight: 800,
                      width: 14, height: 14, borderRadius: '50%',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      {liveAlerts > 9 ? '9+' : liveAlerts}
                    </span>
                  )}
                </div>
                <span>{label}</span>
              </div>
            </Link>
          );
        })}
      </nav>

      {/* Toasts */}
      {toasts.length > 0 && (
        <div className="toast-container" aria-live="polite" aria-label="Alert notifications">
          {toasts.map(toast => (
            <div key={toast.id} className="toast" role="alert">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                  <div className="toast-header">
                    <Bell size={9} style={{ display: 'inline', marginRight: 4 }} />
                    SUSPICIOUS PATTERN DETECTED
                  </div>
                  <div className="toast-body">
                    <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                      {toast.alertType.replace(/_/g, ' ')}
                    </span>
                    {' '}— Risk:{' '}
                    <span style={{ color: toast.riskScore >= 80 ? '#f87171' : toast.riskScore >= 60 ? '#fb923c' : '#fbbf24' }}>
                      {toast.riskScore.toFixed(0)}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => dismissToast(toast.id)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-tertiary)', padding: '2px', marginLeft: 8 }}
                  aria-label="Dismiss notification"
                >
                  <X size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
