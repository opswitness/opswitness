const ROLE_VALUES = new Set([
  'lead',
  'researcher',
  'operator',
  'reviewer',
  'reporter',
  'specialist',
]);

const RUNTIME_VALUES = new Set(['claude_code', 'codex_cli', 'aion_cli']);
const CONTROL_VALUES = new Set(['deny', 'always_ask', 'inherit_run_mode']);

const PLATFORM_TOOLS = [
  'ListMcpResourcesTool',
  'ToolSearch',
  'mcp__aionui-team__team_list_assistants',
  'mcp__aionui-team__team_members',
  'mcp__aionui-team__team_send_message',
  'mcp__aionui-team__team_task_create',
  'mcp__aionui-team__team_task_list',
  'mcp__aionui-team__team_task_update',
  'mcp__opswitness__qd_artifact_verify',
  'mcp__opswitness__qd_artifacts',
  'mcp__opswitness__qd_request_input',
];

function exactToolIdentifier(value) {
  return /^[A-Za-z0-9_.:-]+$/.test(value);
}

function outputPath(label, index) {
  const safe = label
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48);
  return `artifacts/${safe || `output-${index}`}.json`;
}

function defaultContract(plan, agent, index) {
  const hasReporter = plan.agents.some((candidate) => candidate.role === 'reporter');
  const ownsDelivery = hasReporter ? agent.role === 'reporter' : agent.role === 'lead';
  const outputs = ownsDelivery
    ? (plan.artifacts || []).map((label, outputIndex) => ({
      output_id: `output_${index + 1}_${outputIndex + 1}`,
      label,
      relative_path: outputPath(label, outputIndex + 1),
      media_type: null,
      acceptance_criteria: [],
      required: true,
    }))
    : [];
  return {
    schema_version: 1,
    instructions: agent.responsibility,
    prohibitions: [
      'Do not expand beyond the reviewed Work objective and constraints.',
      'Do not claim a business result from process completion alone.',
    ],
    inputs: [],
    outputs,
    acceptance_criteria: [],
    default_tool_policy: 'deny',
    tool_rules: [...new Set([
      ...PLATFORM_TOOLS,
      ...(plan.tools || []).filter(exactToolIdentifier),
    ])].map((toolName) => ({
      tool_name: toolName,
      policy: 'always_ask',
    })),
    data_scope: {
      allowed_relative_paths: outputs.map((output) => output.relative_path),
      attachment_ids: [],
      managed_network_domains: [],
    },
    side_effects: {
      file_write: 'deny',
      operator_input: 'deny',
      managed_network: 'deny',
      send: 'deny',
      publish: 'deny',
      delete: 'deny',
    },
    memory: { mode: 'none', version_ids: [] },
    handoff: {
      allowed_target_agent_ids: [],
      acceptance_criteria: [],
      require_cas_receipt: true,
    },
    escalation: { target_agent_id: null, conditions: [] },
    approval_checkpoints: [...(plan.approvals || [])],
    retry: { max_attempts: 1, retryable_errors: [], backoff_seconds: 5 },
    stop: {
      timeout_seconds: Math.max(
        30,
        Math.min(86400, (plan.estimated_duration_minutes || 15) * 60),
      ),
      stop_conditions: [
        'A required approval is rejected.',
        'A required artifact digest or acceptance check fails.',
      ],
      stop_on_approval_rejection: true,
      stop_on_contract_violation: true,
      stop_on_digest_mismatch: true,
    },
  };
}

