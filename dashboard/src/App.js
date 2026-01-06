import React, { useState } from 'react';
import { useConfig, useRoutes, useStats, useBrokenItems, useDryRun } from './hooks';
import './App.css';

/**
 * Dry Run Toggle component
 */
function DryRunToggle() {
  const { dryrun, loading, toggleDryRun } = useDryRun();
  const [message, setMessage] = useState('');

  const handleToggle = async () => {
    const result = await toggleDryRun();
    if (result.success) {
      setMessage(result.message);
      setTimeout(() => setMessage(''), 5000); // Clear message after 5 seconds
    } else {
      setMessage(`Error: ${result.error}`);
    }
  };

  if (loading) return <div className="dryrun-toggle loading">Loading...</div>;

  return (
    <div className="dryrun-toggle-container">
      <div className="dryrun-toggle">
        <span className="toggle-label">Dry Run Mode:</span>
        <button 
          className={`toggle-btn ${dryrun ? 'active' : 'inactive'}`}
          onClick={handleToggle}
          title={dryrun ? 'Click to disable dry run (allow repairs)' : 'Click to enable dry run (safe mode)'}
        >
          <span className="toggle-status">
            {dryrun ? '🟢 ON (Safe)' : '🔴 OFF (Active)'}
          </span>
        </button>
      </div>
      {message && (
        <div className={`toggle-message ${message.includes('Error') ? 'error' : 'success'}`}>
          {message}
        </div>
      )}
    </div>
  );
}

/**
 * Stats card component to display metrics
 */
function StatsCard({ title, value, subtitle, color = 'blue' }) {
  return (
    <div className={`stats-card ${color}`}>
      <h3>{title}</h3>
      <div className="stats-value">{value}</div>
      {subtitle && <div className="stats-subtitle">{subtitle}</div>}
    </div>
  );
}

/**
 * Config display component
 */
function ConfigSection() {
  const { config, loading, error } = useConfig();

  if (loading) return <div className="section loading">Loading configuration...</div>;
  if (error) return <div className="section error">Error loading config: {error}</div>;
  if (!config) return null;

  return (
    <div className="section">
      <h2>Configuration</h2>
      <div className="config-grid">
        <div className="config-item">
          <strong>Scan Roots:</strong>
          <ul>
            {config.scan?.roots?.map((root, i) => <li key={i}>{root}</li>)}
          </ul>
        </div>
        <div className="config-item">
          <strong>Scan Interval:</strong> {config.scan?.interval}s
        </div>
        <div className="config-item">
          <strong>Dry Run Mode:</strong> {config.dryrun ? 'Yes' : 'No'}
        </div>
        <div className="config-item">
          <strong>Relay Configured:</strong> {config.relay?.token_set ? 'Yes' : 'No'}
        </div>
      </div>
    </div>
  );
}

/**
 * Routing display component with examples
 */
function RoutingSection() {
  const { routes, loading, error } = useRoutes();

  if (loading) return <div className="section loading">Loading routing...</div>;
  if (error) return <div className="section error">Error loading routes: {error}</div>;
  if (!routes) return null;

  return (
    <div className="section">
      <h2>Path Routing & Mapping</h2>
      
      {routes.routing && routes.routing.length > 0 && (
        <div className="subsection">
          <h3>Route Configuration</h3>
          <table className="routing-table">
            <thead>
              <tr>
                <th>Path Prefix</th>
                <th>Routes To</th>
              </tr>
            </thead>
            <tbody>
              {routes.routing.map((route, i) => (
                <tr key={i}>
                  <td><code>{route.prefix}</code></td>
                  <td><span className="badge">{route.type}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {routes.path_mappings && routes.path_mappings.length > 0 && (
        <div className="subsection">
          <h3>Path Mappings (Container ↔ Host)</h3>
          <table className="routing-table">
            <thead>
              <tr>
                <th>Container Path</th>
                <th>Host/Logical Path</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {routes.path_mappings.map((mapping, i) => (
                <tr key={i}>
                  <td><code>{mapping.container_path}</code></td>
                  <td><code>{mapping.logical_path}</code></td>
                  <td>{mapping.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {routes.examples && routes.examples.length > 0 && (
        <div className="subsection">
          <h3>Routing Examples</h3>
          {routes.examples.map((example, i) => (
            <div key={i} className="example-box">
              <div><strong>Path:</strong> <code>{example.path}</code></div>
              <div><strong>Routes to:</strong> <span className="badge">{example.routes_to}</span></div>
              <div className="example-desc">{example.description}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Stats dashboard component
 */
function StatsSection() {
  const { stats, loading, error, refresh } = useStats();

  if (loading) return <div className="section loading">Loading statistics...</div>;
  if (error) return <div className="section error">Error loading stats: {error}</div>;
  if (!stats) return null;

  // Helper to safely extract values with defaults
  const safeValue = (obj, key, defaultVal = 0) => obj?.[key] ?? defaultVal;

  return (
    <div className="section">
      <div className="section-header">
        <h2>Symlink Health Statistics</h2>
        <button onClick={refresh} className="refresh-btn">Refresh</button>
      </div>
      
      <div className="stats-grid">
        <StatsCard
          title="Total Symlinks"
          value={safeValue(stats.symlinks, 'total')}
          subtitle={`${safeValue(stats.symlinks, 'percentage_healthy')}% healthy`}
          color="blue"
        />
        <StatsCard
          title="Healthy"
          value={safeValue(stats.symlinks, 'ok')}
          subtitle="Working symlinks"
          color="green"
        />
        <StatsCard
          title="Broken"
          value={safeValue(stats.symlinks, 'broken')}
          subtitle="Needs repair"
          color="red"
        />
      </div>

      <div className="stats-grid">
        <StatsCard
          title="Movies"
          value={`${safeValue(stats.movies, 'linked')} / ${safeValue(stats.movies, 'total')}`}
          subtitle={`${safeValue(stats.movies, 'percentage')}% linked`}
          color="purple"
        />
        <StatsCard
          title="Episodes"
          value={`${safeValue(stats.episodes, 'linked')} / ${safeValue(stats.episodes, 'total')}`}
          subtitle={`${safeValue(stats.episodes, 'percentage')}% linked`}
          color="orange"
        />
      </div>
    </div>
  );
}

/**
 * Main App component
 */
function App() {
  return (
    <div className="App">
      <header className="app-header">
        <div className="header-content">
          <div className="header-title">
            <h1>Refresherr Dashboard</h1>
            <p>Symlink Health Monitoring & Repair</p>
          </div>
          <DryRunToggle />
        </div>
      </header>

      <main className="app-main">
        <StatsSection />
        <ConfigSection />
        <RoutingSection />
      </main>

      <footer className="app-footer">
        <p>Refresherr - Future-proof repair layer for media symlinks</p>
      </footer>
    </div>
  );
}

export default App;
