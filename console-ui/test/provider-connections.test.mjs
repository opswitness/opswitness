import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8');
const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');

test('connections expose DeepSeek API and both supported Grok paths', () => {
  assert.match(appSource, /data\.providers\.deepseek/);
  assert.match(appSource, /data\.providers\.xai/);
  assert.match(appSource, /startConnection\('deepseek', 'api_key', apiKey\)/);
  assert.match(appSource, /startConnection\('xai', 'api_key', apiKey\)/);
  assert.match(appSource, /startConnection\('xai', 'account'\)/);
  assert.match(apiSource, /'openai' \| 'anthropic' \| 'deepseek' \| 'xai'/);
});

test('persistent provider keys require Keychain consent and never mention AionUi storage', () => {
  assert.match(appSource, /const persistent = provider !== 'openai'/);
  assert.match(appSource, /不会写入 AionUi、配置、日志或账本/);
  assert.match(appSource, /Grok 订阅与 xAI API 用量分别计费/);
  assert.match(appSource, /method === 'api_key'/);
});

test('credential connection is rendered separately from task runtime readiness', () => {
  assert.match(appSource, /provider\.runtime_ready/);
  assert.match(appSource, /provider\.authenticated \? '已连接'/);
  assert.match(appSource, /安装官方 Grok Build 后可连接账户/);
});

test('connections expose confirmed fixed-loopback Ollama and LM Studio flows', () => {
  assert.match(appSource, /data\.providers\.ollama/);
  assert.match(appSource, /data\.providers\.lmstudio/);
  assert.match(appSource, /startConnection\(provider, 'local'\)/);
  assert.match(appSource, /http:\/\/127\.0\.0\.1:11434\/v1/);
  assert.match(appSource, /http:\/\/127\.0\.0\.1:1234\/v1/);
  assert.match(appSource, /我确认启动本地模型服务/);
  assert.match(apiSource, /method === 'api_key' \|\| method === 'local'/);
});

test('local model dialog has no arbitrary endpoint or API key input', () => {
  const localDialog = appSource.slice(
    appSource.indexOf('function LocalProviderDialog'),
    appSource.indexOf('function ProviderApiKeyDialog'),
  );
  assert.doesNotMatch(localDialog, /type="password"/);
  assert.doesNotMatch(localDialog, /placeholder=.*https/);
  assert.match(localDialog, /Quarterdeck 不接受自定义远程 URL/);
});
