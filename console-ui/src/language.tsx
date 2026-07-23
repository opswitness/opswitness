import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import {
  DEFAULT_UI_LANGUAGE,
  LEGACY_UI_LANGUAGE_STORAGE_KEY,
  resolveUiLanguage,
  translateUi,
  UI_LANGUAGE_STORAGE_KEY,
} from './i18n.js';
import type { TranslationValues, UiLanguage } from './i18n.js';

type LanguageContextValue = {
  language: UiLanguage;
  setLanguage: (language: UiLanguage) => void;
  t: (source: string, values?: TranslationValues) => string;
};

const LanguageContext = createContext<LanguageContextValue>({
  language: DEFAULT_UI_LANGUAGE,
  setLanguage: () => undefined,
  t: (source, values) => translateUi(DEFAULT_UI_LANGUAGE, source, values),
});

function storedLanguage(): UiLanguage {
  try {
    const canonical = window.localStorage.getItem(UI_LANGUAGE_STORAGE_KEY);
    return resolveUiLanguage(
      canonical ?? window.localStorage.getItem(LEGACY_UI_LANGUAGE_STORAGE_KEY),
    );
  } catch {
    return DEFAULT_UI_LANGUAGE;
  }
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguage] = useState<UiLanguage>(storedLanguage);

  useEffect(() => {
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
    try {
      window.localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, language);
    } catch {
      // Private browsing can reject local storage; the in-memory choice still works.
    }
  }, [language]);

  const value = useMemo<LanguageContextValue>(() => ({
    language,
    setLanguage,
    t: (source, values) => translateUi(language, source, values),
  }), [language]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  return useContext(LanguageContext);
}
