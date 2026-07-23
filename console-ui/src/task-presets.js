export const TASK_PRESET_CATEGORIES = [
  { id: 'operate', label: { en: 'Run', zh: '日常运营' } },
  { id: 'decide', label: { en: 'Decide', zh: '研究决策' } },
  { id: 'grow', label: { en: 'Grow', zh: '增长营销' } },
  { id: 'serve', label: { en: 'Serve', zh: '客户经营' } },
  { id: 'specialist', label: { en: 'Specialist', zh: '专业场景' } },
];

export const TASK_PRESETS = [
  {
    id: 'inbox-command-center',
    category: 'operate',
    title: { en: 'Inbox command center', zh: '每日邮箱指挥台' },
    description: {
      en: 'Turn unread mail metadata into a prioritized morning action list.',
      zh: '把未读邮件元数据整理成有优先级的晨间行动清单。',
    },
    objective: {
      en: 'Create a daily inbox command-center task. Use only the authorized read-only Gmail metadata scope: sender, subject, date, and message-id; exclude spam and trash. Plan triage, follow-up extraction, and review agents that produce a prioritized summary, messages likely needing replies, and unresolved items. Do not read or send message bodies, archive, delete, label, or otherwise modify mail; require human approval before any future outbound action.',
      zh: '创建一个每日邮箱指挥台任务。只使用已授权的 Gmail 只读元数据范围：发件人、主题、日期和 message-id，并排除垃圾邮件与回收站。规划分流、待办提取、复核三个 Agent，输出有优先级的摘要、可能需要回复的邮件和未解决事项。不要读取或发送正文，不要归档、删除、加标签或修改邮件；任何未来的外发动作都必须人工批准。',
    },
  },
  {
    id: 'weekly-operator-review',
    category: 'operate',
    title: { en: 'Weekly operator review', zh: '每周经营复盘' },
    description: {
      en: 'Summarize progress, exceptions, approvals, evidence, and next decisions.',
      zh: '汇总进展、异常、审批、证据和下一步决策。',
    },
    objective: {
      en: 'Create a weekly operator-review task for a one-person company. Plan operations, evidence-review, and reporting agents that summarize completed and active work, failed or blocked tasks, pending approvals, verified outcomes, and the five most important next actions. Separate execution evidence from business outcomes, cite every task or artifact used, and flag missing coverage instead of reporting a false green status. Produce a review draft for human confirmation; do not change schedules, permissions, or tasks.',
      zh: '创建一个面向一人公司的每周经营复盘任务。规划运营汇总、证据复核、报告编辑三个 Agent，汇总已完成与进行中的工作、失败或阻塞任务、待审批事项、已验证结果和最重要的五项下一步行动。必须区分执行证据与业务结果，引用使用到的每个任务或 artifact；覆盖缺失时应明确翻红，不能假报健康。输出供人工确认的复盘草稿，不要修改调度、权限或任务。',
    },
  },
  {
    id: 'meeting-prep-follow-up',
    category: 'operate',
    title: { en: 'Meeting prep and follow-up', zh: '会议准备与行动跟进' },
    description: {
      en: 'Build a briefing, decision log, owners, and due dates around a meeting.',
      zh: '围绕会议生成简报、决策记录、负责人和截止日期。',
    },
    objective: {
      en: 'Create a meeting preparation and follow-up task using only the calendar details and notes I explicitly provide. Plan briefing, decision-extraction, and follow-up review agents that produce an agenda brief, open questions, a decision log, named owners, due dates, and a concise follow-up draft. Mark assumptions and missing context, and require human approval before sending messages, changing calendar events, or assigning work to external people.',
      zh: '创建一个会议准备与行动跟进任务，只使用我明确提供的日历信息和会议记录。规划会前简报、决策提取、行动复核三个 Agent，输出议程简报、待确认问题、决策记录、负责人、截止日期和精简的跟进草稿。标记所有假设与缺失信息；发送消息、修改日历或向外部人员分配工作前必须人工批准。',
    },
  },
  {
    id: 'project-status-risk-review',
    category: 'operate',
    title: { en: 'Project status and risk review', zh: '项目进度与风险复盘' },
    description: {
      en: 'Turn scattered project updates into blockers, decisions, owners, and next actions.',
      zh: '把分散的项目更新整理成阻塞项、决策、负责人和下一步行动。',
    },
    objective: {
      en: 'Create a project status and risk review using only the task exports, milestones, and notes I explicitly provide. Plan progress-collection, dependency-risk, and executive-review agents that produce a workstream status table, overdue items, blockers, decisions needed, owners, due dates, and evidence links. Separate reported progress from verified completion and flag stale or contradictory updates. Do not change assignments or dates, close tasks, send updates, or report an unsupported percentage complete.',
      zh: '只使用我明确提供的任务导出、里程碑和项目记录，创建一个项目进度与风险复盘任务。规划进度汇总、依赖风险、管理复核三个 Agent，输出工作流状态表、逾期事项、阻塞项、待决策问题、负责人、截止日期和证据链接。必须区分自报进度与已验证完成，并标记过期或矛盾信息。不要修改负责人或日期、关闭任务、发送更新，也不要给出没有证据支持的完成百分比。',
    },
  },
  {
    id: 'sop-knowledge-base-builder',
    category: 'operate',
    title: { en: 'SOP and knowledge-base builder', zh: 'SOP 与知识库整理' },
    description: {
      en: 'Convert approved source material into a versioned operating procedure.',
      zh: '把已批准资料整理成可版本化的操作流程。',
    },
    objective: {
      en: 'Create an SOP and knowledge-base drafting task from the approved documents, notes, and transcripts I will provide. Plan procedure-extraction, conflict-check, and editorial agents that produce prerequisites, ordered steps, decision points, exceptions, owners, review dates, and source citations, plus a list of unresolved contradictions. Keep every instruction traceable to approved material. Do not invent policy, credentials, permissions, or safety steps, and do not publish or replace an existing SOP without human approval.',
      zh: '根据我随后提供的已批准文档、笔记和记录，创建一个 SOP 与知识库整理任务。规划流程提取、冲突核验、编辑三个 Agent，输出前置条件、顺序步骤、决策点、例外、负责人、复核日期和来源引用，并列出尚未解决的矛盾。每条指令都必须可追溯到批准资料。不要编造政策、凭据、权限或安全步骤，未经人工批准不得发布或替换现有 SOP。',
    },
  },
  {
    id: 'document-pdf-digest',
    category: 'operate',
    title: { en: 'Document and PDF digest', zh: '文档与 PDF 要点提取' },
    description: {
      en: 'Extract decisions, obligations, dates, and contradictions with page-level citations.',
      zh: '带页码提取决策、义务、日期和矛盾内容。',
    },
    objective: {
      en: 'Create a document and PDF digest using only the files I explicitly provide. Plan structured-extraction, cross-document comparison, and citation-review agents that produce an executive summary, key decisions, obligations, dates, named entities, contradictions, open questions, and page-level citations. Preserve document boundaries and label unreadable or ambiguous passages instead of guessing. Do not distribute the source files, infer missing legal or financial facts, or take any action described in the documents.',
      zh: '只使用我明确提供的文件，创建一个文档与 PDF 要点提取任务。规划结构化提取、跨文档对比、引用复核三个 Agent，输出执行摘要、关键决策、义务、日期、命名实体、矛盾、待确认问题和页码级引用。必须保留文档边界，对无法读取或含糊段落明确标记而不是猜测。不要分发源文件、推断缺失的法律或财务事实，也不要执行文档中描述的任何动作。',
    },
  },
  {
    id: 'hiring-scorecard-interview-kit',
    category: 'operate',
    title: { en: 'Hiring scorecard and interview kit', zh: '招聘评分卡与面试包' },
    description: {
      en: 'Build a structured, job-related interview process without automating hiring decisions.',
      zh: '建立与岗位相关的结构化面试流程，但不自动作出招聘决定。',
    },
    objective: {
      en: 'Create a hiring scorecard and interview kit from an approved job description and role requirements I will provide. Plan requirement-analysis, interview-design, and fairness-review agents that produce measurable job-related criteria, structured questions, evidence anchors, interviewer guidance, and a consistent note template. Exclude protected characteristics and unsupported personality inference. Do not rank or reject real candidates automatically, make a hiring decision, contact applicants, or process unsanitized personal data.',
      zh: '根据我随后提供的已批准职位描述和岗位要求，创建一个招聘评分卡与面试包任务。规划要求分析、面试设计、公平性复核三个 Agent，输出可衡量且与岗位相关的标准、结构化问题、证据锚点、面试官指南和统一记录模板。排除受保护特征和无依据的人格推断。不要自动排名或拒绝真人候选人、作出招聘决定、联系申请人，也不要处理未经脱敏的个人数据。',
    },
  },
  {
    id: 'company-commercial-analysis',
    category: 'decide',
    title: { en: 'Company commercial analysis report', zh: '公司商业分析报告' },
    description: {
      en: 'Turn company evidence into a market, business-model, economics, and risk brief.',
      zh: '把公司证据整理成市场、商业模式、经营质量与风险简报。',
    },
    objective: {
      en: 'Create a company commercial-analysis task for a company and decision question I will specify. Use only the company materials I provide and dated, publicly accessible primary sources. Plan company-research, market-and-competition, financial-evidence, and decision-review agents that produce a company profile, customer and revenue model, market and competitor map, operating and unit-economics analysis where supported, material changes, risks, counterarguments, source ledger, and a decision brief. Every material claim and number must cite its source, date, and any calculation; distinguish reported facts, calculations, and inference, and flag unavailable evidence. Do not contact the company, bypass access controls, make an investment or legal conclusion, invent valuation precision, or take the recommended action automatically.',
      zh: '为我随后指定的公司和决策问题创建一个公司商业分析任务。只使用我提供的公司资料和带日期、公开可访问的一手来源。规划公司研究、市场与竞争、财务证据、决策复核四个 Agent，输出公司画像、客户与收入模式、市场与竞品地图、有证据支持的经营与单位经济分析、重大变化、风险、反方观点、来源账本和决策简报。每项重要结论与数字必须标注来源、日期和计算过程；区分已报告事实、计算结果与推断，并标记不可获得的证据。不要联系公司、绕过访问限制、作出投资或法律结论、编造精确估值，也不要自动执行建议。',
    },
  },
  {
    id: 'source-backed-research',
    category: 'decide',
    title: { en: 'Source-backed research brief', zh: '可溯源深度研究' },
    description: {
      en: 'Research a decision with source verification and an editorial pass.',
      zh: '用来源核验与编辑复核支持一个重要决策。',
    },
    objective: {
      en: 'Create a source-backed research brief for a topic I will specify. Plan research, source-verification, and editorial agents that compare credible primary sources, distinguish facts from inference, surface conflicting evidence, and produce a concise recommendation with citations, assumptions, and unresolved questions. Preserve a traceable source list and review result as artifacts. Do not fabricate sources or take the recommended action automatically.',
      zh: '为我随后指定的主题创建一个可溯源深度研究任务。规划研究、来源核验、编辑复核三个 Agent，对比可信的一手来源，区分事实与推断，呈现相互冲突的证据，并输出带引用、假设和未解决问题的精简建议。将可追溯来源清单与审核结果登记为 artifact。不要编造来源，也不要自动执行建议。',
    },
  },
  {
    id: 'competitor-watch',
    category: 'decide',
    title: { en: 'Competitor watch', zh: '竞品动态监控' },
    description: {
      en: 'Track public product, pricing, hiring, and positioning changes.',
      zh: '跟踪公开的产品、价格、招聘和定位变化。',
    },
    objective: {
      en: 'Create a weekly competitor-watch task for a company list I will provide. Plan monitoring, evidence-verification, and analyst agents that track public product, pricing, release, hiring, and positioning changes, compare them with the previous snapshot, and explain what materially changed. Save dated source links and a change log, clearly label unavailable evidence, and never bypass logins, paywalls, robots restrictions, or other access controls.',
      zh: '为我随后提供的公司名单创建一个每周竞品动态监控任务。规划监控、证据核验、分析三个 Agent，跟踪公开的产品、价格、发布、招聘和定位变化，与上次快照对比，并解释哪些变化具有实际意义。保存带日期的来源链接和变更记录，明确标记不可用证据；绝不绕过登录、付费墙、robots 限制或其他访问控制。',
    },
  },
  {
    id: 'procurement-comparison',
    category: 'decide',
    title: { en: 'Procurement comparison', zh: '采购与比价决策' },
    description: {
      en: 'Compare products or vendors against explicit requirements and budget.',
      zh: '根据明确需求与预算比较产品或供应商。',
    },
    objective: {
      en: 'Create a procurement comparison task for requirements, location, and budget I will provide. Plan requirements, market-research, and decision-review agents that compare current price, availability, warranty, return terms, compatibility, and material tradeoffs using dated source links. Produce a shortlist, comparison table, recommendation, and questions to verify with the seller. Do not place an order, enter payment details, accept terms, or contact a vendor without explicit human approval.',
      zh: '根据我随后提供的需求、地区和预算创建一个采购与比价决策任务。规划需求整理、市场调研、决策复核三个 Agent，用带日期的来源链接比较当前价格、库存、保修、退货条款、兼容性和关键取舍。输出候选清单、对比表、建议和需要向卖家核实的问题。未经明确人工批准，不得下单、填写支付信息、接受条款或联系供应商。',
    },
  },
  {
    id: 'spreadsheet-data-analysis',
    category: 'decide',
    title: { en: 'Spreadsheet data analysis', zh: '表格数据分析' },
    description: {
      en: 'Profile a dataset, verify calculations, and produce decision-ready charts and findings.',
      zh: '检查数据、核验计算，并输出可用于决策的图表与发现。',
    },
    objective: {
      en: 'Create a spreadsheet data-analysis task using only the CSV or workbook I explicitly provide. Plan data-profiling, analysis, and independent-verification agents that document schema and quality issues, calculate requested metrics with reproducible code, identify anomalies, and produce clear tables, charts, findings, assumptions, and a calculation audit. Preserve the original file and distinguish correlation from causation. Do not overwrite source data, silently impute values, expose sensitive rows, or make unsupported business claims.',
      zh: '只使用我明确提供的 CSV 或工作簿，创建一个表格数据分析任务。规划数据画像、分析、独立核验三个 Agent，记录字段结构与质量问题，用可复现代码计算所需指标，识别异常，并输出清晰表格、图表、发现、假设和计算审计。保留原始文件，并区分相关性与因果关系。不要覆盖源数据、静默填补缺失值、暴露敏感行或给出无依据的业务结论。',
    },
  },
  {
    id: 'customer-feedback-synthesis',
    category: 'decide',
    title: { en: 'Customer feedback synthesis', zh: '客户反馈与问卷分析' },
    description: {
      en: 'Turn sanitized feedback into themes, evidence, frequency, and unresolved needs.',
      zh: '把已脱敏反馈整理成主题、证据、频率和未满足需求。',
    },
    objective: {
      en: 'Create a customer-feedback synthesis task from sanitized surveys, tickets, reviews, or interview notes I will provide. Plan taxonomy, evidence-coding, and product-review agents that identify recurring themes, frequency, sentiment with uncertainty, representative excerpts, affected segments, feature requests, and contradictory evidence. Preserve links to source records and separate volume from importance. Do not expose personal data, invent prevalence, contact customers, or automatically prioritize the product roadmap.',
      zh: '根据我随后提供的已脱敏问卷、工单、评论或访谈记录，创建一个客户反馈与问卷分析任务。规划分类体系、证据编码、产品复核三个 Agent，识别重复主题、频率、带不确定性的情绪、代表性摘录、受影响群体、功能请求和相互矛盾的证据。保留到源记录的链接，并区分数量与重要性。不要暴露个人数据、编造普遍性、联系客户或自动决定产品路线优先级。',
    },
  },
  {
    id: 'product-roadmap-brief',
    category: 'decide',
    title: { en: 'Product roadmap evidence brief', zh: '产品路线证据简报' },
    description: {
      en: 'Compare product options against goals, evidence, capacity, dependencies, and risk.',
      zh: '根据目标、证据、产能、依赖和风险比较产品方案。',
    },
    objective: {
      en: 'Create a product-roadmap evidence brief from the goals, customer evidence, constraints, and capacity inputs I will provide. Plan opportunity-analysis, tradeoff-modeling, and decision-review agents that produce option briefs, explicit scoring criteria, expected outcomes, dependencies, effort ranges, risks, evidence quality, and questions requiring validation. Keep recommendations reversible and show dissenting evidence. Do not commit delivery dates, create engineering tickets, change the roadmap, or present estimates as guarantees.',
      zh: '根据我随后提供的目标、客户证据、约束和产能输入，创建一个产品路线证据简报任务。规划机会分析、取舍建模、决策复核三个 Agent，输出方案简报、明确评分标准、预期结果、依赖、工作量区间、风险、证据质量和需要验证的问题。建议必须可逆并展示反方证据。不要承诺交付日期、创建工程工单、修改路线图或把估算当作保证。',
    },
  },
  {
    id: 'lead-research-qualification',
    category: 'grow',
    title: { en: 'Lead research and qualification', zh: '潜客研究与评分' },
    description: {
      en: 'Build an explainable prospect list from a user-defined customer profile.',
      zh: '根据用户定义的客户画像生成可解释的潜客清单。',
    },
    objective: {
      en: 'Create a lead research and qualification task from an ideal-customer profile I will provide. Plan discovery, qualification, and review agents that use public business information to build a deduplicated prospect list, score fit with explicit criteria, cite evidence, and explain each recommendation. Exclude restricted or sensitive personal data, respect source terms, and do not enrich private identities, send outreach, or update a CRM without human approval.',
      zh: '根据我随后提供的理想客户画像创建一个潜客研究与评分任务。规划发现、资格评估、复核三个 Agent，使用公开商业信息生成去重潜客清单，按明确标准评分，引用证据并解释每项建议。排除受限或敏感个人数据，遵守来源条款；未经人工批准，不得补全私人身份、发送外联或更新 CRM。',
    },
  },
  {
    id: 'proposal-quote-pack',
    category: 'grow',
    title: { en: 'Proposal and quote pack', zh: '提案与报价草稿' },
    description: {
      en: 'Turn a client brief into a scoped proposal with assumptions and risks.',
      zh: '把客户需求整理成包含假设与风险的提案草稿。',
    },
    objective: {
      en: 'Create a proposal and quote drafting task from the client brief, pricing inputs, and delivery constraints I will provide. Plan scope, commercial-review, and editor agents that produce an executive summary, deliverables, milestones, assumptions, exclusions, price placeholders, dependencies, risks, and open questions. Verify every numeric input against the supplied source and flag missing terms. The output is a draft for human approval only; do not send, sign, promise delivery, or create an invoice.',
      zh: '根据我随后提供的客户需求、定价输入和交付限制创建一个提案与报价草稿任务。规划范围梳理、商务复核、编辑三个 Agent，输出执行摘要、交付物、里程碑、假设、排除项、价格占位、依赖、风险和待确认问题。每个数字必须与提供的来源核对，缺失条款必须标记。结果只供人工审批，不要发送、签署、承诺交付或创建发票。',
    },
  },
  {
    id: 'content-calendar',
    category: 'grow',
    title: { en: 'Content calendar', zh: '内容选题与发布包' },
    description: {
      en: 'Plan four weeks of evidence-backed content without auto-publishing.',
      zh: '规划四周有证据支持的内容，但不自动发布。',
    },
    objective: {
      en: 'Create a four-week content calendar for the audience, offer, channels, and brand constraints I will provide. Plan audience-research, content-strategy, and editorial-review agents that produce themes, titles, briefs, draft copy, source links, calls to action, and a realistic publishing cadence. Check factual claims and brand consistency, label experimental ideas, and preserve a review checklist. Do not publish, schedule posts, buy ads, or use customer data without explicit approval.',
      zh: '根据我随后提供的受众、产品、渠道和品牌约束创建一个四周内容选题与发布包任务。规划受众研究、内容策略、编辑复核三个 Agent，输出主题、标题、内容简报、草稿、来源链接、行动号召和合理发布节奏。检查事实陈述与品牌一致性，标记实验性想法，并保留审核清单。未经明确批准，不得发布、定时发帖、购买广告或使用客户数据。',
    },
  },
  {
    id: 'content-repurposing',
    category: 'grow',
    title: { en: 'Content repurposing', zh: '多平台内容改写' },
    description: {
      en: 'Adapt one approved source asset into channel-specific drafts.',
      zh: '把一份已批准原稿改写成不同平台的草稿。',
    },
    objective: {
      en: 'Create a content repurposing task using one approved source asset I will provide. Plan extraction, channel-adaptation, and fact-check agents that preserve the original meaning while producing platform-appropriate drafts, headlines, short summaries, and a claims checklist. Identify any claim that needs a new source or permission and keep each output traceable to the source asset. Do not invent testimonials, alter quoted meaning, or publish any draft.',
      zh: '使用我随后提供的一份已批准原稿创建一个多平台内容改写任务。规划信息提取、渠道适配、事实核验三个 Agent，在保持原意的同时输出适合各平台的草稿、标题、短摘要和事实检查清单。指出任何需要新来源或授权的陈述，并让每项输出都可追溯到原稿。不要编造评价、改变引用原意或发布任何草稿。',
    },
  },
  {
    id: 'website-seo-audit',
    category: 'grow',
    title: { en: 'Website and SEO audit', zh: '网站与 SEO 审计' },
    description: {
      en: 'Audit public pages for technical, content, search, and conversion issues.',
      zh: '检查公开页面的技术、内容、搜索与转化问题。',
    },
    objective: {
      en: 'Create a website and SEO audit for the public site and analytics extracts I explicitly authorize. Plan technical-audit, content-search, and conversion-review agents that identify crawl and index issues, metadata gaps, broken links, performance concerns, content overlap, search intent, accessibility problems, and prioritized experiments with evidence. Respect robots and rate limits and label unavailable measurements. Do not change the site, publish content, buy links or ads, bypass access controls, or guarantee rankings.',
      zh: '针对我明确授权的公开网站和分析数据导出，创建一个网站与 SEO 审计任务。规划技术审计、内容搜索、转化复核三个 Agent，识别抓取与索引问题、元数据缺口、失效链接、性能风险、内容重叠、搜索意图、可访问性问题和带证据的优先实验。遵守 robots 与速率限制，并标记无法测量的项目。不要修改网站、发布内容、购买链接或广告、绕过访问控制或保证排名。',
    },
  },
  {
    id: 'sales-account-prep',
    category: 'grow',
    title: { en: 'Sales account preparation', zh: '销售客户会前准备' },
    description: {
      en: 'Build an evidence-backed account brief, hypotheses, and discovery questions.',
      zh: '生成带证据的客户简报、业务假设和探索问题。',
    },
    objective: {
      en: 'Create a sales account-preparation task using public company information and only the CRM fields I explicitly authorize. Plan account-research, opportunity-hypothesis, and briefing-review agents that produce company context, recent material changes, public stakeholders, likely priorities, relationship history, evidence links, risks, and tailored discovery questions. Label every hypothesis and stale CRM field. Do not enrich private identities, infer sensitive traits, send outreach, change CRM records, or promise commercial terms.',
      zh: '使用公开公司信息和我明确授权的 CRM 字段，创建一个销售客户会前准备任务。规划客户研究、机会假设、简报复核三个 Agent，输出公司背景、近期重要变化、公开利益相关者、可能优先事项、关系历史、证据链接、风险和定制探索问题。每项假设与过期 CRM 字段都必须标记。不要补全私人身份、推断敏感特征、发送外联、修改 CRM 记录或承诺商务条款。',
    },
  },
  {
    id: 'support-triage',
    category: 'serve',
    title: { en: 'Support triage', zh: '客服分流与回复建议' },
    description: {
      en: 'Classify customer issues and draft evidence-bound response options.',
      zh: '分类客户问题并生成受证据约束的回复建议。',
    },
    objective: {
      en: 'Create a customer-support triage task for sanitized tickets I will provide. Plan triage, knowledge-check, and response-review agents that classify urgency and topic, identify missing facts, cite the approved policy or knowledge source, propose a response, and flag cases requiring a person. Redact unnecessary personal data and separate verified facts from assumptions. Do not send replies, issue refunds, change an account, or make legal or safety promises without human approval.',
      zh: '针对我随后提供的已脱敏工单创建一个客服分流与回复建议任务。规划分流、知识核验、回复复核三个 Agent，分类紧急程度与主题，识别缺失事实，引用已批准政策或知识来源，提出回复建议，并标记必须人工处理的案例。去除不必要的个人数据，区分已验证事实与假设。未经人工批准，不得发送回复、退款、修改账户或作出法律与安全承诺。',
    },
  },
  {
    id: 'ecommerce-operations',
    category: 'serve',
    title: { en: 'E-commerce operations review', zh: '电商商品与评论优化' },
    description: {
      en: 'Review listings, reviews, FAQs, and conversion experiments.',
      zh: '复核商品页、评论、FAQ 与转化实验。',
    },
    objective: {
      en: 'Create an e-commerce operations review for product data and sanitized customer feedback I will provide. Plan listing-audit, review-insight, and merchandising-review agents that identify recurring objections, improve titles and descriptions, draft FAQs, check claims, and propose measurable conversion experiments. Preserve source references and flag regulated or unverifiable claims. Do not change price or inventory, publish listings, message customers, or launch promotions without approval.',
      zh: '根据我随后提供的商品数据与已脱敏客户反馈创建一个电商商品与评论优化任务。规划商品页审计、评论洞察、运营复核三个 Agent，识别重复异议，优化标题与描述，起草 FAQ，核验陈述，并提出可衡量的转化实验。保留来源引用，标记受监管或无法验证的说法。未经批准，不得修改价格或库存、发布商品页、联系客户或启动促销。',
    },
  },
  {
    id: 'finance-admin-review',
    category: 'serve',
    title: { en: 'Invoice and expense review', zh: '发票与费用复核' },
    description: {
      en: 'Reconcile documents, due dates, duplicates, and cash obligations.',
      zh: '核对单据、到期日、重复项和现金义务。',
    },
    objective: {
      en: 'Create an invoice and expense review task using the documents and accounting export I explicitly provide. Plan extraction, reconciliation, and exception-review agents that identify vendors, dates, amounts, tax fields, due dates, duplicates, missing documents, and upcoming cash obligations, with every field traceable to its source. Produce an exceptions list and approval-ready summary. Do not initiate payments, change accounting records, file taxes, or present legal or tax conclusions.',
      zh: '使用我明确提供的单据与会计导出数据创建一个发票与费用复核任务。规划信息提取、对账、异常复核三个 Agent，识别供应商、日期、金额、税务字段、到期日、重复项、缺失单据和近期现金义务，并让每个字段都可追溯到来源。输出异常清单和供审批的摘要。不要发起付款、修改会计记录、报税，也不要给出法律或税务结论。',
    },
  },
  {
    id: 'cpa-month-end-workpaper-pack',
    category: 'specialist',
    title: { en: 'CPA/EA month-end workpaper pack', zh: 'CPA/EA 月结与报税前工作底稿包' },
    description: {
      en: 'Prepare traceable tie-outs, missing-document lists, and exceptions for licensed review.',
      zh: '为持牌复核准备可追溯对账、缺件清单与异常工作底稿。',
    },
    objective: {
      en: 'Create a month-end and pre-tax-preparation workpaper task for a CPA or EA using only the source documents, general-ledger export, prior-period workpapers, and approved mapping or checklist I provide. Plan document-intake, deterministic-reconciliation, exception-review, and licensed-review-preparation agents that tie amounts and dates to source records, identify missing or duplicate documents, surface unexplained variances and tax-field questions, preserve calculation formulas, and produce a review index with source/page/cell references. Deliver an exception pack for the CPA or EA to review and sign. Do not post journal entries, change books, initiate payment, choose a tax position, prepare or file a return, represent the taxpayer, or present the pack as tax advice or a completed filing.',
      zh: '只使用我提供的源单据、总账导出、上期工作底稿以及已批准的字段映射或检查清单，为 CPA 或 EA 创建月结与报税前工作底稿任务。规划单据归集、确定性对账、异常复核、持牌审签准备四个 Agent，将金额和日期逐项关联到源记录，识别缺失或重复单据、未解释差异和待确认税务字段，保留计算公式，并生成带来源、页码或单元格引用的复核索引。交付供 CPA 或 EA 审阅并签字的异常包。不要入账或修改账簿、发起付款、选择税务立场、准备或提交税表、代理纳税人，也不得把该工作包表述为税务意见或已完成申报。',
    },
  },
  {
    id: 'customs-entry-support-pack',
    category: 'specialist',
    title: { en: 'Customs entry-support evidence pack', zh: '报关行进口申报支持证据包' },
    description: {
      en: 'Check import-document completeness and preserve a broker-reviewable evidence trail.',
      zh: '检查进口单证完整性，并形成可供报关员复核的证据链。',
    },
    objective: {
      en: 'Create an import entry-support evidence task for a licensed U.S. customs broker using only the commercial invoice, packing list, transport document, purchase order, product specifications, supplier-origin evidence, prior approved rulings, and broker checklist I provide. Plan document-extraction, cross-document-reconciliation, discrepancy-review, and broker-signoff-preparation agents that build a document matrix, compare parties, quantities, weights, values, currencies, product descriptions, and dates, identify missing or conflicting evidence, preserve source/page references, and assemble a five-year retention index. The licensed customs broker must determine HTS classification, customs value, origin, admissibility, and filing. Do not make those determinations, transmit an entry, communicate with CBP, alter source documents, or claim that the evidence pack constitutes customs compliance.',
      zh: '只使用我提供的商业发票、装箱单、运输单证、采购订单、产品规格、供应商原产地证据、已批准的既往裁定和报关行检查清单，为美国持牌报关行创建进口申报支持证据任务。规划单证提取、跨文档对账、差异复核、报关员审签准备四个 Agent，生成单证矩阵，核对交易方、数量、重量、金额、币种、品名和日期，识别缺失或冲突证据，保留来源与页码引用，并整理五年留档索引。HTS 分类、海关估价、原产地、准入性和正式申报必须由持牌报关员决定。不要作出这些判断、传输 entry、联系 CBP、修改源文件，也不得宣称该证据包本身即构成海关合规。',
    },
  },
  {
    id: 'commercial-insurance-renewal-pack',
    category: 'specialist',
    title: { en: 'Commercial P&C renewal readiness pack', zh: '商业财产与责任险续保资料包' },
    description: {
      en: 'Check submission completeness and conflicts before licensed broker review.',
      zh: '在持牌经纪人复核前检查续保资料完整性与冲突。',
    },
    objective: {
      en: 'Create a commercial property-and-casualty renewal-readiness task for a licensed insurance producer using only the ACORD forms, loss runs, financial statements, exposure schedules, current policies, prior submissions, and broker checklist I provide. Plan submission-intake, cross-document-consistency, exception-review, and broker-signoff-preparation agents that produce a document matrix, stale-data and missing-item list, conflicts across locations, payroll, revenue, vehicles, limits, and loss history, plus a source-linked broker review brief. Clearly label client-provided, carrier-provided, calculated, and inferred fields. The licensed producer must decide coverage, limits, markets, representations, and placement. Do not recommend coverage, certify an application, obtain or negotiate quotes, contact carriers, bind or alter insurance, submit forms, or present the pack as insurance advice.',
      zh: '只使用我提供的 ACORD 表格、loss runs、财务报表、exposure schedule、现有保单、既往 submission 和经纪人检查清单，为持牌保险 producer 创建商业财产与责任险续保资料准备任务。规划资料归集、跨文档一致性、异常复核、经纪人审签准备四个 Agent，输出单证矩阵、过期资料与缺件清单，检查营业地点、工资、收入、车辆、限额和损失记录之间的冲突，并生成带来源链接的经纪人复核简报。明确区分客户提供、保险公司提供、计算得出和推断字段。保障范围、限额、市场、声明与 placement 必须由持牌 producer 决定。不要推荐保障、认证申请、获取或谈判报价、联系保险公司、bind 或修改保险、提交表格，也不得把资料包表述为保险意见。',
    },
  },
  {
    id: 'client-onboarding-plan',
    category: 'serve',
    title: { en: 'Client onboarding plan', zh: '客户 Onboarding 计划' },
    description: {
      en: 'Turn signed scope into milestones, dependencies, access requests, and handoffs.',
      zh: '把已签范围转成里程碑、依赖、访问请求与交接计划。',
    },
    objective: {
      en: 'Create a client onboarding plan from the signed scope, approved checklist, and client-provided details I will supply. Plan setup-planning, dependency-tracking, and handoff-review agents that produce milestones, owners, dates, required documents, access requests, training steps, acceptance criteria, risks, and a status template. Keep credentials out of the plan and identify every client dependency. Do not create accounts, invite users, send messages, request secrets, or change a client system without explicit human approval.',
      zh: '根据我随后提供的已签范围、批准清单和客户提供信息，创建一个客户 Onboarding 计划任务。规划设置计划、依赖跟踪、交接复核三个 Agent，输出里程碑、负责人、日期、所需文档、访问请求、培训步骤、验收标准、风险和状态模板。凭据不得进入计划，并标出每项客户依赖。未经明确人工批准，不要创建账户、邀请用户、发送消息、索取密钥或修改客户系统。',
    },
  },
  {
    id: 'contract-policy-review',
    category: 'specialist',
    title: { en: 'Contract and policy review', zh: '合同与政策条款复核' },
    description: {
      en: 'Extract obligations, dates, deviations, and review questions without giving legal advice.',
      zh: '提取义务、日期、偏差和复核问题，但不提供法律意见。',
    },
    objective: {
      en: 'Create a contract and policy review using only the documents and approved comparison baseline I explicitly provide. Plan clause-extraction, baseline-comparison, and risk-review agents that produce obligations, payment and renewal dates, termination terms, data and security clauses, deviations, ambiguous language, missing exhibits, and questions for qualified counsel, with page-level citations. Treat the output as informational review, not legal advice. Do not sign, accept, submit, edit the source, or make a legal conclusion.',
      zh: '只使用我明确提供的文档和已批准对比基线，创建一个合同与政策条款复核任务。规划条款提取、基线对比、风险复核三个 Agent，输出义务、付款与续约日期、终止条款、数据与安全条款、偏差、含糊表述、缺失附件和需要向合格法律顾问确认的问题，并附页码引用。结果只作信息复核，不构成法律意见。不要签署、接受、提交、编辑源文件或作出法律结论。',
    },
  },
  {
    id: 'incident-troubleshooting-runbook',
    category: 'specialist',
    title: { en: 'Incident troubleshooting runbook', zh: '故障排查与恢复方案' },
    description: {
      en: 'Turn authorized logs and status into hypotheses, evidence, rollback, and approval gates.',
      zh: '把已授权日志与状态整理成假设、证据、回滚和审批门。',
    },
    objective: {
      en: 'Create an incident troubleshooting and recovery task using only the authorized logs, metrics, status output, and runbooks I provide. Plan incident-triage, hypothesis-testing, and recovery-review agents that produce a timeline, affected scope, evidence-ranked hypotheses, read-only diagnostic steps, proposed remediation, rollback plan, validation checks, and an incident summary. Mark missing telemetry and preserve log references. Do not execute commands, restart services, delete data, rotate secrets, change infrastructure, or declare recovery without human approval and verified health evidence.',
      zh: '只使用我提供的已授权日志、指标、状态输出和运行手册，创建一个故障排查与恢复方案任务。规划故障分流、假设验证、恢复复核三个 Agent，输出时间线、影响范围、按证据排序的假设、只读诊断步骤、拟议修复、回滚计划、验证检查和事故摘要。标记缺失遥测并保留日志引用。未经人工批准和已验证健康证据，不要执行命令、重启服务、删除数据、轮换密钥、修改基础设施或宣布恢复。',
    },
  },
  {
    id: 'github-release-assistant',
    category: 'specialist',
    title: { en: 'GitHub release assistant', zh: 'GitHub 发布协作' },
    description: {
      en: 'Triage changes, assemble release evidence, and stop before publishing.',
      zh: '整理变更与发布证据，并在正式发布前停下。',
    },
    objective: {
      en: 'Create a GitHub release-assistant task for a repository and target version I will specify. Plan change-triage, test-evidence, and release-review agents that classify issues and pull requests, identify blockers, draft a changelog, verify required checks, and assemble a release checklist with traceable commit and artifact references. Keep unverified claims visible and require human approval before merge, tag creation, release publication, deployment, or writing to protected branches.',
      zh: '为我随后指定的仓库与目标版本创建一个 GitHub 发布协作任务。规划变更分流、测试证据、发布复核三个 Agent，分类 issue 与 PR，识别阻塞项，起草 changelog，核验必要检查，并用可追溯 commit 与 artifact 引用生成发布清单。明确显示未经核验的结论；合并、创建 tag、发布 release、部署或写入受保护分支前必须人工批准。',
    },
  },
  {
    id: 'bazi-report-demo',
    category: 'specialist',
    title: { en: 'Bazi report demo', zh: '八字命理报告演示' },
    description: {
      en: 'Demonstrate deterministic charting, cited interpretation, and sign-off.',
      zh: '演示确定性排盘、带引用解读与人工审签。',
    },
    objective: {
      en: 'Create a Bazi report demonstration using only synthetic client DEMO-001. The chart must be calculated deterministically with lunar-python; AI may only interpret the result against the approved knowledge base. Plan three agents for interpretation, citation verification, and report editing, with a mandatory human sign-off checkpoint. Produce a traceable chart JSON, citation list, review result, and PDF report; do not deliver the report and do not use any real person\'s information.',
      zh: '创建一个八字命理报告演示任务。只使用合成客户 DEMO-001，排盘必须由 lunar-python 确定性完成，AI 只负责基于已批准知识库解释。规划解读、引用核验、报告编辑三个 Agent，并设置强制人工审签检查点。最终输出可追溯的命盘 JSON、引用清单、审核结果和 PDF 报告；不要发送报告，不要使用真人个人信息。',
    },
  },
];

