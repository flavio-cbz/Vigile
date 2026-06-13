import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router';
import { useAuthStore } from '../store/authStore';
import { LoginForm } from '../components/auth/LoginForm';
import { ShieldAlert, KeyRound, Loader2, Cpu, Activity, Terminal as TerminalIcon } from 'lucide-react';
import { api } from '../hooks/useApi';

// Dynamic particle canvas visualization matching the visual style
const ParticleCanvas: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let w = (canvas.width = canvas.offsetWidth);
    let h = (canvas.height = canvas.offsetHeight);

    const handleResize = () => {
      if (!canvas) return;
      w = canvas.width = canvas.offsetWidth;
      h = canvas.height = canvas.offsetHeight;
    };
    window.addEventListener('resize', handleResize);

    const particles: Array<{
      x: number;
      y: number;
      vx: number;
      vy: number;
      r: number;
      c: string;
    }> = [];

    const num = 35;
    for (let i = 0; i < num; i++) {
      particles.push({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.35,
        r: Math.random() * 1.5 + 1,
        c: 'rgba(232, 101, 10, 0.25)', // Orange accent color translucent
      });
    }

    const draw = () => {
      ctx.clearRect(0, 0, w, h);

      // Grid outline
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.008)';
      ctx.lineWidth = 0.5;
      const size = 60;
      for (let x = 0; x < w; x += size) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let y = 0; y < h; y += size) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }

      // Draw lines between nodes
      ctx.lineWidth = 0.6;
      for (let i = 0; i < num; i++) {
        for (let j = i + 1; j < num; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < 110) {
            const alpha = (1 - dist / 110) * 0.12;
            ctx.strokeStyle = `rgba(232, 101, 10, ${alpha})`;
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.stroke();
          }
        }
      }

      particles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;

        if (p.x < 0 || p.x > w) p.vx *= -1;
        if (p.y < 0 || p.y > h) p.vy *= -1;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = p.c;
        ctx.fill();
      });

      animId = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animId);
    };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 w-full h-full pointer-events-none" />;
};

// Simulated bootlogs display
const BootLogs: React.FC = () => {
  const [logs, setLogs] = useState<string[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const raw = [
      'SECURE MANAGER: Cryptography layer loaded (Ed25519 standard).',
      'DATABASE: aiosqlite pool initialized.',
      'AUDIT: Append-only hash chain checked. Integrity validated.',
      'WEBSOCKET: join listener configured on port 8000.',
      'NODE MANAGER: Loading active worker inventory...',
      'SYSTEM: 3 nodes loaded. Health checks resolved.',
      'PLUGINS: metric snapshot scanning active (60s tick).',
      'RATE LIMITER: Sliding window setup initialized.',
      'LLM INTEGRITY: Custom OpenAI complete client active.',
      'SYSTEM: challenge response handshake initialized.',
    ];

    const initial = raw.slice(0, 6).map((log, i) => {
      const ts = new Date(Date.now() - (6 - i) * 3000).toLocaleTimeString();
      return `[${ts}] ${log}`;
    });
    setLogs(initial);

    const interval = setInterval(() => {
      setLogs((prev) => {
        const next = raw[Math.floor(Math.random() * raw.length)];
        const ts = new Date().toLocaleTimeString();
        const full = `[${ts}] ${next}`;
        const update = [...prev, full];
        if (update.length > 15) update.shift();
        return update;
      });
    }, 4500);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [logs]);

  return (
    <div className="font-mono text-[11px] text-text-3 leading-relaxed p-4 bg-black/40 border border-border rounded-lg h-44 overflow-hidden flex flex-col justify-end relative shadow-inner">
      <div className="absolute top-2 left-3 flex items-center gap-1.5 text-[8px] text-text-3 uppercase tracking-wider font-semibold pointer-events-none select-none">
        <TerminalIcon className="w-3 h-3 text-accent animate-pulse" />
        <span>Vigile System Kernel logs</span>
      </div>
      <div ref={ref} className="overflow-y-auto max-h-[140px] space-y-1 pr-1 no-scrollbar">
        {logs.map((log, i) => {
          let c = 'text-text-3';
          if (log.includes('SECURE') || log.includes('AUDIT') || log.includes('Integrity')) c = 'text-accent';
          else if (log.includes('validated') || log.includes('initialized') || log.includes('loaded')) c = 'text-severity-ok';
          return <div key={i} className={c}>{log}</div>;
        })}
      </div>
    </div>
  );
};

