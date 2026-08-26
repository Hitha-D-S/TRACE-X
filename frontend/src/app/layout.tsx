'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard, Network, AlertTriangle, PlayCircle,
  FlaskConical, Bot, BarChart3, Upload, Activity, Shield
} from 'lucide-react';
import './globals.css';

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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [liveAlerts, setLiveAlerts] = useState(0);
  const [connected, setConnected] = useState(false);
  const [notifications, setNotifications] = useState<string[]>([]);

  useEffect(() => {
    const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    // Try SSE first, fall back gracefully
    let source: EventSource | null = null;
    try {
      source = new EventSource(`${API}/api/v1/events/alerts`);
      source.onopen = () => setConnected(true);
      source.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data);
          if (data.type !== 'connected') {
            setLiveAlerts(n => n + 1);
            setNotifications(prev => [
              `Alert: ${data.alert_type || 'New'} — Risk ${data.final_risk_score?.toFixed(0) || '?'}`,
              ...prev.slice(0, 4)
            ]);
          }
        } catch { /* non-JSON keep-alive */ }
      };
      source.onerror = () => setConnected(false);
    } catch {
      setConnected(false);
    }

    return () => source?.close();
  }, []);

  return (
    <html lang="en" className="dark">
      <head>
        <title>TRACE-X — Financial Crime Intelligence</title>
        <meta name="description" content="Real-Time Financial Crime Graph Intelligence — TRACE-X" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🔍</text></svg>" />
      </head>
      <body>
        {/* Synthetic data banner */}
        <div className="synthetic-banner">
          ⚠️ SYNTHETIC DATA DEMONSTRATION ONLY — All entities and transactions are artificially generated.
          TRACE-X is an investigator decision-support system, not a legal determination system.
        </div>

        <div style={{ display: 'flex', height: 'calc(100vh - 32px)' }}>
          {/* Sidebar */}
          <aside style={{
            width: '240px',
            minWidth: '240px',
            background: '#0f1624',
            borderRight: '1px solid #1e293b',
            display: 'flex',
            flexDirection: 'column',
            padding: '0',
            overflow: 'hidden',
          }}>
            {/* Logo */}
            <div style={{ padding: '20px 16px 16px', borderBottom: '1px solid #1e293b' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Shield size={24} style={{ color: '#3b82f6' }} />
                <div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: '#e2e8f0', letterSpacing: '0.05em' }}>
                    TRACE-X
                  </div>
                  <div style={{ fontSize: 10, color: '#64748b', marginTop: 1 }}>
                    Crime Intelligence
                  </div>
                </div>
              </div>
            </div>

            {/* Live status */}
            <div style={{ padding: '12px 16px', borderBottom: '1px solid #1e293b' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div className={connected ? 'pulse-dot' : ''} style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: connected ? '#10b981' : '#64748b'
                }} />
                <span style={{ fontSize: 11, color: connected ? '#10b981' : '#64748b' }}>
                  {connected ? 'LIVE' : 'OFFLINE'}
                </span>
                {liveAlerts > 0 && (
                  <span style={{
                    marginLeft: 'auto', background: '#ef4444',
                    color: 'white', fontSize: 10, fontWeight: 700,
                    padding: '1px 6px', borderRadius: 10,
                  }}>{liveAlerts}</span>
                )}
              </div>
            </div>

            {/* Navigation */}
            <nav style={{ flex: 1, padding: '8px', overflow: 'auto' }}>
              {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
                <Link key={href} href={href} style={{ textDecoration: 'none' }}>
                  <div className={`nav-item ${pathname === href ? 'active' : ''}`}>
                    <Icon size={16} />
                    <span>{label}</span>
                    {label === 'Alerts' && liveAlerts > 0 && (
                      <span style={{
                        marginLeft: 'auto', background: '#ef4444',
                        color: 'white', fontSize: 10,
                        padding: '1px 6px', borderRadius: 10,
                      }}>{liveAlerts}</span>
                    )}
                  </div>
                </Link>
              ))}
            </nav>

            {/* Team info */}
            <div style={{ padding: '12px 16px', borderTop: '1px solid #1e293b', fontSize: 10, color: '#64748b' }}>
              <div>Team BrainBytes</div>
              <div>Omnikon Hackathon 2026</div>
            </div>
          </aside>

          {/* Main content */}
          <main style={{ flex: 1, overflow: 'auto', background: '#0a0d14' }}>
            {children}
          </main>
        </div>

        {/* Live alert toast notifications */}
        {notifications.length > 0 && (
          <div style={{
            position: 'fixed', bottom: 20, right: 20,
            display: 'flex', flexDirection: 'column', gap: 8,
            zIndex: 1000,
          }}>
            {notifications.map((n, i) => (
              <div key={i} className="fade-in-up" style={{
                background: 'rgba(26, 34, 54, 0.95)',
                border: '1px solid rgba(239, 68, 68, 0.4)',
                borderRadius: 8,
                padding: '10px 14px',
                fontSize: 12,
                color: '#fca5a5',
                backdropFilter: 'blur(12px)',
                maxWidth: 280,
                boxShadow: '0 0 20px rgba(239, 68, 68, 0.2)',
              }}>
                <div style={{ color: '#ef4444', fontWeight: 600, fontSize: 10, marginBottom: 2 }}>
                  ⚡ ALERT DETECTED
                </div>
                {n}
              </div>
            ))}
          </div>
        )}
      </body>
    </html>
  );
}