export function createAgentGraphDraft(plan) {
  const lead = plan.agents.find((agent) => agent.role === 'lead') || plan.agents[0];
  const keyByName = new Map(
    plan.agents.map((agent, index) => [
      agent.name,
      agent.agent_id || `new:legacy_${index + 1}`,
    ]),
  );
  const keyById = new Map(
    plan.agents
      .filter((agent) => agent.agent_id)
      .map((agent) => [agent.agent_id, agent.agent_id]),
  );
  const hasExplicitHierarchy = plan.schema_version === 2
    || plan.agents.some((agent) => Boolean(agent.reports_to));
  const agents = plan.agents.map((agent, index) => {
    const key = agent.agent_id || `new:legacy_${index + 1}`;
    const managerKey = plan.schema_version === 2
      ? agent.reports_to_agent_id || null
      : hasExplicitHierarchy
        ? (agent.reports_to ? keyByName.get(agent.reports_to) || null : null)
        : agent.name === lead.name ? null : keyByName.get(lead.name) || null;
    return {
      key,
      name: agent.name,
      role: agent.role,
      responsibility: agent.responsibility,
      runtime: agent.runtime,
      model: agent.model || 'default',
      model_binding: agent.model_binding || (agent.model && agent.model !== 'default' ? 'exact' : 'default'),
      runtime_binding: agent.runtime_binding || {
        adapter_version: 'Resolved by OpsWitness during preview',
        executable_sha256: null,
        status: 'unverified',
      },
      runtime_reason: agent.runtime_reason || '当前方案未记录运行时推荐理由。',
      reports_to_key: managerKey,
      contract: agent.contract
        ? structuredClone(agent.contract)
        : defaultContract(plan, agent, index),
    };
  });
  const knownKey = (id, name) => keyById.get(id) || keyByName.get(name) || '';
  return {
    schema_version: 2,
    runtime_mode: plan.runtime_mode || 'aion_compatible',
    agents,
    loops: (plan.collaboration_loops || []).map((loop) => ({
      source_key: knownKey(loop.source_agent_id, loop.source_agent),
      target_key: knownKey(loop.target_agent_id, loop.target_agent),
      condition: loop.condition,
      max_iterations: loop.max_iterations,
    })),
    stages: plan.stages.map((stage) => ({
      order: stage.order,
      title: stage.title,
      outcome: stage.outcome,
      checkpoint: stage.checkpoint,
      owner_key: knownKey(stage.owner_agent_id, stage.owner),
    })),
  };
}

function validRelativePath(value) {
  return typeof value === 'string'
    && value.length > 0
    && value === value.trim()
    && !value.startsWith('/')
    && !value.startsWith('~')
    && !value.includes('\\')
    && value.split('/').every((part) => part && part !== '.' && part !== '..');
}

