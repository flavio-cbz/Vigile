import React, { useState } from 'react';
import { Eye, EyeOff, LogIn, Loader2, Sparkles } from 'lucide-react';

interface LoginFormProps {
  onSubmit: (username: string, password: string) => Promise<void>;
  loading?: boolean;
  onDemoLogin?: () => void;
}

export const LoginForm: React.FC<LoginFormProps> = ({ onSubmit, loading = false, onDemoLogin }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim() || loading) return;
    onSubmit(username.trim(), password.trim());
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 font-sans text-xs">
      <div className="space-y-1.5">
        <label className="block text-[10px] font-extrabold text-text-2 uppercase tracking-wider font-interface mb-1" htmlFor="username">
          Identifiant
        </label>
        <input
          id="username"
          type="text"
          required
          disabled={loading}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="ex: demo"
          className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded px-3.5 py-2.5 text-text-1 focus:outline-none placeholder:text-text-2 font-normal disabled:opacity-50 transition-colors"
          autoFocus
        />
      </div>

      <div className="space-y-1.5">
        <label className="block text-[10px] font-extrabold text-text-2 uppercase tracking-wider font-interface mb-1" htmlFor="password">
          Mot de passe
        </label>
        <div className="relative">
          <input
            id="password"
            type={showPassword ? 'text' : 'password'}
            required
            disabled={loading}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            className="w-full bg-surface-2 border border-border focus:border-accent/40 rounded px-3.5 py-2.5 pr-10 text-text-1 focus:outline-none placeholder:text-text-2 font-normal disabled:opacity-50 transition-colors"
          />
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            aria-label={showPassword ? 'Masquer le mot de passe' : 'Afficher le mot de passe'}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-text-3 hover:text-text-1 transition-colors cursor-pointer"
          >
            {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
      </div>

      <button
        type="submit"
        title="Appuyez sur Entrée pour valider"
        disabled={loading || !username.trim() || !password.trim()}
        className="w-full bg-accent hover:bg-accent-hover text-text-1 py-2.5 rounded font-interface font-bold tracking-wider uppercase flex items-center justify-center gap-2 cursor-pointer shadow-lg shadow-accent/15 disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-150 mt-6"
      >
        {loading ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <>
            <LogIn className="w-4 h-4" />
            <span>Se connecter</span>
          </>
        )}
      </button>

      {!loading && (
        <p className="text-[8px] text-text-3 text-center tracking-wider mt-1">
          Entrée pour valider
        </p>
      )}

      {onDemoLogin && (
        <div className="pt-2 space-y-1">
          <button
            type="button"
            onClick={onDemoLogin}
            disabled={loading}
            className="w-full border border-accent/20 hover:border-accent/50 text-accent py-2 rounded font-interface font-bold tracking-wider text-[9px] uppercase flex items-center justify-center gap-1.5 cursor-pointer transition-all duration-150 bg-transparent hover:bg-accent/5 disabled:opacity-40"
          >
            <Sparkles className="w-3 h-3" />
            <span>Mode démo</span>
          </button>
          <p className="text-[8px] text-text-3 text-center tracking-wider">
            Mode démo · Données simulées en mémoire
          </p>
        </div>
      )}
    </form>
  );
};