function workTemplate(id, recipe) {
  const preset = TASK_PRESETS.find((item) => item.id === id);
  if (!preset) throw new Error(`unknown built-in work template: ${id}`);
  return { ...preset, recipe };
}

export const FEATURED_WORK_TEMPLATES = [
  workTemplate('company-commercial-analysis', {
    agentCount: 4,
    stageCount: 6,
    cadence: { en: 'On demand or quarterly', zh: '按需或每季度' },
    team: {
      en: 'Company researcher -> market analyst -> financial verifier -> decision editor',
      zh: '公司研究 -> 市场分析 -> 财务核验 -> 决策编辑',
    },
    outputs: {
      en: ['Commercial analysis', 'Source ledger', 'Decision brief'],
      zh: ['商业分析报告', '来源账本', '决策简报'],
    },
    checkpoint: {
      en: 'Human decision; no investment, legal, or external action',
      zh: '最终决策必须由人作出；不自动进行投资、法律或外部行动',
    },
  }),
  workTemplate('cpa-month-end-workpaper-pack', {
    agentCount: 4,
    stageCount: 6,
    cadence: { en: 'Monthly and pre-filing', zh: '每月及报税前' },
    team: {
      en: 'Document intake -> deterministic tie-out -> exception reviewer -> CPA/EA review prep',
      zh: '单据归集 -> 确定性对账 -> 异常复核 -> CPA/EA 审签准备',
    },
    outputs: {
      en: ['Tie-out workpapers', 'Exception list', 'Licensed review index'],
      zh: ['对账工作底稿', '异常与缺件清单', '持牌复核索引'],
    },
    checkpoint: {
      en: 'CPA/EA signs; no posting, payment, tax position, or filing',
      zh: '必须由 CPA/EA 审签；不入账、不付款、不选税务立场、不申报',
    },
  }),
  workTemplate('customs-entry-support-pack', {
    agentCount: 4,
    stageCount: 6,
    cadence: { en: 'Per shipment or entry', zh: '每票货物或 entry' },
    team: {
      en: 'Document extractor -> reconciliation analyst -> discrepancy reviewer -> broker review prep',
      zh: '单证提取 -> 跨单证对账 -> 差异复核 -> 报关员审签准备',
    },
    outputs: {
      en: ['Document matrix', 'Discrepancy list', 'Retention evidence index'],
      zh: ['单证矩阵', '差异与缺件清单', '留档证据索引'],
    },
    checkpoint: {
      en: 'Licensed broker decides classification, value, origin, and filing',
      zh: '分类、估价、原产地与申报必须由持牌报关员决定',
    },
  }),
  workTemplate('commercial-insurance-renewal-pack', {
    agentCount: 4,
    stageCount: 6,
    cadence: { en: 'Per renewal', zh: '每次续保' },
    team: {
      en: 'Submission intake -> consistency analyst -> exception reviewer -> producer review prep',
      zh: '资料归集 -> 一致性分析 -> 异常复核 -> Producer 审签准备',
    },
    outputs: {
      en: ['Submission matrix', 'Conflict and missing-item list', 'Broker review brief'],
      zh: ['Submission 矩阵', '冲突与缺件清单', '经纪人复核简报'],
    },
    checkpoint: {
      en: 'Licensed producer approves; no advice, submission, quoting, or binding',
      zh: '必须由持牌 Producer 批准；不提供保险意见、不提交、不报价、不出单',
    },
  }),
  workTemplate('weekly-operator-review', {
    agentCount: 3,
    stageCount: 5,
    cadence: { en: 'Weekly', zh: '每周' },
    team: {
      en: 'Operations lead -> evidence reviewer -> report editor',
      zh: '运营负责人 -> 证据复核 -> 报告编辑',
    },
    outputs: {
      en: ['Operating review', 'Exception list', 'Five next actions'],
      zh: ['经营复盘', '异常清单', '五项下一步行动'],
    },
    checkpoint: {
      en: 'Human review before any operational change',
      zh: '执行任何运营变更前，必须由负责人完成人工确认',
    },
  }),
  workTemplate('project-status-risk-review', {
    agentCount: 3,
    stageCount: 5,
    cadence: { en: 'Weekly or manual', zh: '每周或手动' },
    team: {
      en: 'Progress collector -> dependency analyst -> executive reviewer',
      zh: '进度汇总 -> 依赖分析 -> 管理复核',
    },
    outputs: {
      en: ['Status table', 'Blockers', 'Decision queue'],
      zh: ['状态表', '阻塞项', '待决策清单'],
    },
    checkpoint: {
      en: 'Human review before dates or owners change',
      zh: '修改交付日期或负责人之前，必须完成人工确认',
    },
  }),
  workTemplate('source-backed-research', {
    agentCount: 3,
    stageCount: 5,
    cadence: { en: 'On demand', zh: '按需运行' },
    team: {
      en: 'Research lead -> source verifier -> decision editor',
      zh: '研究负责人 -> 来源核验 -> 决策编辑',
    },
    outputs: {
      en: ['Research brief', 'Source ledger', 'Recommendation'],
      zh: ['研究简报', '来源账本', '决策建议'],
    },
    checkpoint: {
      en: 'Human decision after evidence review',
      zh: '完成证据复核后，必须由人工作出最终决策',
    },
  }),
  workTemplate('content-repurposing', {
    agentCount: 3,
    stageCount: 4,
    cadence: { en: 'On demand', zh: '按需运行' },
    team: {
      en: 'Source extractor -> channel adapter -> fact checker',
      zh: '原稿提取 -> 渠道适配 -> 事实核验',
    },
    outputs: {
      en: ['Channel drafts', 'Claims checklist', 'Source map'],
      zh: ['多平台草稿', '事实清单', '来源映射'],
    },
    checkpoint: {
      en: 'Human approval before publication',
      zh: '任何内容对外发布之前，必须取得人工批准',
    },
  }),
  workTemplate('client-onboarding-plan', {
    agentCount: 3,
    stageCount: 5,
    cadence: { en: 'Per client', zh: '每位客户一次' },
    team: {
      en: 'Setup planner -> dependency tracker -> handoff reviewer',
      zh: '设置规划 -> 依赖跟踪 -> 交接复核',
    },
    outputs: {
      en: ['Milestone plan', 'Dependency log', 'Handoff checklist'],
      zh: ['里程碑计划', '依赖清单', '交接检查表'],
    },
    checkpoint: {
      en: 'Human approval before account or access changes',
      zh: '创建账户或修改访问权限之前，必须取得人工批准',
    },
  }),
  workTemplate('bazi-report-demo', {
    agentCount: 3,
    stageCount: 5,
    cadence: { en: 'Demo run', zh: '演示运行' },
    team: {
      en: 'Deterministic chart lead -> citation verifier -> report editor',
      zh: '确定性排盘负责人 -> 引用核验 -> 报告编辑',
    },
    outputs: {
      en: ['Chart JSON', 'Citation audit', 'Signed-off PDF'],
      zh: ['命盘 JSON', '引用审计', '审签 PDF'],
    },
    checkpoint: {
      en: 'Mandatory human sign-off; synthetic data only',
      zh: '报告必须完成人工审签，并且只能使用合成数据',
    },
  }),
];

export function localizedTaskPreset(preset, language) {
  const localized = {
    ...preset,
    title: preset.title[language],
    description: preset.description[language],
    objective: preset.objective[language],
  };
  if (!preset.recipe) return localized;
  return {
    ...localized,
    recipe: {
      ...preset.recipe,
      cadence: preset.recipe.cadence[language],
      team: preset.recipe.team[language],
      outputs: preset.recipe.outputs[language],
      checkpoint: preset.recipe.checkpoint[language],
    },
  };
}

export function filterTaskPresets(language, category = 'all', query = '') {
  const locale = language === 'zh' ? 'zh-CN' : 'en-US';
  const normalizedQuery = query.trim().toLocaleLowerCase(locale);
  return TASK_PRESETS.filter((preset) => {
    if (category !== 'all' && preset.category !== category) return false;
    if (!normalizedQuery) return true;
    const localized = localizedTaskPreset(preset, language);
    return [localized.title, localized.description, localized.objective]
      .some((value) => value.toLocaleLowerCase(locale).includes(normalizedQuery));
  });
}
