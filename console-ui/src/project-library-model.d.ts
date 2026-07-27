import type { ProjectLibraryItem } from './types';

export function projectLibraryVersionCandidates(
  items: ProjectLibraryItem[],
  selected: ProjectLibraryItem | null,
): ProjectLibraryItem[];

export function projectLibrarySourceLabel(item: ProjectLibraryItem): string;

export function splitProjectLibraryTags(value: string): string[];
