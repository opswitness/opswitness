import type { PlanArtifact, PlanArtifactPreview } from './types';

export type ResultSummaryFact = {
  kind: 'customer' | 'data_scope' | 'four_pillars' | 'day_master' | 'engine' | 'subject';
  value: string;
};

export type ResultSummaryConclusion = {
  title: string;
  statement: string;
  source: string;
};

export type ResultSummaryCheck = {
  kind: 'audit' | 'consistency' | 'signoff' | 'evidence';
  state: 'pass' | 'attention';
  detail: string;
};

export type ResultSummary = {
  facts: ResultSummaryFact[];
  conclusions: ResultSummaryConclusion[];
  checks: ResultSummaryCheck[];
  report: PlanArtifact | null;
  hasReadableSummary: boolean;
};

export function selectResultPreviewArtifacts(
  artifacts: PlanArtifact[],
  limit?: number,
): PlanArtifact[];

export function buildResultSummary(
  previews: PlanArtifactPreview[],
  artifacts: PlanArtifact[],
): ResultSummary;