export function validateAgentGraphDraft(draft) {
  const errors = [];
  if (!Array.isArray(draft.agents) || draft.agents.length < 1 || draft.agents.length > 5) {
    errors.push('agent_count');
    return errors;
  }
  const keys = new Set(draft.agents.map((agent) => agent.key));
  if (keys.size !== draft.agents.length || keys.has('')) errors.push('agent_keys');
  const names = draft.agents.map((agent) => agent.name.trim().toLocaleLowerCase());
  if (names.some((name) => !name) || new Set(names).size !== names.length) {
    errors.push('agent_names');
  }
  if (draft.agents.some((agent) => (
    !ROLE_VALUES.has(agent.role)
    || !RUNTIME_VALUES.has(agent.runtime)
    || !agent.responsibility.trim()
    || !agent.model.trim()
    || !agent.contract.instructions.trim()
    || agent.contract.default_tool_policy !== 'deny'
  ))) {
    errors.push('agent_contract');
  }
  const leads = draft.agents.filter((agent) => agent.role === 'lead');
  if (leads.length !== 1) errors.push('lead_count');
  const lead = leads[0];
  if (lead && lead.reports_to_key !== null) errors.push('lead_manager');

  const parents = new Map();
  for (const agent of draft.agents) {
    if (agent.role === 'lead') continue;
    if (
      !agent.reports_to_key
      || !keys.has(agent.reports_to_key)
      || agent.reports_to_key === agent.key
    ) {
      errors.push('manager_missing');
      continue;
    }
    parents.set(agent.key, agent.reports_to_key);
  }
  for (const agent of draft.agents) {
    const seen = new Set([agent.key]);
    let cursor = agent.key;
    while (parents.has(cursor)) {
      cursor = parents.get(cursor);
      if (seen.has(cursor)) {
        errors.push('reporting_cycle');
        break;
      }
      seen.add(cursor);
    }
  }

  if (!Array.isArray(draft.loops) || draft.loops.length > 5) errors.push('loop_count');
  const loopPairs = new Set();
  for (const loop of draft.loops || []) {
    const pair = `${loop.source_key}:${loop.target_key}`;
    if (
      !keys.has(loop.source_key)
      || !keys.has(loop.target_key)
      || !loop.condition.trim()
      || loop.condition.trim().length < 3
      || !Number.isInteger(loop.max_iterations)
      || loop.max_iterations < 1
      || loop.max_iterations > 10
      || loopPairs.has(pair)
    ) {
      errors.push('loop_invalid');
    }
    loopPairs.add(pair);
  }

  const stageOrders = new Set();
  for (const stage of draft.stages || []) {
    if (
      !Number.isInteger(stage.order)
      || stageOrders.has(stage.order)
      || !keys.has(stage.owner_key)
    ) {
      errors.push('stage_owner');
    }
    stageOrders.add(stage.order);
  }

  const outputOwners = new Map(
    draft.agents.flatMap((agent) => (
      agent.contract.outputs.map((output) => [output.output_id, agent.key])
    )),
  );
  const outputIds = draft.agents.flatMap(
    (agent) => agent.contract.outputs.map((output) => output.output_id),
  );
  for (const agent of draft.agents) {
    const contract = agent.contract;
    const paths = contract.data_scope.allowed_relative_paths;
    const domains = contract.data_scope.managed_network_domains || [];
    if (
      paths.some((path) => !validRelativePath(path))
      || contract.inputs.some((input) => (
        input.relative_path && !validRelativePath(input.relative_path)
      ))
      || contract.outputs.some((output) => (
        !validRelativePath(output.relative_path)
        || !paths.includes(output.relative_path)
      ))
      || domains.some((domain) => (
        domain !== domain.toLocaleLowerCase()
        || domain.includes('://')
        || domain.includes(':')
        || domain.includes('*')
        || !domain.split('.').every((label) => (
          /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label)
        ))
      ))
    ) errors.push('contract_paths');
    if (
      contract.tool_rules.some((rule) => (
        !rule.tool_name
        || !exactToolIdentifier(rule.tool_name)
        || !CONTROL_VALUES.has(rule.policy)
      ))
      || contract.retry.max_attempts < 1
      || contract.retry.max_attempts > 5
      || contract.stop.timeout_seconds < 30
    ) errors.push('contract_controls');
    const references = [
      ...contract.handoff.allowed_target_agent_ids,
      ...(contract.escalation.target_agent_id ? [contract.escalation.target_agent_id] : []),
      ...contract.inputs.flatMap((input) => (
        input.source_agent_id ? [input.source_agent_id] : []
      )),
    ];
    if (references.some((reference) => !keys.has(reference))) {
      errors.push('contract_references');
    }
    if (contract.inputs.some((input) => (
      Boolean(input.source_agent_id) !== Boolean(input.source_output_id)
      || (
        input.source_output_id
        && outputOwners.get(input.source_output_id) !== input.source_agent_id
      )
    ))) {
      errors.push('contract_references');
    }
  }
  if (
    outputIds.some((outputId) => !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(outputId))
    || new Set(outputIds).size !== outputIds.length
  ) {
    errors.push('output_ids');
  }
  return [...new Set(errors)];
}

export function agentGraphFingerprint(draft) {
  return JSON.stringify(draft);
}

