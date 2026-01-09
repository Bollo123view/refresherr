import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';
import * as api from '../services/api';

// Mock the API module
vi.mock('../services/api', () => ({
  fetchStats: vi.fn(),
  fetchSymlinks: vi.fn(),
  fetchConfig: vi.fn(),
  fetchRoutes: vi.fn(),
  toggleOrchestrator: vi.fn(),
  triggerScan: vi.fn(),
  repairSymlink: vi.fn(),
}));

// Mock Recharts to avoid canvas rendering issues in tests
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  BarChart: ({ children }: any) => <div>{children}</div>,
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  Cell: () => <div />,
}));

describe('App Component', () => {
  const mockStats = {
    total_links: 100,
    broken_links: 5,
    healthy_links: 95,
    last_scan: '2024-01-09T10:00:00Z',
    orchestrator_status: false,
  };

  const mockSymlinks = [
    {
      id: '1',
      source_path: '/opt/media/jelly/tv/Show/episode.mkv',
      target_path: '/mnt/remote/realdebrid/Show/episode.mkv',
      status: 'broken',
      last_checked: '2024-01-09T10:00:00Z',
    },
    {
      id: '2',
      source_path: '/opt/media/jelly/movies/Movie/movie.mkv',
      target_path: '/mnt/remote/realdebrid/Movie/movie.mkv',
      status: 'healthy',
      last_checked: '2024-01-09T10:00:00Z',
    },
  ];

  const mockConfig = {
    media_path: '/opt/media/jelly',
    scan_interval: 300,
    auto_repair: false,
    radarr_url: 'http://radarr:7878',
    sonarr_url: 'http://sonarr:8989',
  };

  const mockRoutes = [
    {
      id: 'route-1',
      source_root: '/opt/media/jelly/movies',
      target_root: 'radarr_movie',
    },
    {
      id: 'route-2',
      source_root: '/opt/media/jelly/tv',
      target_root: 'sonarr_tv',
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    
    // Setup default API responses
    vi.mocked(api.fetchStats).mockResolvedValue(mockStats);
    vi.mocked(api.fetchSymlinks).mockResolvedValue(mockSymlinks);
    vi.mocked(api.fetchConfig).mockResolvedValue(mockConfig);
    vi.mocked(api.fetchRoutes).mockResolvedValue(mockRoutes);
  });

  it('renders loading state initially', () => {
    render(<App />);
    expect(screen.getByText(/Initializing Refresherr/i)).toBeInTheDocument();
  });

  it('displays dashboard after data loads', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });

    // Check stats are displayed
    expect(screen.getByText('100')).toBeInTheDocument(); // total links
    expect(screen.getByText('5')).toBeInTheDocument(); // broken links
    expect(screen.getByText('95')).toBeInTheDocument(); // healthy links
  });

  it('displays broken symlinks on dashboard', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/episode.mkv/i)).toBeInTheDocument();
    });
  });

  it('handles scan button click', async () => {
    const user = userEvent.setup();
    vi.mocked(api.triggerScan).mockResolvedValue(undefined);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });

    const scanButton = screen.getByRole('button', { name: /Scan Now/i });
    await user.click(scanButton);

    expect(api.triggerScan).toHaveBeenCalled();
  });

  it('handles orchestrator toggle', async () => {
    const user = userEvent.setup();
    vi.mocked(api.toggleOrchestrator).mockResolvedValue(undefined);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });

    const toggleButton = screen.getByRole('button', { 
      name: (content, element) => {
        // Find the toggle button near "Auto-Repair" text
        return element?.closest('div')?.textContent?.includes('Auto-Repair') || false;
      }
    });
    
    await user.click(toggleButton);

    expect(api.toggleOrchestrator).toHaveBeenCalled();
  });

  it('switches between tabs', async () => {
    const user = userEvent.setup();
    
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });

    // The Sidebar component should have navigation items
    // We'll check that the Config tab content appears when clicked
    const configTab = screen.getByText('Config');
    await user.click(configTab);

    await waitFor(() => {
      expect(screen.getByText('General Configuration')).toBeInTheDocument();
    });
  });

  it('handles API errors gracefully', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.mocked(api.fetchStats).mockRejectedValue(new Error('API Error'));

    render(<App />);

    await waitFor(() => {
      // Should still render but without data
      expect(screen.queryByText(/Initializing Refresherr/i)).not.toBeInTheDocument();
    });

    consoleSpy.mockRestore();
  });

  it('displays config information', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    const configTab = screen.getByText('Config');
    await user.click(configTab);

    await waitFor(() => {
      expect(screen.getByText('/opt/media/jelly')).toBeInTheDocument();
      expect(screen.getByText('300s')).toBeInTheDocument();
    });
  });

  it('shows routing information', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    const configTab = screen.getByText('Config');
    await user.click(configTab);

    await waitFor(() => {
      expect(screen.getByText('Routing Logic')).toBeInTheDocument();
    });
  });
});
