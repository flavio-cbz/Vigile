import { useLocaleStore, type Locale } from '../store/localeStore';
import { fr } from './fr';
import { en } from './en';

const translations: Record<Locale, Record<string, string>> = { fr, en };

export function t(key: string, variables?: Record<string, string | number>): string {
  const locale = useLocaleStore.getState().locale;
  const dict = translations[locale] || translations['fr'];
  let text = dict[key] || key;

  if (variables) {
    Object.entries(variables).forEach(([k, v]) => {
      text = text.replace(new RegExp(`{${k}}`, 'g'), String(v));
    });
  }

  return text;
}

export function useLocale() {
  const { locale, setLocale } = useLocaleStore();

  const translate = (key: string, variables?: Record<string, string | number>) => {
    const dict = translations[locale] || translations['fr'];
    let text = dict[key] || key;
    if (variables) {
      Object.entries(variables).forEach(([k, v]) => {
        text = text.replace(new RegExp(`{${k}}`, 'g'), String(v));
      });
    }
    return text;
  };

  return {
    locale,
    setLocale,
    t: translate
  };
}
export type { Locale };