export function agentGraphRevisionRequest(draft, expectedPlanSha256) {
  const nameByKey = new Map(draft.agents.map((agent) => [agent.key, agent.name.trim()]));
  return {
    expected_plan_sha256: expectedPlanSha256,
    agents: draft.agents.map((agent) => ({
      name: agent.name.trim(),
      role: agent.role,
      responsibility: agent.responsibility.trim(),
      runtime: agent.runtime,
      model: agent.model,
      runtime_reason: agent.runtime_reason,
      reports_to: agent.reports_to_key
        ? nameByKey.get(agent.reports_to_key) || null
        : null,
    })),
    collaboration_loops: draft.loops.map((loop) => ({
      source_agent: nameByKey.get(loop.source_key) || '',
      target_agent: nameByKey.get(loop.target_key) || '',
      condition: loop.condition.trim(),
      max_iterations: loop.max_iterations,
    })),
    stage_assignments: draft.stages.map((stage) => ({
      stage_order: stage.order,
      owner: nameByKey.get(stage.owner_key) || '',
    })),
    confirmed: true,
  };
}

export function agentContractPlanDraft(draft, plan) {
  return {
    schema_version: 2,
    title: plan.title,
    summary: plan.summary,
    execution_profile: plan.execution_profile || null,
    execution_mode: 'aion_team',
    workflow_id: null,
    runtime_mode: draft.runtime_mode,
    agents: draft.agents.map((agent) => ({
      agent_id: agent.key,
      name: agent.name.trim(),
      role: agent.role,
      responsibility: agent.responsibility.trim(),
      runtime: agent.runtime,
      model: agent.model,
      model_binding: agent.model_binding,
      runtime_binding: agent.runtime_binding,
      runtime_reason: agent.runtime_reason,
      reports_to_agent_id: agent.reports_to_key,
      contract: structuredClone(agent.contract),
    })),
    collaboration_loops: draft.loops.map((loop) => ({
      source_agent_id: loop.source_key,
      target_agent_id: loop.target_key,
      condition: loop.condition.trim(),
      max_iterations: loop.max_iterations,
    })),
    stages: draft.stages.map((stage) => ({
      order: stage.order,
      title: stage.title,
      owner_agent_id: stage.owner_key,
      outcome: stage.outcome,
      checkpoint: stage.checkpoint,
    })),
    cadence: structuredClone(plan.cadence),
    tools: [...plan.tools],
    approvals: [...plan.approvals],
    artifacts: [...plan.artifacts],
    risks: [...plan.risks],
    estimated_duration_minutes: plan.estimated_duration_minutes,
    update_policy: plan.update_policy,
  };
}

export function layoutAgentGraph(draft) {
  const parentByKey = new Map(
    draft.agents
      .filter((agent) => agent.reports_to_key)
      .map((agent) => [agent.key, agent.reports_to_key]),
  );
  const levels = new Map();
  for (const agent of draft.agents) {
    let depth = 0;
    let cursor = agent.key;
    const seen = new Set([cursor]);
    while (parentByKey.has(cursor) && depth < draft.agents.length) {
      cursor = parentByKey.get(cursor);
      if (seen.has(cursor)) break;
      seen.add(cursor);
      depth += 1;
    }
    levels.set(depth, [...(levels.get(depth) || []), agent.key]);
  }
  const width = 1000;
  const nodeWidth = 220;
  const nodeHeight = 116;
  const positions = [];
  const orderedLevels = [...levels.entries()].sort(([left], [right]) => left - right);
  for (const [depth, keys] of orderedLevels) {
    const gap = (width - keys.length * nodeWidth) / (keys.length + 1);
    keys.forEach((key, index) => {
      positions.push({
        key,
        x: Math.round(gap + index * (nodeWidth + gap)),
        y: 34 + depth * 154,
        width: nodeWidth,
        height: nodeHeight,
      });
    });
  }
  const maxDepth = orderedLevels.length
    ? Math.max(...orderedLevels.map(([depth]) => depth))
    : 0;
  return {
    width,
    height: Math.max(330, 34 + (maxDepth + 1) * 154),
    positions,
  };
}
