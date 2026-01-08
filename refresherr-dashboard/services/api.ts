
import { Stats, Symlink, Config, Route } from '../types';

const API_BASE = 'http://localhost:8088';

export const fetchStats = async (): Promise<Stats> => {
  const res = await fetch(`${API_BASE}/api/stats`);
  if (!res.ok) throw new Error('Failed to fetch stats');
  return res.json();
};

export const fetchSymlinks = async (onlyBroken: boolean = false): Promise<Symlink[]> => {
  const endpoint = onlyBroken ? '/api/symlinks/broken' : '/api/symlinks';
  const res = await fetch(`${API_BASE}${endpoint}`);
  if (!res.ok) throw new Error('Failed to fetch symlinks');
  return res.json();
};

export const fetchConfig = async (): Promise<Config> => {
  const res = await fetch(`${API_BASE}/api/config`);
  if (!res.ok) throw new Error('Failed to fetch config');
  return res.json();
};

export const fetchRoutes = async (): Promise<Route[]> => {
  const res = await fetch(`${API_BASE}/api/routes`);
  if (!res.ok) throw new Error('Failed to fetch routes');
  return res.json();
};

export const toggleOrchestrator = async (): Promise<any> => {
  const res = await fetch(`${API_BASE}/api/orchestrator/toggle`, { method: 'POST' });
  return res.json();
};

export const triggerScan = async (): Promise<any> => {
  const res = await fetch(`${API_BASE}/api/scan/trigger`, { method: 'POST' });
  return res.json();
};

export const repairSymlink = async (id: string): Promise<any> => {
  const res = await fetch(`${API_BASE}/api/repair/${id}`, { method: 'POST' });
  return res.json();
};
