import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router';
import { useAuthStore } from '../store/authStore';
import { useLocale } from '../i18n';
import { 
  ShieldAlert, 
  LogIn, 
  Eye, 
  EyeOff, 
  Loader2, 
  KeyRound, 
  Terminal, 
  Activity, 
  Cpu, 
  Layers 
} from 'lucide-react';

// Canvas-based particles network background representing node fleet connections in indigo-violet tones
const NetworkCanvas: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = canvas.offsetWidth);
    let height = (canvas.height = canvas.offsetHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = canvas.offsetWidth;
      height = canvas.height = canvas.offsetHeight;
    };
    window.addEventListener('resize', handleResize);

    const numParticles = 45;
    const particles: Array<{
      x: number;
      y: number;
      vx: number;
      vy: number;
      radius: number;
      color: string;
      pulse: number;
    }> = [];

    const colors = [
      'rgba(99, 102, 241, 0.45)',  // Indigo
      'rgba(168, 85, 247, 0.45)', // Purple
      'rgba(139, 92, 246, 0.35)', // Violet
      'rgba(99, 102, 241, 0.15)',  // Dim Indigo
    ];

    for (let i = 0; i < numParticles; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        radius: Math.random() * 2 + 1.5,
        color: colors[Math.floor(Math.random() * colors.length)],
        pulse: Math.random() * Math.PI,
      });
    }

    const draw = () => {
      ctx.clearRect(0, 0, width, height);

      // Draw grids
      ctx.strokeStyle = 'rgba(99, 102, 241, 0.015)';
      ctx.lineWidth = 1;
      const gridSize = 50;
      for (let x = 0; x < width; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = 0; y < height; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // Draw connections
      ctx.lineWidth = 0.8;
      for (let i = 0; i < numParticles; i++) {
        for (let j = i + 1; j < numParticles; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < 130) {
            const alpha = (1 - dist / 130) * 0.15;
            ctx.strokeStyle = `rgba(99, 102, 241, ${alpha})`;
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.stroke();
          }
        }
      }

      // Update and draw particles
      particles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;
        p.pulse += 0.01;

        if (p.x < 0 || p.x > width) p.vx *= -1;
        if (p.y < 0 || p.y > height) p.vy *= -1;

        const currentRadius = p.radius + Math.sin(p.pulse) * 0.4;
        ctx.beginPath();
        ctx.arc(p.x, p.y, currentRadius, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.fill();

        // White core for more premium glow appearance
        if (p.color.includes('0.45')) {
          ctx.beginPath();
          ctx.arc(p.x, p.y, currentRadius * 0.4, 0, Math.PI * 2);
          ctx.fillStyle = '#ffffff';
          ctx.fill();
        }
      });

      animationFrameId = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none" />;
};

