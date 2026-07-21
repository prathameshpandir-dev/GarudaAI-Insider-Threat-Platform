import React, { useState, useEffect } from 'react';
import { 
  Shield, 
  Lock, 
  Mail, 
  Eye, 
  EyeOff, 
  AlertTriangle, 
  RefreshCw, 
  CheckCircle2, 
  KeyRound, 
  ArrowLeft,
  ShieldCheck,
  Zap
} from 'lucide-react';
import { 
  auth, 
  isFirebaseConfigured, 
  signInWithEmailAndPassword, 
  sendPasswordResetEmail 
} from '../firebase';

export default function LoginPage({ onLoginSuccess }) {
  // Form State
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  
  // UI State Machine
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [isShaking, setIsShaking] = useState(false);

  // Password Reset Flow State
  const [showForgotModal, setShowForgotModal] = useState(false);
  const [resetEmail, setResetEmail] = useState('');
  const [resetLoading, setResetLoading] = useState(false);
  const [resetSuccessMsg, setResetSuccessMsg] = useState('');
  const [resetErrorMsg, setResetErrorMsg] = useState('');

  // Rate Limiting Security State (Client-side UX layer)
  const [failedAttempts, setFailedAttempts] = useState(0);
  const [lockoutTimeLeft, setLockoutTimeLeft] = useState(0);

  // Single Demo Credential (as requested)
  const DEMO_EMAIL = 'admin@garuda.ai';
  const DEMO_PASSWORD = 'password123';
  const DEMO_ROLE = 'admin';

  // Handle countdown timer for rate limit lockout
  useEffect(() => {
    let timer;
    if (lockoutTimeLeft > 0) {
      timer = setInterval(() => {
        setLockoutTimeLeft(prev => prev - 1);
      }, 1000);
    } else if (lockoutTimeLeft === 0 && failedAttempts >= 5) {
      // Reset lockout after timer finishes
      setFailedAttempts(0);
    }
    return () => clearInterval(timer);
  }, [lockoutTimeLeft, failedAttempts]);

  // Trigger error shake effect
  const triggerErrorShake = (message) => {
    setErrorMsg(message);
    setIsShaking(true);
    setTimeout(() => setIsShaking(false), 400);
  };

  // One-click quick fill for demo credential
  const handleQuickFillDemo = () => {
    setEmail(DEMO_EMAIL);
    setPassword(DEMO_PASSWORD);
    setErrorMsg('');
  };

  // Main Submit Handler
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading || lockoutTimeLeft > 0) return;

    setErrorMsg('');

    // 1. Client Validation
    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      triggerErrorShake('Please enter your email address.');
      return;
    }
    
    // Email regex validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(trimmedEmail)) {
      triggerErrorShake('Please provide a valid email format (e.g. user@domain.com).');
      return;
    }

    if (!password) {
      triggerErrorShake('Please enter your security password.');
      return;
    }

    setLoading(true);

    try {
      if (isFirebaseConfigured && auth) {
        // Firebase Production Authentication Flow
        const userCredential = await signInWithEmailAndPassword(auth, trimmedEmail, password);
        const user = userCredential.user;
        
        // Extract Firebase custom claim for role (analyst vs admin)
        const idTokenResult = await user.getIdTokenResult(true);
        const userRole = idTokenResult.claims?.role || 'analyst';

        // Success: Reset rate limit state and notify parent app
        setFailedAttempts(0);
        onLoginSuccess({
          uid: user.uid,
          email: user.email,
          displayName: user.displayName || user.email.split('@')[0],
          role: userRole
        });

      } else {
        // Local Demo Mode Auth Handler
        await new Promise(resolve => setTimeout(resolve, 800)); // Simulate network latency

        if (trimmedEmail.toLowerCase() === DEMO_EMAIL.toLowerCase() && password === DEMO_PASSWORD) {
          setFailedAttempts(0);
          onLoginSuccess({
            uid: 'demo-admin-uid-101',
            email: DEMO_EMAIL,
            displayName: 'Lead Security Administrator',
            role: DEMO_ROLE
          });
        } else {
          throw { code: 'auth/invalid-credential' };
        }
      }
    } catch (err) {
      console.error('Login authentication error:', err);
      
      // Increment client-side failed attempts count
      const nextAttempts = failedAttempts + 1;
      setFailedAttempts(nextAttempts);

      if (nextAttempts >= 5) {
        setLockoutTimeLeft(30); // 30-second cooldown
        triggerErrorShake('Too many failed attempts. Security portal locked for 30 seconds.');
      } else {
        // Map raw Firebase error codes to human-readable security notifications
        let message = 'Authentication failed. Please verify your credentials.';
        const code = err.code || '';

        if (code === 'auth/wrong-password' || code === 'auth/invalid-credential') {
          message = 'Invalid credentials. Please verify your email and password.';
        } else if (code === 'auth/user-not-found') {
          message = 'No active security account found for this email address.';
        } else if (code === 'auth/too-many-requests') {
          message = 'Access restricted by server due to excessive attempts. Try again later.';
        } else if (code === 'auth/network-request-failed') {
          message = 'Network connectivity lost. Unable to contact authentication server.';
        } else if (code === 'auth/user-disabled') {
          message = 'This security account has been disabled by a system administrator.';
        }

        triggerErrorShake(message);
      }
    } finally {
      setLoading(false);
    }
  };

  // Password Reset Handler
  const handleResetPassword = async (e) => {
    e.preventDefault();
    setResetErrorMsg('');
    setResetSuccessMsg('');

    const targetEmail = resetEmail.trim();
    if (!targetEmail) {
      setResetErrorMsg('Please enter your registered email address.');
      return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(targetEmail)) {
      setResetErrorMsg('Please enter a valid email format.');
      return;
    }

    setResetLoading(true);

    try {
      if (isFirebaseConfigured && auth) {
        await sendPasswordResetEmail(auth, targetEmail);
      } else {
        await new Promise(resolve => setTimeout(resolve, 800));
      }
      setResetSuccessMsg(`Password reset instructions sent to ${targetEmail}.`);
    } catch (err) {
      console.error('Password reset error:', err);
      if (err.code === 'auth/user-not-found') {
        setResetErrorMsg('No security account matches this email address.');
      } else {
        setResetErrorMsg('Failed to send reset email. Please try again later.');
      }
    } finally {
      setResetLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen w-screen flex items-center justify-center bg-dark-bg text-gray-200 overflow-hidden font-sans select-none">
      
      {/* Background Aesthetic Layer: Scanning laser line & Subtle Cyber Grid */}
      <div className="absolute inset-0 pointer-events-none opacity-20">
        <div className="absolute inset-0 bg-[radial-gradient(#1F293D_1px,transparent_1px)] [background-size:24px_24px]"></div>
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-blue-500/60 to-transparent animate-pulse"></div>
      </div>

      {/* Main Authentication Card */}
      <div className={`relative z-10 w-full max-w-md px-6 py-8 mx-4 glass glow-card rounded-2xl shadow-2xl border border-dark-border/80 transition-all ${isShaking ? 'animate-shake' : ''}`}>
        
        {/* Branding Header */}
        <div className="flex flex-col items-center text-center mb-6">
          <div className="w-12 h-12 mb-3 bg-blue-600/10 border border-blue-500/30 rounded-xl flex items-center justify-center text-blue-500 shadow-lg shadow-blue-500/10">
            <Shield className="w-6 h-6 animate-pulse" />
          </div>

          <h1 className="text-2xl font-bold tracking-wider text-white flex items-center gap-1">
            GARUDA<span className="text-blue-500">AI</span>
          </h1>
          <p className="text-xs text-gray-400 mt-1 font-medium tracking-wide">
            Behavior-based insider threat detection
          </p>

          <div className="mt-3 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-dark-bg/80 border border-dark-border text-[10px] text-gray-400 font-mono uppercase tracking-wider">
            <ShieldCheck className="w-3 h-3 text-emerald-400" />
            SOC Incident Portal &middot; Restricted Access
          </div>
        </div>

        {/* Demo Credential Quick-Fill Notice */}
        <div className="mb-6 p-3 rounded-lg bg-blue-950/30 border border-blue-800/40 flex items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-blue-400 shrink-0" />
            <div>
              <span className="text-gray-300 font-medium block">Demo Administrator Account:</span>
              <span className="font-mono text-gray-400 text-[11px]">{DEMO_EMAIL}</span>
            </div>
          </div>
          <button
            type="button"
            onClick={handleQuickFillDemo}
            className="px-2.5 py-1 bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 border border-blue-500/30 rounded text-[11px] font-semibold transition-all cursor-pointer whitespace-nowrap"
          >
            Auto Fill
          </button>
        </div>

        {/* Inline Error Message Box */}
        {errorMsg && (
          <div className="mb-5 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2.5 animate-fadeIn">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <span className="leading-snug">{errorMsg}</span>
          </div>
        )}

        {/* Rate limit lockout warning */}
        {lockoutTimeLeft > 0 && (
          <div className="mb-5 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-center gap-2 font-mono">
            <Lock className="w-4 h-4 text-amber-400 shrink-0" />
            <span>Portal locked due to failed attempts ({lockoutTimeLeft}s remaining)</span>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          
          {/* Email Field */}
          <div>
            <label htmlFor="login-email" className="block text-xs font-semibold text-gray-300 uppercase tracking-wider mb-1.5">
              Work Email Address
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-2.5 w-4 h-4 text-gray-500" />
              <input
                id="login-email"
                name="email"
                type="email"
                autoComplete="username"
                disabled={loading || lockoutTimeLeft > 0}
                placeholder="analyst@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-9 pr-4 py-2 text-xs bg-dark-bg border border-dark-border rounded-lg text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50 transition-all font-sans"
              />
            </div>
          </div>

          {/* Password Field */}
          <div>
            <div className="flex justify-between items-center mb-1.5">
              <label htmlFor="login-password" className="block text-xs font-semibold text-gray-300 uppercase tracking-wider">
                Security Password
              </label>
              <button
                type="button"
                onClick={() => {
                  setShowForgotModal(true);
                  setResetEmail(email);
                  setResetErrorMsg('');
                  setResetSuccessMsg('');
                }}
                className="text-[11px] text-blue-400 hover:text-blue-300 transition-colors cursor-pointer"
              >
                Forgot password?
              </button>
            </div>
            <div className="relative">
              <Lock className="absolute left-3 top-2.5 w-4 h-4 text-gray-500" />
              <input
                id="login-password"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                disabled={loading || lockoutTimeLeft > 0}
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-9 pr-10 py-2 text-xs bg-dark-bg border border-dark-border rounded-lg text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50 transition-all font-sans"
              />
              <button
                type="button"
                tabIndex={-1}
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-2.5 text-gray-500 hover:text-gray-300 transition-colors cursor-pointer"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading || lockoutTimeLeft > 0}
            className="w-full mt-2 py-2.5 px-4 bg-blue-600 hover:bg-blue-700 active:scale-[0.99] disabled:opacity-50 text-white rounded-lg text-xs font-bold tracking-wider uppercase transition-all shadow-lg shadow-blue-600/20 cursor-pointer flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Authenticating...
              </>
            ) : (
              'Sign In to Security Console'
            )}
          </button>
        </form>

        {/* Security Notice Footer */}
        <div className="mt-6 pt-4 border-t border-dark-border/60 text-center">
          <p className="text-[11px] text-gray-500 leading-normal">
            Access is provisioned by your corporate security administrator. Self-registration is restricted.
          </p>
          <div className="mt-3 flex items-center justify-center gap-2 text-[10px] text-gray-600 font-mono">
            <span>GarudaAI v1.0.4</span>
            <span>&middot;</span>
            <span>TLS 1.3 Encrypted Session</span>
          </div>
        </div>

      </div>

      {/* Forgot Password Modal Overlay */}
      {showForgotModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-sm glass rounded-xl border border-dark-border p-6 shadow-2xl relative animate-fadeIn">
            
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400">
                <KeyRound className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white">Reset Security Password</h3>
                <p className="text-[11px] text-gray-400">Receive password recovery link via email</p>
              </div>
            </div>

            {resetSuccessMsg ? (
              <div className="py-4 text-center space-y-3">
                <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto animate-bounce" />
                <p className="text-xs text-gray-300">{resetSuccessMsg}</p>
                <button
                  type="button"
                  onClick={() => setShowForgotModal(false)}
                  className="w-full py-2 bg-dark-hover border border-dark-border text-white text-xs rounded-lg font-medium cursor-pointer"
                >
                  Return to Sign In
                </button>
              </div>
            ) : (
              <form onSubmit={handleResetPassword} className="space-y-4">
                {resetErrorMsg && (
                  <div className="p-2.5 rounded bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
                    <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                    <span>{resetErrorMsg}</span>
                  </div>
                )}

                <div>
                  <label className="block text-[11px] font-semibold text-gray-300 uppercase tracking-wider mb-1">
                    Registered Email
                  </label>
                  <input
                    type="email"
                    required
                    placeholder="analyst@company.com"
                    value={resetEmail}
                    onChange={e => setResetEmail(e.target.value)}
                    className="w-full px-3 py-2 text-xs bg-dark-bg border border-dark-border rounded-lg text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setShowForgotModal(false)}
                    className="flex-1 py-2 bg-dark-hover border border-dark-border text-gray-300 text-xs rounded-lg font-medium cursor-pointer"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={resetLoading}
                    className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded-lg font-bold cursor-pointer disabled:opacity-50 flex items-center justify-center gap-1.5"
                  >
                    {resetLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : 'Send Reset Link'}
                  </button>
                </div>
              </form>
            )}

          </div>
        </div>
      )}

    </div>
  );
}
