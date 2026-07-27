import {
  File,
  FileCheck2,
  FileInput,
  FolderSearch,
  LoaderCircle,
  Save,
  Search,
  ShieldCheck,
  Tag,
  X,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  getProjectLibrary,
  getProjectLibraryItem,
  updateProjectLibraryItem,
} from './api';
import { useLanguage } from './language';
import {
  projectLibrarySourceLabel,
  projectLibraryVersionCandidates,
  splitProjectLibraryTags,
} from './project-library-model.js';
import type { ProjectLibraryItem, ProjectLibraryItemPreview } from './types';
import './project-library.css';

function compactBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function compactId(value: string) {
  return `${value.slice(0, 8)}…`;
}

function sourceIcon(item: ProjectLibraryItem) {
  if (item.source_kind === 'planning_input') return FileInput;
  if (item.source_kind === 'registered_output') return FileCheck2;
  return File;
}

export function EvidenceProjectLibraryView() {
  const { language, t } = useLanguage();
  const [items, setItems] = useState<ProjectLibraryItem[]>([]);
  const [selected, setSelected] = useState<ProjectLibraryItemPreview | null>(null);
  const [query, setQuery] = useState('');
  const [fileType, setFileType] = useState('');
  const [tagDraft, setTagDraft] = useState('');
  const [predecessor, setPredecessor] = useState('');
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const refresh = async (preferredAssetId?: string) => {
    setLoading(true);
    try {
      const next = await getProjectLibrary();
      setItems(next);
      setError('');
      const targetId = preferredAssetId || selected?.asset_id;
      if (targetId && next.some((item) => item.asset_id === targetId)) {
        const detail = await getProjectLibraryItem(targetId);
        setSelected(detail);
        setTagDraft(detail.user_tags.join(', '));
        setPredecessor(detail.supersedes_asset_id || '');
      } else if (selected) {
        setSelected(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('项目资料暂时无法读取'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    // Initial projection only. Refresh is also called explicitly after a metadata change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const visibleItems = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase(language === 'zh' ? 'zh-CN' : 'en-US');
    return items.filter((item) => {
      if (fileType && item.file_type !== fileType) return false;
      if (!normalized) return true;
      return [
        item.name,
        item.work_title,
        item.work_id,
        item.plan_id,
        item.file_type,
        item.mime,
        ...item.system_tags,
        ...item.user_tags,
      ].some((value) => value.toLocaleLowerCase().includes(normalized));
    });
  }, [fileType, items, language, query]);

  const fileTypes = useMemo(
    () => Array.from(new Set(items.map((item) => item.file_type))).filter(Boolean).sort(),
    [items],
  );
  const versionCandidates = projectLibraryVersionCandidates(items, selected);

  const openItem = async (item: ProjectLibraryItem) => {
    setDetailLoading(true);
    setError('');
    try {
      const detail = await getProjectLibraryItem(item.asset_id);
      setSelected(detail);
      setTagDraft(detail.user_tags.join(', '));
      setPredecessor(detail.supersedes_asset_id || '');
    } catch (err) {
      setError(err instanceof Error ? err.message : t('无法打开这份项目资料'));
    } finally {
      setDetailLoading(false);
    }
  };

  const saveMetadata = async () => {
    if (!selected || saving) return;
    setSaving(true);
    setError('');
    try {
      const updated = await updateProjectLibraryItem(selected.asset_id, {
        expected_sha256: selected.sha256,
        user_tags: splitProjectLibraryTags(tagDraft),
        supersedes_asset_id: predecessor || null,
      });
      setSelected(updated);
      setTagDraft(updated.user_tags.join(', '));
      setPredecessor(updated.supersedes_asset_id || '');
      await refresh(updated.asset_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('项目资料标签保存失败'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="project-library-page" aria-label={t('项目资料库')}>
      <header className="project-library-header">
        <div>
          <span className="section-kicker">{t('跨 Work 的统一文件入口')}</span>
          <h2>{t('项目资料库')}</h2>
          <p>{t('查看已保留的输入材料和运行产物；原文件不会被复制。')}</p>
        </div>
        <div className="project-library-boundary">
          <ShieldCheck size={16} />
          <span>{t('打开前重新核对路径与 SHA-256')}</span>
        </div>
      </header>

      <div className="project-library-toolbar">
        <label>
          <Search size={17} />
          <input
            type="search"
            value={query}
            placeholder={t('搜索文件名、Work、标签或类型…')}
            aria-label={t('搜索项目资料')}
            onChange={(event) => setQuery(event.target.value)}
          />
          {query && (
            <button type="button" aria-label={t('清除搜索')} onClick={() => setQuery('')}>
              <X size={15} />
            </button>
          )}
        </label>
        <select
          value={fileType}
          aria-label={t('按文件类型筛选')}
          onChange={(event) => setFileType(event.target.value)}
        >
          <option value="">{t('全部类型')}</option>
          {fileTypes.map((type) => <option key={type} value={type}>{type.toUpperCase()}</option>)}
        </select>
        <span>{t('{count} 份资料', { count: visibleItems.length })}</span>
      </div>

      {error && <div className="project-library-error" role="alert">{error}</div>}

      <div className="project-library-layout">
        <div className="project-library-list" aria-live="polite">
          {loading ? (
            <div className="project-library-empty">
              <LoaderCircle size={22} className="spin" />
              <span>{t('正在核对项目资料…')}</span>
            </div>
          ) : visibleItems.length ? visibleItems.map((item) => {
            const Icon = sourceIcon(item);
            return (
              <button
                className={selected?.asset_id === item.asset_id ? 'active' : ''}
                type="button"
                key={item.asset_id}
                onClick={() => void openItem(item)}
              >
                <span className="project-library-file-icon"><Icon size={18} /></span>
                <span className="project-library-file-copy">
                  <strong>{item.name}</strong>
                  <small>{item.work_title} · v{item.revision_number}</small>
                  <span>
                    <em>{t(projectLibrarySourceLabel(item))}</em>
                    <code>{item.file_type.toUpperCase()} · {compactBytes(item.size)}</code>
                  </span>
                  {(item.user_tags.length > 0 || item.supersedes_asset_id) && (
                    <span className="project-library-file-tags">
                      {item.user_tags.map((tag) => <i key={tag}>{tag}</i>)}
                      {item.supersedes_asset_id && (
                        <i>
                          {t(
                            item.supersedes_status === 'unavailable'
                              ? '前一版本已不可用'
                              : '有前一版本',
                          )}
                        </i>
                      )}
                    </span>
                  )}
                </span>
              </button>
            );
          }) : (
            <div className="project-library-empty">
              <FolderSearch size={26} />
              <strong>{t('没有匹配的项目资料')}</strong>
              <span>{t('完成 Work 或附加输入材料后，会自动出现在这里。')}</span>
            </div>
          )}
        </div>

        <aside className="project-library-detail">
          {detailLoading ? (
            <div className="project-library-empty"><LoaderCircle size={22} className="spin" /></div>
          ) : selected ? (
            <>
              <header>
                <span className="section-kicker">{t('只读文件')}</span>
                <h3>{selected.name}</h3>
                <p>{selected.work_title} · {t('第 {version} 版', { version: selected.revision_number })}</p>
              </header>
              <dl>
                <div><dt>{t('来源')}</dt><dd>{t(projectLibrarySourceLabel(selected))}</dd></div>
                <div><dt>SHA-256</dt><dd><code title={selected.sha256}>{compactId(selected.sha256)}</code></dd></div>
                <div><dt>{t('证据状态')}</dt><dd>{t({
                  retained_input: '已保留输入',
                  registered: '已登记到 CAS',
                  workspace_unverified: '运行目录中发现 · 未登记',
                }[selected.evidence_status])}</dd></div>
              </dl>
              <div className="project-library-preview">
                {selected.preview_kind === 'json' ? (
                  <pre>{JSON.stringify(selected.preview, null, 2)}</pre>
                ) : selected.preview_kind === 'text' ? (
                  <pre>{String(selected.preview)}</pre>
                ) : (
                  <div>
                    <File size={22} />
                    <span>{t('此类型不提供内嵌预览，可从下方只读打开。')}</span>
                  </div>
                )}
              </div>
              <a
                className="primary-button project-library-open"
                href={selected.content_url}
                target="_blank"
                rel="noreferrer"
              >
                <FolderSearch size={16} />
                {t('打开只读文件')}
              </a>
              <div className="project-library-metadata">
                <label>
                  <span><Tag size={14} />{t('标签')}</span>
                  <input
                    value={tagDraft}
                    maxLength={400}
                    placeholder={t('例如：客户、合同、待复核')}
                    onChange={(event) => setTagDraft(event.target.value)}
                  />
                </label>
                <label>
                  <span>{t('版本关系')}</span>
                  <select value={predecessor} onChange={(event) => setPredecessor(event.target.value)}>
                    <option value="">{t('没有指定前一版本')}</option>
                    {selected.supersedes_asset_id
                      && selected.supersedes_status === 'unavailable' && (
                      <option value={selected.supersedes_asset_id}>
                        {t('前一版本已不可用')} · {compactId(selected.supersedes_asset_id)}
                      </option>
                    )}
                    {versionCandidates.map((candidate) => (
                      <option key={candidate.asset_id} value={candidate.asset_id}>
                        {candidate.work_title} · v{candidate.revision_number} · {candidate.name} · {compactId(candidate.sha256)}
                      </option>
                    ))}
                  </select>
                  <small>{t('只记录明确的“替代上一版”关系，不改写历史文件。')}</small>
                </label>
                <button
                  className="secondary-button"
                  type="button"
                  disabled={saving}
                  onClick={() => void saveMetadata()}
                >
                  {saving ? <LoaderCircle size={15} className="spin" /> : <Save size={15} />}
                  {t('保存标签与版本关系')}
                </button>
              </div>
            </>
          ) : (
            <div className="project-library-empty">
              <FolderSearch size={28} />
              <strong>{t('选择一份资料')}</strong>
              <span>{t('可预览内容、核对哈希，并整理标签与版本关系。')}</span>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
