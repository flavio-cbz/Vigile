import { useEffect } from 'react';
import { useUiStore } from '../store/uiStore';
import { themes, type ThemeKey } from '../design/themes';

export function useTheme() {
  const { theme, setTheme } = useUiStore();

  useEffect(() => {
    const root = document.documentElement;
    const activeTheme = themes[theme];

    Object.entries(activeTheme).forEach(([variable, value]) => {
      root.style.setProperty(variable, value);
    });

    // Body class enables utility-class matching against the active theme.
    Object.keys(themes).forEach((k) => {
      root.classList.toggle(k, k === theme);
    });
  }, [theme]);

  const availableThemes: ThemeKey[] = Object.keys(themes) as ThemeKey[];

  return {
    theme,
    setTheme,
    availableThemes,
  };
}
export type { ThemeKey };
