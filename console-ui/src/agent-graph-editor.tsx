import {
  AlertTriangle,
  ArrowRight,
  Bot,
  Check,
  CircleDot,
  Cpu,
  FileCheck2,
  GitBranch,
  LoaderCircle,
  Network,
  PencilLine,
  Plus,
  Repeat2,
  RotateCcw,
  Save,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import {
  agentContractPlanDraft,
  agentGraphFingerprint,
  createAgentGraphDraft,
  layoutAgentGraph,
  validateAgentGraphDraft,
} from './agent-graph-model.js';
import type {
  AgentGraphDraft,
  AgentGraphDraftAgent,
} from './agent-graph-model.js';
import { useLanguage } from './language';
import { SHOW_ANTHROPIC_PROVIDER_UI } from './product-boundaries';
import type {
  AgentContract,
  AgentContractDiffEntry,
  AgentContractPreview,
  ContractControl,
  RuntimeCapability,
  TaskPlan,
  WorkspaceMemorySummary,
} from './types';

const ROLE_LABELS: Record<AgentGraphDraftAgent['role'], string> = {
  lead: '负责人',
  researcher: '研究',
  operator: '执行',
  reviewer: '复核',
  reporter: '汇报',
  specialist: '专家',
};

const RUNTIME_LABELS: Record<AgentGraphDraftAgent['runtime'], string> = {
  claude_code: 'Claude',
  codex_cli: 'Codex',
  aion_cli: '本地 AI',
};

const CONTROL_LABELS: Record<ContractControl, string> = {
  deny: '拒绝',
  always_ask: '每次询问',
  inherit_run_mode: '沿用 Work 模式',
};

const ENFORCEMENT_LABELS = {
  software_enforced: '软件强制',
  runtime_approval: '运行时审批',
  execution_instruction: '执行指令',
  unsupported: '暂不支持',
};

const TABS = [
  ['basic', '基本信息'],
  ['method', '工作方法'],
  ['results', '输入与结果'],
  ['controls', '资料与控制'],
  ['collaboration', '协作与停止'],
  ['model', '模型与版本'],
] as const;

type TabId = typeof TABS[number][0];

const VALIDATION_LABELS: Record<string, string> = {
  agent_count: 'Agent 数量必须为 1–5 个。',
  agent_keys: 'Agent 图包含无效节点。',
  agent_names: '每个 Agent 都需要唯一名称。',
  agent_contract: '每个 Agent 都需要完整职责、工作指令和默认拒绝策略。',
  lead_count: '团队必须且只能有一名负责人。',
  lead_manager: '负责人不能向其他 Agent 汇报。',
  manager_missing: '每名非负责人 Agent 都需要一个直属上级。',
  reporting_cycle: '汇报关系不能形成循环。',
  loop_count: '复核循环最多 5 个。',
  loop_invalid: '复核循环需要有效 Agent、条件和 1–10 次上限。',
  stage_owner: '每个阶段都必须分配给一个现有 Agent。',
  contract_paths: '输入、输出和资料路径必须是已授权的规范相对路径。',
  contract_controls: '工具、重试或停止策略无效。',
  contract_references: '移交、升级或输入引用了不存在的 Agent。',
};

function lines(value: string[]) {
  return value.join('\n');
}

function parseLines(value: string) {
  return [...new Set(value.split('\n').map((row) => row.trim()).filter(Boolean))];
}

function shortValue(value: unknown) {
  if (value === undefined) return '—';
  const encoded = JSON.stringify(value);
  return encoded.length > 180 ? `${encoded.slice(0, 177)}…` : encoded;
}

function curveBetween(
  source: { x: number; y: number },
  target: { x: number; y: number },
) {
  const middle = source.y + (target.y - source.y) / 2;
  return `M ${source.x} ${source.y} C ${source.x} ${middle}, ${target.x} ${middle}, ${target.x} ${target.y}`;
}

function loopCurve(
  source: { x: number; y: number },
  target: { x: number; y: number },
  self: boolean,
) {
  if (self) {
    return `M ${source.x} ${source.y} C ${source.x + 75} ${source.y - 70}, ${source.x + 75} ${source.y + 70}, ${source.x} ${source.y + 4}`;
  }
  const offset = Math.max(55, Math.abs(target.x - source.x) / 2);
  return `M ${source.x} ${source.y} C ${source.x + offset} ${source.y + 60}, ${target.x - offset} ${target.y + 60}, ${target.x} ${target.y}`;
}

function setJsonPointer(root: Record<string, unknown>, entry: AgentContractDiffEntry) {
  const tokens = entry.path
    .split('/')
    .slice(1)
    .map((token) => token.replaceAll('~1', '/').replaceAll('~0', '~'));
  if (!tokens.length) return root;
  const clone = structuredClone(root) as Record<string, unknown>;
  let cursor: unknown = clone;
  for (const token of tokens.slice(0, -1)) {
    if (Array.isArray(cursor)) cursor = cursor[Number(token)];
    else if (cursor && typeof cursor === 'object') cursor = (cursor as Record<string, unknown>)[token];
  }
  const leaf = tokens.at(-1) || '';
  if (Array.isArray(cursor)) {
    const index = Number(leaf);
    if (entry.change === 'added') cursor.splice(index, 1);
    else cursor[index] = structuredClone(entry.before);
  } else if (cursor && typeof cursor === 'object') {
    if (entry.change === 'added') delete (cursor as Record<string, unknown>)[leaf];
    else (cursor as Record<string, unknown>)[leaf] = structuredClone(entry.before);
  }
  return clone;
}

function ControlSelect({
  value,
  disabled,
  onChange,
}: {
  value: ContractControl;
  disabled: boolean;
  onChange: (value: ContractControl) => void;
}) {
  return (
    <select
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value as ContractControl)}
    >
      {Object.entries(CONTROL_LABELS).map(([policy, label]) => (
        <option key={policy} value={policy}>{label}</option>
      ))}
    </select>
  );
}

