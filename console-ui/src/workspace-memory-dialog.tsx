import {
  Ban,
  BookOpen,
  BrainCircuit,
  Check,
  FilePlus2,
  GitBranch,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLanguage } from './language';
import type {
  RepeatableWork,
  WorkspaceMemoryStatus,
  WorkspaceMemoryView,
} from './types';

type CandidateBody = {
  kind: 'process' | 'knowledge';
  title: string;
  content: string;
  tags: string[];
  workspace?: string;
  source_plan_id?: string | null;
  supersedes_version_id?: string | null;
};

function memoryStateLabel(row: WorkspaceMemoryView): string {
  if (row.state === 'approved' && row.active) return '已批准';
  if (row.state === 'candidate') return '待审核';
  if (row.state === 'superseded') return '已被新版替代';
  if (row.state === 'dismissed') return '已忽略';
  return '已撤销';
}

function formatDate(value: string, language: 'en' | 'zh'): string {
  try {
    return new Intl.DateTimeFormat(language === 'zh' ? 'zh-CN' : 'en-US', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export function WorkspaceMemoryDialog({
  status,
  repeatableWorks,
  onClose,
  onLoad,
  onCreate,
  onProposeProcess,
  onApprove,
  onDismiss,
  onRevoke,
  onRollback,
}: {
  status: WorkspaceMemoryStatus;
  repeatableWorks: RepeatableWork[];
  onClose: () => void;
  onLoad: (query?: string, includeHistory?: boolean) => Promise<WorkspaceMemoryView[]>;
  onCreate: (body: CandidateBody) => Promise<WorkspaceMemoryView>;
  onProposeProcess: (work: RepeatableWork) => Promise<WorkspaceMemoryView>;
  onApprove: (
    versionId: string,
    expectedContentSha256: string,
    expectedFingerprint: string | null,
    reason?: string,
  ) => Promise<WorkspaceMemoryView>;
  onDismiss: (
    versionId: string,
    expectedContentSha256: string,
    expectedFingerprint: string | null,
    reason?: string,
  ) => Promise<WorkspaceMemoryView>;
  onRevoke: (versionId: string, reason?: string) => Promise<WorkspaceMemoryView>;
  onRollback: (versionId: string, reason: string) => Promise<WorkspaceMemoryView>;
}) {
  const { language, t } = useLanguage();
  const [rows, setRows] = useState<WorkspaceMemoryView[]>([]);
  const [query, setQuery] = useState('');
  const [includeHistory, setIncludeHistory] = useState(true);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [editorOpen, setEditorOpen] = useState(false);
  const [kind, setKind] = useState<'process' | 'knowledge'>('process');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [tags, setTags] = useState('');
  const [workspace, setWorkspace] = useState('');
  const [supersedesVersionId, setSupersedesVersionId] = useState<string | null>(null);
  const [sourcePlanId, setSourcePlanId] = useState<string | null>(null);
  const [selectedWorkId, setSelectedWorkId] = useState(repeatableWorks[0]?.work_id || '');
  const [decisionReason, setDecisionReason] = useState('');

  const refresh = useCallback(async (nextQuery = query, nextHistory = includeHistory) => {
    setLoading(true);
    setError('');
    try {
      setRows(await onLoad(nextQuery, nextHistory));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('Workspace 记忆读取失败'));
    } finally {
      setLoading(false);
    }
  }, [includeHistory, onLoad, query, t]);

  useEffect(() => {
    void refresh('', true);
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]); // eslint-disable-line react-hooks/exhaustive-deps

  const activeRows = useMemo(
    () => rows.filter((row) => row.state === 'approved' && row.active),
    [rows],
  );

  const resetEditor = () => {
    setEditorOpen(false);
    setKind('process');
    setTitle('');
    setContent('');
    setTags('');
    setWorkspace('');
    setSupersedesVersionId(null);
    setSourcePlanId(null);
  };

  const editVersion = (row: WorkspaceMemoryView) => {
    setKind(row.kind);
    setTitle(row.title);
    setContent(row.content);
    setTags(row.tags.join(', '));
    setWorkspace(row.workspace);
    setSupersedesVersionId(row.version_id);
    setSourcePlanId(row.source_plan_id || null);
    setEditorOpen(true);
  };

  const createCandidate = async () => {
    if (!title.trim() || content.trim().length < 3 || busy) return;
    setBusy('create');
    setError('');
    try {
      await onCreate({
        kind,
        title: title.trim(),
        content: content.trim(),
        tags: tags.split(',').map((tag) => tag.trim()).filter(Boolean),
        workspace: workspace.trim(),
        source_plan_id: sourcePlanId,
        supersedes_version_id: supersedesVersionId,
      });
      resetEditor();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('记忆候选保存失败'));
    } finally {
      setBusy('');
    }
  };

  const proposeFromWork = async () => {
    const work = repeatableWorks.find((row) => row.work_id === selectedWorkId);
    if (!work || busy) return;
    setBusy(`propose:${work.work_id}`);
    setError('');
    try {
      await onProposeProcess(work);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('流程记忆候选生成失败'));
    } finally {
      setBusy('');
    }
  };

  const decide = async (
    row: WorkspaceMemoryView,
    action: 'approve' | 'dismiss' | 'revoke' | 'rollback',
  ) => {
    if (busy) return;
    if (action === 'rollback' && decisionReason.trim().length < 3) {
      setError(t('回滚前请填写原因，保留审计记录。'));
      return;
    }
    setBusy(`${action}:${row.version_id}`);
    setError('');
    try {
      if (action === 'approve') {
        await onApprove(
          row.version_id,
          row.content_sha256,
          row.fingerprint || null,
          decisionReason.trim(),
        );
      }
      if (action === 'dismiss') {
        await onDismiss(
          row.version_id,
          row.content_sha256,
          row.fingerprint || null,
          decisionReason.trim(),
        );
      }
      if (action === 'revoke') await onRevoke(row.version_id, decisionReason.trim());
      if (action === 'rollback') await onRollback(row.version_id, decisionReason.trim());
      setDecisionReason('');
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t('记忆状态更新失败'));
    } finally {
      setBusy('');
    }
  };

  return (
    <div className="modal-layer" role="dialog" aria-modal="true" aria-label={t('Workspace 记忆')}>
      <button className="modal-backdrop" type="button" aria-label={t('关闭 Workspace 记忆')} onClick={onClose} />
      <section className="mail-setup-dialog workspace-memory-dialog">
        <header className="modal-header">
          <div>
            <span className="section-kicker">{t('可审计长期记忆')}</span>
            <h2>{t('Workspace 记忆')}</h2>
          </div>
          <button className="icon-button" type="button" title={t('关闭')} aria-label={t('关闭 Workspace 记忆')} onClick={onClose}>
            <X size={19} />
          </button>
        </header>

        <div className="workspace-memory-content">
          <div className="workspace-memory-summary">
            <BrainCircuit size={20} />
            <div><strong>{t('{count} 条已批准记忆', { count: activeRows.length || status.approved_count })}</strong><span>{t('新 Work 只读取已批准快照；Agent 只能提出候选。')}</span></div>
            <code>{status.vault_path}</code>
          </div>

          {repeatableWorks.length > 0 && (
            <div className="memory-proposal-row">
              <div>
                <strong>{t('从已完成 Work 提取流程记忆')}</strong>
                <span>{t('系统生成待审核候选，不会直接改变后续 Work。')}</span>
              </div>
              <select value={selectedWorkId} onChange={(event) => setSelectedWorkId(event.target.value)}>
                {repeatableWorks.map((work) => <option key={work.work_id} value={work.work_id}>{work.title}</option>)}
              </select>
              <button className="secondary-button" type="button" disabled={!selectedWorkId || Boolean(busy)} onClick={() => void proposeFromWork()}>
                {busy.startsWith('propose:') ? <LoaderCircle size={15} className="spin" /> : <FilePlus2 size={15} />}
                {t('生成候选')}
              </button>
            </div>
          )}

          <div className="workspace-memory-toolbar">
            <form
              className="workspace-memory-search"
              onSubmit={(event) => {
                event.preventDefault();
                void refresh(query, includeHistory);
              }}
            >
              <Search size={16} />
              <input value={query} placeholder={t('搜索标题、标签或内容…')} onChange={(event) => setQuery(event.target.value)} />
              <button className="icon-button" type="submit" title={t('搜索')} aria-label={t('搜索')}><Search size={15} /></button>
            </form>
            <label className="memory-history-toggle">
              <input
                type="checkbox"
                checked={includeHistory}
                onChange={(event) => {
                  const checked = event.target.checked;
                  setIncludeHistory(checked);
                  void refresh(query, checked);
                }}
              />
              <span>{t('显示历史版本')}</span>
            </label>
            <button className="secondary-button" type="button" onClick={() => setEditorOpen((open) => !open)}>
              <FilePlus2 size={15} />{t('新建候选')}
            </button>
            <button className="icon-button" type="button" title={t('刷新')} aria-label={t('刷新')} onClick={() => void refresh()}>
              <RefreshCw size={16} className={loading ? 'spin' : ''} />
            </button>
          </div>

          {editorOpen && (
            <form
              className="workspace-memory-editor"
              onSubmit={(event) => {
                event.preventDefault();
                void createCandidate();
              }}
            >
              <div className="workspace-memory-editor-heading">
                <div>
                  <strong>{supersedesVersionId ? t('创建不可变新版本') : t('创建记忆候选')}</strong>
                  <span>{t('保存后必须人工批准，才会进入规划器。')}</span>
                </div>
                {supersedesVersionId && <code>← {supersedesVersionId.slice(0, 8)}</code>}
              </div>
              <div className="workspace-memory-fields">
                <label><span>{t('类型')}</span><select value={kind} onChange={(event) => setKind(event.target.value as 'process' | 'knowledge')}><option value="process">{t('流程记忆')}</option><option value="knowledge">{t('知识记忆')}</option></select></label>
                <label><span>{t('标题')}</span><input value={title} maxLength={120} onChange={(event) => setTitle(event.target.value)} /></label>
                <label><span>{t('标签')}</span><input value={tags} maxLength={300} placeholder={t('用逗号分隔')} onChange={(event) => setTags(event.target.value)} /></label>
                <label><span>{t('Workspace 范围')}</span><input value={workspace} maxLength={1024} placeholder={t('留空表示全局')} onChange={(event) => setWorkspace(event.target.value)} /></label>
              </div>
              <label className="workspace-memory-body"><span>{t('记忆内容')}</span><textarea rows={7} maxLength={24000} value={content} placeholder={t('记录流程、检查点、失败教训、常用输入或带来源的知识…')} onChange={(event) => setContent(event.target.value)} /></label>
              <div className="workspace-memory-editor-actions">
                <span><ShieldCheck size={14} />{t('正式记忆不会被直接覆盖')}</span>
                <button type="button" className="text-button" onClick={resetEditor}>{t('取消')}</button>
                <button className="primary-button" type="submit" disabled={!title.trim() || content.trim().length < 3 || Boolean(busy)}>
                  {busy === 'create' ? <LoaderCircle size={15} className="spin" /> : <FilePlus2 size={15} />}{t('保存候选')}
                </button>
              </div>
            </form>
          )}

          <label className="workspace-memory-reason">
            <span>{t('审核说明')}</span>
            <input value={decisionReason} maxLength={500} placeholder={t('批准与撤销可选；回滚必须填写原因')} onChange={(event) => setDecisionReason(event.target.value)} />
          </label>

          {error && <div className="inline-error" role="alert">{error}</div>}

          {loading && !rows.length ? (
            <div className="memory-empty"><LoaderCircle size={22} className="spin" /><span>{t('正在读取记忆版本…')}</span></div>
          ) : rows.length ? (
            <div className="workspace-memory-list">
              {rows.map((row) => (
                <article className={`workspace-memory-row ${row.state}`} key={row.version_id}>
                  <div className="workspace-memory-row-heading">
                    <span className="memory-kind-icon">{row.kind === 'process' ? <GitBranch size={17} /> : <BookOpen size={17} />}</span>
                    <div>
                      <strong>{row.title}</strong>
                      <small>{t('{kind} · 第 {version} 版 · {time}', { kind: t(row.kind === 'process' ? '流程记忆' : '知识记忆'), version: row.version_number, time: formatDate(row.created_at, language) })}</small>
                      {row.origin === 'automatic_experience' && (
                        <small className="memory-origin automatic">
                          {t('自动生成的经验候选 · 尚未进入任何新 Work')}
                        </small>
                      )}
                    </div>
                    <span className={`memory-state ${row.state}`}>{t(memoryStateLabel(row))}</span>
                  </div>
                  {row.tags.length > 0 && <div className="memory-tags">{row.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>}
                  <details className="memory-content-preview">
                    <summary>{t('查看内容与来源')}</summary>
                    <pre>{row.content}</pre>
                    {row.origin === 'automatic_experience' && (
                      <div className="memory-provenance">
                        <strong>{t('本机确定性生成')}</strong>
                        <span>{t('只使用已审核方案与完整终结记录；未读取交付物正文，也未调用模型。')}</span>
                        {row.source_plan_id && <code>{t('来源 Work')} {row.source_plan_id}</code>}
                        {row.source_terminal_event_id && <code>{t('终结证据')} {row.source_terminal_event_id}</code>}
                        {row.fingerprint && <code>{t('候选指纹')} {row.fingerprint}</code>}
                      </div>
                    )}
                    <div><code>{row.relative_path}</code><code>SHA-256 {row.content_sha256.slice(0, 12)}…</code></div>
                  </details>
                  <div className="workspace-memory-row-actions">
                    <button className="text-button" type="button" disabled={Boolean(busy)} onClick={() => editVersion(row)}><GitBranch size={14} />{t('创建修订')}</button>
                    {row.state === 'candidate' && <button className="secondary-button" type="button" disabled={Boolean(busy)} onClick={() => void decide(row, 'dismiss')}>{busy === `dismiss:${row.version_id}` ? <LoaderCircle size={14} className="spin" /> : <Ban size={14} />}{t('忽略候选')}</button>}
                    {row.state === 'candidate' && <button className="primary-button" type="button" disabled={Boolean(busy)} onClick={() => void decide(row, 'approve')}>{busy === `approve:${row.version_id}` ? <LoaderCircle size={14} className="spin" /> : <Check size={14} />}{t('批准')}</button>}
                    {row.state === 'approved' && row.active && <button className="danger-button" type="button" disabled={Boolean(busy)} onClick={() => void decide(row, 'revoke')}>{busy === `revoke:${row.version_id}` ? <LoaderCircle size={14} className="spin" /> : <Ban size={14} />}{t('撤销')}</button>}
                    {['superseded', 'revoked'].includes(row.state) && <button className="secondary-button" type="button" disabled={Boolean(busy) || decisionReason.trim().length < 3} onClick={() => void decide(row, 'rollback')}>{busy === `rollback:${row.version_id}` ? <LoaderCircle size={14} className="spin" /> : <RotateCcw size={14} />}{t('回滚到此版本')}</button>}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="memory-empty"><BrainCircuit size={26} /><strong>{t('还没有 Workspace 记忆')}</strong><span>{t('从已完成 Work 生成流程候选，或手动创建带来源的知识候选。')}</span></div>
          )}

          <div className="memory-trust-boundary">
            <ShieldCheck size={15} />
            <span>{t('Agent 不能直接修改正式记忆。自动经验只会成为候选；批准与忽略都绑定内容哈希和候选指纹并写入账本。')}</span>
          </div>
        </div>
      </section>
    </div>
  );
}
