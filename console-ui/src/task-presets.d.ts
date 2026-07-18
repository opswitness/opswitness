import type { UiLanguage } from './i18n.js';

export type TaskPresetCategoryId = 'operate' | 'decide' | 'grow' | 'serve' | 'specialist';

export type LocalizedText = Record<UiLanguage, string>;

export interface TaskPresetCategory {
  id: TaskPresetCategoryId;
  label: LocalizedText;
}

export interface TaskPreset {
  id: string;
  category: TaskPresetCategoryId;
  title: LocalizedText;
  description: LocalizedText;
  objective: LocalizedText;
}

export interface LocalizedTaskPreset extends Omit<TaskPreset, 'title' | 'description' | 'objective'> {
  title: string;
  description: string;
  objective: string;
}

export const TASK_PRESET_CATEGORIES: TaskPresetCategory[];
export const TASK_PRESETS: TaskPreset[];
export function localizedTaskPreset(preset: TaskPreset, language: UiLanguage): LocalizedTaskPreset;
export function filterTaskPresets(
  language: UiLanguage,
  category?: 'all' | TaskPresetCategoryId,
  query?: string,
): TaskPreset[];
