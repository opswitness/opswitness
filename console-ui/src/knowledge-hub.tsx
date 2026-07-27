import {
  Archive,
  BookOpenCheck,
  Check,
  CheckCircle2,
  Database,
  Download,
  FilePlus2,
  Files,
  FolderInput,
  FolderPlus,
  LoaderCircle,
  PackageCheck,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Tags,
  UploadCloud,
  X,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import {
  cancelLibraryImport,
  commitLibraryImport,
  createLibraryCardJob,
  createLibraryCollection,
  createLibraryExport,
  createLibraryImport,
  decideLibraryCard,
  downloadLibrarySemanticModel,
  getLibraryCardJob,
  getLibraryCards,
  getLibraryCollections,
  getLibraryDocuments,
  getLibraryIndexStatus,
  getLibrarySemanticModelStatus,
  previewLibraryExport,
  requestPlanFromLibrary,
  searchLibrary,
  uploadLibraryImportEntry,
} from './api';
import type { LibraryExportPolicy } from './api';
import { useLanguage } from './language';
import { SHOW_ANTHROPIC_PROVIDER_UI } from './product-boundaries';
import { EvidenceProjectLibraryView } from './project-library';
import type {
  KnowledgeCardVersion,
  LibraryCardJob,
  LibraryCollection,
  LibraryDocumentVersion,
  LibraryExport,
  LibraryImport,
  LibraryIndexStatus,
  LibrarySemanticModelStatus,
  LibrarySearchResult,
  PlanRecord,
} from './types';
import './knowledge-hub.css';

type HubTab = 'inbox' | 'documents' | 'cards' | 'collections' | 'exports';
type SelectedFile = { file: File; relativePath: string };

const DEFAULT_POLICY = {
  schema_version: 1 as const,
  purpose: 'General reference material',
  default_tags: [] as string[],
  allowed_formats: [
    'txt',
    'md',
    'csv',
    'json',
    'pdf',
    'docx',
    'xlsx',
    'png',
    'jpg',
    'jpeg',
    'webp',
  ],
  exclude_name_patterns: ['.DS_Store', 'Thumbs.db'],
  knowledge_card_language: 'auto' as const,
  generation_instructions: (
    'Summarize only supported source material. Keep claims bounded and attach an '
    + 'exact source citation to every key point.'
  ),
};

function compactBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function shortSha(value: string | null | undefined) {
  return value ? `${value.slice(0, 12)}…` : '—';
}

function selectedFiles(files: File[]): SelectedFile[] {
  return files.map((file) => ({
    file,
    relativePath: file.webkitRelativePath || file.name,
  }));
}

async function readDroppedDirectory(entry: FileSystemEntry): Promise<FileSystemEntry[]> {
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  const collected: FileSystemEntry[] = [];
  while (true) {
    const next = await new Promise<FileSystemEntry[]>((resolve, reject) => {
      reader.readEntries(resolve, reject);
    });
    if (!next.length) return collected;
    collected.push(...next);
  }
}

async function walkDroppedEntry(
  entry: FileSystemEntry,
  parent = '',
): Promise<SelectedFile[]> {
  const relativePath = parent ? `${parent}/${entry.name}` : entry.name;
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) => {
      (entry as FileSystemFileEntry).file(resolve, reject);
    });
    return [{ file, relativePath }];
  }
  if (!entry.isDirectory) return [];
  const children = await readDroppedDirectory(entry);
  const nested = await Promise.all(
    children.map((child) => walkDroppedEntry(child, relativePath)),
  );
  return nested.flat();
}

async function droppedFiles(dataTransfer: DataTransfer): Promise<SelectedFile[]> {
  const entries = Array.from(dataTransfer.items || [])
    .map((item) => {
      const candidate = item as DataTransferItem & {
        webkitGetAsEntry?: () => FileSystemEntry | null;
      };
      return candidate.webkitGetAsEntry?.() || null;
    })
    .filter((entry): entry is FileSystemEntry => entry !== null);
  if (!entries.length) return selectedFiles(Array.from(dataTransfer.files || []));
  const nested = await Promise.all(entries.map((entry) => walkDroppedEntry(entry)));
  return nested.flat();
}

function statusLabel(status: LibraryImport['entries'][number]['status']) {
  return {
    pending: '待上传',
    uploaded: '新资料',
    duplicate: '已去重',
    new_version: '新版本',
    skipped: '已跳过',
    error: '失败',
    committed: '已入库',
  }[status];
}

