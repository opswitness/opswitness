const PREVIEW_LIMIT = 8;
const CONCLUSION_LIMIT = 12;

function objectValue(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value : null;
}

function textValue(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : '';
}

function numberValue(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function previewPriority(artifact) {
  const name = artifact.name.toLocaleLowerCase();
  if (/interpretation|conclusion|finding|insight|summary|result/.test(name)) return 100;
  if (/chart|profile|facts|data/.test(name)) return 80;
  if (/audit|evaluation|eval|verification/.test(name)) return 70;
  if (/manifest|signoff/.test(name)) return 40;
  if (/knowledge|source|citation/.test(name)) return 20;
  return 50;
}

export function selectResultPreviewArtifacts(artifacts, limit = PREVIEW_LIMIT) {
  return artifacts
    .filter((artifact) => artifact.available && artifact.preview_supported)
    .sort((left, right) => (
      previewPriority(right) - previewPriority(left)
      || Number(right.evidence_status === 'registered') - Number(left.evidence_status === 'registered')
      || left.name.localeCompare(right.name)
    ))
    .slice(0, limit);
}

function addUniqueFact(facts, kind, value) {
  const normalized = textValue(value);
  if (!normalized || facts.some((fact) => fact.kind === kind || fact.value === normalized)) return;
  facts.push({ kind, value: normalized });
}

function fourPillarsValue(root) {
  const pillars = objectValue(root.four_pillars);
  if (!pillars) return '';
  return ['year', 'month', 'day', 'time']
    .map((key) => textValue(objectValue(pillars[key])?.ganzhi))
    .filter(Boolean)
    .join(' · ');
}

function engineValue(root) {
  const engine = objectValue(root.engine);
  if (!engine) return textValue(root.engine);
  const library = textValue(engine.library) || textValue(engine.name);
  const version = textValue(engine.version);
  return [library, version].filter(Boolean).join(' ');
}

function conclusionRows(root) {
  const rows = [];
  const collectionKeys = [
    'interpretations',
    'conclusions',
    'findings',
    'highlights',
    'recommendations',
    'insights',
    'results',
  ];
  for (const key of collectionKeys) {
    const collection = root[key];
    if (!Array.isArray(collection)) continue;
    for (const value of collection) {
      if (typeof value === 'string') {
        rows.push({ title: '', statement: textValue(value) });
        continue;
      }
      const row = objectValue(value);
      if (!row) continue;
      const title = [row.title, row.name, row.label, row.id]
        .map(textValue)
        .find(Boolean) || '';
      const statement = [
        row.statement,
        row.summary,
        row.description,
        row.conclusion,
        row.result,
        row.text,
      ].map(textValue).find(Boolean) || '';
      if (title || statement) rows.push({ title, statement });
    }
  }
  return rows;
}

function isPassingVerdict(value) {
  return ['pass', 'passed', 'approved', 'ok', 'success', 'succeeded', 'verified']
    .includes(textValue(value).toLocaleLowerCase());
}

function auditCheck(preview) {
  const root = objectValue(preview.content);
  if (!root) return null;
  const summary = objectValue(root.summary);
  const auditLike = /audit|evaluation|eval|verification/.test(preview.name.toLocaleLowerCase())
    || /audit|evaluation|eval|verification/.test(textValue(root.artifact_type).toLocaleLowerCase());
  if (!auditLike) return null;
  const verdict = textValue(root.verdict)
    || textValue(root.status)
    || textValue(summary?.overall_verdict);
  const total = numberValue(summary?.total_interpretations)
    ?? numberValue(summary?.total)
    ?? numberValue(root.total);
  const traceable = numberValue(summary?.traceable)
    ?? numberValue(summary?.passed)
    ?? numberValue(root.traceable);
  const passed = root.passed === true || isPassingVerdict(verdict);
  const detail = total !== null && traceable !== null
    ? `${traceable}/${total}`
    : verdict;
  return { kind: 'audit', state: passed ? 'pass' : 'attention', detail };
}

function consistencyCheck(preview) {
  const root = objectValue(preview.content);
  const consistency = objectValue(root?.consistency_check);
  if (!consistency) return null;
  const mismatches = Array.isArray(consistency.mismatches) ? consistency.mismatches.length : null;
  const passed = consistency.passed === true;
  return {
    kind: 'consistency',
    state: passed ? 'pass' : 'attention',
    detail: mismatches === null ? '' : String(mismatches),
  };
}

export function buildResultSummary(previews, artifacts) {
  const facts = [];
  const conclusions = [];
  const checks = [];
  const seenConclusions = new Set();

  for (const preview of previews) {
    const root = objectValue(preview.content);
    if (!root) continue;
    addUniqueFact(facts, 'customer', root.customer_id);
    if (root.synthetic === true) addUniqueFact(facts, 'data_scope', 'synthetic');
    addUniqueFact(facts, 'four_pillars', fourPillarsValue(root));
    addUniqueFact(facts, 'day_master', root.day_master_gan || root.day_master);
    addUniqueFact(facts, 'engine', engineValue(root));
    addUniqueFact(facts, 'subject', root.subject || root.title);

    for (const row of conclusionRows(root)) {
      if (conclusions.length >= CONCLUSION_LIMIT) break;
      const dedupeKey = `${row.title}\n${row.statement}`;
      if (!row.statement || seenConclusions.has(dedupeKey)) continue;
      seenConclusions.add(dedupeKey);
      conclusions.push({ ...row, source: preview.name });
    }

    const consistency = consistencyCheck(preview);
    if (consistency && !checks.some((check) => check.kind === consistency.kind)) {
      checks.push(consistency);
    }
    const audit = auditCheck(preview);
    if (audit && !checks.some((check) => check.kind === audit.kind)) checks.push(audit);
  }

  const report = artifacts.find((artifact) => (
    artifact.evidence_status === 'registered'
    && (artifact.mime === 'application/pdf' || artifact.name.toLocaleLowerCase().endsWith('.pdf'))
  )) || artifacts.find((artifact) => (
    artifact.mime === 'application/pdf' || artifact.name.toLocaleLowerCase().endsWith('.pdf')
  )) || null;
  const signedArtifact = artifacts.find((artifact) => (
    artifact.evidence_status === 'registered'
    && /sign[-_ ]?off|signoff/.test(artifact.name.toLocaleLowerCase())
    && /signed|approved/.test(artifact.name.toLocaleLowerCase())
  ));
  const signoffArtifact = signedArtifact || artifacts.find((artifact) => (
    /sign[-_ ]?off|signoff/.test(artifact.name.toLocaleLowerCase())
  ));
  if (signoffArtifact) {
    checks.push({
      kind: 'signoff',
      state: signedArtifact ? 'pass' : 'attention',
      detail: signoffArtifact.name,
    });
  }

  if (artifacts.length) {
    const registered = artifacts.filter((artifact) => artifact.evidence_status === 'registered').length;
    checks.push({
      kind: 'evidence',
      state: registered === artifacts.length ? 'pass' : 'attention',
      detail: `${registered}/${artifacts.length}`,
    });
  }

  return {
    facts: facts.slice(0, 6),
    conclusions,
    checks,
    report,
    hasReadableSummary: facts.length > 0 || conclusions.length > 0,
  };
}
