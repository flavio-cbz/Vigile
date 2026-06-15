import { useLocaleStore, type Locale } from '../store/localeStore';
import { fr } from './fr';
import { en } from './en';

const translations: Record<Locale, Record<string, string>> = { fr, en };

function translateWith(locale: Locale, key: string, variables?: Record<string, string | number>): string {
  const dict = translations[locale] || translations.fr;
  let text = dict[key] || key;
  if (variables) {
    Object.entries(variables).forEach(([k, v]) => {
      text = text.replaceAll(`{${k}}`, String(v));
    });
  }
  return text;
}

export function t(key: string, variables?: Record<string, string | number>): string {
  return translateWith(useLocaleStore.getState().locale, key, variables);
}

export function useLocale() {
  const { locale, setLocale } = useLocaleStore();
  return {
    locale,
    setLocale,
    t: (key: string, variables?: Record<string, string | number>) => translateWith(locale, key, variables),
  };
}
export type { Locale };