export function AgentGraphEditor({
  plan,
  planSha256,
  editable,
  runtimeCapabilities,
  workspaceMemories,
  onPreview,
  onSave,
}: {
  plan: TaskPlan;
  planSha256: string;
  editable: boolean;
  runtimeCapabilities: RuntimeCapability[];
  workspaceMemories: WorkspaceMemorySummary[];
  onPreview: (draft: Record<string, unknown>) => Promise<AgentContractPreview>;
  onSave: (draft: Record<string, unknown>) => Promise<void>;
}) {
  const { t } = useLanguage();
  const original = useMemo(() => createAgentGraphDraft(plan), [plan]);
  const [draft, setDraft] = useState<AgentGraphDraft>(original);
  const [selectedKey, setSelectedKey] = useState(original.agents[0]?.key || '');
  const [editing, setEditing] = useState(false);
  const [activeTab, setActiveTab] = useState<TabId>('basic');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState<AgentContractPreview | null>(null);

  useEffect(() => {
    setDraft(original);
    setSelectedKey(original.agents[0]?.key || '');
    setEditing(false);
    setPreview(null);
    setError('');
  }, [original]);

  const validation = useMemo(() => validateAgentGraphDraft(draft), [draft]);
  const validationMessage = validation.length ? t(VALIDATION_LABELS[validation[0]]) : '';
  const changed = agentGraphFingerprint(draft) !== agentGraphFingerprint(original);
  const layout = useMemo(() => layoutAgentGraph(draft), [draft]);
  const agentByKey = useMemo(
    () => new Map(draft.agents.map((agent) => [agent.key, agent])),
    [draft.agents],
  );
  const positionByKey = useMemo(
    () => new Map(layout.positions.map((position) => [position.key, position])),
    [layout.positions],
  );
  const selected = agentByKey.get(selectedKey) || draft.agents[0] || null;

  const updateAgent = (
    key: string,
    patch: Partial<AgentGraphDraftAgent>,
  ) => {
    setDraft((current) => ({
      ...current,
      agents: current.agents.map((agent) => (
        agent.key === key ? { ...agent, ...patch } : agent
      )),
    }));
  };

  const updateContract = (
    key: string,
    patch: Partial<AgentContract>,
  ) => {
    setDraft((current) => ({
      ...current,
      agents: current.agents.map((agent) => (
        agent.key === key
          ? { ...agent, contract: { ...agent.contract, ...patch } }
          : agent
      )),
    }));
  };

  const changeRole = (key: string, role: AgentGraphDraftAgent['role']) => {
    setDraft((current) => {
      const currentAgent = current.agents.find((agent) => agent.key === key);
      if (!currentAgent) return current;
      let agents = current.agents;
      if (role === 'lead') {
        agents = agents.map((agent) => (
          agent.role === 'lead' && agent.key !== key
            ? { ...agent, role: 'specialist' as const, reports_to_key: key }
            : agent
        ));
      }
      return {
        ...current,
        agents: agents.map((agent) => (
          agent.key === key
            ? {
              ...agent,
              role,
              reports_to_key: role === 'lead'
                ? null
                : agent.reports_to_key || agents.find((row) => row.role === 'lead')?.key || null,
            }
            : agent
        )),
      };
    });
  };

  const changeRuntime = (
    key: string,
    runtime: AgentGraphDraftAgent['runtime'],
  ) => {
    const capability = runtimeCapabilities.find((entry) => entry.runtime === runtime);
    const selectedModel = capability?.models.find((model) => model.id === capability.default_model)
      || capability?.models[0];
    updateAgent(key, {
      runtime,
      model: selectedModel?.id || 'default',
      model_binding: selectedModel?.pinning || 'default',
      runtime_reason: capability?.reason || '由操作员选择；预览时由 OpsWitness 重新绑定。',
    });
  };

  const addAgent = () => {
    if (draft.agents.length >= 5) return;
    const lead = draft.agents.find((agent) => agent.role === 'lead') || draft.agents[0];
    const key = `new:${crypto.randomUUID()}`;
    const template = createAgentGraphDraft({
      ...plan,
      schema_version: 1,
      agents: [{
        name: `Agent ${draft.agents.length + 1}`,
        role: 'specialist',
        responsibility: '完成已分配的受边界约束任务',
        runtime: lead.runtime,
        model: lead.model,
        runtime_reason: '由操作员新增；预览时由 OpsWitness 绑定运行时。',
        reports_to: null,
      }],
      collaboration_loops: [],
      stages: [{
        order: 1,
        title: '占位阶段',
        owner: `Agent ${draft.agents.length + 1}`,
        outcome: '完成分配结果',
        checkpoint: false,
      }],
    }).agents[0];
    setDraft((current) => ({
      ...current,
      agents: [
        ...current.agents,
        {
          ...template,
          key,
          reports_to_key: lead.key,
          contract: {
            ...template.contract,
            handoff: {
              ...template.contract.handoff,
              allowed_target_agent_ids: [],
            },
          },
        },
      ],
    }));
    setSelectedKey(key);
    setActiveTab('basic');
  };

  const deleteAgent = (key: string) => {
    const target = draft.agents.find((agent) => agent.key === key);
    if (!target || target.role === 'lead' || draft.agents.length <= 1) return;
    if (!window.confirm(t('删除后将重新分配其阶段、下属、循环、移交和升级引用。继续吗？'))) {
      return;
    }
    const lead = draft.agents.find((agent) => agent.role === 'lead')!;
    const replacement = target.reports_to_key || lead.key;
    setDraft((current) => ({
      ...current,
      agents: current.agents
        .filter((agent) => agent.key !== key)
        .map((agent) => ({
          ...agent,
          reports_to_key: agent.reports_to_key === key ? replacement : agent.reports_to_key,
          contract: {
            ...agent.contract,
            inputs: agent.contract.inputs.filter((input) => input.source_agent_id !== key),
            handoff: {
              ...agent.contract.handoff,
              allowed_target_agent_ids:
                agent.contract.handoff.allowed_target_agent_ids.filter((id) => id !== key),
            },
            escalation: {
              ...agent.contract.escalation,
              target_agent_id:
                agent.contract.escalation.target_agent_id === key
                  ? replacement
                  : agent.contract.escalation.target_agent_id,
            },
          },
        })),
      loops: current.loops.filter(
        (loop) => loop.source_key !== key && loop.target_key !== key,
      ),
      stages: current.stages.map((stage) => (
        stage.owner_key === key ? { ...stage, owner_key: replacement } : stage
      )),
    }));
    setSelectedKey(replacement);
  };

  const addLoop = () => {
    if (draft.loops.length >= 5 || !selected) return;
    const target = draft.agents.find((candidate) => (
      !draft.loops.some(
        (loop) => loop.source_key === selected.key && loop.target_key === candidate.key,
      )
    ));
    if (!target) {
      setError(t('当前 Agent 已没有可添加的唯一协作方向。'));
      return;
    }
    setDraft((current) => ({
      ...current,
      loops: [...current.loops, {
        source_key: selected.key,
        target_key: target.key,
        condition: t('验收未通过时返回修改；通过即停止'),
        max_iterations: 2,
      }],
    }));
  };

  const reviewChanges = async () => {
    if (!editable || !changed || validation.length || saving) return;
    setSaving(true);
    setError('');
    try {
      const result = await onPreview(agentContractPlanDraft(draft, plan));
      setPreview(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('Agent Contract 预览失败'));
    } finally {
      setSaving(false);
    }
  };

  const createVersion = async () => {
    if (!preview || saving) return;
    setSaving(true);
    setError('');
    try {
      await onSave(agentContractPlanDraft(draft, plan));
      setEditing(false);
      setPreview(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('Agent Contract 保存失败'));
    } finally {
      setSaving(false);
    }
  };

  const restoreDiff = (entry: AgentContractDiffEntry) => {
    if (!preview) return;
    const restored = setJsonPointer(
      preview.normalized_plan as unknown as Record<string, unknown>,
      entry,
    ) as unknown as TaskPlan;
    setDraft(createAgentGraphDraft(restored));
    setPreview(null);
  };

  const selectedCapability = selected
    ? runtimeCapabilities.find((capability) => capability.runtime === selected.runtime)
    : undefined;
  const selectedModels = selectedCapability?.models || [];
  const selectedOwnedStages = selected
    ? draft.stages.filter((stage) => stage.owner_key === selected.key)
    : [];
  const approvedMemories = workspaceMemories.filter(
    (memory) => memory.state === 'approved' && memory.active,
  );

  if (preview) {
    return (
      <section className="agent-studio agent-contract-review">
        <header className="agent-studio-header">
          <div>
            <span className="section-kicker">{t('审阅字段级变化')}</span>
            <h3><FileCheck2 size={18} />{t('创建新的 Agent Contract 版本')}</h3>
            <p>{t('当前 Work 不会被覆盖；确认后创建新的 ready 子版本。')}</p>
          </div>
          <div className="agent-studio-header-actions">
            <button className="text-button" type="button" onClick={() => setPreview(null)}>
              <ArrowRight size={15} className="flip-x" />{t('返回编辑')}
            </button>
            <button className="secondary-button" type="button" disabled={saving} onClick={() => void createVersion()}>
              {saving ? <LoaderCircle size={15} className="spin" /> : <Save size={15} />}
              {t('创建 v{version}', { version: 'N+1' })}
            </button>
          </div>
        </header>
        <div className="contract-review-hashes">
          <span><b>Plan</b>{preview.candidate_plan_sha256}</span>
          <span><b>Contract</b>{preview.contract_sha256}</span>
        </div>
        {preview.normalized_plan.runtime_mode === 'strict' && !preview.strict_runtime_available && (
          <div className="agent-studio-error" role="alert">
            <AlertTriangle size={16} />
            <span>{t('严格运行时当前不可用；此版本可以保存，但确认运行时会拒绝，不会静默降级。')}</span>
          </div>
        )}
        <div className="contract-diff-list" role="list" aria-label={t('Agent Contract 字段变化')}>
          {preview.diff.length ? preview.diff.map((entry) => (
            <article role="listitem" key={`${entry.path}-${entry.change}`}>
              <div>
                <span className={`diff-direction ${entry.direction}`}>
                  {entry.direction === 'tighter' ? t('权限变严')
                    : entry.direction === 'looser' ? t('权限变松') : t('普通变化')}
                </span>
                <code>{entry.path}</code>
              </div>
              <p><del>{shortValue(entry.before)}</del><ArrowRight size={13} /><ins>{shortValue(entry.after)}</ins></p>
              <button className="text-button" type="button" onClick={() => restoreDiff(entry)}>
                <RotateCcw size={13} />{t('恢复此字段到草稿')}
              </button>
            </article>
          )) : (
            <div className="agent-loop-empty"><Check size={16} />{t('这是从 v1 生成的保守 v2 投影，没有额外字段变化。')}</div>
          )}
        </div>
        <details className="contract-envelope-review">
          <summary><ShieldCheck size={14} />{t('Effective Instructions 与执行等级')}</summary>
          {preview.envelopes.map((envelope) => (
            <article key={envelope.agent_id}>
              <h4>{envelope.agent_name}<small>{envelope.delivery === 'exact_lead_payload'
                ? t('精确 Lead 载荷') : envelope.delivery === 'strict_runtime'
                  ? t('严格运行时载荷') : t('精确计划 Packet（Aion 不保证逐字转交）')}</small></h4>
              <div className="enforcement-grid">
                {Object.entries(envelope.enforcement).map(([control, level]) => (
                  <span key={control}><b>{control}</b>{t(ENFORCEMENT_LABELS[level])}</span>
                ))}
              </div>
              <details>
                <summary>{t('查看规范化载荷')} · SHA-256 {envelope.sha256.slice(0, 12)}…</summary>
                <pre>{envelope.canonical_json}</pre>
              </details>
            </article>
          ))}
        </details>
        <div className="agent-studio-edit-footer">
          <button className="text-button" type="button" onClick={() => {
            setDraft(original);
            setPreview(null);
          }}>
            <RotateCcw size={14} />{t('恢复整套原版本到草稿')}
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className={`agent-studio ${editing ? 'editing' : ''}`}>
      <header className="agent-studio-header">
        <div>
          <span className="section-kicker">{t('可视化 Agent 管理')}</span>
          <h3><Network size={18} />{t('Agent Studio')}</h3>
          <p>{t('画布用于理解关系；普通列表和六页合同编辑器是完整可访问入口。')}</p>
        </div>
        <div className="agent-studio-header-actions">
          <span className="agent-studio-count">{t('{agents} 个 Agent · {loops} 个循环', {
            agents: draft.agents.length,
            loops: draft.loops.length,
          })}</span>
          {editable && !editing && (
            <button className="secondary-button" type="button" onClick={() => setEditing(true)}>
              <PencilLine size={15} />{t(plan.schema_version === 1 ? '升级并编辑 Agent Contract' : '编辑 Agent Contract')}
            </button>
          )}
          {editable && editing && (
            <>
              <button className="text-button" type="button" disabled={saving} onClick={() => {
                setDraft(original);
                setEditing(false);
                setError('');
              }}>
                <X size={15} />{t('取消')}
              </button>
              <button
                className="secondary-button"
                type="button"
                disabled={!changed || Boolean(validation.length) || saving}
                onClick={() => void reviewChanges()}
              >
                {saving ? <LoaderCircle size={15} className="spin" /> : <FileCheck2 size={15} />}
                {t('审阅变化')}
              </button>
            </>
          )}
        </div>
      </header>

      <div className="agent-studio-body">
        <div className="agent-graph-shell">
          <div className="agent-graph-legend" aria-label={t('Agent 图图例')}>
            <span><i className="reporting" />{t('汇报')}</span>
            <span><i className="loop" />{t('复核循环')}</span>
            <span><ShieldCheck size={13} />{t('位置不进入哈希')}</span>
          </div>
          <svg className="agent-graph-canvas" viewBox={`0 0 ${layout.width} ${layout.height}`} aria-hidden="true">
            <defs>
              <marker id="agent-report-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" className="agent-report-arrow" />
              </marker>
              <marker id="agent-loop-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" className="agent-loop-arrow" />
              </marker>
            </defs>
            <g className="agent-reporting-edges">
              {draft.agents.filter((agent) => agent.reports_to_key).map((agent) => {
                const child = positionByKey.get(agent.key);
                const manager = positionByKey.get(agent.reports_to_key || '');
                if (!child || !manager) return null;
                return <path key={`report-${agent.key}`} d={curveBetween(
                  { x: manager.x + manager.width / 2, y: manager.y + manager.height },
                  { x: child.x + child.width / 2, y: child.y },
                )} markerEnd="url(#agent-report-arrow)" />;
              })}
            </g>
            <g className="agent-loop-edges">
              {draft.loops.map((loop, index) => {
                const source = positionByKey.get(loop.source_key);
                const target = positionByKey.get(loop.target_key);
                if (!source || !target) return null;
                const self = loop.source_key === loop.target_key;
                return <path
                  key={`loop-${loop.source_key}-${loop.target_key}-${index}`}
                  d={loopCurve(
                    { x: source.x + source.width, y: source.y + source.height / 2 + index * 3 },
                    self
                      ? { x: source.x + source.width, y: source.y + source.height / 2 + index * 3 }
                      : { x: target.x, y: target.y + target.height / 2 + index * 3 },
                    self,
                  )}
                  markerEnd="url(#agent-loop-arrow)"
                />;
              })}
            </g>
            {layout.positions.map((position) => {
              const agent = agentByKey.get(position.key);
              if (!agent) return null;
              return (
                <foreignObject key={agent.key} x={position.x} y={position.y} width={position.width} height={position.height}>
                  <button type="button" tabIndex={-1} className={`agent-graph-node role-${agent.role} ${agent.key === selected?.key ? 'selected' : ''}`} onClick={() => setSelectedKey(agent.key)}>
                    <span className="agent-graph-node-top"><Bot size={16} /><small>{t(ROLE_LABELS[agent.role])}</small></span>
                    <strong>{agent.name || t('未命名 Agent')}</strong>
                    <span>{t(RUNTIME_LABELS[agent.runtime])} · {agent.model}</span>
                    <small>{t('{count} 个负责阶段', { count: draft.stages.filter((stage) => stage.owner_key === agent.key).length })}</small>
                  </button>
                </foreignObject>
              );
            })}
          </svg>
          <div className="agent-dom-list" role="list" aria-label={t('Agent 普通列表')}>
            {draft.agents.map((agent) => (
              <button
                role="listitem"
                type="button"
                key={agent.key}
                aria-current={agent.key === selected?.key ? 'true' : undefined}
                onClick={() => setSelectedKey(agent.key)}
              >
                <Bot size={15} /><span><b>{agent.name}</b><small>{t(ROLE_LABELS[agent.role])} · {t(RUNTIME_LABELS[agent.runtime])}</small></span>
              </button>
            ))}
            {editing && (
              <button type="button" disabled={draft.agents.length >= 5} onClick={addAgent}>
                <Plus size={15} /><span><b>{t('添加 Agent')}</b><small>{t('最多 5 名')}</small></span>
              </button>
            )}
          </div>
        </div>

        <aside className="agent-inspector" aria-label={t('Agent 合同属性')}>
          {selected ? (
            <>
              <div className="agent-inspector-heading">
                <div className="agent-inspector-icon"><Bot size={18} /></div>
                <div><span>{t('当前 Agent')}</span><strong>{selected.name || t('未命名 Agent')}</strong></div>
                {editing && selected.role !== 'lead' && (
                  <button className="icon-button" type="button" aria-label={t('删除 Agent')} onClick={() => deleteAgent(selected.key)}>
                    <Trash2 size={15} />
                  </button>
                )}
              </div>
              <nav className="agent-contract-tabs" aria-label={t('Agent Contract 六页编辑器')}>
                {TABS.map(([id, label]) => (
                  <button type="button" key={id} aria-current={activeTab === id ? 'page' : undefined} onClick={() => setActiveTab(id)}>
                    {t(label)}
                  </button>
                ))}
              </nav>

              {activeTab === 'basic' && (
                <div className="agent-inspector-fields">
                  <label><span>{t('名称')}</span><input value={selected.name} maxLength={80} disabled={!editing} onChange={(event) => updateAgent(selected.key, { name: event.target.value })} /></label>
                  <label><span>{t('角色')}</span><select value={selected.role} disabled={!editing} onChange={(event) => changeRole(selected.key, event.target.value as AgentGraphDraftAgent['role'])}>
                    {Object.entries(ROLE_LABELS).map(([value, label]) => <option key={value} value={value}>{t(label)}</option>)}
                  </select></label>
                  {selected.role !== 'lead' && <label><span>{t('直属上级')}</span><select value={selected.reports_to_key || ''} disabled={!editing} onChange={(event) => updateAgent(selected.key, { reports_to_key: event.target.value || null })}>
                    <option value="">{t('请选择')}</option>
                    {draft.agents.filter((agent) => agent.key !== selected.key).map((agent) => <option key={agent.key} value={agent.key}>{agent.name}</option>)}
                  </select></label>}
                  <label><span>{t('团队执行等级')}</span><select value={draft.runtime_mode} disabled={!editing} onChange={(event) => setDraft((current) => ({ ...current, runtime_mode: event.target.value as AgentGraphDraft['runtime_mode'] }))}>
                    <option value="aion_compatible">{t('Aion 兼容 · 部分为执行指令')}</option>
                    <option value="strict">{t('严格运行时 · 不可用时拒绝运行')}</option>
                  </select></label>
                </div>
              )}

              {activeTab === 'method' && (
                <div className="agent-inspector-fields">
                  <label><span>{t('职责与边界')}</span><textarea rows={4} maxLength={600} value={selected.responsibility} disabled={!editing} onChange={(event) => updateAgent(selected.key, { responsibility: event.target.value })} /></label>
                  <label><span>{t('完整工作指令')}</span><textarea rows={8} maxLength={12000} value={selected.contract.instructions} disabled={!editing} onChange={(event) => updateContract(selected.key, { instructions: event.target.value })} /></label>
                  <label><span>{t('明确禁止事项 · 每行一条')}</span><textarea rows={5} value={lines(selected.contract.prohibitions)} disabled={!editing} onChange={(event) => updateContract(selected.key, { prohibitions: parseLines(event.target.value) })} /></label>
                </div>
              )}

              {activeTab === 'results' && (
                <div className="agent-inspector-fields">
                  <div className="contract-tool-list">
                    <div className="agent-inspector-subheading">
                      <span>{t('输入合同')}</span>
                      <small>{t('输入可绑定路径，或绑定另一个 Agent 的确切产物。')}</small>
                    </div>
                    {selected.contract.inputs.map((input, index) => {
                      const source = draft.agents.find(
                        (agent) => agent.key === input.source_agent_id,
                      );
                      return (
                        <div className="contract-io-card" key={input.input_id}>
                          <label><span>{t('输入名称')}</span><input value={input.label} disabled={!editing} onChange={(event) => updateContract(selected.key, { inputs: selected.contract.inputs.map((row, rowIndex) => rowIndex === index ? { ...row, label: event.target.value } : row) })} /></label>
                          <label><span>{t('相对路径')}</span><input value={input.relative_path || ''} disabled={!editing} onChange={(event) => updateContract(selected.key, { inputs: selected.contract.inputs.map((row, rowIndex) => rowIndex === index ? { ...row, relative_path: event.target.value || null } : row) })} /></label>
                          <label><span>{t('来源 Agent')}</span><select value={input.source_agent_id || ''} disabled={!editing} onChange={(event) => updateContract(selected.key, { inputs: selected.contract.inputs.map((row, rowIndex) => rowIndex === index ? { ...row, source_agent_id: event.target.value || null, source_output_id: null } : row) })}><option value="">{t('外部或操作员输入')}</option>{draft.agents.filter((agent) => agent.key !== selected.key).map((agent) => <option key={agent.key} value={agent.key}>{agent.name}</option>)}</select></label>
                          <label><span>{t('来源产物')}</span><select value={input.source_output_id || ''} disabled={!editing || !source} onChange={(event) => updateContract(selected.key, { inputs: selected.contract.inputs.map((row, rowIndex) => rowIndex === index ? { ...row, source_output_id: event.target.value || null } : row) })}><option value="">{t('请选择')}</option>{(source?.contract.outputs || []).map((output) => <option key={output.output_id} value={output.output_id}>{output.label} · {output.relative_path}</option>)}</select></label>
                          <label className="contract-checkbox"><input type="checkbox" checked={input.required} disabled={!editing} onChange={(event) => updateContract(selected.key, { inputs: selected.contract.inputs.map((row, rowIndex) => rowIndex === index ? { ...row, required: event.target.checked } : row) })} /><span>{t('必需')}</span></label>
                          {editing && <button className="text-button" type="button" onClick={() => updateContract(selected.key, { inputs: selected.contract.inputs.filter((_, rowIndex) => rowIndex !== index) })}><Trash2 size={13} />{t('删除输入')}</button>}
                        </div>
                      );
                    })}
                    {editing && selected.contract.inputs.length < 30 && <button className="text-button" type="button" onClick={() => updateContract(selected.key, { inputs: [...selected.contract.inputs, { input_id: `input_${crypto.randomUUID().replaceAll('-', '').slice(0, 12)}`, label: 'New input', relative_path: null, source_agent_id: null, source_output_id: null, required: true, sha256: null }] })}><Plus size={13} />{t('添加输入')}</button>}
                  </div>
                  <div className="contract-tool-list">
                    <div className="agent-inspector-subheading">
                      <span>{t('预期输出合同')}</span>
                      <small>{t('每个必需产物都会在运行结束后核对 SHA-256 与 CAS。')}</small>
                    </div>
                    {selected.contract.outputs.map((output, index) => (
                      <div className="contract-io-card" key={output.output_id}>
                        <label><span>{t('输出名称')}</span><input value={output.label} disabled={!editing} onChange={(event) => updateContract(selected.key, { outputs: selected.contract.outputs.map((row, rowIndex) => rowIndex === index ? { ...row, label: event.target.value } : row) })} /></label>
                        <label><span>{t('相对路径')}</span><input value={output.relative_path} disabled={!editing} onChange={(event) => {
                          const relativePath = event.target.value;
                          updateContract(selected.key, {
                            outputs: selected.contract.outputs.map((row, rowIndex) => rowIndex === index ? { ...row, relative_path: relativePath } : row),
                            data_scope: {
                              ...selected.contract.data_scope,
                              allowed_relative_paths: [...new Set([...selected.contract.data_scope.allowed_relative_paths, relativePath].filter(Boolean))],
                            },
                          });
                        }} /></label>
                        <label><span>{t('媒体类型')}</span><input value={output.media_type || ''} disabled={!editing} placeholder="application/json" onChange={(event) => updateContract(selected.key, { outputs: selected.contract.outputs.map((row, rowIndex) => rowIndex === index ? { ...row, media_type: event.target.value || null } : row) })} /></label>
                        <label><span>{t('产物验收标准 · 每行一条')}</span><textarea rows={3} value={lines(output.acceptance_criteria)} disabled={!editing} onChange={(event) => updateContract(selected.key, { outputs: selected.contract.outputs.map((row, rowIndex) => rowIndex === index ? { ...row, acceptance_criteria: parseLines(event.target.value) } : row) })} /></label>
                        <label className="contract-checkbox"><input type="checkbox" checked={output.required} disabled={!editing} onChange={(event) => updateContract(selected.key, { outputs: selected.contract.outputs.map((row, rowIndex) => rowIndex === index ? { ...row, required: event.target.checked } : row) })} /><span>{t('必需')}</span></label>
                        {editing && <button className="text-button" type="button" onClick={() => updateContract(selected.key, { outputs: selected.contract.outputs.filter((_, rowIndex) => rowIndex !== index) })}><Trash2 size={13} />{t('删除输出')}</button>}
                      </div>
                    ))}
                    {editing && selected.contract.outputs.length < 30 && <button className="text-button" type="button" onClick={() => {
                      const outputId = `output_${crypto.randomUUID().replaceAll('-', '').slice(0, 12)}`;
                      const relativePath = `artifacts/${outputId}.json`;
                      updateContract(selected.key, {
                        outputs: [...selected.contract.outputs, { output_id: outputId, label: 'New output', relative_path: relativePath, media_type: 'application/json', acceptance_criteria: [], required: true }],
                        data_scope: { ...selected.contract.data_scope, allowed_relative_paths: [...new Set([...selected.contract.data_scope.allowed_relative_paths, relativePath])] },
                      });
                    }}><Plus size={13} />{t('添加输出')}</button>}
                  </div>
                  <label><span>{t('验收标准 · 每行一条')}</span><textarea rows={5} value={lines(selected.contract.acceptance_criteria)} disabled={!editing} onChange={(event) => updateContract(selected.key, { acceptance_criteria: parseLines(event.target.value) })} /></label>
                  <div className="agent-stage-owners">
                    <div className="agent-inspector-subheading"><span><GitBranch size={14} />{t('阶段负责人')}</span></div>
                    {draft.stages.map((stage) => <label key={stage.order}><span><b>{stage.order}</b>{stage.title}</span><select value={stage.owner_key} disabled={!editing} onChange={(event) => setDraft((current) => ({
                      ...current,
                      stages: current.stages.map((row) => row.order === stage.order ? { ...row, owner_key: event.target.value } : row),
                    }))}>{draft.agents.map((agent) => <option key={agent.key} value={agent.key}>{agent.name}</option>)}</select></label>)}
                  </div>
                </div>
              )}

              {activeTab === 'controls' && (
                <div className="agent-inspector-fields">
                  <label><span>{t('允许的数据相对路径 · 每行一个')}</span><textarea rows={4} value={lines(selected.contract.data_scope.allowed_relative_paths)} disabled={!editing} onChange={(event) => updateContract(selected.key, { data_scope: { ...selected.contract.data_scope, allowed_relative_paths: parseLines(event.target.value) } })} /></label>
                  <label><span>{t('受管网络域名白名单 · 每行一个')}</span><textarea rows={3} value={lines(selected.contract.data_scope.managed_network_domains || [])} disabled={!editing} onChange={(event) => updateContract(selected.key, { data_scope: { ...selected.contract.data_scope, managed_network_domains: parseLines(event.target.value) } })} /><small>{t('仅适用于 OpsWitness 管理的网络工具；任意 Shell 联网不受支持。')}</small></label>
                  <fieldset className="contract-memory-picker">
                    <legend>{t('Workspace Memory 版本')}</legend>
                    {draft.runtime_mode === 'aion_compatible' && selected.role !== 'lead' && <small>{t('Aion 兼容模式不能证明非 Lead 的私有 Memory 投递；请使用严格模式。')}</small>}
                    {approvedMemories.length ? approvedMemories.map((memory) => {
                      const checked = selected.contract.memory.version_ids.includes(memory.version_id);
                      const disabled = !editing || (draft.runtime_mode === 'aion_compatible' && selected.role !== 'lead');
                      return <label key={memory.version_id}><input type="checkbox" checked={checked} disabled={disabled} onChange={() => {
                        const versionIds = checked
                          ? selected.contract.memory.version_ids.filter((id) => id !== memory.version_id)
                          : [...selected.contract.memory.version_ids, memory.version_id];
                        updateContract(selected.key, { memory: { mode: versionIds.length ? 'selected' : 'none', version_ids: versionIds } });
                      }} /><span>{memory.title}<small>v{memory.version_number} · {memory.content_sha256.slice(0, 10)}…</small></span></label>;
                    }) : <small>{t('当前 Work 没有可选的已批准 Memory。')}</small>}
                  </fieldset>
                  <div className="contract-control-grid">
                    {([
                      ['file_write', '文件写入'],
                      ['operator_input', '询问用户'],
                      ['managed_network', '受管网络'],
                      ['send', '发送'],
                      ['publish', '发布'],
                      ['delete', '删除'],
                    ] as const).map(([key, label]) => <label key={key}><span>{t(label)}</span><ControlSelect value={selected.contract.side_effects[key]} disabled={!editing} onChange={(value) => updateContract(selected.key, { side_effects: { ...selected.contract.side_effects, [key]: value } })} /></label>)}
                  </div>
                  <div className="contract-tool-list">
                    <div className="agent-inspector-subheading"><span>{t('工具规则')}</span><small>{t('未知工具始终拒绝')}</small></div>
                    {selected.contract.tool_rules.map((rule, index) => <label key={`${rule.tool_name}-${index}`}><input value={rule.tool_name} disabled={!editing} onChange={(event) => updateContract(selected.key, { tool_rules: selected.contract.tool_rules.map((row, rowIndex) => rowIndex === index ? { ...row, tool_name: event.target.value } : row) })} /><ControlSelect value={rule.policy} disabled={!editing} onChange={(value) => updateContract(selected.key, { tool_rules: selected.contract.tool_rules.map((row, rowIndex) => rowIndex === index ? { ...row, policy: value } : row) })} />{editing && <button className="icon-button" type="button" onClick={() => updateContract(selected.key, { tool_rules: selected.contract.tool_rules.filter((_, rowIndex) => rowIndex !== index) })}><Trash2 size={13} /></button>}</label>)}
                    {editing && <button className="text-button" type="button" onClick={() => updateContract(selected.key, { tool_rules: [...selected.contract.tool_rules, { tool_name: 'new_tool', policy: 'deny' }] })}><Plus size={13} />{t('添加工具规则')}</button>}
                  </div>
                </div>
              )}

              {activeTab === 'collaboration' && (
                <div className="agent-inspector-fields">
                  <fieldset><legend>{t('允许移交给')}</legend>{draft.agents.filter((agent) => agent.key !== selected.key).map((agent) => {
                    const checked = selected.contract.handoff.allowed_target_agent_ids.includes(agent.key);
                    return <label key={agent.key}><input type="checkbox" checked={checked} disabled={!editing} onChange={() => updateContract(selected.key, { handoff: { ...selected.contract.handoff, allowed_target_agent_ids: checked ? selected.contract.handoff.allowed_target_agent_ids.filter((id) => id !== agent.key) : [...selected.contract.handoff.allowed_target_agent_ids, agent.key] } })} /><span>{agent.name}</span></label>;
                  })}</fieldset>
                  <label><span>{t('升级给')}</span><select value={selected.contract.escalation.target_agent_id || ''} disabled={!editing} onChange={(event) => updateContract(selected.key, { escalation: { ...selected.contract.escalation, target_agent_id: event.target.value || null } })}><option value="">{t('不自动升级')}</option>{draft.agents.filter((agent) => agent.key !== selected.key).map((agent) => <option key={agent.key} value={agent.key}>{agent.name}</option>)}</select></label>
                  <label><span>{t('升级条件 · 每行一条')}</span><textarea rows={3} value={lines(selected.contract.escalation.conditions)} disabled={!editing} onChange={(event) => updateContract(selected.key, { escalation: { ...selected.contract.escalation, conditions: parseLines(event.target.value) } })} /></label>
                  <label><span>{t('审批检查点 · 每行一条')}</span><textarea rows={3} value={lines(selected.contract.approval_checkpoints)} disabled={!editing} onChange={(event) => updateContract(selected.key, { approval_checkpoints: parseLines(event.target.value) })} /></label>
                  <div className="contract-control-grid">
                    <label><span>{t('最多尝试次数')}</span><input type="number" min={1} max={5} value={selected.contract.retry.max_attempts} disabled={!editing} onChange={(event) => updateContract(selected.key, { retry: { ...selected.contract.retry, max_attempts: Number(event.target.value), retryable_errors: Number(event.target.value) === 1 ? [] : selected.contract.retry.retryable_errors } })} /></label>
                    <label><span>{t('阶段超时（秒）')}</span><input type="number" min={30} max={86400} value={selected.contract.stop.timeout_seconds} disabled={!editing} onChange={(event) => updateContract(selected.key, { stop: { ...selected.contract.stop, timeout_seconds: Number(event.target.value) } })} /></label>
                  </div>
                  <label><span>{t('停止条件 · 每行一条')}</span><textarea rows={4} value={lines(selected.contract.stop.stop_conditions)} disabled={!editing} onChange={(event) => updateContract(selected.key, { stop: { ...selected.contract.stop, stop_conditions: parseLines(event.target.value) } })} /></label>
                </div>
              )}

              {activeTab === 'model' && (
                <div className="agent-inspector-fields">
                  <label><span>{t('运行时')}</span><select value={selected.runtime} disabled={!editing} onChange={(event) => changeRuntime(selected.key, event.target.value as AgentGraphDraftAgent['runtime'])}>{runtimeCapabilities.filter((capability) => SHOW_ANTHROPIC_PROVIDER_UI || capability.runtime !== 'claude_code' || selected.runtime === 'claude_code').map((capability) => <option key={capability.runtime} value={capability.runtime} disabled={!capability.available || (!SHOW_ANTHROPIC_PROVIDER_UI && capability.runtime === 'claude_code')}>{t(capability.label)}{capability.available && (SHOW_ANTHROPIC_PROVIDER_UI || capability.runtime !== 'claude_code') ? '' : ` · ${t('不可用')}`}</option>)}</select></label>
                  <label><span>{t('模型')}</span><select value={selected.model} disabled={!editing || !selectedCapability?.available} onChange={(event) => {
                    const option = selectedModels.find((model) => model.id === event.target.value);
                    updateAgent(selected.key, { model: event.target.value, model_binding: option?.pinning || 'exact', runtime_reason: '由操作员选择；保存时写入新的不可变方案版本。' });
                  }}>{!selectedModels.some((model) => model.id === selected.model) && <option value={selected.model}>{selected.model} · {t('当前选择')}</option>}{selectedModels.map((model) => <option key={model.id} value={model.id}>{t(model.label)} · {model.id} · {model.pinning}</option>)}</select></label>
                  <div className="runtime-binding-card"><Cpu size={16} /><span><b>{selected.model_binding === 'exact' ? t('Exact ID') : selected.model_binding === 'alias' ? t('Rolling alias') : t('Provider default')}</b><small>{selected.runtime_binding.adapter_version}</small><code>{selected.runtime_binding.executable_sha256 || t('可执行文件 Digest 将在服务端预览时绑定')}</code></span></div>
                  <label><span>{t('运行时选择理由')}</span><textarea rows={3} value={selected.runtime_reason} disabled={!editing} onChange={(event) => updateAgent(selected.key, { runtime_reason: event.target.value })} /></label>
                </div>
              )}

              <details className="effective-instructions">
                <summary><CircleDot size={14} />{t('Effective Instructions 三层预览')}</summary>
                <h4>{t('1. 操作员指令')}</h4><pre>{selected.contract.instructions}</pre>
                <h4>{t('2. 结构化合同')}</h4><pre>{JSON.stringify(selected.contract, null, 2)}</pre>
                <h4>{t('3. 只读平台安全层')}</h4><p>{t('未知 Agent/工具拒绝；凭证不得进入日志或产物；进程完成不等于业务结果；供应商隐藏指令不可见。')}</p>
                <p><strong>{t('负责阶段')}</strong>{selectedOwnedStages.map((stage) => `${stage.order}. ${stage.title}`).join('；') || t('暂无')}</p>
              </details>
            </>
          ) : <div className="agent-inspector-empty"><Bot size={22} />{t('选择一个 Agent 查看属性')}</div>}
        </aside>
      </div>

      <div className="agent-loop-editor">
        <div className="agent-loop-editor-heading"><div><span><Repeat2 size={15} />{t('有界复核循环')}</span><small>{draft.runtime_mode === 'strict' ? t('严格运行时硬执行次数上限。') : t('Aion 兼容模式仅作为执行指令。')}</small></div>{editing && <button className="text-button" type="button" disabled={draft.loops.length >= 5} onClick={addLoop}><Plus size={14} />{t('添加循环')}</button>}</div>
        {draft.loops.length ? <div className="agent-loop-grid">{draft.loops.map((loop, index) => <article className="agent-loop-card" key={`${loop.source_key}-${loop.target_key}-${index}`}><div className="agent-loop-route">{editing ? <><select value={loop.source_key} onChange={(event) => setDraft((current) => ({ ...current, loops: current.loops.map((row, rowIndex) => rowIndex === index ? { ...row, source_key: event.target.value } : row) }))}>{draft.agents.map((agent) => <option key={agent.key} value={agent.key}>{agent.name}</option>)}</select><ArrowRight size={15} /><select value={loop.target_key} onChange={(event) => setDraft((current) => ({ ...current, loops: current.loops.map((row, rowIndex) => rowIndex === index ? { ...row, target_key: event.target.value } : row) }))}>{draft.agents.map((agent) => <option key={agent.key} value={agent.key}>{agent.name}</option>)}</select></> : <><strong>{agentByKey.get(loop.source_key)?.name}</strong><ArrowRight size={15} /><strong>{agentByKey.get(loop.target_key)?.name}</strong></>}<span>{t('最多 {count} 轮', { count: loop.max_iterations })}</span>{editing && <button className="icon-button" type="button" onClick={() => setDraft((current) => ({ ...current, loops: current.loops.filter((_, rowIndex) => rowIndex !== index) }))}><Trash2 size={14} /></button>}</div>{editing ? <div className="agent-loop-fields"><label><span>{t('返回与停止条件')}</span><input value={loop.condition} onChange={(event) => setDraft((current) => ({ ...current, loops: current.loops.map((row, rowIndex) => rowIndex === index ? { ...row, condition: event.target.value } : row) }))} /></label><label><span>{t('最多轮次')}</span><input type="number" min={1} max={10} value={loop.max_iterations} onChange={(event) => setDraft((current) => ({ ...current, loops: current.loops.map((row, rowIndex) => rowIndex === index ? { ...row, max_iterations: Number(event.target.value) } : row) }))} /></label></div> : <p>{loop.condition}</p>}</article>)}</div> : <div className="agent-loop-empty"><Repeat2 size={17} />{t('没有循环；阶段按顺序执行一次。')}</div>}
      </div>

      {editing && <div className="agent-studio-edit-footer"><span><ShieldCheck size={14} />{t('保存顺序：编辑 → 审阅字段变化 → 创建新版本 → 再确认运行。')}</span><button className="text-button" type="button" onClick={() => { setDraft(original); setError(''); }}><RotateCcw size={14} />{t('撤销本次编辑')}</button></div>}
      {(validationMessage || error) && <div className="agent-studio-error" role="alert"><CircleDot size={15} /><span>{error || validationMessage}</span></div>}
    </section>
  );
}
