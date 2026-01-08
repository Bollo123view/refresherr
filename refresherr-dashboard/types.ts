
export interface Stats {
  total_links: number;
  broken_links: number;
  healthy_links: number;
  last_scan: string;
  orchestrator_status: boolean;
}

export interface Symlink {
  id: string;
  source_path: string;
  target_path: string;
  status: 'healthy' | 'broken' | 'repairing';
  last_checked: string;
  error_message?: string;
}

export interface Config {
  scan_interval: number;
  media_path: string;
  radarr_url?: string;
  sonarr_url?: string;
  auto_repair: boolean;
}

export interface Route {
  id: string;
  source_root: string;
  target_root: string;
}
