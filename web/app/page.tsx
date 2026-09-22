"use client";

import { useState, useEffect, useRef } from 'react';
import { UploadCloud, CheckCircle, AlertTriangle, Loader2, Database, BarChart3, Activity } from 'lucide-react';

export default function Dashboard() {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<{ text: string, type: 'success' | 'error' } | null>(null);
  
  const [stats, setStats] = useState<any[]>([]);
  const [logs, setLogs] = useState<any[]>([]);
  const [loadingData, setLoadingData] = useState(true);
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [statsExpanded, setStatsExpanded] = useState(true);
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');

  const fetchDashboardData = async () => {
    setLoadingData(true);
    try {
      const statsRes = await fetch('/api/stats');
      if (statsRes.ok) setStats(await statsRes.json());
      
      await fetchLogs();
    } catch (error) {
      console.error("Error fetching data:", error);
    } finally {
      setLoadingData(false);
    }
  };

  const fetchLogs = async (start = startDate, end = endDate) => {
    try {
      let url = '/api/logs?limit=50';
      if (start) url += `&startDate=${start}`;
      if (end) url += `&endDate=${end}`;
      const logsRes = await fetch(url);
      if (logsRes.ok) setLogs((await logsRes.json()).logs || []);
    } catch (error) {
      console.error("Error fetching logs:", error);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const handleStartDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newDate = e.target.value;
    setStartDate(newDate);
    fetchLogs(newDate, endDate);
  };
  
  const handleEndDateChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newDate = e.target.value;
    setEndDate(newDate);
    fetchLogs(startDate, newDate);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    
    setUploading(true);
    setMessage(null);
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });
      
      const data = await res.json();
      
      if (!res.ok) throw new Error(data.error || 'Upload failed');
      
      setMessage({ text: `Success: Parsed ${data.totalParsed} rows, inserted ${data.insertedCount} new records.`, type: 'success' });
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      
      // Refresh dashboard
      fetchDashboardData();
    } catch (err: any) {
      setMessage({ text: err.message, type: 'error' });
    } finally {
      setUploading(false);
    }
  };

  return (
    <main className="container">
      <header className="header">
        <div className="logo">
          <Activity size={32} />
          EarthRe SLA Monitor
        </div>
        <div>
          <button className="btn btn-primary" onClick={fetchDashboardData}>
            Refresh Data
          </button>
        </div>
      </header>

      {message && (
        <div className={`message message-${message.type}`}>
          {message.type === 'success' ? <CheckCircle size={20} /> : <AlertTriangle size={20} />}
          {message.text}
        </div>
      )}

      {/* Upload Section */}
      <section className="card" style={{ marginBottom: '3rem' }}>
        <div className="card-header">
          <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Database size={20} />
            Data Ingestion
          </h2>
        </div>
        
        <div className="upload-area" onClick={() => fileInputRef.current?.click()}>
          <UploadCloud size={48} className="upload-icon" />
          <h3>{file ? file.name : 'Upload Monitoring CSV'}</h3>
          <p className="stat-label" style={{ marginTop: '0.5rem' }}>Click to browse or drag and drop</p>
          <input 
            type="file" 
            accept=".csv" 
            ref={fileInputRef} 
            onChange={handleFileChange}
            style={{ display: 'none' }}
          />
        </div>
        
        {file && (
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <button 
              className="btn btn-primary" 
              onClick={handleUpload} 
              disabled={uploading}
            >
              {uploading ? <><Loader2 size={18} className="loader" /> Processing...</> : 'Process & Ingest Data'}
            </button>
          </div>
        )}
      </section>

      {/* Stats Section */}
      <section style={{ marginBottom: '3rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <h2 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <BarChart3 size={20} />
            Service SLA Availability (Target: 99.9%)
          </h2>
          <button 
            className="btn" 
            onClick={() => setStatsExpanded(!statsExpanded)}
            style={{ padding: '0.5rem 1rem', border: '1px solid var(--border)', background: 'var(--card)', color: 'var(--foreground)' }}
          >
            {statsExpanded ? 'Collapse Stats' : 'Expand Stats'}
          </button>
        </div>
        
        {statsExpanded && (
          loadingData ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--muted)' }}>
              <Loader2 size={32} className="loader" style={{ margin: '0 auto' }} />
              <p>Loading stats...</p>
            </div>
          ) : stats.length === 0 ? (
            <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
              <p className="stat-label">No data available. Upload a CSV to begin.</p>
            </div>
          ) : (
            <div className="grid stats-grid">
              {stats.map(s => (
                <div key={s.service_id} className={`card ${s.is_breached ? 'stat-breached' : 'stat-ok'}`}>
                  <div className="stat-label">{s.service_id}</div>
                  <div className="stat-value">{s.availability_pct.toFixed(3)}%</div>
                  <div className="stat-label" style={{ marginTop: '0.5rem', fontSize: '0.75rem' }}>
                    {s.successful_checks} / {s.total_checks} Checks
                  </div>
                  {s.is_breached && (
                    <div style={{ marginTop: '1rem' }} className="badge badge-error">
                      SLA BREACHED
                    </div>
                  )}
                </div>
              ))}
            </div>
          )
        )}
      </section>

      {/* Logs Section */}
      <section>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <h2 className="card-title">Recent Check Logs</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <label htmlFor="startDate" className="stat-label" style={{ margin: 0 }}>Date Range:</label>
            <input 
              type="date" 
              id="startDate" 
              value={startDate} 
              onChange={handleStartDateChange}
              style={{ padding: '0.5rem', borderRadius: '0.25rem', border: '1px solid var(--border)', background: 'var(--background)', color: 'var(--foreground)' }}
            />
            <span style={{ color: 'var(--muted)' }}>to</span>
            <input 
              type="date" 
              id="endDate" 
              value={endDate} 
              onChange={handleEndDateChange}
              style={{ padding: '0.5rem', borderRadius: '0.25rem', border: '1px solid var(--border)', background: 'var(--background)', color: 'var(--foreground)' }}
            />
            {(startDate || endDate) && (
              <button 
                className="btn" 
                onClick={() => { setStartDate(''); setEndDate(''); fetchLogs('', ''); }}
                style={{ padding: '0.5rem', fontSize: '0.75rem', background: 'transparent', color: 'var(--muted)' }}
              >
                Clear
              </button>
            )}
          </div>
        </div>
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Timestamp (UTC)</th>
                <th>Service</th>
                <th>Status</th>
                <th>Latency</th>
                <th>Agent</th>
                <th>Region</th>
              </tr>
            </thead>
            <tbody>
              {loadingData && logs.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '2rem' }}>
                    Loading logs...
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '2rem', color: 'var(--muted)' }}>
                    No logs found.
                  </td>
                </tr>
              ) : (
                logs.map(log => (
                  <tr key={log.id}>
                    <td>{new Date(log.timestamp).toLocaleString()}</td>
                    <td style={{ fontWeight: 500 }}>{log.service_id}</td>
                    <td>
                      <span className={`badge ${log.is_success ? 'badge-success' : 'badge-error'}`}>
                        {log.status_code}
                      </span>
                    </td>
                    <td>{log.latency_ms ? `${log.latency_ms.toFixed(0)} ms` : 'N/A'}</td>
                    <td className="stat-label">{log.agent}</td>
                    <td className="stat-label">{log.region}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
