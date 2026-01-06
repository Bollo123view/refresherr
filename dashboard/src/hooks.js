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
  const [dryrun, setDryrun] = useState(true);
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
