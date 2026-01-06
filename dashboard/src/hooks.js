/**
 * Custom React hook for fetching config from the API.
 * This hook provides configuration data including routing, path mappings, and settings.
 */
import { useState, useEffect } from 'react';

export function useConfig() {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch('/api/config')
      .then(response => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
      })
      .then(data => {
        setConfig(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return { config, loading, error };
}

/**
 * Custom React hook for fetching routing/mapping configuration.
 * This hook provides path routing and mapping information for troubleshooting.
 */
export function useRoutes() {
  const [routes, setRoutes] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch('/api/routes')
      .then(response => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
      })
      .then(data => {
        setRoutes(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, []);

  return { routes, loading, error };
}

/**
 * Custom React hook for fetching symlink statistics.
 * This hook provides health metrics for movies, episodes, and symlinks.
 */
export function useStats() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refresh = () => {
    setLoading(true);
    fetch('/api/stats')
      .then(response => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
      })
      .then(data => {
        setStats(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  };

  useEffect(() => {
    refresh();
  }, []);

  return { stats, loading, error, refresh };
}

/**
 * Custom React hook for fetching broken symlinks.
 */
export function useBrokenItems() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refresh = () => {
    setLoading(true);
    fetch('/api/broken')
      .then(response => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
      })
      .then(data => {
        setItems(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  };

  useEffect(() => {
    refresh();
  }, []);

  return { items, loading, error, refresh };
}

/**
 * Custom React hook for managing dry run mode.
 * Provides current dry run status and a toggle function.
 */
export function useDryRun() {
  const [dryrun, setDryrun] = useState(null); // Start with null to indicate loading
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch current dry run status
  const fetchStatus = () => {
    setLoading(true);
    fetch('/api/config')
      .then(response => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
      })
      .then(data => {
        setDryrun(data.dryrun ?? true);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
        setDryrun(true); // Default to safe mode on error
      });
  };

  // Toggle dry run mode
  const toggleDryRun = async () => {
    const newValue = !dryrun;
    
    try {
      const response = await fetch('/api/config/dryrun', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ dryrun: newValue }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      if (data.success) {
        setDryrun(newValue);
        return { success: true, message: data.message };
      } else {
        throw new Error(data.error || 'Failed to toggle dry run');
      }
    } catch (err) {
      setError(err.message);
      return { success: false, error: err.message };
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  return { dryrun, loading, error, toggleDryRun, refresh: fetchStatus };
}

/**
 * Custom React hook for fetching the dry run manifest.
 * This shows what actions would be performed in dry run mode.
 */
export function useManifest() {
  const [manifest, setManifest] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchManifest = () => {
    setLoading(true);
    fetch('/api/manifest')
      .then(response => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
      })
      .then(data => {
        setManifest(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  };

  return { manifest, loading, error, fetchManifest };
}

/**
 * Custom React hook for orchestrator state management.
 * Provides orchestrator status (enabled/disabled) and toggle function.
 */
export function useOrchestrator() {
  const [state, setState] = useState(null);
  const [currentRun, setCurrentRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch orchestrator status
  const fetchStatus = () => {
    setLoading(true);
    fetch('/api/orchestrator/status')
      .then(response => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
      })
      .then(data => {
        setState(data.state);
        setCurrentRun(data.current_run);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  };

  // Toggle orchestrator enabled/disabled
  const toggleOrchestrator = async () => {
    if (!state) return { success: false, error: 'State not loaded' };
    
    const newEnabled = !state.enabled;
    
    try {
      const response = await fetch('/api/orchestrator/toggle', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ enabled: newEnabled }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      if (data.success) {
        setState(data.state);
        return { success: true, message: data.message };
      } else {
        throw new Error(data.error || 'Failed to toggle orchestrator');
      }
    } catch (err) {
      setError(err.message);
      return { success: false, error: err.message };
    }
  };

  useEffect(() => {
    fetchStatus();
    // Poll status every 10 seconds
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  return { state, currentRun, loading, error, toggleOrchestrator, refresh: fetchStatus };
}

/**
 * Custom React hook for repair operations.
 * Provides functions to trigger repairs and fetch repair history.
 */
export function useRepair() {
  const [history, setHistory] = useState([]);
  const [currentRun, setCurrentRun] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch repair history
  const fetchHistory = (limit = 50, offset = 0) => {
    setLoading(true);
    fetch(`/api/repair/history?limit=${limit}&offset=${offset}`)
      .then(response => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
      })
      .then(data => {
        setHistory(data.history);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  };

  // Fetch current repair status
  const fetchStatus = () => {
    fetch('/api/repair/status')
      .then(response => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
      })
      .then(data => {
        setCurrentRun(data.running ? data.run : null);
      })
      .catch(err => {
        setError(err.message);
      });
  };

  // Trigger cinesync repair
  const runCinesyncRepair = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/repair/cinesync', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setLoading(false);
      
      if (data.success) {
        // Refresh history and status after repair
        fetchHistory();
        fetchStatus();
        return { success: true, result: data.result };
      } else {
        throw new Error(data.error || 'Repair failed');
      }
    } catch (err) {
      setError(err.message);
      setLoading(false);
      return { success: false, error: err.message };
    }
  };

  // Trigger ARR repair
  const runArrRepair = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/repair/arr', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setLoading(false);
      
      if (data.success) {
        // Refresh history and status after repair
        fetchHistory();
        fetchStatus();
        return { success: true, result: data.result };
      } else {
        throw new Error(data.error || 'Repair failed');
      }
    } catch (err) {
      setError(err.message);
      setLoading(false);
      return { success: false, error: err.message };
    }
  };

  useEffect(() => {
    fetchHistory();
    fetchStatus();
    // Poll status every 5 seconds
    const interval = setInterval(() => {
      fetchStatus();
      // Refresh history periodically
      fetchHistory();
    }, 5000);
    return () => clearInterval(interval);
  }, []); // Empty dependency array - set up polling once on mount

  return { 
    history, 
    currentRun, 
    loading, 
    error, 
    runCinesyncRepair, 
    runArrRepair,
    refresh: fetchHistory,
    refreshStatus: fetchStatus
  };
}
