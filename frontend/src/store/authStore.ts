import { create } from 'zustand';

interface User {
  username: string;
  role: string;
  user_id: string;
}

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
  isAuthenticated: boolean;
  login: (accessToken: string, refreshToken: string, user: User) => void;
  logout: () => void;
  setAccessToken: (token: string | null) => void;
}

// Helper to get initial state from localStorage
const getStoredAuth = () => {
  try {
    const accessToken = localStorage.getItem('vigile_access_token');
    const refreshToken = localStorage.getItem('vigile_refresh_token');
    const userStr = localStorage.getItem('vigile_user');
    const user = userStr ? JSON.parse(userStr) : null;
    return {
      accessToken,
      refreshToken,
      user,
      isAuthenticated: !!accessToken,
    };
  } catch (e) {
    console.error('Failed to parse stored auth', e);
    return {
      accessToken: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
    };
  }
};

export const useAuthStore = create<AuthState>((set) => ({
  ...getStoredAuth(),
  login: (accessToken, refreshToken, user) => {
    localStorage.setItem('vigile_access_token', accessToken);
    localStorage.setItem('vigile_refresh_token', refreshToken);
    localStorage.setItem('vigile_user', JSON.stringify(user));
    set({ accessToken, refreshToken, user, isAuthenticated: true });
  },
  logout: () => {
    localStorage.removeItem('vigile_access_token');
    localStorage.removeItem('vigile_refresh_token');
    localStorage.removeItem('vigile_user');
    set({ accessToken: null, refreshToken: null, user: null, isAuthenticated: false });
  },
  setAccessToken: (accessToken) => {
    if (accessToken) {
      localStorage.setItem('vigile_access_token', accessToken);
    } else {
      localStorage.removeItem('vigile_access_token');
    }
    set({ accessToken, isAuthenticated: !!accessToken });
  },
}));
