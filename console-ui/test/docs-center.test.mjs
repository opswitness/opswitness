import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const docsSource = readFileSync(
  new URL('../src/docs-center.tsx', import.meta.url),
  'utf8',
);
const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const onboardingSource = readFileSync(
  new URL('../src/onboarding.tsx', import.meta.url),
  'utf8',
);
const styleSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');
const indexSource = readFileSync(
  new URL('../../docs/INDEX.md', import.meta.url),
  'utf8',
);
const namingSource = readFileSync(
  new URL('../../docs/NAMING.md', import.meta.url),
  'utf8',
);

test('Docs Center ships all six practical topics in both languages', () => {
  for (const topic of [
    'first-use',
    'run-work',
    'approvals',
    'project-library',
    'evidence',
    'recovery',
  ]) {
    const quoted = [...docsSource.matchAll(new RegExp(`'${topic}'`, 'g'))].length;
    const bare = [...docsSource.matchAll(new RegExp(`\\b${topic}(?=:)`, 'g'))].length;
    assert.equal(quoted + bare >= 3, true, `${topic} should have an id, icon, and bilingual content`);
  }
  assert.match(docsSource, /Available offline/);
  assert.match(docsSource, /可离线使用/);
  assert.doesNotMatch(docsSource, /\bfetch\s*\(/);
  assert.match(docsSource, /It does not attach a library file to a new Work/);
  assert.match(docsSource, /尚不能把资料库文件直接加入新 Work/);
  assert.doesNotMatch(docsSource, /Selecting a library file for a new Work makes it a proposed input/);
});

test('Docs Center is a first-class local navigation view', () => {
  assert.match(appSource, /import \{ DocsCenter \} from '\.\/docs-center'/);
  assert.match(appSource, /view === 'docs' && <DocsCenter \/>/);
  assert.match(appSource, /id: 'docs' as const, label: '帮助文档'/);
  assert.match(
    styleSource,
    /@media \(max-width: 760px\)[\s\S]*?grid-template-columns: repeat\(5, 1fr\)/,
  );
});

test('onboarding opens first-use and recovery help without leaving the flow', () => {
  assert.match(docsSource, /const ONBOARDING_HELP_TOPICS: TopicId\[\] = \['first-use', 'recovery'\]/);
  assert.match(docsSource, /export function OnboardingHelp/);
  assert.match(onboardingSource, /import \{ OnboardingHelp \} from '\.\/docs-center'/);
  assert.match(onboardingSource, /const \[helpOpen, setHelpOpen\] = useState\(false\)/);
  assert.match(onboardingSource, /onClick=\{\(\) => setHelpOpen\(true\)\}/);
  assert.match(onboardingSource, /\{helpOpen && <OnboardingHelp onClose=\{\(\) => setHelpOpen\(false\)\} \/>\}/);
  assert.match(styleSource, /\.onboarding-help-layer[\s\S]*position: fixed/);
});

test('official naming is consistent and the legacy alias is compatibility-only', () => {
  assert.match(docsSource, /productValue: 'OpsWitness'/);
  assert.match(docsSource, /commandValue: 'opswitness'/);
  assert.match(docsSource, /qd — legacy compatibility only/);
  assert.match(docsSource, /qd — 仅用于旧版兼容/);
  assert.match(appSource, />OpsWitness · v\{APP_VERSION\}</);
  assert.match(onboardingSource, />OpsWitness · v\{APP_VERSION\}</);
  assert.doesNotMatch(appSource, />OPSWITNESS · v/);
  assert.doesNotMatch(onboardingSource, />OPSWITNESS · v/);
  assert.match(namingSource, /\*\*OpsWitness\*\*/);
  assert.match(namingSource, /primary CLI \| `opswitness`/);
  assert.match(namingSource, /Legacy CLI alias \| `qd`/);
});

test('documentation index points to the offline topics and naming contract', () => {
  assert.match(indexSource, /\[Naming standard\]\(NAMING\.md\)/);
  assert.match(indexSource, /six practical operator topics/);
  assert.match(indexSource, /Project Library/);
  assert.match(indexSource, /Evidence and sign-off/);
  assert.match(namingSource, /does not rewrite historical ledger events/);
  assert.match(namingSource, /new mutation requests/);
  assert.match(namingSource, /human writing conventions/);
  assert.match(namingSource, /not API-enforced semantic checks/);
});
