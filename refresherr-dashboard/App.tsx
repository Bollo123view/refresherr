
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Stats, Symlink, Config, Route } from './types';
import * as api from './services/api';
import Sidebar from './components/Sidebar';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [stats, setStats] = useState<Stats | null>(null);
  const [symlinks, setSymlinks] = useState<Symlink[]>([]);
  const [config, setConfig] = useState<Config | null>(null);
  const [routes, setRoutes] = useState<Route[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [repairingId, setRepairingId] = useState<string | null>(null);
  const [flashUpdate, setFlashUpdate] = useState(false);
  
  const statsRef = useRef<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setRefreshing(true);
      const [s, syms, cfg, rts] = await Promise.all([
        api.fetchStats(),
        api.fetchSymlinks(),
        api.fetchConfig(),
        api.fetchRoutes()
      ]);
      
      // Check if data actually changed or if it's just a routine refresh
      const statsSignature = JSON.stringify(s);
      if (statsRef.current && statsRef.current !== statsSignature) {
        setFlashUpdate(true);
        setTimeout(() => setFlashUpdate(false), 1000);
      }
      statsRef.current = statsSignature;
      
      setStats(s);
      setSymlinks(syms);
      setConfig(cfg);
      setRoutes(rts);
    } catch (err) {
      console.error('Error loading data:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  const handleToggleOrchestrator = async () => {
    try {
      await api.toggleOrchestrator();
      loadData();
    } catch (err) {
      alert('Failed to toggle orchestrator');
    }
  };

  const handleManualScan = async () => {
    try {
      setRefreshing(true);
      await api.triggerScan();
      setTimeout(loadData, 2000);
    } catch (err) {
      alert('Scan trigger failed');
    }
  };

  const handleRepair = async (id: string) => {
    try {
      setRepairingId(id);
      await api.repairSymlink(id);
      loadData();
    } catch (err) {
      alert('Repair failed');
    } finally {
      setRepairingId(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-950">
        <div className="flex flex-col items-center space-y-4">
          <div className="w-12 h-12 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
          <p className="text-slate-400 font-medium animate-pulse">Initializing Refresherr...</p>
        </div>
      </div>
    );
  }

  const chartData = [
    { name: 'Healthy', value: stats?.healthy_links || 0, color: '#10b981' },
    { name: 'Broken', value: stats?.broken_links || 0, color: '#ef4444' },
  ];

  return (
    <div className="flex min-h-screen bg-slate-950">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      
      <main className="flex-1 ml-64 p-8 overflow-y-auto">
        {/* Header */}
        <header className="flex justify-between items-center mb-8">
          <div>
            <h2 className="text-2xl font-bold text-white capitalize">{activeTab}</h2>
            <p className="text-slate-400 text-sm mt-1">
              Last updated: {stats?.last_scan ? new Date(stats.last_scan).toLocaleString() : 'Never'}
            </p>
          </div>
          <div className="flex items-center space-x-4">
            <button 
              onClick={handleManualScan}
              disabled={refreshing}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg font-medium transition-all flex items-center space-x-2"
            >
              <svg className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
              <span>Scan Now</span>
            </button>
            <div className="h-8 w-px bg-slate-800 mx-2"></div>
            <div className="flex items-center space-x-3 bg-slate-900 border border-slate-800 rounded-full px-4 py-2">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-widest">Auto-Repair</span>
              <button 
                onClick={handleToggleOrchestrator}
                className={`w-12 h-6 rounded-full transition-colors relative ${stats?.orchestrator_status ? 'bg-emerald-500' : 'bg-slate-700'}`}
              >
                <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform ${stats?.orchestrator_status ? 'left-7' : 'left-1'}`}></div>
              </button>
            </div>
          </div>
        </header>

        {activeTab === 'dashboard' && (
          <div className="space-y-8 animate-in fade-in duration-500">
            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className={`glass rounded-2xl p-6 relative overflow-hidden group transition-all ${flashUpdate ? 'update-flash' : ''}`}>
                <div className="absolute top-0 right-0 w-24 h-24 bg-indigo-600/10 rounded-full -mr-12 -mt-12 blur-3xl group-hover:bg-indigo-600/20 transition-all"></div>
                <div className="flex justify-between items-start mb-4">
                  <div className="p-2 bg-indigo-600/20 rounded-lg text-indigo-400">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>
                  </div>
                </div>
                <h3 className="text-slate-400 text-sm font-medium">Total Symlinks</h3>
                <p className="text-3xl font-bold text-white mt-1">{stats?.total_links || 0}</p>
              </div>

              <div className={`glass rounded-2xl p-6 relative overflow-hidden group transition-all ${flashUpdate ? 'update-flash' : ''}`}>
                <div className="absolute top-0 right-0 w-24 h-24 bg-rose-600/10 rounded-full -mr-12 -mt-12 blur-3xl group-hover:bg-rose-600/20 transition-all"></div>
                <div className="flex justify-between items-start mb-4">
                  <div className="p-2 bg-rose-600/20 rounded-lg text-rose-400">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                  </div>
                  {stats?.broken_links && stats.broken_links > 0 ? (
                    <span className="bg-rose-900/40 text-rose-400 text-[10px] font-bold px-2 py-1 rounded-full uppercase tracking-widest border border-rose-500/20">Critical</span>
                  ) : null}
                </div>
                <h3 className="text-slate-400 text-sm font-medium">Broken Links</h3>
                <p className="text-3xl font-bold text-white mt-1">{stats?.broken_links || 0}</p>
              </div>

              <div className={`glass rounded-2xl p-6 relative overflow-hidden group transition-all ${flashUpdate ? 'update-flash' : ''}`}>
                <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-600/10 rounded-full -mr-12 -mt-12 blur-3xl group-hover:bg-emerald-600/20 transition-all"></div>
                <div className="flex justify-between items-start mb-4">
                  <div className="p-2 bg-emerald-600/20 rounded-lg text-emerald-400">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" /></svg>
                  </div>
                </div>
                <h3 className="text-slate-400 text-sm font-medium">Healthy Links</h3>
                <p className="text-3xl font-bold text-white mt-1">{stats?.healthy_links || 0}</p>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Chart */}
              <div className="glass rounded-2xl p-6">
                <h3 className="text-white font-semibold mb-6">Health Overview</h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                      <XAxis dataKey="name" stroke="#64748b" axisLine={false} tickLine={false} />
                      <YAxis stroke="#64748b" axisLine={false} tickLine={false} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }}
                        itemStyle={{ color: '#f8fafc' }}
                      />
                      <Bar dataKey="value" radius={[4, 4, 0, 0]} barSize={40}>
                        {chartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Recent Broken Links */}
              <div className="glass rounded-2xl p-6">
                <div className="flex justify-between items-center mb-6">
                  <h3 className="text-white font-semibold">Broken Links Priority</h3>
                  <button onClick={() => setActiveTab('symlinks')} className="text-indigo-400 text-xs font-medium hover:underline">View All</button>
                </div>
                <div className="space-y-4">
                  {symlinks.filter(s => s.status === 'broken').slice(0, 4).length > 0 ? (
                    symlinks.filter(s => s.status === 'broken').slice(0, 4).map(s => (
                      <div key={s.id} className="flex items-center justify-between p-3 bg-slate-900/40 rounded-xl border border-slate-800">
                        <div className="flex-1 min-w-0 mr-4">
                          <p className="text-slate-300 text-sm truncate mono">{s.source_path.split('/').pop()}</p>
                          <p className="text-rose-500/80 text-[10px] mt-0.5 truncate uppercase font-bold tracking-tighter">Missing target: {s.target_path.split('/').pop()}</p>
                        </div>
                        <button 
                          disabled={repairingId === s.id}
                          onClick={() => handleRepair(s.id)}
                          className="px-3 py-1.5 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 rounded-lg text-xs font-semibold border border-rose-500/20 transition-all flex items-center space-x-1"
                        >
                          <svg className={`w-3 h-3 ${repairingId === s.id ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /></svg>
                          <span>{repairingId === s.id ? 'Repairing...' : 'Repair'}</span>
                        </button>
                      </div>
                    ))
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full py-10 opacity-40">
                      <svg className="w-12 h-12 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                      <p className="text-sm">No broken links found</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'symlinks' && (
          <div className="animate-in slide-in-from-bottom-4 duration-500">
            <div className="glass rounded-2xl overflow-hidden">
              <div className="p-6 border-b border-slate-800 flex justify-between items-center bg-slate-900/40">
                <div className="flex items-center space-x-2">
                  <div className="w-2 h-2 rounded-full bg-indigo-500"></div>
                  <h3 className="text-white font-semibold">Symlink Inventory</h3>
                </div>
                <div className="relative">
                   <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                   </span>
                   <input 
                    type="text" 
                    placeholder="Filter links..." 
                    className="bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-4 py-1.5 text-sm text-slate-300 focus:outline-none focus:border-indigo-500 transition-all w-64"
                   />
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead className="bg-slate-900/60 border-b border-slate-800">
                    <tr>
                      <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Status</th>
                      <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Source</th>
                      <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Target</th>
                      <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider">Last Checked</th>
                      <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase tracking-wider text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {symlinks.map(link => (
                      <tr key={link.id} className="hover:bg-indigo-600/5 transition-colors group">
                        <td className="px-6 py-4">
                          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                            link.status === 'healthy' 
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                              : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                          }`}>
                            {link.status}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <div className="text-sm text-slate-200 mono truncate max-w-xs">{link.source_path}</div>
                        </td>
                        <td className="px-6 py-4">
                          <div className="text-sm text-slate-400 mono truncate max-w-xs">{link.target_path}</div>
                        </td>
                        <td className="px-6 py-4 text-xs text-slate-500">
                          {new Date(link.last_checked).toLocaleString()}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <button 
                            onClick={() => handleRepair(link.id)}
                            className="p-2 text-slate-500 hover:text-indigo-400 transition-colors opacity-0 group-hover:opacity-100"
                          >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'config' && (
          <div className="max-w-4xl animate-in slide-in-from-bottom-4 duration-500">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              <div className="glass rounded-2xl p-6">
                <h3 className="text-white font-semibold mb-6 flex items-center space-x-2">
                  <svg className="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" /></svg>
                  <span>General Configuration</span>
                </h3>
                <div className="space-y-6">
                  <div>
                    <label className="block text-xs font-semibold text-slate-500 uppercase mb-2">Media Library Path</label>
                    <div className="bg-slate-950 border border-slate-800 rounded-lg px-4 py-2 text-sm text-slate-300 mono">{config?.media_path}</div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-slate-500 uppercase mb-2">Scan Interval</label>
                      <div className="bg-slate-950 border border-slate-800 rounded-lg px-4 py-2 text-sm text-slate-300">{config?.scan_interval}s</div>
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-500 uppercase mb-2">Orchestrator</label>
                      <div className={`inline-flex px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest ${config?.auto_repair ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                        {config?.auto_repair ? 'Active' : 'Disabled'}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="glass rounded-2xl p-6">
                <h3 className="text-white font-semibold mb-6 flex items-center space-x-2">
                   <svg className="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>
                  <span>Routing Logic</span>
                </h3>
                <div className="space-y-4">
                  {routes.map(route => (
                    <div key={route.id} className="p-4 bg-slate-900/40 border border-slate-800 rounded-xl">
                      <div className="flex justify-between items-center mb-2">
                        <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">Route #{route.id.slice(0, 4)}</span>
                      </div>
                      <div className="space-y-2">
                        <div className="flex items-center space-x-2">
                          <div className="w-1.5 h-1.5 rounded-full bg-slate-600"></div>
                          <p className="text-xs text-slate-400 mono truncate">{route.source_root}</p>
                        </div>
                        <div className="ml-0.5 border-l border-slate-700 h-4 mx-0.5"></div>
                        <div className="flex items-center space-x-2">
                          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>
                          <p className="text-xs text-slate-200 mono truncate">{route.target_root}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="glass rounded-2xl p-6 md:col-span-2">
                <h3 className="text-white font-semibold mb-6 flex items-center space-x-2">
                   <svg className="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
                  <span>Connected Apps</span>
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 bg-slate-900/40 border border-slate-800 rounded-xl flex items-center space-x-4">
                    <div className="w-10 h-10 bg-orange-600/20 rounded-lg flex items-center justify-center text-orange-500 font-bold">R</div>
                    <div>
                      <p className="text-sm font-semibold text-white">Radarr Integration</p>
                      <p className="text-xs text-slate-500">{config?.radarr_url || 'Not configured'}</p>
                    </div>
                    {config?.radarr_url && <span className="ml-auto w-2 h-2 rounded-full bg-emerald-500"></span>}
                  </div>
                  <div className="p-4 bg-slate-900/40 border border-slate-800 rounded-xl flex items-center space-x-4">
                    <div className="w-10 h-10 bg-indigo-600/20 rounded-lg flex items-center justify-center text-indigo-400 font-bold">S</div>
                    <div>
                      <p className="text-sm font-semibold text-white">Sonarr Integration</p>
                      <p className="text-xs text-slate-500">{config?.sonarr_url || 'Not configured'}</p>
                    </div>
                    {config?.sonarr_url && <span className="ml-auto w-2 h-2 rounded-full bg-emerald-500"></span>}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default App;