// Simulated security and operational logs
const TerminalLogs: React.FC = () => {
  const [logs, setLogs] = useState<string[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const rawLogs = [
      'SECURITY MANAGER: Ed25519 cryptography layer initialized.',
      'NODE MANAGER: Loading node inventory from SQLite database...',
      'NODE MANAGER: 0 stale pending intents cleaned up.',
      'AUDIT TRAIL: SHA256 integrity chain verified. All blocks OK.',
      'WEBSOCKET MASTER: Listening on interface 0.0.0.0:8000/ws/join',
      'API DEPS: OAuth2 password bearer flow bound to /api/auth/token',
      'LLM CO-PILOT: Direct OpenAI compatible client loaded.',
      'RATE LIMITER: Sliding window memory cache initialized (clean interval 120s)',
      'SYSTEM: Node "ams-edge-01" reported status CONNECTED',
      'SYSTEM: Node "nyc-db-03" latency: 12ms, heartbeat OK',
      'AUDIT: Block appended to chain (action=LOGIN, user=admin, status=SUCCESS)',
      'SYSTEM: Node "sf-app-09" status updated: PENDING -> ENROLLING',
      'WEBSOCKET: challenge sent to "sf-app-09" (Ed25519 challenge size: 64B)',
      'SYSTEM: Node "sf-app-09" challenge solved. Status: CONNECTED',
      'PLUGINS: Metric scanner plugin triggered for fleet.',
      'PLUGINS: Docker manager loaded hooks successfully.',
      'SYSTEM: Node "tokyo-proxy-04" reported 99.4% uptime.',
      'INTEGRITY: Performing 60-second database verification...',
      'INTEGRITY: No database mutations mismatch. State clean.',
    ];

    const now = new Date();
    const seeded = rawLogs.slice(0, 10).map((log, i) => {
      const timeStr = new Date(now.getTime() - (10 - i) * 5000).toLocaleTimeString();
      return `[${timeStr}] ${log}`;
    });
    setLogs(seeded);

    const interval = setInterval(() => {
      setLogs((prev) => {
        const nextLog = rawLogs[Math.floor(Math.random() * rawLogs.length)];
        const timestamp = new Date().toLocaleTimeString();
        const formattedLog = `[${timestamp}] ${nextLog}`;
        
        const newLogs = [...prev, formattedLog];
        if (newLogs.length > 25) {
          newLogs.shift();
        }
        return newLogs;
      });
    }, 3200);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="font-mono text-[10px] text-ink-muted leading-relaxed p-4 bg-black/60 border border-border rounded-lg h-[240px] overflow-hidden flex flex-col justify-end relative shadow-inner">
      <div className="absolute top-2 left-3 flex items-center gap-1.5 text-[9px] text-ink-muted uppercase tracking-wider font-semibold pointer-events-none select-none">
        <Terminal className="w-3 h-3 text-accent-primary animate-pulse" />
        <span>Vigile Secure Kernel Logs</span>
      </div>
      <div ref={containerRef} className="overflow-y-auto max-h-[200px] space-y-1.5 pr-2 scrollbar-thin">
        {logs.map((log, i) => {
          let colorClass = 'text-ink-muted';
          if (log.includes('SECURITY') || log.includes('AUDIT') || log.includes('integrity') || log.includes('INTEGRITY')) {
            colorClass = 'text-accent-primary';
          } else if (log.includes('CONNECTED') || log.includes('OK') || log.includes('SUCCESS')) {
            colorClass = 'text-success';
          } else if (log.includes('challenge') || log.includes('PENDING') || log.includes('ENROLLING')) {
            colorClass = 'text-warning';
          }
          return (
            <div key={i} className={`${colorClass} transition-all duration-300`}>
              {log}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export const Login: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const login = useAuthStore((state) => state.login);
  const { t } = useLocale();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Forced password change flow
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [tempAccessToken, setTempAccessToken] = useState<string | null>(null);

  const from = (location.state as any)?.from?.pathname || '/';

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isLoading) return;

    setIsLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      });

      if (response.status === 401) {
        throw new Error(t('login.error'));
      }
      if (response.status === 403) {
        throw new Error('Compte désactivé');
      }
      if (!response.ok) {
        throw new Error('Erreur de connexion serveur');
      }

      const data = await response.json();
      const { access_token, refresh_token } = data;

      // Test access token by calling /me to check must_change_password
      const meResponse = await fetch('/api/auth/me', {
        headers: {
          'Authorization': `Bearer ${access_token}`,
        },
      });

      if (meResponse.status === 403) {
        const meData = await meResponse.json();
        if (meData.code === 'MUST_CHANGE_PASSWORD' || meData.detail === 'Must change password first') {
          setTempAccessToken(access_token);
          setOldPassword(password);
          setMustChangePassword(true);
          setIsLoading(false);
          return;
        }
      }

      if (!meResponse.ok) {
        throw new Error('Erreur de validation de session');
      }

      const meData = await meResponse.json();
      
      login(access_token, refresh_token, {
        username: meData.username,
        role: meData.role,
        user_id: meData.user_id,
      });

      navigate(from, { replace: true });
    } catch (err: any) {
      setError(err.message);
      setIsLoading(false);
    }
  };

  const handlePasswordChangeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isLoading) return;

    if (newPassword !== confirmPassword) {
      setError('Les mots de passe ne correspondent pas');
      return;
    }

    if (newPassword.length < 8) {
      setError('Le nouveau mot de passe doit faire au moins 8 caractères');
      return;
    }

    setIsLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await fetch('/api/auth/change-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${tempAccessToken}`,
        },
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword,
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Impossible de changer le mot de passe');
      }

      setMustChangePassword(false);
      setTempAccessToken(null);
      setPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setSuccess(t('login.success_password_change'));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-screen bg-[#0a0a0f] flex flex-col lg:flex-row overflow-hidden relative select-none">
      
      {/* LEFT PANEL: CYBER OPS HUD & NETWORK VIZ (Desktop Only) */}
      <div className="hidden lg:flex lg:w-1/2 xl:w-3/5 bg-gradient-to-br from-[#0a0a0f] to-[#12121a] border-r border-border flex-col p-12 justify-between relative overflow-hidden shrink-0">
        <NetworkCanvas />

        {/* Top Header info */}
        <div className="z-10 flex items-center gap-3">
          <div className="w-10 h-10 border border-accent-primary/30 bg-accent-subtle rounded-lg flex flex-col items-center justify-center shadow-[0_0_15px_rgba(99,102,241,0.15)]">
            <ShieldAlert className="w-5 h-5 text-accent-primary animate-pulse" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-ink-primary tracking-tight">Vigile</h2>
            <div className="text-[9px] font-bold text-accent-primary uppercase tracking-widest mt-0.5">
              {t('login.subtitle')}
            </div>
          </div>
        </div>

        {/* Center Graphic / HUD layout */}
        <div className="z-10 max-w-lg my-auto space-y-8 animate-fade-in">
          <div>
            <span className="text-[10px] font-extrabold text-accent-primary uppercase tracking-widest bg-accent-subtle px-2 py-0.5 border border-accent-primary/20 rounded">
              Secured Console Access
            </span>
            <h1 className="text-xl font-bold text-ink-primary tracking-tight mt-3 leading-snug">
              Supervision visuelle et contrôle autonome de flotte.
            </h1>
            <p className="text-xs text-ink-secondary mt-3 leading-relaxed">
              Vigile fournit un contrôle sans faille de vos serveurs par le biais d'un tunnel WebSocket chiffré de bout en bout, avec audit d'intégrité infalsifiable et assistance intelligente intégrée.
            </p>
          </div>

          {/* HUD Metric Badges */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-surface-0 border border-border p-3 rounded-lg flex flex-col gap-1">
              <span className="text-[8px] font-bold text-ink-muted uppercase tracking-wider flex items-center gap-1">
                <Activity className="w-2.5 h-2.5 text-accent-primary" /> Integrity state
              </span>
              <span className="text-xs font-bold text-success">CHAIN SECURED</span>
            </div>
            <div className="bg-surface-0 border border-border p-3 rounded-lg flex flex-col gap-1">
              <span className="text-[8px] font-bold text-ink-muted uppercase tracking-wider flex items-center gap-1">
                <Cpu className="w-2.5 h-2.5 text-accent-primary" /> Cryptography
              </span>
              <span className="text-xs font-bold text-ink-primary">Ed25519-AES</span>
            </div>
            <div className="bg-surface-0 border border-border p-3 rounded-lg flex flex-col gap-1">
              <span className="text-[8px] font-bold text-ink-muted uppercase tracking-wider flex items-center gap-1">
                <Layers className="w-2.5 h-2.5 text-accent-primary" /> Protocol
              </span>
              <span className="text-xs font-bold text-accent-primary">RFC 6455 WS</span>
            </div>
          </div>
        </div>

        {/* Live console logs at the bottom */}
        <div className="z-10">
          <TerminalLogs />
        </div>
      </div>

      {/* RIGHT PANEL: LOGIN FORM CARD */}
      <div className="w-full lg:w-1/2 xl:w-2/5 flex items-center justify-center p-6 sm:p-12 relative overflow-hidden bg-[#0d0d14]">
        <div className="absolute inset-0 block lg:hidden">
          <NetworkCanvas />
        </div>

        {/* Neon blur orb */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[350px] h-[350px] bg-accent-subtle rounded-full filter blur-[90px] opacity-40 pointer-events-none" />

        {/* Login Box */}
        <div className="w-full max-w-sm card p-8 relative animate-fade-up z-10">
          
          <div className="flex flex-col items-center mb-8 text-center lg:mb-10">
            <div className="w-12 h-12 border border-accent-primary/20 bg-accent-subtle rounded-xl flex items-center justify-center mb-3 shadow-[0_0_12px_rgba(99,102,241,0.15)] lg:hidden">
              <ShieldAlert className="w-6 h-6 text-accent-primary animate-pulse" />
            </div>
            <h1 className="text-lg font-bold text-ink-primary tracking-tight">{t('login.title')}</h1>
            <p className="text-[9px] font-bold text-accent-primary uppercase tracking-widest mt-1.5">
              Accès Console Vigile
            </p>
          </div>

          {error && (
            <div className="mb-5 p-3.5 rounded-lg bg-danger-subtle border border-danger text-danger text-xs animate-fade-in font-semibold flex items-start gap-2 shadow-[0_2px_8px_rgba(239,68,68,0.05)]">
              <div className="w-1.5 h-1.5 rounded-full bg-danger mt-1 animate-pulse shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {success && (
            <div className="mb-5 p-3.5 rounded-lg bg-success-subtle border border-success text-success text-xs animate-fade-in font-semibold flex items-start gap-2 shadow-[0_2px_8px_rgba(34,197,94,0.05)]">
              <div className="w-1.5 h-1.5 rounded-full bg-success mt-1 animate-pulse shrink-0" />
              <span>{success}</span>
            </div>
          )}

          {!mustChangePassword ? (
            /* Login Form */
            <form onSubmit={handleLoginSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider" htmlFor="username">
                  {t('login.username')}
                </label>
                <input
                  id="username"
                  type="text"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="admin"
                  className="input"
                  autoFocus
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider" htmlFor="password">
                  {t('login.password')}
                </label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="input pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink-primary transition-colors cursor-pointer"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={isLoading}
                className="btn btn-primary w-full py-2.5 mt-6 flex items-center justify-center gap-2"
              >
                {isLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <>
                    <LogIn className="w-4 h-4" />
                    <span>{t('login.btn')}</span>
                  </>
                )}
              </button>
            </form>
          ) : (
            /* Force Password Change Form */
            <form onSubmit={handlePasswordChangeSubmit} className="space-y-4">
              <div className="mb-4 text-xs text-warning bg-warning-subtle border border-warning/20 p-3.5 rounded-lg font-medium flex items-start gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-warning mt-1.5 animate-pulse shrink-0" />
                <span>Changement de mot de passe obligatoire pour la première connexion.</span>
              </div>

              <div className="space-y-1.5">
                <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider" htmlFor="newPassword">
                  Nouveau mot de passe
                </label>
                <input
                  id="newPassword"
                  type="password"
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Au moins 8 caractères"
                  className="input"
                  autoFocus
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-[10px] font-bold text-ink-muted uppercase tracking-wider" htmlFor="confirmPassword">
                  Confirmer le mot de passe
                </label>
                <input
                  id="confirmPassword"
                  type="password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Ressaisir le mot de passe"
                  className="input"
                />
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  type="button"
                  onClick={() => {
                    setMustChangePassword(false);
                    setTempAccessToken(null);
                    setError(null);
                  }}
                  className="btn btn-secondary flex-1 py-2 text-xs"
                >
                  Annuler
                </button>
                <button
                  type="submit"
                  disabled={isLoading}
                  className="btn btn-primary flex-1 py-2 text-xs flex items-center justify-center gap-2"
                >
                  {isLoading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <>
                      <KeyRound className="w-4 h-4" />
                      <span>Confirmer</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          )}

          <div className="text-center text-[9px] text-ink-muted mt-8 select-none tracking-wider font-mono">
            SYSTEM VERSION: v0.2.0-sprint3
          </div>
        </div>
      </div>
    </div>
  );
};
