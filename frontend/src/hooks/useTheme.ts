import { useEffect } from 'react';
import { useUiStore } from '../store/uiStore';
import { themes, type ThemeKey } from '../design/themes';

export function useTheme() {
  const { theme, setTheme } = useUiStore();

  useEffect(() => {
    const root = document.documentElement;
    const activeTheme = themes[theme];

    // Remove any previously set themes (represented by variables)
    // and apply the new ones.
    Object.entries(activeTheme).forEach(([variable, value]) => {
      root.style.setProperty(variable, value);
    });

    // Save active theme class on body for utility classes matching
    Object.keys(themes).forEach((k) => {
      if (k === theme) {
        root.classList.add(k);
      } else {
        root.classList.remove(k);
      }
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
