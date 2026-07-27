import {
  BookOpen,
  CheckCircle2,
  ChevronRight,
  FileCheck2,
  FolderOpen,
  Play,
  RefreshCw,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { useLanguage } from './language';

const TOPIC_IDS = [
  'first-use',
  'run-work',
  'approvals',
  'project-library',
  'evidence',
  'recovery',
] as const;

type TopicId = (typeof TOPIC_IDS)[number];

type TopicCopy = {
  title: string;
  summary: string;
  steps: string[];
  note: string;
};

type DocsCopy = {
  eyebrow: string;
  title: string;
  introduction: string;
  offline: string;
  contents: string;
  namingTitle: string;
  namingBody: string;
  productLabel: string;
  productValue: string;
  commandLabel: string;
  commandValue: string;
  compatibilityLabel: string;
  compatibilityValue: string;
  topicLabel: string;
  topics: Record<TopicId, TopicCopy>;
};

const TOPIC_ICONS = {
  'first-use': BookOpen,
  'run-work': Play,
  approvals: ShieldCheck,
  'project-library': FolderOpen,
  evidence: FileCheck2,
  recovery: RefreshCw,
} as const;

export const DOCS_CENTER_COPY: Record<'en' | 'zh', DocsCopy> = {
  en: {
    eyebrow: 'OFFLINE GUIDE',
    title: 'Docs Center',
    introduction:
      'Practical guidance for using OpsWitness safely. This guide is included with the app and never needs a network connection.',
    offline: 'Available offline',
    contents: 'GUIDE TOPICS',
    namingTitle: 'Official names',
    namingBody:
      'Use these names in new documentation, screenshots, support messages, and integrations. Existing audit records and IDs are historical evidence and are never renamed.',
    productLabel: 'Product',
    productValue: 'OpsWitness',
    commandLabel: 'Command and package',
    commandValue: 'opswitness',
    compatibilityLabel: 'Compatibility alias',
    compatibilityValue: 'qd — legacy compatibility only',
    topicLabel: 'Guide topic',
    topics: {
      'first-use': {
        title: 'First use',
        summary: 'Set up the local app and complete the safe built-in demonstration.',
        steps: [
          'Choose a fresh environment or import a copy of older data. Import never takes over the old service or changes the old directory.',
          'Connect Codex through its official sign-in flow. This Alpha does not expose other model-provider connection options.',
          'Review the built-in customer-reply demonstration before it starts. It uses only fictional data in an empty app-managed folder.',
          'Approve each of the two expected local file saves separately, then review both registered files before finishing setup.',
        ],
        note:
          'The first Work proves the local technical path only. It does not assess a real customer or business outcome.',
      },
      'run-work': {
        title: 'Run a Work',
        summary: 'Turn a clear outcome into a reviewed plan, then follow its live progress.',
        steps: [
          'Describe the outcome, allowed inputs, expected deliverables, limits, and the decisions that must come back to you.',
          'Review the proposed team, stage owners, tools, output files, approval mode, and risks. Revise anything unclear before confirming.',
          'Confirm the exact plan. During execution, OpsWitness shows observable stage status and pauses when your approval or input is required.',
          'Treat “Execution complete · Verification needed” as a handoff for review, not as proof that the business result is correct.',
        ],
        note:
          'A new Work never starts from a saved template, project file, or approved experience until you review and confirm its plan.',
      },
      approvals: {
        title: 'Approvals and safety',
        summary: 'Approve the exact action you understand, one request at a time.',
        steps: [
          'Check the Work, agent, tool, target, and requested action shown on the approval card.',
          'Approve only the displayed request. A single-use approval does not authorize a later write, send, install, delete, or different target.',
          'Reject unexpected or broader requests. The Work remains stopped at that governed action and the rejection is recorded.',
          '“Automatic safe” covers only the app’s fixed internal coordination actions; governed file or external actions still follow the reviewed policy.',
        ],
        note:
          'Credentials are not supposed to enter artifacts, the ledger, or the release manifest. Never paste a password or secret into a Work.',
      },
      'project-library': {
        title: 'Project Library',
        summary: 'Find inputs and registered outputs from different Works in one place.',
        steps: [
          'Search by file name, Work, tag, or file type. The library is a local index over retained inputs and outputs, not a second copy of every file.',
          'Add your own tags to group material by customer, project, status, or topic. Tags change private metadata only, never the file bytes or evidence digest.',
          'Link a newer file as a version of an older one. The relationship is explicit; OpsWitness does not guess or overwrite either version.',
          'Open a file from its unified entry to see its source Work, evidence status, digest, and other versions in one read-only view.',
        ],
        note:
          'This view currently supports read-only opening, private tags, and explicit version links. It does not attach a library file to a new Work.',
      },
      evidence: {
        title: 'Evidence and sign-off',
        summary: 'Separate technical completion from your judgment about the result.',
        steps: [
          'Open the registered outputs and compare them with the promised deliverables in the confirmed plan.',
          'Check each file’s source Work, evidence status, and SHA-256 digest. A matching digest proves which bytes were reviewed, not whether the content is good.',
          'Record sign-off only after reviewing the exact displayed artifacts. Sign-off records your review and keeps the execution status distinct.',
          'If an artifact is missing, changed, or does not match the task, leave it unsigned and create a corrected Work instead of rewriting history.',
        ],
        note:
          'OpsWitness preserves technical evidence. It does not make legal, compliance, quality, or business-result claims on your behalf.',
      },
      recovery: {
        title: 'Troubleshooting and recovery',
        summary: 'Let the governed Recovery Agent investigate a stalled Work without silently expanding its authority.',
        steps: [
          'Only an active Work with no new verifiable progress for three minutes enters diagnosis. Waiting for approval, waiting for input, and an intentionally paused Work are not treated as stuck.',
          'The signed-in model receives only bounded status counts and runtime-control state. It does not receive raw logs, prompts, file contents, credentials, or hidden reasoning.',
          'Automatic recovery is limited to refreshing status or continuing the same ledger-bound Work and team. It stops after two attempts, and a continue acknowledgement remains “verifying” until new stage or activity evidence appears.',
          'A possible product bug can produce a Repair Work suggestion. Creating it requires a second explicit confirmation; the new Work remains unconfirmed and every governed operation requires manual approval.',
        ],
        note:
          'Runtime recovery does not verify the business result. OpsWitness never rewrites its signed installed App; product-code fixes still require a reviewed Repair Work and a signed update.',
      },
    },
  },
  zh: {
    eyebrow: '离线使用指南',
    title: 'Docs Center',
    introduction:
      '帮助你安全使用 OpsWitness 的实用指南。内容随 App 内置，无需联网即可阅读。',
    offline: '可离线使用',
    contents: '指南主题',
    namingTitle: '正式命名',
    namingBody:
      '新文档、截图、支持消息和集成统一使用以下名称。历史审计记录和 ID 属于既有证据，绝不因改名而重写。',
    productLabel: '产品显示名',
    productValue: 'OpsWitness',
    commandLabel: '命令与软件包',
    commandValue: 'opswitness',
    compatibilityLabel: '兼容别名',
    compatibilityValue: 'qd — 仅用于旧版兼容',
    topicLabel: '指南主题',
    topics: {
      'first-use': {
        title: '首次使用',
        summary: '设置本地 App，并完成安全的内置演示。',
        steps: [
          '选择创建全新环境，或导入旧数据的副本。导入不会接管旧服务，也不会改动旧目录。',
          '通过 Codex 官方登录流程连接账户。本 Alpha 不展示其他模型提供商的连接入口。',
          '启动前先审核内置的客户回复演示。它只使用虚构数据和 App 管理的空白目录。',
          '分别批准两次预期的本地文件保存，最后查看两个已登记文件，再完成首次设置。',
        ],
        note: '首个 Work 只验证本地技术流程，不评估任何真实客户或业务结果。',
      },
      'run-work': {
        title: '运行 Work',
        summary: '把明确目标变成可审核方案，并跟随真实进度。',
        steps: [
          '写清目标、允许使用的输入、预期交付物、限制条件，以及必须交回给你决定的事项。',
          '审核团队、阶段负责人、工具、输出文件、审批模式和风险；不清楚的地方先修改再确认。',
          '确认这份准确方案。执行中只展示可观测的阶段状态，需要你批准或补充信息时会暂停。',
          '把“执行完成 · 待核验”理解为交给你审阅，而不是业务结果已经正确。',
        ],
        note: '模板、项目文件或已批准经验都不会自动启动新 Work；仍需你审核并确认方案。',
      },
      approvals: {
        title: '审批与安全',
        summary: '一次只批准一个你完全理解的明确动作。',
        steps: [
          '检查审批卡上的 Work、Agent、工具、目标位置和具体动作。',
          '只批准当前显示的请求。一次性批准不授权后续写入、发送、安装、删除或其他目标。',
          '拒绝意外或范围更大的请求；Work 会停在该受管动作，拒绝决定会被记录。',
          '“自动放行安全操作”只覆盖 App 固定的内部协作动作；文件和外部操作仍遵循已审核策略。',
        ],
        note: '密码和密钥不应进入交付物、账本或发布清单。不要把任何凭据粘贴到 Work 中。',
      },
      'project-library': {
        title: '项目资料库',
        summary: '在统一入口查找不同 Work 的输入和已登记输出。',
        steps: [
          '按文件名、Work、标签或类型搜索。资料库是本地索引，不会为每个文件再复制一份内容。',
          '用自定义标签按客户、项目、状态或主题整理。标签只改变私有元数据，不改变文件内容或证据摘要。',
          '明确把新文件关联为旧文件的新版本。OpsWitness 不会自行猜测版本，也不会覆盖任一版本。',
          '从统一入口打开文件，可在同一个只读页面查看来源 Work、证据状态、摘要和其他版本。',
        ],
        note: '当前页面只支持只读打开、私有标签和明确版本关系，尚不能把资料库文件直接加入新 Work。',
      },
      evidence: {
        title: '证据与审签',
        summary: '把技术执行完成和你对结果的判断明确分开。',
        steps: [
          '打开已登记输出，与确认方案中承诺的交付物逐项比较。',
          '检查每个文件的来源 Work、证据状态和 SHA-256。摘要一致只证明审阅的是哪一份内容，不证明内容质量。',
          '审阅准确文件后再记录审签。审签记录你的人工审阅，不会把执行状态改写为业务成功。',
          '文件缺失、变化或不符合目标时，不要审签；创建修正版 Work，保留原历史。',
        ],
        note: 'OpsWitness 保存技术证据，不替你作出法律、合规、质量或业务结果保证。',
      },
      recovery: {
        title: '故障恢复',
        summary: '让受治理的 Recovery Agent 调查卡住的 Work，同时不静默扩大权限。',
        steps: [
          '只有仍在运行、连续三分钟没有新可验证进展的 Work 才会进入诊断。等待审批、等待补充信息和主动暂停都不算卡住。',
          '已登录模型只会收到受限的状态数量和运行控制状态，不会收到原始日志、提示词、文件内容、凭据或隐藏推理。',
          '自动恢复只允许重新核对状态，或继续账本已绑定的同一个 Work 和团队；最多尝试两次。继续命令被接受后仍处于“正在验证”，看到新的阶段或活动证据才算恢复。',
          '如果可能是产品缺陷，只会生成 Repair Work 建议。创建它需要第二次明确确认；新 Work 仍未确认，所有受治理操作都必须人工审批。',
        ],
        note: '运行恢复不等于业务结果通过。OpsWitness 不会改写已签名安装包；产品代码修复仍需审阅 Repair Work，并通过签名更新发布。',
      },
    },
  },
};

export function DocsCenter() {
  const { language } = useLanguage();
  const copy = DOCS_CENTER_COPY[language];
  const [activeTopic, setActiveTopic] = useState<TopicId>('first-use');
  const topic = copy.topics[activeTopic];
  const ActiveIcon = TOPIC_ICONS[activeTopic];

  return (
    <div className="docs-center">
      <section className="docs-center-hero">
        <div>
          <span className="section-kicker">{copy.eyebrow}</span>
          <h2>{copy.title}</h2>
          <p>{copy.introduction}</p>
        </div>
        <span className="docs-center-offline">
          <CheckCircle2 size={16} />
          {copy.offline}
        </span>
      </section>

      <section className="docs-center-layout">
        <nav className="docs-center-topics" aria-label={copy.topicLabel}>
          <span className="section-kicker">{copy.contents}</span>
          {TOPIC_IDS.map((topicId) => {
            const Icon = TOPIC_ICONS[topicId];
            const current = activeTopic === topicId;
            return (
              <button
                key={topicId}
                type="button"
                className={current ? 'docs-topic active' : 'docs-topic'}
                aria-current={current ? 'page' : undefined}
                onClick={() => setActiveTopic(topicId)}
              >
                <Icon size={18} />
                <span>
                  <strong>{copy.topics[topicId].title}</strong>
                  <small>{copy.topics[topicId].summary}</small>
                </span>
                <ChevronRight size={16} />
              </button>
            );
          })}
        </nav>

        <article className="docs-center-article">
          <header>
            <span><ActiveIcon size={22} /></span>
            <div>
              <h3>{topic.title}</h3>
              <p>{topic.summary}</p>
            </div>
          </header>
          <ol>
            {topic.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <div className="docs-center-note">
            <ShieldCheck size={18} />
            <p>{topic.note}</p>
          </div>
        </article>
      </section>

      <section className="docs-center-naming">
        <header>
          <span className="section-kicker">{copy.namingTitle}</span>
          <p>{copy.namingBody}</p>
        </header>
        <dl>
          <div>
            <dt>{copy.productLabel}</dt>
            <dd>{copy.productValue}</dd>
          </div>
          <div>
            <dt>{copy.commandLabel}</dt>
            <dd><code>{copy.commandValue}</code></dd>
          </div>
          <div>
            <dt>{copy.compatibilityLabel}</dt>
            <dd><code>qd</code><span>{copy.compatibilityValue.slice(2)}</span></dd>
          </div>
        </dl>
      </section>
    </div>
  );
}

const ONBOARDING_HELP_TOPICS: TopicId[] = ['first-use', 'recovery'];

export function OnboardingHelp({ onClose }: { onClose: () => void }) {
  const { language } = useLanguage();
  const copy = DOCS_CENTER_COPY[language];
  const [activeTopic, setActiveTopic] = useState<TopicId>('first-use');
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const topic = copy.topics[activeTopic];
  const ActiveIcon = TOPIC_ICONS[activeTopic];

  useEffect(() => {
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div className="onboarding-help-layer" role="dialog" aria-modal="true" aria-labelledby="onboarding-help-title">
      <section className="onboarding-help-card">
        <header>
          <div>
            <span className="section-kicker">{copy.eyebrow}</span>
            <h2 id="onboarding-help-title">{copy.title}</h2>
            <p>{copy.offline}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            aria-label={language === 'zh' ? '关闭帮助' : 'Close help'}
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        <nav aria-label={copy.topicLabel}>
          {ONBOARDING_HELP_TOPICS.map((topicId) => {
            const Icon = TOPIC_ICONS[topicId];
            return (
              <button
                key={topicId}
                type="button"
                className={activeTopic === topicId ? 'active' : ''}
                aria-pressed={activeTopic === topicId}
                onClick={() => setActiveTopic(topicId)}
              >
                <Icon size={17} />
                {copy.topics[topicId].title}
              </button>
            );
          })}
        </nav>
        <article>
          <header>
            <span><ActiveIcon size={20} /></span>
            <div>
              <h3>{topic.title}</h3>
              <p>{topic.summary}</p>
            </div>
          </header>
          <ol>
            {topic.steps.map((step) => <li key={step}>{step}</li>)}
          </ol>
          <div className="docs-center-note">
            <ShieldCheck size={18} />
            <p>{topic.note}</p>
          </div>
        </article>
      </section>
    </div>
  );
}
