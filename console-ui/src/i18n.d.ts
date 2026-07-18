export type UiLanguage = 'en' | 'zh';
export type TranslationValues = Record<string, string | number>;

export const UI_LANGUAGE_STORAGE_KEY: 'opswitness.ui-language';
export const LEGACY_UI_LANGUAGE_STORAGE_KEY: 'quarterdeck.ui-language';
export const DEFAULT_UI_LANGUAGE: 'en';

export function resolveUiLanguage(value: unknown): UiLanguage;
export function translateUi(
  language: UiLanguage,
  source: string,
  values?: TranslationValues,
): string;
export function translateApiError(
  language: UiLanguage,
  code: string | undefined,
  fallback: string,
): string;
