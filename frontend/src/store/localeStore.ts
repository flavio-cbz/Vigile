import { create } from 'zustand';

export type Locale = 'fr' | 'en';

interface LocaleState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
}

export const useLocaleStore = create<LocaleState>((set) => ({
  locale: (localStorage.getItem('vigile_locale') as Locale) || 'fr',
  setLocale: (locale) => {
    localStorage.setItem('vigile_locale', locale);
    set({ locale });
  },
}));