export const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const loginStore = useAuthStore((state) => state.login);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [originalUsername, setOriginalUsername] = useState<string>('');

  // Forced password update variables
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [tempToken, setTempToken] = useState<string | null>(null);

  const from = (location.state as any)?.from?.pathname || '/';

  const handleLogin = async (username: string, password: string) => {
    setOriginalUsername(username);
    setIsLoading(true);
    setError(null);

    try {
      const data = await api<{ access_token: string; refresh_token: string }>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
        skipToast: true,
      });

      if (!data) {
        throw new Error('Identifiant ou mot de passe invalide.');
      }
      const { access_token, refresh_token } = data;

      // Call /me to inspect password status
      let meData: any = null;
      try {
        meData = await api<any>('/api/auth/me', {
          headers: {
            'Authorization': `Bearer ${access_token}`,
          },
          skipToast: true,
        });
      } catch (err: any) {
        // If meData throws 403, check if it's MUST_CHANGE_PASSWORD
        try {
          const parsed = JSON.parse(err.message);
          if (parsed.code === 'MUST_CHANGE_PASSWORD' || parsed.detail === 'Must change password first') {
            setTempToken(access_token);
            setOldPassword(password);
            setMustChangePassword(true);
            setIsLoading(false);
            return;
          }
        } catch {
          // Fall through
        }
        throw err;
      }

      if (!meData) {
        throw new Error('Erreur de validation de la session.');
      }

      loginStore(access_token, refresh_token, {
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

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isLoading) return;

    if (newPassword !== confirmPassword) {
      setError('Les mots de passe ne correspondent pas.');
      return;
    }

    if (newPassword.length < 8) {
      setError('Le mot de passe doit faire au moins 8 caractères.');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      await api<any>('/api/auth/change-password', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${tempToken}`,
        },
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword,
        }),
        skipToast: true,
      });

      // Re-trigger login with new credentials
      setMustChangePassword(false);
      setTempToken(null);

      // Auto reconnect with original username
      await handleLogin(originalUsername, newPassword);
    } catch (err: any) {
      setError(err.message);
      setIsLoading(false);
    }
  };

  const formatError = (msg: string): string => {
    try {
      const parsed = JSON.parse(msg);
      return typeof parsed?.detail === 'string' ? parsed.detail : msg;
    } catch {
      return msg;
    }
  };

  return (
    <div className="min-h-screen w-screen bg-[#0a0a0f] flex flex-col lg:flex-row overflow-hidden relative">
      {/* Decorative Network visualisation (Left panel) */}
      <div className="hidden lg:flex lg:w-1/2 xl:w-3/5 bg-gradient-to-br from-[#0e0b09] to-[#161210] border-r border-border flex-col p-12 justify-between relative overflow-hidden shrink-0">
        <ParticleCanvas />

        {/* LOGO */}
        <div className="z-10 flex items-center gap-3">
          <div className="w-10 h-10 border border-accent/20 bg-accent/5 rounded-lg flex items-center justify-center shadow-lg">
            <ShieldAlert className="w-5 h-5 text-accent animate-pulse" />
          </div>
          <div>
            <div className="font-serif text-lg font-bold text-text-1 tracking-wide">Vigile</div>
            <div className="text-[8px] font-extrabold text-accent uppercase tracking-widest mt-0.5 font-interface">
              Homelab supervision console
            </div>
          </div>
        </div>

        {/* Hero headline */}
        <div className="z-10 max-w-lg my-auto space-y-8 animate-fade-in">
          <div>
            <span className="text-[9px] font-extrabold text-accent uppercase tracking-widest bg-accent-muted px-2 py-0.5 border border-accent/15 rounded font-interface">
              Accès Opérationnel Sécurisé
            </span>
            <h1 className="font-serif text-3xl font-bold text-text-1 tracking-wide mt-3 leading-snug">
              Supervision visuelle intuitive et copilote IA autonome.
            </h1>
            <p className="text-xs text-text-2 mt-3 leading-relaxed font-sans">
              Vigile repense le monitoring de homelab : les métriques complexes sont résumées en diagnostics humains immédiats, assistées d'une IA capable de corriger les dysfonctionnements sous votre contrôle strict.
            </p>
          </div>

          {/* Core HUD stats */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-surface border border-border p-3 rounded-lg flex flex-col gap-1" title="La chaîne d'audit SHA-256 empêche toute modification non autorisée">
              <span className="text-[8px] font-extrabold text-text-3 uppercase tracking-wider flex items-center gap-1 font-interface">
                <Activity className="w-2.5 h-2.5 text-accent" /> Chaîne d'Audit
              </span>
              <span className="text-xs font-bold text-severity-ok font-interface" title="Toutes les données sont infalsifiables et horodatées">INFALSIFIABLE</span>
            </div>
            <div className="bg-surface border border-border p-3 rounded-lg flex flex-col gap-1" title="Chiffrement de clés Ed25519 + AES pour une sécurité maximale">
              <span className="text-[8px] font-extrabold text-text-3 uppercase tracking-wider flex items-center gap-1 font-interface">
                <Cpu className="w-2.5 h-2.5 text-accent" /> Chiffrement
              </span>
              <span className="text-xs font-bold text-text-1 font-interface font-mono" title="Chiffrement asymmetric Ed25519 avec AES-256-GCM">Ed25519-AES</span>
            </div>
            <div className="bg-surface border border-border p-3 rounded-lg flex flex-col gap-1" title="WebSocket natif sans bibliothèque tierce, conforme à la RFC 6455">
              <span className="text-[8px] font-extrabold text-text-3 uppercase tracking-wider flex items-center gap-1 font-interface">
                <TerminalIcon className="w-2.5 h-2.5 text-accent" /> WebSocket
              </span>
              <span className="text-xs font-bold text-accent font-interface" title="WebSocket natif sans bibliothèque tierce (RFC 6455)">RFC 6455 PURE</span>
            </div>
          </div>
        </div>

        {/* Live system boot logs */}
        <div className="z-10">
          <BootLogs />
        </div>
      </div>

      {/* Right panel: Forms card */}
      <div className="w-full lg:w-1/2 xl:w-2/5 flex items-center justify-center p-6 sm:p-12 bg-[#0a0a0f] relative overflow-hidden shrink-0">
        <div className="absolute inset-0 block lg:hidden">
          <ParticleCanvas />
        </div>

        {/* Background glow shadow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80 h-80 bg-accent-muted rounded-full filter blur-[100px] opacity-40 pointer-events-none" />

        {/* Form container */}
        <div className="w-full max-w-sm border border-border rounded-xl bg-surface p-8 relative animate-fade-in z-10 shadow-2xl">
          <div className="flex flex-col items-center mb-8 text-center">
            <div className="w-12 h-12 border border-accent/20 bg-accent-muted rounded-xl flex items-center justify-center mb-3 shadow lg:hidden">
              <ShieldAlert className="w-6 h-6 text-accent animate-pulse" />
            </div>
            <h2 className="font-serif text-xl font-bold text-text-1 tracking-wide">
              {mustChangePassword ? 'Nouveau mot de passe' : 'Connexion'}
            </h2>
            <p className="text-[9px] font-extrabold text-accent uppercase tracking-widest mt-1.5 font-interface">
              Console Vigile
            </p>
          </div>

          {error && (
            <div className="mb-5 p-3.5 rounded-lg bg-severity-critical/10 border border-severity-critical/20 text-severity-critical text-xs animate-fade-in font-semibold flex items-start gap-2">
              <div className="w-1.5 h-1.5 rounded-full bg-severity-critical mt-1 animate-pulse shrink-0" />
              <span>{formatError(error)}</span>
            </div>
          )}

          {!mustChangePassword ? (
            <LoginForm onSubmit={handleLogin} loading={isLoading} onDemoLogin={() => handleLogin('guest', 'guest')} />
          ) : (
            <form onSubmit={handlePasswordChange} className="space-y-4 font-sans text-xs">
              <div className="mb-4 text-xs text-severity-warning bg-severity-warning/10 border border-severity-warning/20 p-3.5 rounded-lg font-medium flex items-start gap-2 leading-relaxed">
                <div className="w-1.5 h-1.5 rounded-full bg-severity-warning mt-1.5 animate-pulse shrink-0" />
                <span>Pour des raisons de sécurité, vous devez changer votre mot de passe administrateur lors de votre première connexion.</span>
              </div>

              <div className="space-y-1.5">
                <label className="block text-[10px] font-extrabold text-text-2 uppercase tracking-wider font-interface" htmlFor="newPassword">
                  Nouveau mot de passe
                </label>
                <input
                  id="newPassword"
                  type="password"
                  required
                  disabled={isLoading}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Min. 8 caractères"
                  className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded px-3.5 py-2.5 text-text-1 focus:outline-none placeholder:text-text-3 font-normal"
                  autoFocus
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-[10px] font-extrabold text-text-2 uppercase tracking-wider font-interface" htmlFor="confirmPassword">
                  Confirmer le mot de passe
                </label>
                <input
                  id="confirmPassword"
                  type="password"
                  required
                  disabled={isLoading}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Saisissez à nouveau"
                  className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded px-3.5 py-2.5 text-text-1 focus:outline-none placeholder:text-text-3 font-normal"
                />
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  type="button"
                  onClick={() => {
                    setMustChangePassword(false);
                    setTempToken(null);
                    setError(null);
                  }}
                  className="flex-1 border border-border hover:border-border-strong px-4 py-2 text-[10px] font-bold font-interface uppercase tracking-wider rounded cursor-pointer transition-colors"
                >
                  Retour
                </button>
                <button
                  type="submit"
                  disabled={isLoading || !newPassword.trim() || !confirmPassword.trim()}
                  className="flex-1 bg-accent hover:bg-accent-hover text-text-1 px-4 py-2 text-[10px] font-bold font-interface uppercase tracking-wider rounded flex items-center justify-center gap-1.5 cursor-pointer shadow-lg shadow-accent/15 transition-all"
                >
                  {isLoading ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <>
                      <KeyRound className="w-3.5 h-3.5" />
                      <span>Valider</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          )}

          <div className="text-center text-[8px] text-text-3 mt-8 select-none tracking-widest font-mono">
            VIGILE KERNEL CONSOLE: v0.2.0-sprint3
          </div>
        </div>
      </div>
    </div>
  );
};
