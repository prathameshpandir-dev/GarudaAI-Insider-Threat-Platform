import React, { useState, useEffect, useRef } from 'react';
import { 
  Shield, ShieldAlert, ShieldCheck, Search, Users, User, Clock, 
  AlertTriangle, FileText, HardDrive, Mail, Globe, Key, Terminal, 
  RefreshCw, Send, Brain, ChevronRight, Activity, Cpu, AlertCircle, Info, LogOut
} from 'lucide-react';
import { Chart } from 'chart.js/auto';
import LoginPage from './components/LoginPage';
import { auth, signOut, onAuthStateChanged, isFirebaseConfigured } from './firebase';

const API_BASE = 'http://localhost:5000/api';

export default function App() {
  // Authentication State
  const [authUser, setAuthUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);

  // Application State
  const [employees, setEmployees] = useState([]);
  const [selectedEmp, setSelectedEmp] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [scoreHistory, setScoreHistory] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [health, setHealth] = useState(null);
  
  // Interactive Controls state
  const [search, setSearch] = useState('');
  const [deptFilter, setDeptFilter] = useState('All');
  const [selectedScenario, setSelectedScenario] = useState('usb_theft');
  const [simulating, setSimulating] = useState(false);
  const [resetting, setResetting] = useState(false);
  
  // AI Investigation & Chat State
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [aiReport, setAiReport] = useState('');
  const [loadingReport, setLoadingReport] = useState(false);
  const [chatMessage, setChatMessage] = useState('');
  const [chatHistory, setChatHistory] = useState([
    { role: 'assistant', text: 'Hello, I am the GarudaAI Analyst Assistant. You can ask me to list at-risk employees or query specific departments.' }
  ]);
  const [sendingChat, setSendingChat] = useState(false);
  
  // Loading & Error States
  const [loadingEmployees, setLoadingEmployees] = useState(true);
  const [loadingTimeline, setLoadingTimeline] = useState(false);

  const chartRef = useRef(null);
  const chartInstance = useRef(null);
  const chatBottomRef = useRef(null);

  // Monitor Firebase Auth session persistence
  useEffect(() => {
    if (isFirebaseConfigured && auth) {
      const unsubscribe = onAuthStateChanged(auth, async (user) => {
        if (user) {
          try {
            const tokenResult = await user.getIdTokenResult();
            const role = tokenResult.claims?.role || 'analyst';
            setAuthUser({
              uid: user.uid,
              email: user.email,
              displayName: user.displayName || user.email.split('@')[0],
              role: role
            });
          } catch (e) {
            setAuthUser({
              uid: user.uid,
              email: user.email,
              displayName: user.email.split('@')[0],
              role: 'analyst'
            });
          }
        } else {
          setAuthUser(null);
        }
        setAuthLoading(false);
      });
      return () => unsubscribe();
    } else {
      setAuthLoading(false);
    }
  }, []);

  const handleLogout = async () => {
    if (isFirebaseConfigured && auth) {
      await signOut(auth);
    }
    setAuthUser(null);
  };

  // Initialize and Fetch Initial Dashboard Data
  useEffect(() => {
    if (authUser) {
      fetchHealth();
      fetchEmployees();
      fetchAlerts();
    }
  }, [authUser]);

  // Fetch employee details when selection changes
  useEffect(() => {
    if (selectedEmp) {
      fetchEmployeeDetails(selectedEmp.employee_id);
    }
  }, [selectedEmp]);

  // Scroll Chat to bottom on history change
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);

  // Render History Chart.js Line Chart
  useEffect(() => {
    if (scoreHistory.length > 0 && chartRef.current) {
      if (chartInstance.current) {
        chartInstance.current.destroy();
      }
      
      const ctx = chartRef.current.getContext('2d');
      const labels = scoreHistory.map(h => h.timestamp.split(' ')[0]);
      const scores = scoreHistory.map(h => h.score);

      chartInstance.current = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: 'Behavior Trust Score',
            data: scores,
            borderColor: '#3B82F6',
            backgroundColor: 'rgba(59, 130, 246, 0.05)',
            borderWidth: 2,
            tension: 0.3,
            fill: true,
            pointBackgroundColor: '#3B82F6',
            pointBorderColor: '#090D16',
            pointHoverRadius: 6,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: '#121826',
              titleColor: '#94A3B8',
              bodyColor: '#F3F4F6',
              borderColor: '#1F293D',
              borderWidth: 1,
              callbacks: {
                label: function(context) {
                  const idx = context.dataIndex;
                  const reason = scoreHistory[idx]?.reason || 'Standard update';
                  return ` Score: ${context.raw} (${reason})`;
                }
              }
            }
          },
          scales: {
            x: {
              grid: { color: 'rgba(31, 41, 61, 0.2)' },
              ticks: { color: '#64748B', font: { size: 10 } }
            },
            y: {
              min: 0,
              max: 100,
              grid: { color: 'rgba(31, 41, 61, 0.2)' },
              ticks: { color: '#64748B', font: { size: 10 } }
            }
          }
        }
      });
    }
  }, [scoreHistory]);

  // API Call Implementations
  const fetchHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      const data = await res.json();
      setHealth(data);
    } catch (e) {
      console.error('Health check failed', e);
    }
  };

  const fetchEmployees = async () => {
    setLoadingEmployees(true);
    try {
      const res = await fetch(`${API_BASE}/employees`);
      const data = await res.json();
      setEmployees(data);
      if (data.length > 0 && !selectedEmp) {
        setSelectedEmp(data[0]);
      }
    } catch (e) {
      console.error('Error fetching employees', e);
    } finally {
      setLoadingEmployees(false);
    }
  };

  const fetchAlerts = async () => {
    try {
      const res = await fetch(`${API_BASE}/alerts`);
      const data = await res.json();
      setAlerts(data);
      if (data.length > 0 && !selectedAlert) {
        setSelectedAlert(data[0]);
        fetchAIExplanation(data[0].alert_id);
      }
    } catch (e) {
      console.error('Error fetching alerts', e);
    }
  };

  const fetchEmployeeDetails = async (empId) => {
    setLoadingTimeline(true);
    try {
      // Fetch timeline
      const tRes = await fetch(`${API_BASE}/employees/${empId}/timeline`);
      const tData = await tRes.json();
      setTimeline(tData);

      // Fetch history
      const hRes = await fetch(`${API_BASE}/employees/${empId}/trust-score/history`);
      const hData = await hRes.json();
      setScoreHistory(hData);
    } catch (e) {
      console.error('Error fetching employee details', e);
    } finally {
      setLoadingTimeline(false);
    }
  };

  const fetchAIExplanation = async (alertId) => {
    setLoadingReport(true);
    setAiReport('');
    try {
      const res = await fetch(`${API_BASE}/alerts/${alertId}/explanation`);
      const data = await res.json();
      setAiReport(data.explanation);
    } catch (e) {
      setAiReport('Failed to generate AI investigation narrative.');
      console.error('Error generating explanation', e);
    } finally {
      setLoadingReport(false);
    }
  };

  // Action Handlers
  const handleSimulate = async () => {
    if (!selectedEmp) return;
    setSimulating(true);
    try {
      const res = await fetch(`${API_BASE}/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario: selectedScenario,
          employee_id: selectedEmp.employee_id
        })
      });
      const data = await res.json();
      
      // Update UI components
      await fetchEmployees();
      await fetchAlerts();
      
      // Reload current selected employee details
      if (selectedEmp.employee_id === data.employee_id) {
        await fetchEmployeeDetails(data.employee_id);
      }
      
      // Auto select the newly generated simulation alert
      if (data.alert_id) {
        const simAlert = {
          alert_id: data.alert_id,
          employee_id: data.employee_id,
          type: selectedScenario === 'usb_theft' ? 'USB Theft' : selectedScenario === 'mass_download' ? 'Mass File Download' : selectedScenario === 'impossible_travel' ? 'Impossible Travel' : 'Privilege Escalation',
          severity: 'Critical'
        };
        setSelectedAlert(simAlert);
        fetchAIExplanation(data.alert_id);
      }
    } catch (e) {
      console.error('Simulation failed', e);
    } finally {
      setSimulating(false);
    }
  };

  const handleResetDemo = async () => {
    setResetting(true);
    try {
      await fetch(`${API_BASE}/reset`, { method: 'POST' });
      await fetchEmployees();
      await fetchAlerts();
      if (selectedEmp) {
        await fetchEmployeeDetails(selectedEmp.employee_id);
      }
      setAiReport('Demo database successfully reset to standard baseline state.');
    } catch (e) {
      console.error('Database reset failed', e);
    } finally {
      setResetting(false);
    }
  };

  const handleSendChat = async (e) => {
    e.preventDefault();
    if (!chatMessage.trim()) return;
    
    const userMsg = chatMessage;
    setChatMessage('');
    setChatHistory(prev => [...prev, { role: 'user', text: userMsg }]);
    setSendingChat(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMsg })
      });
      const data = await res.json();
      setChatHistory(prev => [...prev, { role: 'assistant', text: data.response }]);
    } catch (e) {
      setChatHistory(prev => [...prev, { role: 'assistant', text: 'Error contacting security assistant server.' }]);
    } finally {
      setSendingChat(false);
    }
  };

  // Helper styling calculators
  const getScoreColorClass = (score) => {
    if (score >= 80) return 'text-low border-low';
    if (score >= 60) return 'text-medium border-medium';
    if (score >= 40) return 'text-high border-high';
    return 'text-critical border-critical';
  };

  const getScoreProgressClass = (score) => {
    if (score >= 80) return 'bg-emerald-500';
    if (score >= 60) return 'bg-amber-500';
    if (score >= 40) return 'bg-rose-500';
    return 'bg-fuchsia-500';
  };

  const getTimelineIcon = (type) => {
    switch (type) {
      case 'logon': return <Key className="w-4 h-4 text-blue-400" />;
      case 'file': return <FileText className="w-4 h-4 text-amber-400" />;
      case 'device': return <HardDrive className="w-4 h-4 text-purple-400" />;
      case 'http': return <Globe className="w-4 h-4 text-emerald-400" />;
      case 'email': return <Mail className="w-4 h-4 text-indigo-400" />;
      case 'privilege': return <Terminal className="w-4 h-4 text-rose-400" />;
      default: return <Info className="w-4 h-4 text-gray-400" />;
    }
  };

  // Filters calculation
  const filteredEmployees = employees.filter(emp => {
    const matchesSearch = emp.full_name.toLowerCase().includes(search.toLowerCase()) || 
                          emp.employee_id.toLowerCase().includes(search.toLowerCase());
    const matchesDept = deptFilter === 'All' || emp.department === deptFilter;
    return matchesSearch && matchesDept;
  });

  // Unauthenticated Guard
  if (authLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-dark-bg text-blue-500 font-sans">
        <RefreshCw className="w-8 h-8 animate-spin" />
      </div>
    );
  }

  if (!authUser) {
    return <LoginPage onLoginSuccess={(userProfile) => setAuthUser(userProfile)} />;
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-dark-bg text-gray-200">
      
      {/* Sidebar: Identity panel */}
      <aside className="w-80 flex flex-col border-r border-dark-border bg-dark-card/50">
        
        {/* Branding header */}
        <div className="p-5 border-b border-dark-border flex items-center gap-3">
          <Shield className="w-7 h-7 text-blue-500 animate-pulse" />
          <div>
            <h1 className="text-xl font-bold tracking-wider text-white">GARUDA<span className="text-blue-500">AI</span></h1>
            <p className="text-[10px] text-gray-500 uppercase tracking-widest font-semibold">Insider Threat Intelligence</p>
          </div>
        </div>

        {/* Global status summary */}
        <div className="p-4 mx-4 my-3 bg-dark-bg/60 rounded-lg border border-dark-border/50 flex flex-col gap-2">
          <div className="flex justify-between items-center text-xs text-gray-400">
            <span>Database Connection:</span>
            <span className="flex items-center gap-1.5 font-medium text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
              {health?.database || 'Checking...'}
            </span>
          </div>
          <div className="flex justify-between items-center text-xs text-gray-400">
            <span>AI Processing:</span>
            <span className="text-blue-400 font-medium">{health?.gemini_api || 'Offline'}</span>
          </div>
        </div>

        {/* Filters */}
        <div className="p-4 flex flex-col gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 w-4 h-4 text-gray-500" />
            <input 
              type="text" 
              placeholder="Search employee id or name..."
              className="w-full pl-9 pr-4 py-2 text-sm bg-dark-bg border border-dark-border rounded-md text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          
          <select
            className="w-full py-2 px-3 text-sm bg-dark-bg border border-dark-border rounded-md text-gray-400 focus:outline-none focus:border-blue-500"
            value={deptFilter}
            onChange={e => setDeptFilter(e.target.value)}
          >
            <option value="All">All Departments</option>
            <option value="Engineering">Engineering</option>
            <option value="HR">HR</option>
            <option value="Finance">Finance</option>
            <option value="Sales">Sales</option>
          </select>
        </div>

        {/* Employee List container */}
        <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-2">
          {loadingEmployees ? (
            <div className="flex justify-center p-8">
              <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          ) : filteredEmployees.length === 0 ? (
            <div className="text-center p-8 text-gray-500 text-sm">No employees found.</div>
          ) : (
            filteredEmployees.map(emp => {
              const isSelected = selectedEmp?.employee_id === emp.employee_id;
              const hasAlert = alerts.some(a => a.employee_id === emp.employee_id);
              
              return (
                <button
                  key={emp.employee_id}
                  onClick={() => setSelectedEmp(emp)}
                  className={`w-full text-left p-3 rounded-lg border transition-all flex flex-col gap-1.5 cursor-pointer ${
                    isSelected 
                      ? 'bg-dark-hover/80 border-blue-500/80' 
                      : 'bg-dark-card border-dark-border/40 hover:bg-dark-hover/40'
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div className="font-semibold text-sm text-gray-200 flex items-center gap-1.5">
                      {emp.full_name}
                      {hasAlert && <span className="w-2 h-2 rounded-full bg-rose-500" title="Active Security Alert"></span>}
                    </div>
                    <span className="text-[10px] bg-dark-bg/80 text-gray-500 px-1.5 py-0.5 rounded font-mono">
                      {emp.employee_id}
                    </span>
                  </div>

                  <div className="flex justify-between items-center text-xs text-gray-500">
                    <span>{emp.role}</span>
                    <span className={`font-semibold font-mono ${
                      emp.current_score >= 80 ? 'text-emerald-400' : emp.current_score >= 50 ? 'text-amber-500' : 'text-rose-500'
                    }`}>
                      {emp.current_score}/100
                    </span>
                  </div>

                  {/* Tiny progress bar */}
                  <div className="w-full bg-dark-bg rounded-full h-1">
                    <div 
                      className={`h-1 rounded-full ${getScoreProgressClass(emp.current_score)}`}
                      style={{ width: `${emp.current_score}%` }}
                    ></div>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </aside>

      {/* Main Panel: Analysis dashboard */}
      <main className="flex-1 flex flex-col overflow-hidden">
        
        {/* Top Header controls */}
        <header className="p-4 border-b border-dark-border bg-dark-card/30 flex justify-between items-center">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-blue-500" />
            <span className="font-semibold text-white tracking-wide">Threat Analysis Console</span>
          </div>

          <div className="flex items-center gap-3">
            {/* Active User Identity & Role Badge */}
            {authUser && (
              <div className="flex items-center gap-2 px-3 py-1.5 bg-dark-card border border-dark-border/80 rounded-md text-xs">
                <User className="w-3.5 h-3.5 text-blue-400" />
                <span className="font-semibold text-gray-200">{authUser.email}</span>
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                  authUser.role === 'admin' ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30' : 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                }`}>
                  {authUser.role || 'ANALYST'}
                </span>
              </div>
            )}

            <button
              onClick={handleResetDemo}
              disabled={resetting}
              className="flex items-center gap-2 text-xs font-semibold py-2 px-3 border border-dark-border hover:bg-dark-hover hover:text-white rounded-md transition-all cursor-pointer text-gray-400 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${resetting ? 'animate-spin' : ''}`} />
              Reset Demo State
            </button>

            {/* Logout Action Button */}
            <button
              onClick={handleLogout}
              title="Sign Out of GarudaAI"
              className="flex items-center gap-1.5 text-xs font-semibold py-2 px-3 border border-rose-500/30 bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 rounded-md transition-all cursor-pointer"
            >
              <LogOut className="w-3.5 h-3.5" />
              Sign Out
            </button>
          </div>
        </header>

        {/* Layout split pane */}
        <div className="flex-1 flex overflow-hidden">
          
          {/* Left panel: Deep Dive employee info */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            
            {selectedEmp ? (
              <>
                {/* Employee Info Header */}
                <div className="glass p-6 rounded-xl flex items-center justify-between glow-card">
                  <div className="flex items-center gap-5">
                    <div className="w-14 h-14 bg-dark-hover border border-dark-border rounded-xl flex items-center justify-center text-blue-500">
                      <User className="w-7 h-7" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2.5">
                        <h2 className="text-2xl font-bold text-white leading-tight">{selectedEmp.full_name}</h2>
                        {selectedEmp.is_privileged_user && (
                          <span className="flex items-center gap-1 text-[9px] font-bold text-rose-400 border border-rose-500/30 bg-rose-500/5 px-2 py-0.5 rounded-full uppercase tracking-wider">
                            <ShieldAlert className="w-2.5 h-2.5 text-rose-400 animate-pulse" />
                            Privileged
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-400 font-medium">{selectedEmp.role} &middot; <span className="text-gray-500">{selectedEmp.department} &middot; {selectedEmp.office_location}</span></p>
                    </div>
                  </div>
                  
                  {/* Circular trust badge */}
                  <div className="flex flex-col items-center">
                    <div className={`w-14 h-14 rounded-full border-2 flex items-center justify-center font-mono font-bold text-xl ${getScoreColorClass(selectedEmp.current_score)}`}>
                      {selectedEmp.current_score}
                    </div>
                    <span className="text-[10px] text-gray-500 uppercase tracking-widest mt-1.5 font-bold">Trust Index</span>
                  </div>
                </div>

                {/* Score Trend & Simulator split grid */}
                <div className="grid grid-cols-12 gap-6">
                  
                  {/* Trend chart */}
                  <div className="col-span-8 glass p-5 rounded-xl flex flex-col gap-3 min-h-[220px]">
                    <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">Score Trend History</span>
                    <div className="flex-1 relative">
                      <canvas ref={chartRef}></canvas>
                    </div>
                  </div>

                  {/* Simulator widget */}
                  <div className="col-span-4 glass p-5 rounded-xl flex flex-col gap-4">
                    <span className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-1">
                      <Cpu className="w-3.5 h-3.5 text-blue-500" />
                      Attack Simulator
                    </span>
                    <p className="text-xs text-gray-500 leading-normal">Inject a mock threat activity pattern to test behavioral detection rules and AI models.</p>
                    
                    <select
                      className="w-full py-2 px-3 text-xs bg-dark-bg border border-dark-border rounded-md text-gray-300 focus:outline-none focus:border-blue-500"
                      value={selectedScenario}
                      onChange={e => setSelectedScenario(e.target.value)}
                    >
                      <option value="usb_theft">Midnight Login & USB Copy</option>
                      <option value="mass_download">Mass File Download Spike</option>
                      <option value="impossible_travel">Impossible Travel Auth</option>
                      <option value="privilege_escalation">Privilege Escalation Access</option>
                    </select>

                    <button
                      onClick={handleSimulate}
                      disabled={simulating}
                      className="w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-md text-xs font-semibold tracking-wide transition-all shadow-lg shadow-blue-600/10 cursor-pointer text-center"
                    >
                      {simulating ? 'Injecting Threat...' : 'Inject Simulation Scenario'}
                    </button>
                  </div>
                </div>

                {/* Event timeline */}
                <div className="glass p-6 rounded-xl flex flex-col gap-4">
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-blue-500" />
                    Interactive Incident Timeline
                  </span>
                  
                  {loadingTimeline ? (
                    <div className="flex justify-center p-8">
                      <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
                    </div>
                  ) : timeline.length === 0 ? (
                    <div className="text-center p-8 text-gray-500 text-sm">No activity logs recorded.</div>
                  ) : (
                    <div className="relative border-l border-dark-border/60 ml-3.5 space-y-4">
                      {timeline.map((entry, idx) => {
                        const isAnom = entry.is_anomaly;
                        return (
                          <div key={idx} className="relative pl-6">
                            
                            {/* Chronological bullet icon */}
                            <div className={`absolute -left-[13px] top-1 p-1 rounded-full border bg-dark-card flex items-center justify-center ${
                              isAnom 
                                ? entry.severity === 'Critical' ? 'border-fuchsia-500 text-fuchsia-500' : entry.severity === 'High' ? 'border-red-500 text-red-500' : 'border-amber-500 text-amber-500'
                                : 'border-dark-border text-gray-400'
                            }`}>
                              {getTimelineIcon(entry.type)}
                            </div>

                            {/* Log item details */}
                            <div className={`p-3 rounded-lg border text-sm transition-all ${
                              isAnom 
                                ? entry.severity === 'Critical' ? 'bg-fuchsia-500/5 border-fuchsia-500/20' : entry.severity === 'High' ? 'bg-red-500/5 border-red-500/20' : 'bg-amber-500/5 border-amber-500/20'
                                : 'bg-dark-card/30 border-dark-border/20 hover:border-dark-border/40'
                            }`}>
                              <div className="flex justify-between items-start gap-3">
                                <span className={`font-semibold ${isAnom ? 'text-white' : 'text-gray-300'}`}>
                                  {entry.description}
                                </span>
                                <span className="text-[10px] text-gray-500 font-mono whitespace-nowrap">{entry.timestamp}</span>
                              </div>
                              
                              {isAnom && (
                                <div className="mt-2 flex items-center gap-2">
                                  <span className={`text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${
                                    entry.severity === 'Critical' ? 'bg-fuchsia-500/10 text-fuchsia-400' : entry.severity === 'High' ? 'bg-red-500/10 text-red-400' : 'bg-amber-500/10 text-amber-400'
                                  }`}>
                                    {entry.severity} Alert
                                  </span>
                                </div>
                              )}
                            </div>

                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="flex flex-col items-center justify-center h-96 text-gray-500">
                <Users className="w-16 h-16 text-gray-600 mb-3" />
                <p>Select an employee from the sidebar to inspect behavioral data.</p>
              </div>
            )}
          </div>

          {/* Right panel: AI Command Center (Investigate + chat) */}
          <div className="w-[450px] border-l border-dark-border bg-dark-card/30 flex flex-col">
            
            {/* Split panel selectors */}
            <div className="border-b border-dark-border flex">
              <button className="flex-1 py-3 text-xs font-bold text-center tracking-wider border-b-2 border-blue-500 text-white bg-dark-card/50 flex items-center justify-center gap-1.5">
                <Brain className="w-4 h-4 text-blue-500" />
                AI INVESTIGATION
              </button>
            </div>

            {/* Split content container */}
            <div className="flex-1 flex flex-col overflow-hidden">
              
              {/* Top half: Investigation documentation report */}
              <div className="flex-1 overflow-y-auto p-5 border-b border-dark-border space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-1">
                    <ShieldAlert className="w-3.5 h-3.5 text-rose-500" />
                    Recent Incidents
                  </span>
                  
                  {alerts.length > 0 && (
                    <select
                      className="text-xs bg-dark-bg border border-dark-border rounded px-2 py-1 text-gray-300"
                      value={selectedAlert?.alert_id || ''}
                      onChange={e => {
                        const sel = alerts.find(a => a.alert_id === e.target.value);
                        setSelectedAlert(sel);
                        if (sel) fetchAIExplanation(sel.alert_id);
                      }}
                    >
                      {alerts.map(a => (
                        <option key={a.alert_id} value={a.alert_id}>
                          {a.employee_id} ({a.type})
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                {loadingReport ? (
                  <div className="flex flex-col items-center justify-center h-48 gap-2">
                    <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
                    <span className="text-xs text-gray-500">Querying Gemini security models...</span>
                  </div>
                ) : aiReport ? (
                  <div className="prose prose-invert text-xs max-w-none text-gray-300 space-y-3 font-sans leading-relaxed">
                    {/* Render investigation narrative */}
                    {aiReport.split('\n').map((line, i) => {
                      if (line.startsWith('### ')) {
                        return <h3 key={i} className="text-sm font-bold text-white mt-4 border-b border-dark-border/40 pb-1">{line.replace('### ', '')}</h3>;
                      }
                      if (line.startsWith('- **')) {
                        const parts = line.replace('- **', '').split('**');
                        return (
                          <div key={i} className="flex gap-2 pl-2">
                            <span className="text-blue-500 font-bold">&bull;</span>
                            <span><strong>{parts[0]}</strong>{parts.slice(1).join('')}</span>
                          </div>
                        );
                      }
                      if (line.startsWith('1. ') || line.startsWith('2. ') || line.startsWith('3. ') || line.startsWith('4. ')) {
                        return <div key={i} className="pl-4 font-semibold text-gray-200 mt-1">{line}</div>;
                      }
                      return <p key={i}>{line}</p>;
                    })}
                  </div>
                ) : (
                  <div className="text-center p-8 text-gray-500 text-xs">No active alerts selected for AI generation.</div>
                )}
              </div>

              {/* Bottom half: Command Chat widget */}
              <div className="h-[300px] flex flex-col bg-dark-bg/60">
                <div className="p-3 border-b border-dark-border/60 bg-dark-card/80 flex items-center justify-between">
                  <span className="text-xs font-bold text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                    <Terminal className="w-3.5 h-3.5 text-blue-500" />
                    AI Security Command Chat
                  </span>
                </div>

                {/* Messages container */}
                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                  {chatHistory.map((chat, idx) => (
                    <div key={idx} className={`flex ${chat.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`p-2.5 rounded-lg max-w-[85%] text-xs leading-normal ${
                        chat.role === 'user' 
                          ? 'bg-blue-600 text-white rounded-br-none shadow-md' 
                          : 'bg-dark-card border border-dark-border text-gray-300 rounded-bl-none'
                      }`}>
                        {/* Splitting simple markdown text inside chat messages */}
                        {chat.text.split('\n').map((para, pIdx) => (
                          <p key={pIdx} className={pIdx > 0 ? 'mt-1.5' : ''}>
                            {para.split('**').map((part, partIdx) => 
                              partIdx % 2 === 1 ? <strong key={partIdx} className="text-white">{part}</strong> : part
                            )}
                          </p>
                        ))}
                      </div>
                    </div>
                  ))}
                  {sendingChat && (
                    <div className="flex justify-start">
                      <div className="bg-dark-card border border-dark-border p-2.5 rounded-lg rounded-bl-none text-xs text-gray-500 flex items-center gap-1.5">
                        <RefreshCw className="w-3 h-3 animate-spin text-blue-500" />
                        Analyzing query...
                      </div>
                    </div>
                  )}
                  <div ref={chatBottomRef}></div>
                </div>

                {/* Chat input box */}
                <form onSubmit={handleSendChat} className="p-3 border-t border-dark-border bg-dark-card/60 flex gap-2">
                  <input
                    type="text"
                    placeholder="Ask assistant (e.g., 'who has score below 40?')"
                    className="flex-1 py-1.5 px-3 text-xs bg-dark-bg border border-dark-border rounded-md text-gray-200 focus:outline-none focus:border-blue-500"
                    value={chatMessage}
                    onChange={e => setChatMessage(e.target.value)}
                    disabled={sendingChat}
                  />
                  <button
                    type="submit"
                    className="p-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-md transition-all flex items-center justify-center cursor-pointer"
                    disabled={sendingChat || !chatMessage.trim()}
                  >
                    <Send className="w-3.5 h-3.5" />
                  </button>
                </form>
              </div>

            </div>

          </div>

        </div>

      </main>

    </div>
  );
}