export function KnowledgeHubView({
  onPlanCreated,
}: {
  onPlanCreated: (record: PlanRecord) => void;
}) {
  const { t } = useLanguage();
  const [tab, setTab] = useState<HubTab>('inbox');
  const [collections, setCollections] = useState<LibraryCollection[]>([]);
  const [collectionId, setCollectionId] = useState('');
  const [documents, setDocuments] = useState<LibraryDocumentVersion[]>([]);
  const [cards, setCards] = useState<KnowledgeCardVersion[]>([]);
  const [indexStatus, setIndexStatus] = useState<LibraryIndexStatus | null>(null);
  const [semanticModel, setSemanticModel] =
    useState<LibrarySemanticModelStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [importRow, setImportRow] = useState<LibraryImport | null>(null);
  const [currentUpload, setCurrentUpload] = useState('');
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);

  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([]);
  const [selectedCardSources, setSelectedCardSources] = useState<string[]>([]);
  const [selectedContextCards, setSelectedContextCards] = useState<string[]>([]);
  const [workObjective, setWorkObjective] = useState('');
  const [creatingWork, setCreatingWork] = useState(false);

  const [searchQuery, setSearchQuery] = useState('');
  const [searchMode, setSearchMode] = useState<'lexical' | 'semantic' | 'hybrid'>('lexical');
  const [searchResult, setSearchResult] = useState<LibrarySearchResult | null>(null);
  const [searching, setSearching] = useState(false);

  const [cardProvider, setCardProvider] = useState<'openai' | 'anthropic'>('openai');
  const [cardDisclosureConfirmed, setCardDisclosureConfirmed] = useState(false);
  const [cardJob, setCardJob] = useState<LibraryCardJob | null>(null);

  const [newCollectionName, setNewCollectionName] = useState('');
  const [newCollectionPurpose, setNewCollectionPurpose] = useState('');
  const [creatingCollection, setCreatingCollection] = useState(false);

  const [exportCardIds, setExportCardIds] = useState<string[]>([]);
  const [sensitiveTerms, setSensitiveTerms] = useState('');
  const [exportPreview, setExportPreview] = useState<{
    preview_sha256: string;
    included: Record<string, unknown>;
    excluded: string[];
    replacements: Record<string, unknown>;
    static_share_boundary: string;
  } | null>(null);
  const [exporting, setExporting] = useState(false);
  const [libraryExport, setLibraryExport] = useState<LibraryExport | null>(null);

  const currentCollection = collections.find((item) => item.collection_id === collectionId);

  const refreshCollections = async () => {
    const next = await getLibraryCollections();
    setCollections(next);
    setCollectionId((current) => {
      if (current && next.some((item) => item.collection_id === current)) return current;
      return next.find((item) => item.is_inbox)?.collection_id || next[0]?.collection_id || '';
    });
  };

  const refreshContent = async (targetCollectionId = collectionId) => {
    if (!targetCollectionId) return;
    const [nextDocuments, nextCards, nextIndex, nextSemanticModel] = await Promise.all([
      getLibraryDocuments(targetCollectionId),
      getLibraryCards(targetCollectionId),
      getLibraryIndexStatus(),
      getLibrarySemanticModelStatus(),
    ]);
    setDocuments(nextDocuments);
    setCards(nextCards);
    setIndexStatus(nextIndex);
    setSemanticModel(nextSemanticModel);
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    refreshCollections()
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : t('资料库暂时无法读取'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
    // Initial load only; later writes refresh explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!collectionId) return;
    let cancelled = false;
    setLoading(true);
    refreshContent(collectionId)
      .catch((reason) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : t('资料库内容暂时无法读取'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
    // Collection identity is the only trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collectionId]);

  useEffect(() => {
    if (!cardJob || !['queued', 'running'].includes(cardJob.status)) return undefined;
    const timer = window.setTimeout(() => {
      getLibraryCardJob(cardJob.job_id)
        .then(async (next) => {
          setCardJob(next);
          if (next.status === 'completed') {
            await refreshContent(next.collection_id);
            setSelectedCardSources([]);
            setCardDisclosureConfirmed(false);
          }
        })
        .catch((reason) => setError(reason instanceof Error ? reason.message : t('知识卡任务状态读取失败')));
    }, 2_000);
    return () => window.clearTimeout(timer);
    // Poll one exact job only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cardJob]);

  useEffect(() => {
    if (semanticModel?.state !== 'downloading') return undefined;
    const timer = window.setTimeout(() => {
      getLibrarySemanticModelStatus()
        .then((next) => setSemanticModel(next))
        .catch((reason) => setError(
          reason instanceof Error ? reason.message : t('本地语义模型状态读取失败'),
        ));
    }, 1_000);
    return () => window.clearTimeout(timer);
  }, [semanticModel, t]);

  const activeDocuments = useMemo(
    () => documents.filter((document) => document.status === 'active'),
    [documents],
  );
  const approvedCards = useMemo(
    () => cards.filter((card) => card.state === 'approved'),
    [cards],
  );

  const scanAndUpload = async (files: SelectedFile[]) => {
    if (!currentCollection || !files.length || uploading) return;
    setUploading(true);
    setError('');
    setImportRow(null);
    try {
      let batch = await createLibraryImport({
        collection_id: currentCollection.collection_id,
        expected_collection_revision: currentCollection.revision,
        entries: files.map(({ file, relativePath }) => ({
          relative_path: relativePath,
          size_bytes: file.size,
          media_type: file.type || 'application/octet-stream',
          source_kind: 'file',
        })),
      });
      setImportRow(batch);
      for (let index = 0; index < batch.entries.length; index += 1) {
        const entry = batch.entries[index];
        if (entry.status === 'skipped') continue;
        setCurrentUpload(entry.relative_path);
        batch = await uploadLibraryImportEntry(
          batch.import_id,
          entry.entry_id,
          files[index].file,
        );
        setImportRow(batch);
      }
      setCurrentUpload('');
      setImportRow(batch);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('资料上传失败'));
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
      if (folderInput.current) folderInput.current.value = '';
    }
  };

  const commitImport = async () => {
    if (!currentCollection || !importRow?.manifest_sha256) return;
    setUploading(true);
    setError('');
    try {
      const committed = await commitLibraryImport(
        importRow.import_id,
        currentCollection.revision,
        importRow.manifest_sha256,
      );
      setImportRow(committed);
      await Promise.all([refreshCollections(), refreshContent(currentCollection.collection_id)]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('资料清单提交失败'));
    } finally {
      setUploading(false);
    }
  };

  const cancelImport = async () => {
    if (!importRow || importRow.status === 'committed') return;
    try {
      setImportRow(await cancelLibraryImport(importRow.import_id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('取消导入失败'));
    }
  };

  const runSearch = async () => {
    if (!searchQuery.trim() || searching) return;
    setSearching(true);
    setError('');
    try {
      setSearchResult(await searchLibrary({
        query: searchQuery.trim(),
        mode: searchMode,
        collection_ids: collectionId ? [collectionId] : [],
        limit: 30,
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('资料搜索失败'));
    } finally {
      setSearching(false);
    }
  };

  const enableSemanticSearch = async () => {
    setError('');
    try {
      setSemanticModel(await downloadLibrarySemanticModel());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('本地语义模型下载未能启动'));
    }
  };

  const createWork = async () => {
    if (!selectedDocuments.length || workObjective.trim().length < 3 || creatingWork) return;
    setCreatingWork(true);
    setError('');
    try {
      const record = await requestPlanFromLibrary({
        objective: workObjective.trim(),
        constraints: (
          'Use only the exact library inputs and approved context packet shown in review. '
          + 'Treat search relevance as discovery, not proof. Do not run before operator confirmation.'
        ),
        workspace: '',
        preferred_cadence: 'once',
        document_version_ids: selectedDocuments,
        knowledge_card_version_ids: selectedContextCards,
        confirmed_context_packet: true,
      });
      onPlanCreated(record);
      setSelectedDocuments([]);
      setSelectedContextCards([]);
      setWorkObjective('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('从资料库创建 Work 失败'));
    } finally {
      setCreatingWork(false);
    }
  };

  const startCardJob = async () => {
    if (!currentCollection || !selectedCardSources.length || !cardDisclosureConfirmed) return;
    setError('');
    try {
      const sources = activeDocuments.filter(
        (document) => selectedCardSources.includes(document.version_id),
      );
      const next = await createLibraryCardJob({
        collection_id: currentCollection.collection_id,
        document_version_ids: sources.map((document) => document.version_id),
        provider: cardProvider,
        model: 'default',
        disclosed_character_count: sources.reduce(
          (total, document) => total + document.text_character_count,
          0,
        ),
        confirmed_source_disclosure: true,
      });
      setCardJob(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('知识卡任务启动失败'));
    }
  };

  const decideCard = async (
    card: KnowledgeCardVersion,
    action: 'approve' | 'dismiss' | 'revoke',
  ) => {
    setError('');
    try {
      await decideLibraryCard(card.version_id, action, card.card_sha256);
      await Promise.all([refreshCollections(), refreshContent(card.collection_id)]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('知识卡审核失败'));
    }
  };

  const addCollection = async () => {
    if (newCollectionName.trim().length < 1 || creatingCollection) return;
    setCreatingCollection(true);
    setError('');
    try {
      const created = await createLibraryCollection({
        name: newCollectionName.trim(),
        policy: {
          ...DEFAULT_POLICY,
          purpose: newCollectionPurpose.trim() || DEFAULT_POLICY.purpose,
        },
      });
      await refreshCollections();
      setCollectionId(created.collection_id);
      setNewCollectionName('');
      setNewCollectionPurpose('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('资料库创建失败'));
    } finally {
      setCreatingCollection(false);
    }
  };

  const exportPolicy = (): LibraryExportPolicy => ({
    schema_version: 1,
    profile: 'safe_partner',
    include_card_version_ids: exportCardIds,
    include_tags: true,
    include_citation_excerpts: true,
    custom_sensitive_terms: sensitiveTerms
      .split(/\r?\n|,/)
      .map((item) => item.trim())
      .filter(Boolean),
  });

  const previewExport = async () => {
    if (!currentCollection || !exportCardIds.length) return;
    setExporting(true);
    setError('');
    try {
      setExportPreview(await previewLibraryExport({
        collection_id: currentCollection.collection_id,
        expected_collection_revision: currentCollection.revision,
        policy: exportPolicy(),
      }));
      setLibraryExport(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('导出预览失败'));
    } finally {
      setExporting(false);
    }
  };

  const createExport = async () => {
    if (!currentCollection || !exportPreview || exporting) return;
    setExporting(true);
    setError('');
    try {
      setLibraryExport(await createLibraryExport({
        collection_id: currentCollection.collection_id,
        expected_collection_revision: currentCollection.revision,
        policy: exportPolicy(),
        expected_preview_sha256: exportPreview.preview_sha256,
        confirmed: true,
      }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t('离线知识库导出失败'));
    } finally {
      setExporting(false);
    }
  };

  const toggle = (
    value: string,
    values: string[],
    setter: (next: string[]) => void,
    limit: number,
  ) => {
    if (values.includes(value)) {
      setter(values.filter((item) => item !== value));
    } else if (values.length < limit) {
      setter([...values, value]);
    }
  };

  const progressDone = importRow
    ? importRow.files_uploaded + importRow.files_skipped + importRow.files_failed
    : 0;
  const progressPercent = importRow
    ? Math.round((progressDone / importRow.files_total) * 100)
    : 0;

  return (
    <section className="knowledge-hub" aria-label={t('项目资料库')}>
      <header className="knowledge-hub-header">
        <div>
          <span className="section-kicker">{t('资料只上传一次，以后按版本复用')}</span>
          <h2>{t('Knowledge Hub')}</h2>
          <p>{t('收件、去重、生成带引用的知识卡，并把准确版本加入新 Work。')}</p>
        </div>
        <label className="knowledge-collection-switcher">
          <span>{t('当前资料库')}</span>
          <select value={collectionId} onChange={(event) => setCollectionId(event.target.value)}>
            {collections.map((collection) => (
              <option key={collection.collection_id} value={collection.collection_id}>
                {collection.name}
              </option>
            ))}
          </select>
        </label>
      </header>

      <nav className="knowledge-hub-tabs" aria-label={t('资料库页面')}>
        {([
          ['inbox', InboxTabIcon, '收件箱'],
          ['documents', Files, '资料'],
          ['cards', BookOpenCheck, '知识卡'],
          ['collections', Database, '资料库'],
          ['exports', PackageCheck, '导出'],
        ] as Array<[HubTab, typeof Files, string]>).map(([key, Icon, label]) => (
          <button
            key={key}
            type="button"
            aria-current={tab === key ? 'page' : undefined}
            onClick={() => setTab(key)}
          >
            <Icon size={16} />
            {t(label)}
          </button>
        ))}
      </nav>

      {error && (
        <div className="knowledge-hub-error" role="alert">
          <span>{error}</span>
          <button type="button" aria-label={t('关闭')} onClick={() => setError('')}>
            <X size={15} />
          </button>
        </div>
      )}

      {loading && !collections.length ? (
        <div className="knowledge-hub-empty">
          <LoaderCircle size={24} className="spin" />
          <span>{t('正在准备私人资料库…')}</span>
        </div>
      ) : null}

      {tab === 'inbox' && currentCollection && (
        <div className="knowledge-inbox">
          <section
            className="knowledge-dropzone"
            onDragOver={(event) => {
              event.preventDefault();
              event.dataTransfer.dropEffect = 'copy';
            }}
            onDrop={(event) => {
              event.preventDefault();
              if (!uploading) {
                void droppedFiles(event.dataTransfer)
                  .then(scanAndUpload)
                  .catch((reason) => setError(
                    reason instanceof Error ? reason.message : t('文件夹扫描失败'),
                  ));
              }
            }}
          >
            <UploadCloud size={34} />
            <h3>{t('把文件或整个文件夹放进收件箱')}</h3>
            <p>{t('一次性快照，不持续监控原目录；绝对路径不会保存。')}</p>
            <div>
              <button
                className="primary-button"
                type="button"
                disabled={uploading}
                onClick={() => fileInput.current?.click()}
              >
                <FilePlus2 size={16} />
                {t('选择文件')}
              </button>
              <button
                className="secondary-button"
                type="button"
                disabled={uploading}
                onClick={() => folderInput.current?.click()}
              >
                <FolderInput size={16} />
                {t('选择文件夹')}
              </button>
            </div>
            <input
              ref={fileInput}
              hidden
              multiple
              type="file"
              accept=".txt,.md,.csv,.json,.pdf,.docx,.xlsx,.png,.jpg,.jpeg,.webp"
              onChange={(event) => void scanAndUpload(
                selectedFiles(Array.from(event.target.files || [])),
              )}
            />
            <input
              ref={folderInput}
              hidden
              multiple
              type="file"
              {...({ webkitdirectory: '', directory: '' } as Record<string, string>)}
              onChange={(event) => void scanAndUpload(
                selectedFiles(Array.from(event.target.files || [])),
              )}
            />
            <small>
              {t('每批最多 500 个文件 / 1 GiB；单文件 50 MiB；提交后至少保留 2 GiB 空间。')}
            </small>
          </section>

          {importRow && (
            <section className="knowledge-import-progress" aria-live="polite">
              <header>
                <div>
                  <span className="section-kicker">{t('导入清单')}</span>
                  <h3>{t('{done}/{total} 个文件已处理', {
                    done: progressDone,
                    total: importRow.files_total,
                  })}</h3>
                </div>
                <code>Manifest {shortSha(importRow.manifest_sha256)}</code>
              </header>
              <div
                className="knowledge-progress-track"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={progressPercent}
              >
                <span style={{ width: `${progressPercent}%` }} />
              </div>
              {currentUpload && (
                <p className="knowledge-current-file">
                  <LoaderCircle size={15} className="spin" />
                  {t('正在计算 SHA-256：{name}', { name: currentUpload })}
                </p>
              )}
              <div className="knowledge-import-counts">
                <span><b>{importRow.files_uploaded}</b>{t('已上传')}</span>
                <span><b>{importRow.files_skipped}</b>{t('已跳过')}</span>
                <span><b>{importRow.files_failed}</b>{t('失败')}</span>
                <span><b>{compactBytes(importRow.bytes_uploaded)}</b>{t('已处理')}</span>
              </div>
              <div className="knowledge-import-list" role="list">
                {importRow.entries.map((entry) => (
                  <div role="listitem" key={entry.entry_id} className={entry.status}>
                    <span>
                      {entry.status === 'committed' ? <CheckCircle2 size={15} /> : <Files size={15} />}
                    </span>
                    <strong>{entry.relative_path}</strong>
                    <small>{compactBytes(entry.size_bytes)} · {entry.file_format.toUpperCase()}</small>
                    <em>{t(statusLabel(entry.status))}</em>
                    {entry.reason && <p>{t(entry.reason)}</p>}
                  </div>
                ))}
              </div>
              <footer>
                {importRow.status !== 'committed' && (
                  <button
                    className="text-button"
                    type="button"
                    disabled={uploading}
                    onClick={() => void cancelImport()}
                  >
                    <X size={15} />
                    {t('取消并清理 staging')}
                  </button>
                )}
                {importRow.status === 'ready' && importRow.manifest_sha256 && (
                  <button
                    className="primary-button"
                    type="button"
                    disabled={uploading}
                    onClick={() => void commitImport()}
                  >
                    {uploading ? <LoaderCircle size={15} className="spin" /> : <ShieldCheck size={15} />}
                    {t('确认清单并入库')}
                  </button>
                )}
                {importRow.status === 'committed' && (
                  <span className="knowledge-success">
                    <Check size={15} />
                    {t('已原子提交；相同 SHA-256 只保存一份')}
                  </span>
                )}
              </footer>
            </section>
          )}
        </div>
      )}

      {tab === 'documents' && currentCollection && (
        <div className="knowledge-materials">
          <section className="knowledge-search">
            <header>
              <div>
                <span className="section-kicker">{t('全文与本地语义检索')}</span>
                <h3>{t('搜索资料和已批准知识卡')}</h3>
              </div>
              <span>
                {indexStatus?.state === 'ready' ? <CheckCircle2 size={15} /> : <RefreshCw size={15} />}
                {t('索引 {state}', { state: indexStatus?.state || 'idle' })}
              </span>
            </header>
            <div className="knowledge-search-controls">
              <label>
                <Search size={17} />
                <input
                  type="search"
                  value={searchQuery}
                  placeholder={t('搜索正文、标题或标签…')}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') void runSearch();
                  }}
                />
              </label>
              <select
                value={searchMode}
                onChange={(event) => setSearchMode(
                  event.target.value as 'lexical' | 'semantic' | 'hybrid',
                )}
              >
                <option value="lexical">{t('全文搜索')}</option>
                <option value="semantic">{t('本地语义')}</option>
                <option value="hybrid">{t('混合搜索')}</option>
              </select>
              <button
                className="secondary-button"
                type="button"
                disabled={searching || !searchQuery.trim()}
                onClick={() => void runSearch()}
              >
                {searching ? <LoaderCircle size={15} className="spin" /> : <Search size={15} />}
                {t('搜索')}
              </button>
            </div>
            {searchMode !== 'lexical' && semanticModel?.state !== 'ready' && (
              <div className="knowledge-semantic-setup">
                <Sparkles size={20} />
                <div>
                  <strong>{t('启用完全本地的语义搜索')}</strong>
                  <span>
                    {semanticModel?.state === 'downloading'
                      ? t('正在下载固定模型：{done} / {total}', {
                        done: compactBytes(semanticModel.bytes_downloaded),
                        total: compactBytes(semanticModel.bytes_total),
                      })
                      : t('需下载约 470 MiB 的 multilingual-e5-small；不会把资料发送给远程 embedding。')}
                  </span>
                  {semanticModel?.current_file && (
                    <code>{semanticModel.current_file}</code>
                  )}
                </div>
                {semanticModel?.state === 'downloading' ? (
                  <LoaderCircle size={18} className="spin" />
                ) : (
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => void enableSemanticSearch()}
                  >
                    <Download size={15} />
                    {t('确认下载并启用')}
                  </button>
                )}
              </div>
            )}
            {searchResult && (
              <>
                {searchResult.mode_requested !== searchResult.mode_used && (
                  <div className="knowledge-search-boundary">
                    <ShieldCheck size={15} />
                    {t('本地语义模型当前不可用，已明确降级为仅全文搜索；没有调用远程 embedding。')}
                  </div>
                )}
                <div className="knowledge-search-results">
                  {searchResult.hits.map((hit) => (
                    <article key={hit.hit_id}>
                      <header>
                        <strong>{hit.title}</strong>
                        <span>{hit.source_type} · {hit.source_status}</span>
                      </header>
                      <p>{hit.snippet}</p>
                      <footer>
                        <code>SHA {shortSha(hit.sha256)}</code>
                        <span>{hit.locator}</span>
                        <em>{t('相关，不代表正确或已验证')}</em>
                      </footer>
                    </article>
                  ))}
                  {!searchResult.hits.length && <p>{t('没有找到相关资料。')}</p>}
                </div>
              </>
            )}
          </section>

          <section className="knowledge-document-list">
            <header>
              <div>
                <span className="section-kicker">{t('准确版本')}</span>
                <h3>{t('{count} 份资料', { count: activeDocuments.length })}</h3>
              </div>
              <span>{t('最多选择 10 份 / 250 MiB')}</span>
            </header>
            <div role="list">
              {activeDocuments.map((document) => (
                <label role="listitem" key={document.version_id}>
                  <input
                    type="checkbox"
                    checked={selectedDocuments.includes(document.version_id)}
                    onChange={() => toggle(
                      document.version_id,
                      selectedDocuments,
                      setSelectedDocuments,
                      10,
                    )}
                  />
                  <span className="knowledge-document-icon"><Files size={17} /></span>
                  <span>
                    <strong>{document.display_name}</strong>
                    <small>{document.relative_path} · v{document.version_number}</small>
                    <em>
                      {document.file_format.toUpperCase()} · {compactBytes(document.size_bytes)}
                      {' · '}{t(document.extraction_status)}
                    </em>
                  </span>
                  <code>SHA {shortSha(document.sha256)}</code>
                </label>
              ))}
            </div>
          </section>

          <section className="knowledge-create-work">
            <header>
              <div>
                <span className="section-kicker">{t('用于新 Work')}</span>
                <h3>{t('先创建未确认方案，再审阅和运行')}</h3>
              </div>
              <span>{t('{count} 份资料已选择', { count: selectedDocuments.length })}</span>
            </header>
            <label>
              <span>{t('你想让 Agent 完成什么？')}</span>
              <textarea
                rows={3}
                value={workObjective}
                placeholder={t('例如：根据这些客户资料，整理常见问题和一封待审核回复。')}
                onChange={(event) => setWorkObjective(event.target.value)}
              />
            </label>
            {approvedCards.length > 0 && (
              <details>
                <summary>{t('加入已批准知识卡作为有界 Context Packet')}</summary>
                {approvedCards.map((card) => (
                  <label key={card.version_id}>
                    <input
                      type="checkbox"
                      checked={selectedContextCards.includes(card.version_id)}
                      onChange={() => toggle(
                        card.version_id,
                        selectedContextCards,
                        setSelectedContextCards,
                        20,
                      )}
                    />
                    <span>{card.title}</span>
                  </label>
                ))}
              </details>
            )}
            <button
              className="primary-button"
              type="button"
              disabled={!selectedDocuments.length || workObjective.trim().length < 3 || creatingWork}
              onClick={() => void createWork()}
            >
              {creatingWork ? <LoaderCircle size={15} className="spin" /> : <Sparkles size={15} />}
              {t('创建待审 Work')}
            </button>
          </section>

          <details className="knowledge-legacy-files">
            <summary>{t('查看既有 Work 输入和运行产物')}</summary>
            <EvidenceProjectLibraryView />
          </details>
        </div>
      )}

      {tab === 'cards' && currentCollection && (
        <div className="knowledge-cards">
          <section className="knowledge-card-generator">
            <header>
              <div>
                <span className="section-kicker">{t('候选先生成，批准后才可复用')}</span>
                <h3>{t('生成带来源引用的知识卡')}</h3>
              </div>
              <Sparkles size={22} />
            </header>
            <div className="knowledge-card-source-list">
              {activeDocuments.map((document) => (
                <label key={document.version_id}>
                  <input
                    type="checkbox"
                    checked={selectedCardSources.includes(document.version_id)}
                    disabled={document.extraction_status !== 'included'}
                    onChange={() => toggle(
                      document.version_id,
                      selectedCardSources,
                      setSelectedCardSources,
                      20,
                    )}
                  />
                  <span>
                    <strong>{document.display_name}</strong>
                    <small>
                      {document.text_chunk_count} chunks · {document.text_character_count.toLocaleString()} chars
                    </small>
                  </span>
                  <em>{t(document.extraction_status)}</em>
                </label>
              ))}
            </div>
            <div className="knowledge-provider-row">
              <label>
                <span>{t('发送给已连接模型')}</span>
                <select
                  value={cardProvider}
                  onChange={(event) => setCardProvider(event.target.value as 'openai' | 'anthropic')}
                >
                  <option value="openai">Codex / OpenAI</option>
                  {SHOW_ANTHROPIC_PROVIDER_UI && (
                    <option value="anthropic">Claude / Anthropic</option>
                  )}
                </select>
              </label>
              <label className="knowledge-disclosure-check">
                <input
                  type="checkbox"
                  checked={cardDisclosureConfirmed}
                  onChange={(event) => setCardDisclosureConfirmed(event.target.checked)}
                />
                <span>
                  {t('我确认将所选资料的 {count} 个正文字符发送给 {provider}', {
                    count: activeDocuments
                      .filter((document) => selectedCardSources.includes(document.version_id))
                      .reduce((total, document) => total + document.text_character_count, 0)
                      .toLocaleString(),
                    provider: cardProvider === 'openai' ? 'OpenAI' : 'Anthropic',
                  })}
                </span>
              </label>
              <button
                className="primary-button"
                type="button"
                disabled={!selectedCardSources.length || !cardDisclosureConfirmed || !!(
                  cardJob && ['queued', 'running'].includes(cardJob.status)
                )}
                onClick={() => void startCardJob()}
              >
                {cardJob && ['queued', 'running'].includes(cardJob.status)
                  ? <LoaderCircle size={15} className="spin" />
                  : <Sparkles size={15} />}
                {t(cardJob && ['queued', 'running'].includes(cardJob.status)
                  ? '正在生成候选卡…'
                  : '生成候选卡')}
              </button>
            </div>
            {cardJob?.status === 'failed' && (
              <p className="knowledge-card-failed">
                {t('生成没有完成；资料仍已安全入库。错误代码：{code}', {
                  code: cardJob.error_code || 'unknown',
                })}
              </p>
            )}
          </section>

          <section className="knowledge-card-review">
            <header>
              <div>
                <span className="section-kicker">{t('人工审核')}</span>
                <h3>{t('{count} 张知识卡', { count: cards.length })}</h3>
              </div>
              <span>{t('{count} 张已批准', { count: approvedCards.length })}</span>
            </header>
            <div>
              {cards.map((card) => (
                <article key={card.version_id} className={card.state}>
                  <header>
                    <div>
                      <strong>{card.title}</strong>
                      <span>{t(card.state)} · {card.provider} / {card.model}</span>
                    </div>
                    <code>SHA {shortSha(card.card_sha256)}</code>
                  </header>
                  <p>{card.summary}</p>
                  <ul>
                    {card.key_points.map((point, index) => (
                      <li key={`${card.version_id}-${index}`}>
                        <span>{point.statement}</span>
                        {point.citations.map((citation) => (
                          <blockquote key={citation.excerpt_sha256}>
                            “{citation.excerpt}”
                            <footer>{citation.locator} · SHA {shortSha(citation.document_sha256)}</footer>
                          </blockquote>
                        ))}
                      </li>
                    ))}
                  </ul>
                  <footer>
                    <span>{t('覆盖：{coverage}', { coverage: card.coverage })}</span>
                    {card.state === 'candidate' && (
                      <div>
                        <button
                          className="text-button"
                          type="button"
                          onClick={() => void decideCard(card, 'dismiss')}
                        >
                          <X size={14} />{t('不采用')}
                        </button>
                        <button
                          className="primary-button"
                          type="button"
                          onClick={() => void decideCard(card, 'approve')}
                        >
                          <Check size={14} />{t('批准入库')}
                        </button>
                      </div>
                    )}
                    {card.state === 'approved' && (
                      <button
                        className="text-button"
                        type="button"
                        onClick={() => void decideCard(card, 'revoke')}
                      >
                        <Archive size={14} />{t('撤销批准')}
                      </button>
                    )}
                  </footer>
                </article>
              ))}
              {!cards.length && (
                <div className="knowledge-hub-empty">
                  <BookOpenCheck size={26} />
                  <strong>{t('还没有知识卡')}</strong>
                  <span>{t('选择已抽取正文的资料，确认供应商后生成候选。')}</span>
                </div>
              )}
            </div>
          </section>
        </div>
      )}

      {tab === 'collections' && (
        <div className="knowledge-collections">
          <section>
            <header>
              <div>
                <span className="section-kicker">{t('不可变规则版本')}</span>
                <h3>{t('命名资料库')}</h3>
              </div>
              <FolderPlus size={22} />
            </header>
            <div className="knowledge-collection-list">
              {collections.map((collection) => (
                <button
                  key={collection.collection_id}
                  type="button"
                  className={collection.collection_id === collectionId ? 'active' : ''}
                  onClick={() => setCollectionId(collection.collection_id)}
                >
                  <Database size={18} />
                  <span>
                    <strong>{collection.name}</strong>
                    <small>{collection.policy.purpose}</small>
                    <em>
                      v{collection.revision} · {collection.document_count} {t('份资料')}
                      {' · '}{collection.approved_card_count} {t('张已批准卡')}
                    </em>
                  </span>
                  <code>{shortSha(collection.policy_sha256)}</code>
                </button>
              ))}
            </div>
          </section>
          <section className="knowledge-new-collection">
            <span className="section-kicker">{t('新资料库')}</span>
            <h3>{t('用独立规则整理另一类资料')}</h3>
            <label>
              <span>{t('名称')}</span>
              <input
                value={newCollectionName}
                placeholder={t('例如：客户研究')}
                onChange={(event) => setNewCollectionName(event.target.value)}
              />
            </label>
            <label>
              <span>{t('用途')}</span>
              <textarea
                rows={3}
                value={newCollectionPurpose}
                placeholder={t('这套资料用于什么；知识卡应重点提取什么。')}
                onChange={(event) => setNewCollectionPurpose(event.target.value)}
              />
            </label>
            <button
              className="primary-button"
              type="button"
              disabled={!newCollectionName.trim() || creatingCollection}
              onClick={() => void addCollection()}
            >
              {creatingCollection ? <LoaderCircle size={15} className="spin" /> : <FolderPlus size={15} />}
              {t('创建资料库')}
            </button>
          </section>
        </div>
      )}

      {tab === 'exports' && currentCollection && (
        <div className="knowledge-exports">
          <section>
            <header>
              <div>
                <span className="section-kicker">{t('Safe Partner · 离线静态包')}</span>
                <h3>{t('选择要分享的已批准知识卡')}</h3>
              </div>
              <Download size={22} />
            </header>
            <div className="knowledge-export-card-list">
              {approvedCards.map((card) => (
                <label key={card.version_id}>
                  <input
                    type="checkbox"
                    checked={exportCardIds.includes(card.version_id)}
                    onChange={() => {
                      toggle(card.version_id, exportCardIds, setExportCardIds, 500);
                      setExportPreview(null);
                      setLibraryExport(null);
                    }}
                  />
                  <span>
                    <strong>{card.title}</strong>
                    <small>{card.summary}</small>
                  </span>
                  <code>{shortSha(card.card_sha256)}</code>
                </label>
              ))}
            </div>
            <label>
              <span><Tags size={14} />{t('自定义敏感词（逗号或换行分隔）')}</span>
              <textarea
                rows={3}
                value={sensitiveTerms}
                placeholder={t('例如：客户全名、内部项目代号')}
                onChange={(event) => {
                  setSensitiveTerms(event.target.value);
                  setExportPreview(null);
                  setLibraryExport(null);
                }}
              />
            </label>
            <button
              className="secondary-button"
              type="button"
              disabled={!exportCardIds.length || exporting}
              onClick={() => void previewExport()}
            >
              {exporting ? <LoaderCircle size={15} className="spin" /> : <ShieldCheck size={15} />}
              {t('预览包含、排除和替换')}
            </button>
          </section>

          {exportPreview && (
            <section className="knowledge-export-preview">
              <header>
                <div>
                  <span className="section-kicker">{t('确认前预览')}</span>
                  <h3>{t('只包含已批准内容')}</h3>
                </div>
                <code>Preview {shortSha(exportPreview.preview_sha256)}</code>
              </header>
              <dl>
                <div>
                  <dt>{t('包含')}</dt>
                  <dd><pre>{JSON.stringify(exportPreview.included, null, 2)}</pre></dd>
                </div>
                <div>
                  <dt>{t('排除')}</dt>
                  <dd>{exportPreview.excluded.join(' · ')}</dd>
                </div>
                <div>
                  <dt>{t('替换')}</dt>
                  <dd><pre>{JSON.stringify(exportPreview.replacements, null, 2)}</pre></dd>
                </div>
              </dl>
              <div className="knowledge-export-warning">
                <ShieldCheck size={17} />
                <strong>{t('静态文件分享后无法远程撤回、到期或执行 RBAC。')}</strong>
              </div>
              <button
                className="primary-button"
                type="button"
                disabled={exporting}
                onClick={() => void createExport()}
              >
                {exporting ? <LoaderCircle size={15} className="spin" /> : <PackageCheck size={15} />}
                {t('确认并生成离线 ZIP')}
              </button>
            </section>
          )}

          {libraryExport && (
            <section className="knowledge-export-ready">
              <CheckCircle2 size={26} />
              <div>
                <strong>{t('离线知识库已生成')}</strong>
                <span>{libraryExport.card_count} {t('张知识卡')} · SHA {shortSha(libraryExport.output_sha256)}</span>
              </div>
              <a className="primary-button" href={libraryExport.download_url}>
                <Download size={16} />
                {t('下载 ZIP')}
              </a>
            </section>
          )}
        </div>
      )}
    </section>
  );
}

function InboxTabIcon({ size }: { size: number }) {
  return <FolderInput size={size} />;
}
