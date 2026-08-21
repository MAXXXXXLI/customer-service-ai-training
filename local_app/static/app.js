const DEFAULT_MODEL = "Qwen/Qwen3.5-35B-A3B";
const AVAILABLE_MODELS = [
  { id: "Qwen/Qwen3.5-35B-A3B", label: "Qwen 3.5 35B · 推荐" },
  { id: "deepseek-ai/DeepSeek-V3.2", label: "DeepSeek V3.2 · 高质量" },
  { id: "Qwen/Qwen3.5-27B", label: "Qwen 3.5 27B · 稳定" },
  { id: "Pro/zai-org/GLM-5.1", label: "GLM 5.1 Pro" },
  { id: "Pro/moonshotai/Kimi-K2.6", label: "Kimi K2.6 Pro" },
  { id: "MiniMaxAI/MiniMax-M2.5", label: "MiniMax M2.5" },
];

const state = {
  route: "learning",
  routeModuleId: null,
  mode: "learning",
  modules: [],
  courses: [],
  catalogIndex: [],
  scenarios: [],
  learningModuleId: null,
  practiceModuleId: null,
  objectiveModuleId: null,
  simulationModuleId: null,
  testModuleId: null,
  scenarioIndex: 0,
  scenario: null,
  history: [],
  apiKey: localStorage.getItem("kbai_api_key") || "",
  model: localStorage.getItem("kbai_model") || DEFAULT_MODEL,
  models: [...AVAILABLE_MODELS],
  apiVerified: false,
  busy: false,
  ended: false,
  revising: false,
  knowledge: {},
  examBank: null,
  realExamBank: null,
  objectiveAnswersByModule: {},
  objectiveScoresByModule: {},
  simulationScoresByModule: {},
  requestSerial: 0,
};

const $ = (id) => document.getElementById(id);
const els = {
  modeButtons: document.querySelectorAll(".mode-button"),
  modeBreadcrumb: $("mode-breadcrumb"),
  pageTitle: $("page-title"),
  pageDescription: $("page-description"),
  learningHubPage: $("learning-hub-page"),
  assessmentHubPage: $("assessment-hub-page"),
  moduleGatewayPage: $("module-gateway-page"),
  gatewayBack: $("gateway-back"),
  gatewayTag: $("gateway-tag"),
  gatewayTitle: $("gateway-title"),
  gatewayDescription: $("gateway-description"),
  moduleRouteGrid: $("module-route-grid"),
  learningPage: $("learning-page"),
  trainingPage: $("training-page"),
  testPage: $("test-page"),
  qaPage: $("qa-page"),
  learningSelect: $("learning-module-select"),
  practiceSelect: $("practice-module-select"),
  testSelect: $("test-module-select"),
  learningSummary: $("learning-module-summary"),
  learningChapters: $("learning-chapters"),
  trainingScenario: $("training-scenario-frame"),
  testScenario: $("test-scenario-frame"),
  testRouteBack: $("test-route-back"),
  testRouteTag: $("test-route-tag"),
  testRouteTitle: $("test-route-title"),
  testRouteDescription: $("test-route-description"),
  conversationStage: $("conversation-stage"),
  conversationAvatar: $("conversation-avatar"),
  conversationKicker: $("conversation-kicker"),
  conversationTitle: $("conversation-title"),
  messages: $("messages"),
  input: $("message-input"),
  send: $("send-button"),
  finish: $("finish-session"),
  turnCount: $("turn-count"),
  composerHint: $("composer-hint"),
  apiStatus: $("api-status"),
  healthNumber: $("health-number"),
  courseModalContent: $("course-modal-content"),
  toast: $("toast"),
  clearChat: $("clear-chat"),
};

const modeCopy = {
  learning: {
    nav: "学习与陪练 / 课程学习",
    title: "课程学习",
    description: "按章节学习项目知识、服务流程和接待表达。",
    kicker: "",
    conversation: "",
    hint: "",
  },
  training: {
    nav: "学习与陪练 / 情景陪练",
    title: "情景陪练",
    description: "接待模拟顾客，及时发现并改进表达。",
    kicker: "情景陪练",
    conversation: "接待模拟顾客",
    hint: "发送后即可查看本轮反馈和参考表达",
  },
  test: {
    nav: "实战考核",
    title: "实战考核",
    description: "独立完成模拟接待，查看能力评分和改进建议。",
    kicker: "实战考核",
    conversation: "独立接待模拟顾客",
    hint: "请按真实接待方式独立完成对话",
  },
  qa: {
    nav: "智能接待",
    title: "智能接待",
    description: "根据企业知识库，为你提供专业接待建议。",
    kicker: "接待问答助手",
    conversation: "输入顾客的问题",
    hint: "回答会附上相关课程，方便继续学习",
  },
};

const ROUTE_CONFIG = {
  learning: {
    area: "learning", mode: "learning", screen: "hub",
    nav: "学习与陪练", title: "学习与陪练", description: "学知识、练接待，让每一次服务更专业。",
  },
  "learning/course": {
    area: "learning", mode: "learning", screen: "activity", parent: "learning",
    tag: "课程学习", nav: "学习与陪练 / 课程学习", title: "课程学习", gatewayTitle: "选择课程模块",
    pageDescription: "系统学习项目知识、服务流程和标准表达。", description: "从一个模块开始，按章节学习相关课程。", workspaceDescription: "按章节学习本模块的课程与服务要点。", action: "查看课程",
  },
  "learning/practice": {
    area: "learning", mode: "training", screen: "activity", parent: "learning",
    tag: "情景陪练", nav: "学习与陪练 / 情景陪练", title: "情景陪练", gatewayTitle: "选择陪练主题",
    pageDescription: "在真实顾客情景中练习接待，获得即时反馈。", description: "选择想练习的主题，马上开始接待模拟顾客。", workspaceDescription: "选择顾客场景，练习接待并获得即时反馈。", action: "开始陪练",
  },
  exam: {
    area: "exam", mode: "test", screen: "hub",
    nav: "实战考核", title: "实战考核", description: "通过答题与模拟接待，检验知识掌握和实际应用能力。",
  },
  "exam/objective": {
    area: "exam", mode: "test", screen: "activity", parent: "exam",
    tag: "知识考试", nav: "实战考核 / 客观题考试", title: "客观题考试", gatewayTitle: "选择考试模块",
    pageDescription: "完成知识测试，巩固关键业务要点。", description: "选择一个知识模块，完成本模块的 14 道题。", workspaceDescription: "完成本模块 14 道题，交卷后查看成绩和解析。", action: "开始答题",
  },
  "exam/simulation": {
    area: "exam", mode: "test", screen: "activity", parent: "exam",
    tag: "模拟接待", nav: "实战考核 / 模拟顾客考核", title: "模拟顾客考核", gatewayTitle: "选择考核主题",
    pageDescription: "独立完成模拟接待，检验沟通与风险意识。", description: "选择一个接待主题，完成模拟顾客对话。", workspaceDescription: "完成至少 4 轮接待对话，结束后查看实战评分。", action: "开始考核",
  },
  qa: {
    area: "qa", mode: "qa", screen: "workspace",
    nav: "智能接待", title: "智能接待", description: "根据企业知识库，为你提供专业接待建议。",
  },
};

const VALID_ROUTES = new Set(Object.keys(ROUTE_CONFIG));
const LEGACY_ROUTES = {
  learn: "learning",
  assessment: "exam",
  training: "learning/practice",
  test: "exam",
};

const STATIC_PAGES = window.location.hostname.endsWith(".github.io");
const staticAsset = (name) => STATIC_PAGES ? `./${name}` : `/static/${name}`;
let staticDataPromise = null;
const modalReturnFocus = new Map();

function parseJsonl(text) {
  return text.split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

async function loadStaticData() {
  if (!staticDataPromise) {
    staticDataPromise = Promise.all([
      fetch("./data/scenario_library.jsonl").then((response) => response.text()).then(parseJsonl),
      fetch("./data/rag_documents.jsonl").then((response) => response.text()).then(parseJsonl),
      fetch("./data/common_qa_catalog.jsonl").then((response) => response.text()).then(parseJsonl),
      fetch("./data/common_qa_excel_catalog.jsonl").then((response) => response.text()).then(parseJsonl),
      fetch("./data/scoring_rubric.json").then((response) => response.json()),
      fetch("./data/customer_service_methodology.json").then((response) => response.json()),
      fetch("./data/comprehensive_exam_bank.json").then((response) => response.json()),
    ]).then(([scenarios, documents, commonQa, commonQaExcel, rubric, methodology, examBank]) => ({ scenarios, documents, commonQa: [...commonQa, ...commonQaExcel], rubric, methodology, examBank }));
  }
  return staticDataPromise;
}

function publicStaticDocument(document) {
  const metadata = document.metadata || {};
  const course = resolveReferenceCourse(document);
  const module = course ? moduleById(course.module_id) : null;
  return {
    document_id: document.document_id,
    course_id: course?.id || metadata.course_id || "",
    title: course?.title || metadata.title || document.document_id || "知识库资料",
    module: module?.short_name || module?.title || metadata.module || metadata.domain || "知识库",
    chapter: course?.group_title || metadata.chapter || "",
  };
}

function staticMatchesAny(text, patterns = []) {
  return patterns.some((pattern) => {
    try { return new RegExp(pattern, "i").test(text); } catch { return false; }
  });
}

const STATIC_NEGATED_RED_FLAG_PATTERN = /(?:没有|没|并没有|并无|尚无|未见|未出现|未发生|没出现|不伴有?|否认|无)(?:(?:任何|一点儿?|明显|持续|进行性|新发|突然)){0,2}(?:胸痛|胸闷|气短|呼吸困难|晕厥|昏厥|出冷汗|突发剧痛|突然剧痛|腿(?:部)?(?:新发|新|发)?麻|手(?:臂)?(?:新发|新|发)?麻|胳膊(?:新发|新|发)?麻|发麻|麻木|无力|大小便异常|会阴麻木|发热|红肿|头晕)(?:(?:、|或|和|及|以及)(?:(?:任何|一点儿?|明显|持续|进行性|新发|突然)){0,2}(?:胸痛|胸闷|气短|呼吸困难|晕厥|昏厥|出冷汗|突发剧痛|突然剧痛|腿(?:部)?(?:新发|新|发)?麻|手(?:臂)?(?:新发|新|发)?麻|胳膊(?:新发|新|发)?麻|发麻|麻木|无力|大小便异常|会阴麻木|发热|红肿|头晕))*/gi;

function staticAffirmedSafetyText(text) {
  return String(text || "").replace(STATIC_NEGATED_RED_FLAG_PATTERN, " ");
}

function staticIntentMatches(text, intent) {
  const candidate = intent?.id === "INTENT-RED-FLAG" ? staticAffirmedSafetyText(text) : text;
  return staticMatchesAny(candidate, intent?.patterns || []);
}

function uniqueStaticItems(values = []) {
  return [...new Set(values.filter(Boolean))];
}

function staticRouteCustomerQuestion(query, methodology = {}) {
  const text = String(query || "").replace(/\s+/g, " ").trim();
  const intents = [...(methodology.intent_routes || [])].sort((a, b) => Number(b.priority || 0) - Number(a.priority || 0));
  const matchedIntent = intents.find((item) => staticIntentMatches(text, item)) || null;
  const topics = (methodology.topic_routes || []).filter((item) => staticMatchesAny(text, item.patterns));
  const fallback = methodology.default_route || {};
  const intent = matchedIntent || (topics.length ? {
    id: "INTENT-INFORMATION",
    label: topics[0].label || "项目原理、流程与一般咨询",
    primary_module_id: "DYNAMIC",
    support_module_ids: [],
    course_ids: [],
    focus: topics[0].recommended_next || "使用对应项目课程回答。",
    stop_sales: false,
  } : {
    id: fallback.intent_id || "INTENT-INFORMATION",
    label: fallback.intent_label || "一般需求咨询",
    primary_module_id: fallback.primary_module_id || "MOD-01",
    support_module_ids: fallback.support_module_ids || ["MOD-01"],
    course_ids: fallback.course_ids || [],
    focus: fallback.focus || "先确认顾客目标和必要安全信息。",
    stop_sales: Boolean(fallback.stop_sales),
  });
  const topicPrimary = topics[0]?.module_id || null;
  const intentPrimary = intent.primary_module_id;
  const primaryModuleId = !matchedIntent && topicPrimary ? topicPrimary : intentPrimary === "DYNAMIC" ? (topicPrimary || fallback.primary_module_id || "MOD-01") : (intentPrimary || topicPrimary || fallback.primary_module_id || "MOD-01");
  const supportModuleIds = [];
  if (topicPrimary && topicPrimary !== primaryModuleId) supportModuleIds.push(topicPrimary);
  topics.forEach((topic) => {
    supportModuleIds.push(...(topic.support_module_ids || []));
    if (topic.module_id !== primaryModuleId) supportModuleIds.push(topic.module_id);
  });
  supportModuleIds.push(...(intent.support_module_ids || []));
  if (primaryModuleId !== "MOD-01") supportModuleIds.push("MOD-01");
  const validModuleIds = new Set(state.modules.map((item) => item.id));
  const cleanSupportIds = uniqueStaticItems(supportModuleIds).filter((id) => validModuleIds.has(id) && id !== primaryModuleId);
  const courseIds = [...(intent.course_ids || [])];
  const knowledgePoints = [];
  topics.forEach((topic) => {
    courseIds.push(...(topic.course_ids || []));
    knowledgePoints.push(...(topic.knowledge_points || []));
  });
  if (!topics.length && !matchedIntent) courseIds.push(...(fallback.course_ids || []));
  if (intent.stop_sales) courseIds.push("COURSE-NKB-001", "COURSE-NKB-002", "COURSE-NKB-003", "COURSE-NKB-004");
  const validCourseIds = new Set(state.courses.map((item) => item.id));
  const cleanCourseIds = uniqueStaticItems(courseIds).filter((id) => validCourseIds.has(id));
  const moduleByRouteId = (id) => state.modules.find((item) => item.id === id);
  const courseByRouteId = (id) => state.courses.find((item) => item.id === id);
  const objectionIntents = new Set(["INTENT-PRICE", "INTENT-RESULT", "INTENT-COMPARISON", "INTENT-DECISION"]);
  const methodStep = intent.stop_sales ? "安全确认与停止分流" : objectionIntents.has(intent.id) ? "承接异议、依据回应并确认下一步" : intent.id === "INTENT-SUITABILITY" ? "安全确认后再解释选择" : topics.length ? "定位项目、补充必要信息并解释选择" : "了解目标并完成问题定位";
  return {
    intent_id: intent.id || "INTENT-INFORMATION",
    intent_label: intent.label || "一般需求咨询",
    topic_ids: topics.map((item) => item.id),
    topic_labels: topics.map((item) => item.label).filter(Boolean),
    primary_module_id: primaryModuleId,
    primary_module: moduleByRouteId(primaryModuleId)?.title || "新客接待与需求洞察",
    support_module_ids: cleanSupportIds,
    support_modules: cleanSupportIds.map((id) => moduleByRouteId(id)?.title).filter(Boolean),
    required_course_ids: cleanCourseIds,
    required_courses: cleanCourseIds.map((id) => courseByRouteId(id)?.title).filter(Boolean),
    knowledge_points: uniqueStaticItems(knowledgePoints).slice(0, 6),
    focus: intent.focus || fallback.focus || "先确认顾客目标和必要安全信息。",
    recommended_next: matchedIntent?.recommended_next || topics.find((item) => item.recommended_next)?.recommended_next || fallback.focus || "先确认顾客目标和必要安全信息。",
    method_step: methodStep,
    stop_sales: Boolean(intent.stop_sales),
  };
}

function publicStaticRoute(route = {}) {
  return {
    intent: route.intent_label || "一般需求咨询",
    primary_module: route.primary_module || "新客接待与需求洞察",
    supporting_modules: route.support_modules || [],
    knowledge_points: (route.knowledge_points || []).slice(0, 4),
    courses: (route.required_courses || []).slice(0, 5),
    method_step: route.method_step || "了解目标并完成问题定位",
    stop_sales: Boolean(route.stop_sales),
  };
}

function staticRouteContext(route = {}) {
  return JSON.stringify({
    问题类型: route.intent_label,
    主要知识模块: route.primary_module,
    辅助知识模块: route.support_modules || [],
    必须调用课程: route.required_courses || [],
    回答重点: route.focus,
    项目或主题知识点: route.knowledge_points || [],
    推荐下一步: route.recommended_next,
    是否停止销售推进: Boolean(route.stop_sales),
  });
}

function staticQaQuery(message, history = []) {
  const current = String(message || "").replace(/\s+/g, " ").trim();
  const contextual = /^(?:那|这个|这种|它|刚才|如果|那么|可是|但是|她追问|他追问|顾客(?:又)?问|顾客追问|对方(?:又)?问|对方追问)/.test(current)
    || /^(?:那我|我)?(?:现在|接下来)?(?:应该|该)?(?:怎么办|做什么)(?:呢)?[？?]?$/.test(current)
    || /^(?:可以吗|为什么|多少钱|多少|多久|呢)[？?]?$/.test(current);
  if (!contextual) return current;
  const priorQuestions = history.filter((item) => item?.role === "user").slice(-3).map((item) => item.content);
  return [...priorQuestions, current].filter(Boolean).join(" ");
}

const COMMON_QA_NOISE_RE = /请问|我想(?:问|了解)|想问一下|请教一下|什么是|是什么|为什么|为啥|怎么回事|如何|怎么|怎么办|能不能|可以吗|是否|吗|呢|呀|啊|的|一下/gi;
const COMMON_QA_SYNONYMS = [
  ["头疼", "头不适"],
  ["头痛", "头不适"],
  ["疼痛", "不适"],
  ["疼", "不适"],
  ["痛", "不适"],
  ["为啥", "为什么"],
  ["咋", "怎么"],
];

function normalizeStaticCommonQaText(value) {
  let text = String(value || "").replace(/\s+/g, "").toLowerCase();
  COMMON_QA_SYNONYMS.forEach(([source, target]) => { text = text.replaceAll(source, target); });
  return text.replace(/[^a-z0-9\u4e00-\u9fff]+/g, "");
}

function staticCommonQaCoreText(value) {
  return normalizeStaticCommonQaText(value).replace(COMMON_QA_NOISE_RE, "");
}

function staticCommonQaMatchTerms(value) {
  const text = staticCommonQaCoreText(value);
  const terms = new Set(text.match(/[a-z0-9_]+/g) || []);
  for (let index = 0; index < text.length - 1; index += 1) {
    const pair = text.slice(index, index + 2);
    if (/^[\u4e00-\u9fff]{2}$/.test(pair)) terms.add(pair);
  }
  return terms;
}

function staticCommonQaScore(query, row) {
  const queryCore = staticCommonQaCoreText(query);
  const questionCore = staticCommonQaCoreText(row?.question);
  if (queryCore.length < 2 || questionCore.length < 2) return 0;
  if (queryCore === questionCore) return 1;
  if (Math.min(queryCore.length, questionCore.length) >= 4 && (queryCore.includes(questionCore) || questionCore.includes(queryCore))) return 0.93;

  const queryTerms = staticCommonQaMatchTerms(queryCore);
  const questionTerms = staticCommonQaMatchTerms(questionCore);
  const overlap = [...queryTerms].filter((term) => questionTerms.has(term)).length;
  if (overlap < 2) return 0;
  const keywordHits = (row?.keywords || []).filter((keyword) => {
    const normalized = staticCommonQaCoreText(keyword);
    return normalized.length >= 2 && queryCore.includes(normalized);
  }).length;
  if (!keywordHits && overlap < 3) return 0;
  const queryChars = new Set(queryCore);
  const questionChars = new Set(questionCore);
  const sharedChars = [...queryChars].filter((char) => questionChars.has(char)).length;
  const charDice = (2 * sharedChars) / Math.max(queryChars.size + questionChars.size, 1);
  const questionCoverage = overlap / Math.max(questionTerms.size, 1);
  const queryCoverage = overlap / Math.max(queryTerms.size, 1);
  const keywordScore = Math.min(1, keywordHits / Math.max(1, Math.min((row?.keywords || []).length, 2)));
  const score = questionCoverage * 0.38
    + queryCoverage * 0.18
    + charDice * 0.20
    + keywordScore * 0.16
    + ((queryCore.includes(questionCore) || questionCore.includes(queryCore)) ? 0.08 : 0);
  return Math.min(score, 0.99);
}

function matchStaticCommonQa(query, catalog = []) {
  const candidates = catalog.map((row) => ({ row, score: staticCommonQaScore(query, row) }))
    .filter((item) => item.row?.approved_answer && item.score >= 0.66)
    .sort((a, b) => b.score - a.score || Number(b.row.usage_count || 0) - Number(a.row.usage_count || 0) || String(b.row.question || "").length - String(a.row.question || "").length);
  if (!candidates.length) return null;
  const best = candidates[0];
  return { row: best.row, score: Number(best.score.toFixed(3)) };
}

function publicStaticCommonQaMatch(match) {
  const row = match?.row || {};
  return { id: row.id || "", question: row.question || "", score: match?.score || 0, status: row.status || "" };
}

function staticCommonQaCourseReference(row) {
  const course = resolveReferenceCourse({ course_id: row?.mapped_course_id });
  if (!course) return null;
  const module = moduleById(course.module_id);
  return {
    course_id: course.id,
    title: course.title,
    category: "标准问答课程",
    module: module?.short_name || module?.title || "知识模块",
    chapter: course.group_title || "",
  };
}

function uniqueStaticReferences(references = []) {
  const seen = new Set();
  return references.filter((reference) => {
    const key = reference.course_id || reference.title;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function staticRetrieve(query, documents, limit = 8, route = null, includeCommonQa = true) {
  const text = String(query || "").toLowerCase();
  const terms = new Set(text.match(/[a-z0-9_]{2,}/gi) || []);
  (text.match(/[\u4e00-\u9fff]+/g) || []).forEach((segment) => {
    if (segment.length <= 8) terms.add(segment);
    for (let index = 0; index < segment.length - 1; index += 1) terms.add(segment.slice(index, index + 2));
  });
  const requiredCourseIds = new Set(route?.required_course_ids || []);
  const routedModuleIds = new Set([route?.primary_module_id, ...(route?.support_module_ids || [])].filter(Boolean));
  const ranked = documents.map((document, index) => {
    const metadata = document.metadata || {};
    if (metadata.doc_type === "source") return null;
    if (!includeCommonQa && metadata.doc_type === "common_qa") return null;
    if (route && metadata.doc_type === "course_section" && !routedModuleIds.has(metadata.module_id) && !requiredCourseIds.has(metadata.course_id)) return null;
    const title = String(metadata.title || "").toLowerCase();
    const haystack = `${document.text || ""} ${JSON.stringify(metadata)}`.toLowerCase();
    const baseScore = [...terms].reduce((total, term) => total + (title.includes(term) ? 4 : haystack.includes(term) ? 1 : 0), 0);
    const score = baseScore + (requiredCourseIds.has(metadata.course_id) ? 10 : 0) + (routedModuleIds.has(metadata.module_id) ? 3 : 0);
    return { document, score, index };
  }).filter((item) => item && item.score > 0).sort((a, b) => b.score - a.score || a.index - b.index);
  const selected = [];
  const seen = new Set();
  for (const courseId of requiredCourseIds) {
    const item = ranked.find((candidate) => candidate.document.metadata?.course_id === courseId);
    if (!item) continue;
    selected.push(item.document);
    seen.add(courseId);
    if (selected.length >= limit) return selected;
  }
  for (const item of ranked) {
    const metadata = item.document.metadata || {};
    const key = metadata.course_id || metadata.source_id || item.document.document_id;
    if (seen.has(key)) continue;
    seen.add(key);
    selected.push(item.document);
    if (selected.length >= limit) break;
  }
  return selected;
}

function extractStaticJson(content) {
  const cleaned = String(content || "").replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();
  try {
    return JSON.parse(cleaned);
  } catch {
    const match = cleaned.match(/\{[\s\S]*\}/);
    try { return match ? JSON.parse(match[0]) : null; } catch { return null; }
  }
}

async function callStaticModel(system, messages, model, apiKey, temperature, maxTokens = 1800, timeoutMs = 45000) {
  const payload = {
    model, messages: [{ role: "system", content: system }, ...messages],
    temperature, top_p: 0.7, max_tokens: maxTokens, response_format: { type: "json_object" }, stream: false,
  };
  if (model.startsWith("Qwen/Qwen3") || model.includes("DeepSeek-V3.2") || model.startsWith("Pro/zai-org/GLM-5")) payload.enable_thinking = false;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch("https://api.siliconflow.cn/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${apiKey}` },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(`SiliconFlow API ${response.status}: ${data.error?.message || "请求失败"}`);
    return { content: data.choices?.[0]?.message?.content || "", meta: { model: data.model || model, usage: data.usage || {} } };
  } catch (error) {
    if (controller.signal.aborted) throw new Error("在线 AI 响应超时，请稍后重试。");
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

function staticMock(mode, action, scenario) {
  if (mode === "training") return {
    customer_reply: staticCustomerFallback(scenario, [], ""),
    feedback: { level: "needs_work", issue: "还可以继续追问顾客的目标、持续时间和影响。", why: "先完成需求分析，再介绍项目。", method_step: "了解目标并完成问题定位", knowledge_focus: "目标、持续时间、影响和安全信息", suggested_reply: "这种情况大概持续多久了？对工作或睡眠有影响吗？", next_goal: "下一轮先问清目标、持续时间和影响。" },
  };
  if (mode === "test" && action === "turn") return { reply: scenario?.opening || "我最近有点困扰，想先了解一下你们的项目。", emotion: "hesitant", should_continue: true };
  if (mode === "test" && action === "finish") return { total_score: 72, dimension_scores: [], critical_failures: [], strengths: ["完成了基本接待并保持对话连续"], improvements: ["先问清目标、持续时间、影响和顾虑，再介绍项目"], summary: "演示评分：流程已走通，配置 API Key 后可使用模型评分。" };
  return { answer: "当前是演示模式。保存 SiliconFlow API Key 后，就能生成基于知识库的正式回答。", uncertainties: ["请以门店当前价格、项目标签和合规版本为准。"], recommended_action: "先核对门店当前版本的价格、频次和适用边界。" };
}

function staticKnowledgeQaResponse(message, route, docs) {
  const snippets = [];
  const seenTitles = new Set();
  docs.slice(0, 2).forEach((document) => {
    const course = resolveReferenceCourse(document);
    const title = course?.title || document.metadata?.title || document.document_id || "知识库资料";
    if (seenTitles.has(title)) return;
    seenTitles.add(title);
    const section = course?.sections?.[0];
    const content = Array.isArray(section?.content)
      ? section.content.slice(0, 2).join("；")
      : typeof section?.content === "object" && section?.content
        ? Object.entries(section.content).map(([key, value]) => `${key}：${value}`).join("；")
        : String(section?.content || document.text || "");
    const snippet = `${course?.summary || ""} ${content}`.replace(/\s+/g, " ").trim();
    if (snippet) snippets.push(snippet.slice(0, 220));
  });
  if (!snippets.length) return staticMock("qa", "turn", null);
  return {
    answer: `围绕您问的“${String(message || "").trim()}”，知识库相关课程提到：${snippets.slice(0, 2).join("；")}`,
    uncertainties: ["具体项目、适用条件和门店动态政策仍需按当前有效版本核对。"],
    recommended_action: route.recommended_next || "如需继续了解，可打开下方相关课程并核对当前门店标准。",
  };
}

const STATIC_CRITICAL_PATTERNS = [
  /自动诊疗/i,
  /替代手术/i,
  /保证(?:效果|结果|瘦|减重)/i,
  /(?:保证|一定|肯定).{0,10}(?:治好|治愈|根治)/i,
  /(?:治愈|根治|治疗|治好)[^，。；！？,.;!?\r\n]{0,8}(?:疾病|颈椎病|糖尿病|三高|脂肪肝|炎症)/i,
  /(?:有效|能够|可以|会)[^，。；！？,.;!?\r\n]{0,10}(?:治疗|治好|根治|改善糖尿病|改善三高|改善脂肪肝|提高免疫力|增强免疫力)/i,
  /(?:固定|保证).{0,8}(?:减重|减肥).{0,8}(?:斤|公斤)/i,
  /不反弹/i,
  /百分之百|百分百|100%/i,
  /白血球.{0,10}(?:增加|提高)/i,
  /(?:宫寒|卵巢|肾虚).{0,12}(?:受孕|衰老|疾病|治疗)/i,
  /国家药监局.{0,20}(?:批准|认证)/i,
  /单次治疗|后续疗程|按疗程|进入疗程/i,
  /压迫.{0,8}(?:血管|神经)/i,
  /(?:可能)?涉及.{0,6}(?:神经|血管)/i,
  /脑部.{0,8}供血|供血供氧.{0,8}不足/i,
  /(?:检查|查体).{0,12}(?:僵硬程度|结节|体征)/i,
  /(?:一定|肯定|保证).{0,8}(?:有效|缓解|改善|见效|结果)/i,
  /(?:建议|应该|可以).{0,10}(?:停药|换药|剂量|口服|注射)/i,
];

function staticCriticalHits(message) {
  const text = String(message || "");
  return STATIC_CRITICAL_PATTERNS
    .filter((pattern) => staticHasAffirmativeEmployeeMatch(text, pattern))
    .map((pattern) => pattern.source);
}

function staticMockProgressive(mode, action, scenario, history = [], rubric = null, message = "") {
  const userTurns = history.filter((item) => item?.role === "user").length;
  if (mode === "training") {
    const strong = ["了解", "多久", "哪里", "感受", "目标", "担心", "方便", "预算", "疼", "病史"].some((word) => String(message).includes(word));
    const critical = staticCriticalHits(message).length > 0;
    return {
      customer_reply: staticCustomerFallback(scenario, history, message),
      feedback: {
        level: critical ? "critical" : (strong ? "good" : "needs_work"),
        issue: critical ? "出现了不能承诺疗效或替代专业评估的高风险表达。" : (strong ? "你已围绕顾客的目标和情况继续追问，方向正确。" : "还可以继续追问顾客的目标、持续时间和影响。"),
        why: critical ? "安全边界优先，不能用确定性承诺或医疗化表达推进成交。" : "先完成需求分析，再介绍项目。",
        method_step: "了解目标并完成问题定位",
        knowledge_focus: "目标、持续时间、影响和安全信息",
        suggested_reply: critical ? "我不能承诺结果或替代专业评估，先确认您的具体情况和安全边界，再说明可以提供的服务。" : "这种情况大概持续多久了？对工作或睡眠有影响吗？",
        next_goal: critical ? "下一轮先纠正表达，完成必要安全问询。" : "下一轮先问清目标、持续时间和影响。",
      },
    };
  }
  if (mode === "test" && action === "turn") {
    return { reply: staticCustomerFallback(scenario, history, message), emotion: userTurns > 0 ? "concerned" : "hesitant", should_continue: true };
  }
  if (mode === "test" && action === "finish") {
    const dimensions = (rubric?.dimensions || []).map((item) => ({
      id: item.id,
      name: item.name,
      score: Math.round(Number(item.weight || item.max_score || 0) * 0.72),
      max_score: Number(item.weight || item.max_score || 0),
      evidence: "本地演示评分：已根据当前对话完成基础评估。",
      comment: "建议继续训练需求分析和异议处理。",
    }));
    return { total_score: 72, dimension_scores: dimensions, critical_failures: [], strengths: ["完成了基本接待并保持了对话连续性。"], improvements: ["先问清目标、持续时间、影响和顾虑，再介绍项目。", "面对价格和效果异议时，使用共情—澄清—回应—确认。"], summary: "本地演示评分：流程已走通，配置 API Key 后可使用模型评分。" };
  }
  return staticMock(mode, action, scenario);
}

function normalizeStaticQaResult(result, message, query, route, history = []) {
  const normalized = result && typeof result === "object" ? { ...result } : {};
  const current = String(message || "").trim();
  const context = String(query || current);
  const followUp = /怎么办|现在|下一步|那我|接下来/.test(current) && history.some((item) => item?.role === "user");
  if (/(?:手麻|麻木).{0,18}(?:未缓解|没有缓解|加重)|(?:疼痛加重).{0,18}(?:麻木|手麻)/.test(context)) {
    normalized.answer = "您提到点阵波后疼痛加重并伴有手麻、且目前没有缓解，这需要优先由有资质的医疗人员评估。门店不能判断原因，也不能指导您在家采用热敷、冷敷或其他处理方式；在情况明确前，请停止项目和自行处理。";
    normalized.uncertainties = ["需要由医疗人员评估症状及是否存在紧急情况。"];
    normalized.recommended_action = "如症状持续、加重或伴随无力、胸痛、呼吸困难、晕厥等情况，请及时就医或联系急救；同时保留服务时间和反应记录。";
  } else if (route.stop_sales) {
    const surgeryQuestion = /替代手术/i.test(context);
    const numbnessBoundary = /腰椎间盘突出|颈椎病|腿麻|手麻|麻木|无力/i.test(context);
    normalized.answer = surgeryQuestion
      ? `点阵波不能替代手术、医疗诊断或医生制定的治疗方案。${numbnessBoundary ? "你已提到麻木或无力等症状，今天应先停止项目与销售推进，并由医疗机构评估；若症状持续、加重或伴随大小便异常、会阴麻木等情况，请及时就医或联系急救。" : "如果同时已有相关诊断，或出现麻木、无力等异常，应先由医疗机构评估，不要用项目体验替代医疗评估。"}`
      : numbnessBoundary
        ? "您提到持续不适并出现手麻、腿麻、麻木或无力，这需要先由医疗机构评估；今天先不要体验项目，也不要继续销售沟通。门店不能判断病因，也不能用项目体验替代医疗诊断或评估；症状持续或加重时请及时就医。"
      : followUp
        ? "现在先停止体验和销售沟通，不要自行判断原因。若胸痛、呼吸困难、晕厥、明显出冷汗或进行性麻木无力正在发生、持续或加重，请尽快联系急救或前往医疗机构；情况稳定后再由门店负责人记录并跟进。"
        : "您提到的情况需要先确认安全，今天先不要做项目，也不要继续产品推荐。请告诉我症状从什么时候开始、是否正在加重，以及有没有胸痛、呼吸困难、晕厥或进行性麻木无力；症状明显、持续或加重时，请尽快联系急救或前往医疗机构。";
    normalized.uncertainties = ["需要确认症状开始时间、程度、变化和伴随情况。"];
    normalized.recommended_action = "停止销售推进，完成风险问询、负责人升级和必要的医疗分流。";
  } else if (/(?:背部|后背).{0,8}(?:凉|冷)|(?:凉|冷).{0,8}(?:背部|后背)|器官功能/i.test(context)) {
    normalized.answer = "背部发凉是一种主观感受，不能据此判断某个器官功能不好，也不能由门店作疾病诊断。先确认从什么时候开始、是否持续或加重，以及有没有疼痛、麻木、无力、胸痛、呼吸困难、发热等伴随情况；症状明显、持续或伴随异常时应由医疗机构评估。";
    normalized.uncertainties = ["需要确认持续时间、变化、诱因和伴随症状。"];
    normalized.recommended_action = "先做风险问询；不能用项目体验替代医疗诊断或评估。";
  } else if (/水分测试笔|水分(?:测试|数值|值)|含水量|含水(?:测试|数值)/i.test(context)) {
    normalized.answer = "一次水分数值升高最多说明当次、当时测量出现变化，不能直接证明长期改善。比较时要尽量使用同一设备、同一部位、相近时间和环境，并记录护肤、清洁等条件；长期结论需要在相同条件下多次复测并结合持续观察。";
    normalized.uncertainties = ["需要确认设备、部位、时间、环境和前后测量条件是否一致。"];
    normalized.recommended_action = "按统一条件记录本次结果，约定后续复测，不把单次读数宣传为长期效果。";
  } else if (/GLP-1|司美|减肥针|处方|药品|减肥药|口服片|剂量|停药|换药|怎么用/i.test(context)) {
    normalized.answer = "若涉及儿童或未成年人，药品适用性不能仅凭聊天判断。具体药品的用法和剂量必须依据当前说明书与医生处方，门店不能给剂量，也不能建议开始、停用或更换药物。请携带药品包装和用药记录，由开药医生或药师核实。";
    normalized.uncertainties = ["需要确认具体药品身份、处方、合并用药和当前症状。"];
    normalized.recommended_action = "暂停具体产品或剂量建议，咨询开药医生或药师。";
  } else if (/孩子|儿童|未成年|孕妇|怀孕|备孕|哺乳|慢病|糖尿病|高血压|三高/i.test(context)) {
    normalized.answer = "这类情况不能仅凭聊天直接判断可以做。先暂停项目或产品推荐，确认具体年龄或阶段、疾病与用药、当前症状和产品或设备说明，再由有资质的医生、药师或相应专业人员确认。";
    normalized.uncertainties = ["需要更具体的健康信息、用药信息和产品说明。"];
    normalized.recommended_action = "确认前不操作、不销售具体方案，先转有资质人员核实。";
  } else if (/敏感肌|皮肤过敏|容易过敏|医美恢复|泛红|刺痛|破损/i.test(context)) {
    normalized.answer = "不能只凭敏感肌判断能不能做。先确认目前有没有持续泛红、刺痛、破损、渗出或过敏发作，以及近期是否做过医美、刷酸、激光或使用强刺激产品；存在这些情况时先不操作，状态稳定后也要核对具体项目和成分。";
    normalized.uncertainties = ["需要确认当前皮肤状态、过敏史和近期项目史。"];
    normalized.recommended_action = "先完成肤况和项目适用性确认；无法确认时不操作。";
  } else if (route.intent_id === "INTENT-PRICE") {
    normalized.answer = "价格和活动会随城市、门店、具体项目和日期变化，我不能用历史资料先口头保证。请告诉我您咨询的城市、门店和项目，再按当前系统里的有效版本核对。";
    normalized.uncertainties = ["需要确认城市、门店、具体项目、查询日期和当前生效版本。"];
    normalized.recommended_action = "确认门店与项目后查询当前系统。";
  } else if (route.intent_id === "INTENT-RESULT") {
    normalized.answer = "我理解您希望尽快看到变化，但不能承诺一次、固定时间或固定结果，也不能保证不反弹。先确认您最想改善的指标和既往情况，再按相同条件记录并做阶段观察，长期变化还会受到生活方式和个体差异影响。";
    normalized.uncertainties = ["需要确认具体项目、顾客目标和用于判断变化的指标。"];
    normalized.recommended_action = "先确定一个可观察指标和必要安全信息，再决定是否体验及何时复盘。";
  } else if (route.intent_id === "INTENT-COMPARISON") {
    normalized.answer = "不同项目不能只按名称判断谁更好，需要围绕您想改善的问题、可接受的体验、时间安排和必要安全信息来比较。请先告诉我您正在比较哪两个项目，以及最在意效果感受、时间还是预算中的哪一点。";
    normalized.uncertainties = ["需要确认正在比较的具体项目和最重要的选择标准。"];
    normalized.recommended_action = "先补齐比较对象和选择标准，再按当前课程与门店有效版本逐项说明。";
  } else if (!String(normalized.answer || "").trim() || String(normalized.answer).includes("演示模式")) {
    normalized.answer = `我先回答您当前最关心的问题：${route.focus || "先确认顾客目标和必要安全信息。"} 目前还不能只凭这一句话直接推荐项目、次数或效果。请再告诉我具体想改善什么，以及这种情况大概持续多久。`;
    normalized.uncertainties = ["需要确认具体目标、持续时间和必要安全信息。"];
    normalized.recommended_action = route.recommended_next || "先补充一个必要信息，再确认下一步。";
  }
  normalized.answer = String(normalized.answer || "暂时没有找到足够依据，请补充具体项目和最想解决的问题。").trim();
  normalized.uncertainties = Array.isArray(normalized.uncertainties) ? normalized.uncertainties.filter(Boolean).slice(0, 4) : [];
  normalized.recommended_action = String(normalized.recommended_action || route.recommended_next || "先补充一个必要信息，再按当前标准确认下一步。").trim();
  normalized.route = publicStaticRoute(route);
  return normalized;
}

const STATIC_TRAINING_RED_FLAG_PATTERN = /胸痛|胸闷|气短|呼吸困难|晕厥|昏厥|突发剧痛|进行性麻木|手(?:臂)?(?:新发|新|发)?麻|胳膊(?:新发|新|发)?麻|腿(?:部)?(?:新发|新|发)?麻|发麻|麻木|无力|发热|红肿|大小便异常|会阴麻木/i;
const STATIC_TRAINING_DISCOMFORT_PATTERN = /疼|痛|灼热|烫|头晕|不舒服|设备异常|设备报警|麻|无力/i;

function staticAffirmedCustomerText(value = "") {
  // Remove only the symptom directly covered by a negator.  Do not delete a
  // whole clause: “没有胸痛但手麻” must retain the affirmed hand numbness.
  return String(value || "").replace(STATIC_NEGATED_RED_FLAG_PATTERN, " ");
}

function staticVisibleCustomerText(scenario, history = []) {
  const visibleTurns = history
    .filter((item) => item?.role === "assistant")
    .map((item) => String(item.content || "").trim())
    .filter(Boolean);
  return staticAffirmedCustomerText([scenario?.opening || "", ...visibleTurns].join(" "));
}

function staticHasAffirmativeEmployeeMatch(message, pattern) {
  const text = String(message || "");
  const flags = pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`;
  const matcher = new RegExp(pattern.source, flags);
  let match;
  while ((match = matcher.exec(text))) {
    const preceding = text.slice(0, match.index);
    const clauseStart = Math.max(...["，", "。", "；", "！", "？", ",", ".", ";", "!", "?"].map((mark) => preceding.lastIndexOf(mark))) + 1;
    const followingBoundaries = ["，", "。", "；", "！", "？", ",", ".", ";", "!", "?"]
      .map((mark) => {
        const position = text.indexOf(mark, match.index + match[0].length);
        return position < 0 ? Number.POSITIVE_INFINITY : position + (/[！？!?]/.test(mark) ? 1 : 0);
      });
    const clauseEnd = Math.min(...followingBoundaries, text.length);
    const clause = text.slice(clauseStart, clauseEnd);
    const clausePrefix = text.slice(clauseStart, match.index);
    const semanticPrefix = clausePrefix.split(/(?:但是|但|而是|可是|然而|不过|却|仍然?|还是|也|所以|因此|然后|同时)/i).at(-1) || "";
    const negated = /(?:不能|不可|不要|不应|不建议|不会|不用|不必|无需|无须|未必|不一定|不代表|不认为|不觉得|不承认|并不|绝不|暂不|先不|停止|避免|拒绝|别)[^，。；！？,.;!?]{0,20}$/i.test(semanticPrefix)
      || /(?:不是|并非)(?:要|让|叫|建议)?(?:你|您|我们)?$/i.test(semanticPrefix)
      || /不把.{0,12}(?:说成|解释成|当成)$/i.test(semanticPrefix)
      || /(?:不|不能|不可)算(?:是)?$/i.test(semanticPrefix)
      || /不$/i.test(semanticPrefix);
    const questioned = (/[？?]/.test(clause) && /难道|是否|是不是|会不会|要不要|能不能|可不可以|有没有|怎么(?:能|会|可以)|为什么|为何/i.test(clause))
      || /(?:是否|是不是|算不算|可否)[^，。；！？,.;!?]{0,8}$/i.test(semanticPrefix);
    const directQuestionSuffix = /^[^，。；！,.;!]{0,10}(?:吗|么|呢)[？?]/i.test(text.slice(match.index + match[0].length));
    if (!negated && !questioned && !directQuestionSuffix) return true;
    if (!match[0].length) matcher.lastIndex += 1;
  }
  return false;
}

function staticTrainingMessageDeniesSafetyAction(message = "") {
  return staticHasAffirmativeEmployeeMatch(
    message,
    /(?:不用|不必|无需|无须|不要|不会|拒绝|别|不需要|没必要).{0,8}(?:暂停|停止|记录|登记|留档|上报|联系负责人|联系店长|就医|去医院|医疗评估|检查)|(?:不|别)(?:建议|需要).{0,8}(?:就医|去医院|医疗评估|检查)/i,
  );
}

function staticTrainingSafeActionFlags(message = "") {
  const text = String(message || "");
  return {
    stopped: staticHasAffirmativeEmployeeMatch(text, /暂停|停止|先不(?:做|继续|安排)|不继续|不会继续(?:做|操作|安排)?|绝不继续|不要继续|今天不(?:做|安排)|不做/i),
    keepsBoundary: staticHasAffirmativeEmployeeMatch(text, /不(?:要)?自行判断|无法判断|不能判断|不(?:在店内)?判断原因|不在店内(?:判断|诊断)|不做诊断|不能诊断/i),
    records: staticHasAffirmativeEmployeeMatch(text, /记录|登记|留档|核对上次/i),
    escalates: staticHasAffirmativeEmployeeMatch(text, /上报|升级处理|联系.{0,6}(?:负责人|店长)|负责人|店长/i),
    refers: staticHasAffirmativeEmployeeMatch(text, /就医|医疗|急救|医院|医生|专业评估|去检查|尽快检查/i),
    takesSeriously: staticHasAffirmativeEmployeeMatch(text, /重视|关注|需要注意|不能忽视|需要特别关注/i),
  };
}

function staticTrainingMessageHasUnsafeContradiction(message = "") {
  const text = String(message || "");
  const normalizes = staticHasAffirmativeEmployeeMatch(text, /(?:正常(?:反应|现象)?|没啥问题|没什么问题|没问题|没事|没关系|不要紧|不碍事|微损伤|自我修复|排寒反应|排毒反应)/i);
  const continues = staticHasAffirmativeEmployeeMatch(text, /(?:继续做|继续操作|接着做(?:完)?|照常(?:做|操作)|再做一次|把.{0,4}(?:项目|体验|操作)?做完|做完再说|明天.{0,4}可以做|加量|加大|加强|打透|不用停|不必停|没必要暂停|忍一忍|坚持一下|越痛越有效)/i);
  return staticCriticalHits(text).length > 0 || normalizes || continues || staticTrainingMessageDeniesSafetyAction(text);
}

function staticTrainingMessageHasCompleteSafeClosure(message = "") {
  const text = String(message || "");
  const actions = staticTrainingSafeActionFlags(text);
  return actions.stopped && actions.keepsBoundary && actions.records && actions.escalates && actions.refers
    && !staticTrainingMessageHasUnsafeContradiction(text);
}

function staticTrainingMessageHasSafeDirection(message = "") {
  const text = String(message || "");
  if (staticTrainingMessageDeniesSafetyAction(text)) return false;
  return Object.values(staticTrainingSafeActionFlags(text)).some(Boolean);
}

function staticTrainingSafetyDecision(scenario, history = [], message = "") {
  const employee = String(message || "");
  const customerFacts = staticVisibleCustomerText(scenario, history);
  const knownRedFlag = STATIC_TRAINING_RED_FLAG_PATTERN.test(customerFacts);
  const knownWorsening = /(?:做完|项目后|服务后|点阵波).{0,24}(?:更疼|更痛|疼痛加重|比.{0,8}(?:更重|还重|更痛))|(?:今天|现在).{0,14}(?:比.{0,8})?(?:更疼|更痛|还重|疼痛加重)/i.test(customerFacts);
  const minimizes = staticHasAffirmativeEmployeeMatch(employee, /(?:正常(?:反应|现象)?|没啥问题|没什么问题|没问题|没事|没关系|不要紧|不碍事|微损伤|自我修复|排寒反应|排毒反应)/i);
  const promisesImprovement = staticHasAffirmativeEmployeeMatch(employee, /(?:会|能|肯定|一定).{0,16}(?:更轻松|缓解|好转|恢复|越来越好)/i);
  const continues = staticHasAffirmativeEmployeeMatch(employee, /(?:继续做|继续操作|接着做(?:完)?|照常(?:做|操作)|再做一次|把.{0,4}(?:项目|体验|操作)?做完|做完再说|明天.{0,4}可以做|加量|加大|加强|打透|不用停|不必停|没必要暂停|忍一忍|坚持一下|越痛越有效)/i);
  const deniesSafety = staticTrainingMessageDeniesSafetyAction(employee);
  const globalCritical = staticCriticalHits(employee).length > 0;

  // A dangerous contradiction always wins, even when the same sentence also
  // contains safe words such as "暂停" or "就医".
  if (globalCritical || (knownWorsening && (minimizes || promisesImprovement || continues || deniesSafety)) || (knownRedFlag && (minimizes || promisesImprovement || continues || deniesSafety))) {
    const hasKnownRedFlag = knownRedFlag;
    return {
      level: "critical",
      issue: hasKnownRedFlag
        ? "顾客已明确出现需要优先处理的新症状，本轮却仍在弱化风险、拒绝安全处置或推进服务。"
        : "顾客已明确说服务后疼痛加重，本轮却将它说成正常、拒绝必要安全处置或保证会好转。",
      why: hasKnownRedFlag
        ? "已知存在需要优先处理的新症状时，必须停止项目、保持不诊断边界，并完成记录上报和医疗分流。"
        : "疼痛比服务前加重已是本轮已知信息，不能先定性为正常，也不能保证之后会变轻。",
      method_step: "立即纠正风险表达并完成安全问询",
      knowledge_focus: "服务后变化、异常记录与必要分流",
      suggested_reply: hasKnownRedFlag
        ? "您已经提到了新的异常症状，我们现在先停止所有项目，不在店内判断原因。我会记录并上报负责人，建议您尽快由医疗机构评估。"
        : "我理解您担心被打坏。疼痛比原来更重不能先说是正常反应；我先确认出现时间、部位和变化，以及有没有发热、肿胀、麻木或无力等新情况。",
      next_goal: hasKnownRedFlag ? "确认顾客理解暂停和医疗分流安排。" : "先问清时间、部位、变化和伴随情况，再给安全的下一步。",
    };
  }

  if ((knownRedFlag || knownWorsening) && staticTrainingMessageHasCompleteSafeClosure(employee)) {
    return {
      level: "good",
      issue: "你已明确暂停项目、不判断原因，并完成记录上报和必要的医疗分流。",
      why: "这些表达形成了完整的安全闭环，没有在店内诊断或继续推进服务。",
      method_step: "停止服务并完成安全升级",
      knowledge_focus: "异常记录、负责人升级与医疗分流",
      suggested_reply: knownRedFlag
        ? "您提到的新症状需要优先处理。现在先停止所有项目，我们不在店内判断原因；我会记录并上报负责人，建议您尽快由医疗机构评估。"
        : "您提到服务后疼痛加重，我们先暂停后续项目，不在店内判断原因。我会完整记录并上报负责人，必要时建议您由医疗机构评估。",
      next_goal: "确认顾客理解安全安排，并完成记录、上报与跟进。",
    };
  }

  const acknowledges = /理解|担心|重视|抱歉|先不判断|不能先说/i.test(employee);
  const pauses = staticTrainingSafeActionFlags(employee).stopped;
  const asksChange = /什么时候|何时|多久|是否.{0,6}加重|是否.{0,8}更重|比.{0,8}(?:重|疼|痛)|变化/i.test(employee);
  const asksCompanion = /伴随|还有.{0,10}(?:不适|症状|反应)|(?:有没有|是否)?其他.{0,8}(?:不适|症状|反应)|有没有.{0,12}(?:麻|无力|发热|红肿|胸痛|不舒服)|是否.{0,12}(?:麻|无力|发热|红肿|胸痛|不舒服)/i.test(employee);
  const priorSafePause = history.some((item) => {
    if (item?.role !== "user") return false;
    const prior = String(item.content || "");
    return staticTrainingSafeActionFlags(prior).stopped
      && !staticTrainingMessageHasUnsafeContradiction(prior);
  });
  if (knownWorsening && asksCompanion) {
    if (pauses || priorSafePause) {
      return {
        level: "good",
        issue: "你在暂停后继续追问麻木、无力、发热或红肿等伴随情况，问询顺序正确。",
        why: "本轮只筛查尚未确认的伴随情况，没有把它们提前当作顾客已经出现的事实。",
        method_step: "在暂停后完成伴随情况筛查",
        knowledge_focus: "麻木、无力、发热、红肿等异常变化",
        suggested_reply: "除了疼痛加重，还有没有麻木、无力、发热、红肿或其他新出现的不适？",
        next_goal: "根据顾客下一轮实际补充的信息，决定记录升级和医疗分流。",
      };
    }
    return {
      level: "needs_work",
      issue: "你已追问伴随情况，但还没有先明确暂停今天的后续项目。",
      why: "服务后疼痛加重时应先暂停安排，再筛查时间、变化和伴随情况。",
      method_step: "先暂停，再完成伴随情况筛查",
      knowledge_focus: "服务后变化与安全问询顺序",
      suggested_reply: "疼痛比原来加重需要先重视，今天先暂停后续项目；除了疼痛变化，还有没有麻木、无力、发热、红肿或其他新不适？",
      next_goal: "确认暂停后，根据顾客实际回答决定是否升级和分流。",
    };
  }
  if (knownWorsening && acknowledges && pauses && asksChange) {
    return {
      level: "good",
      issue: "你已经承接顾客的担心、先暂停后续安排，并追问疼痛开始时间和变化。",
      why: "本轮只使用顾客已经说出的“服务后更痛”来判断；先暂停、再问变化，符合安全优先的接待顺序。",
      method_step: "暂停安排并完成服务后变化问询",
      knowledge_focus: "出现时间、变化趋势与伴随情况",
      suggested_reply: "我理解您会担心。疼痛比原来加重不能先简单说是正常，今天先暂停后续项目；请告诉我从什么时候开始、现在是否还在加重。",
      next_goal: "根据顾客下一轮实际补充的信息，再决定是否需要记录升级和医疗分流。",
    };
  }

  if (knownRedFlag && staticTrainingMessageHasSafeDirection(employee)) {
    return {
      level: "needs_work",
      issue: "你已经给出重视和就医的正确方向，但还没有明确暂停服务、保持不诊断边界，并完成记录上报。",
      why: "顾客在本轮之前已经说出新症状；建议就医是安全的，但处置流程仍需补齐。",
      method_step: "补齐暂停、记录上报和医疗分流",
      knowledge_focus: "红旗症状的安全闭环",
      suggested_reply: "您已经提到新的异常症状，我们今天先停止所有项目，不在店内判断原因。我会完整记录并上报负责人，建议您尽快由医疗机构评估。",
      next_goal: "确认顾客理解暂停和分流安排。",
    };
  }
  return null;
}

function sanitizeStaticTrainingSuggestedReply(feedback, scenario, history = []) {
  const advice = String(feedback.suggested_reply || "");
  const unverifiedAdvice = /(?:可能是|可能涉及|说明|属于).{0,14}(?:神经|损伤|炎症|病变)|(?:不要|立即|马上|建议).{0,10}(?:热敷|冷敷|按摩|服药|停药|换药)|(?:热敷|冷敷|按摩).{0,8}(?:手臂|腿|疼痛|发麻)|(?:治疗|治好|治愈|根治)/i;
  if (!unverifiedAdvice.test(advice)) return;
  const knownRedFlag = STATIC_TRAINING_RED_FLAG_PATTERN.test(staticVisibleCustomerText(scenario, history));
  feedback.suggested_reply = knownRedFlag
    ? "您提到的新症状需要优先处理。我们先停止所有项目，不在店内判断原因；我会记录并上报负责人，并建议您尽快由医疗机构评估。"
    : "我先不对原因下结论，想确认这种情况从什么时候开始、是否加重，以及有没有其他新的不适，再按安全流程给您下一步安排。";
}

const STATIC_TRAINING_FACT_MARKERS = ["手麻", "腿麻", "发麻", "麻木", "无力", "胸痛", "呼吸困难", "晕厥", "头晕", "发热", "红肿", "灼热", "设备异常"];

function staticTrainingTextMentionsUnknownFact(text, knownCustomerText) {
  return STATIC_TRAINING_FACT_MARKERS.some((marker) => !knownCustomerText.includes(marker) && String(text || "").includes(marker));
}

function staticTrainingTextClaimsUnknownFact(text, knownCustomerText) {
  return STATIC_TRAINING_FACT_MARKERS.some((marker) => {
    if (knownCustomerText.includes(marker) || !String(text || "").includes(marker)) return false;
    const escaped = marker.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const assertion = new RegExp(`(?:已(?:经)?|刚(?:刚)?|明确|目前|现在|新发|出现|伴有|补充|提到|说(?:了)?).{0,12}${escaped}|${escaped}.{0,8}(?:已(?:经)?|出现|加重|持续)`, "i");
    return assertion.test(String(text || ""));
  });
}

function sanitizeStaticTrainingFutureClaims(feedback, fallback, scenario, history = []) {
  const knownCustomerText = staticVisibleCustomerText(scenario, history);
  let claimedUnknownFact = false;
  ["issue", "why", "method_step", "knowledge_focus", "next_goal"].forEach((key) => {
    if (staticTrainingTextClaimsUnknownFact(feedback[key], knownCustomerText)) claimedUnknownFact = true;
    if (staticTrainingTextMentionsUnknownFact(feedback[key], knownCustomerText)) feedback[key] = fallback[key];
  });
  if (staticTrainingTextClaimsUnknownFact(feedback.suggested_reply, knownCustomerText)) {
    claimedUnknownFact = true;
    feedback.suggested_reply = "我先根据您现在已经说明的情况来处理。这种变化从什么时候开始，现在是否加重，还有没有其他新的不适？";
  }
  if (claimedUnknownFact) feedback.level = fallback.level;
}

function normalizeStaticTrainingFeedback(result, scenario, history, rubric, message, customerReply = "") {
  const fallback = staticMockProgressive("training", "turn", scenario, history, rubric, message).feedback;
  const provided = result?.feedback && typeof result.feedback === "object" ? result.feedback : {};
  const feedback = {};
  ["level", "issue", "why", "method_step", "knowledge_focus", "suggested_reply", "next_goal"].forEach((key) => {
    const value = String(provided[key] || "").trim();
    feedback[key] = value || fallback[key];
  });
  if (!new Set(["good", "needs_work", "critical"]).has(feedback.level)) feedback.level = "needs_work";
  sanitizeStaticTrainingFutureClaims(feedback, fallback, scenario, history);
  const safetyDecision = staticTrainingSafetyDecision(scenario, history, message);
  if (safetyDecision) Object.assign(feedback, safetyDecision);
  sanitizeStaticTrainingSuggestedReply(feedback, scenario, history);
  return feedback;
}

const TEST_INTERNAL_MARKERS = /考核|评分|知识库|方法路由|隐藏异议|must_test|员工应该|培训教练/i;
const CUSTOMER_ROLE_DRIFT_MARKERS = /适用性确认|专业评估|医疗评估|红旗|禁忌|SOP|成分核对|设备型号|阶段指标|复盘|治疗史|特殊护肤品|强刺激产品|作用原理|工作原理|操作流程|测温|设备参数|产品机制|(?:建议|请)您|我建议(?:你|您)|你(?:应该|需要).{0,12}(?:询问|确认|了解|评估|说明)|您.{0,18}(?:有没有|是否|做过|用过|最近一次|病史|过敏史)/i;
const LIMITED_CUSTOMER_POLICY = `顾客认知边界（最高优先级）：顾客只知道自己的困扰、感受、生活情况和真实顾虑；最多听过一个模糊项目名，不知道原理、成分、设备、适用标准、禁忌或操作流程。只回答员工最新问题，每轮只说一个事实、感受或顾虑，通常15—60个汉字，最多问一个普通顾客会问的问题。不得替员工做需求分析、风险筛查或建议，不得反问员工的病史、医美史、过敏史、用药和护肤品。员工答错时可以不满意或要求重讲，但始终保持来咨询的普通顾客身份。不得使用适用性确认、专业评估、医疗评估、红旗、禁忌、SOP、成分核对、设备型号、阶段指标、复盘等专业词。员工只给出简单否定、空泛肯定（例如“有的”“可以”“好的”）或答非所问时，这不算已经回答顾客；先围绕原始困扰追问具体方法、项目或安排，只有员工给出相关实际说明后才进入下一条顾虑。`;

function staticCustomerScenario(scenario = {}) {
  const persona = scenario.persona || {};
  return {
    persona: Object.fromEntries(["age", "gender", "occupation", "style", "goal", "risk", "knowledge_level"].filter((key) => persona[key] != null && persona[key] !== "").map((key) => [key, persona[key]])),
    hidden_objections: scenario.hidden_objections || [],
    hidden_information: scenario.hidden_information || [],
    information_release_rules: scenario.information_release_rules || [],
  };
}

function staticPublicTrainingScenario(scenario = {}) {
  return {
    title: scenario.title || "",
    module_title: scenario.module_title || "",
    task: scenario.task || "",
    opening: scenario.opening || "",
  };
}

const CUSTOMER_VAGUE_EMPLOYEE_REPLY = /^(?:有|有的|有办法|有相关项目|可以|可以的|能做|好的|好|是的|对|对的|没问题|了解|知道)(?:[，。！!、,\s]*(?:有|的|办法|可以|好的|好|是的|对|对的|没问题|了解|知道))*[。！!，,、\s]*$/i;
const CUSTOMER_HOLD_REPLY_MARKERS = /没听明白|具体是什么办法|再具体说说|再说清楚|先介绍一下/i;

function staticCustomerClarificationReply(scenario, history = []) {
  const goal = String(scenario?.persona?.goal || "我现在这个困扰").trim();
  const lastCustomer = [...history].reverse().find((item) => item?.role === "assistant")?.content || "";
  if (/有没有|有适合|什么办法|什么方法|怎么|如何|方案|项目/.test(String(lastCustomer))) return "我还没听明白，具体是什么办法，适合我这种情况吗？";
  return `我还没听明白，能再具体说说吗？我主要还是想解决${goal}。`;
}

function staticEmployeeMessageNeedsCustomerClarification(history = [], employeeMessage = "") {
  const employee = String(employeeMessage || "").trim();
  if (!employee || CUSTOMER_VAGUE_EMPLOYEE_REPLY.test(employee)) return true;
  if (/我错了|说错了|不好意思|抱歉|不能做|做不了|没什么不同|没区别|都一样|不适合|多久|多长时间|什么时候开始|哪里|哪个部位|什么位置/.test(employee)) return false;
  if (employee.length <= 8 && !/[？?]/.test(employee)) return true;
  const lastCustomer = [...history].reverse().find((item) => item?.role === "assistant")?.content || "";
  const asksForMethod = /有没有|有适合|什么办法|什么方法|怎么|如何|方案|项目/.test(String(lastCustomer));
  return asksForMethod && !/方法|办法|方案|项目|体验|流程|步骤|安排|介绍|说明|适合/.test(employee);
}

function staticHiddenObjectionIndex(history = []) {
  const userTurns = history.filter((item) => item?.role === "user").length;
  const heldTurns = history.filter((item) => item?.role === "assistant" && CUSTOMER_HOLD_REPLY_MARKERS.test(String(item.content || ""))).length;
  return Math.max(0, userTurns - heldTurns);
}

function staticSafetyFlowCustomerReply(scenario, history = [], employeeMessage = "") {
  const customerFacts = staticVisibleCustomerText(scenario, history);
  if (!STATIC_TRAINING_RED_FLAG_PATTERN.test(customerFacts) || !staticTrainingMessageHasSafeDirection(employeeMessage) || staticTrainingMessageHasUnsafeContradiction(employeeMessage)) return "";
  if (staticTrainingMessageHasCompleteSafeClosure(employeeMessage)) {
    return "好的，那我先不做了。麻烦您帮我记录下来，也告诉我后面怎么联系负责人。";
  }
  return "好的，我会尽快去检查。那我今天是不是先不做任何项目了？";
}

function staticPointWaveReleaseReply(scenario, history = [], employeeMessage = "", candidateReply = "") {
  if (scenario?.id !== "SCN-CEX-M03-S01") return "";
  return staticGenericInformationReleaseReply(candidateReply, scenario, history, employeeMessage);
}

const STATIC_GENERIC_RELEASE_ASK_MARKERS = /[？?]|(?:请|麻烦).{0,8}(?:说|告诉|提供)|(?:想|需要).{0,6}(?:了解|确认)|是否|有没有|有无|什么|怎么|如何|哪|几|多久|多长|吗|么|呢/i;
const STATIC_GENERIC_RELEASE_SHORT_FACTS = /成都|空腹|高血压|手麻|发麻|麻木|胸闷|胸痛|头晕|发热|无力|电击|备孕|结石|反黑|漏尿|出血|哺乳|便秘|晒伤|红肿|渗出|视物模糊|甲状腺|酸类|玻尿酸|经期|腰围|排便|不耐受|喝不下水|没吃早饭|眼周肿|异味|灌痛/gi;
const STATIC_GENERIC_RELEASE_NUMBER_FACTS = /(?:\d+(?:\.\d+)?|[一二两三四五六七八九十半]+)(?:个)?(?:年|月|天|小时|分钟|分|厘米|次|袋)/gi;
const STATIC_GENERIC_RELEASE_DENIED_QUESTION = /(?:不是|并非).{0,10}(?:问|询问|追问|了解|确认)|(?:不|没|没有|无需|无须|不用|不必|不要|并不|不想|暂不|别).{0,4}(?:问|询问|追问|了解|确认)|(?:多久|多长时间|什么时候|何时|是否|有没有).{0,8}(?:不问|别问|不用问|无需问|不必问)/i;

const STATIC_GENERIC_RELEASE_COMPOUND_QUESTIONS = {
  "时间和变化": [/多久|多长时间|什么时候|何时|哪天|开始|持续/i, /变化|加重|变重|更重|更痛|更疼|越来越|减轻|好转|严重/i],
  "病史和进食": [/病史|高血压|慢性病|基础病/i, /进食|吃饭|吃东西|早饭|空腹/i],
  "饮食和经期": [/饮食|吃|聚餐/i, /经期|月经|例假|生理期/i],
  "复查和出血": [/复查|产后检查|检查过/i, /出血|流血|血性/i],
  "饮水排便": [/饮水|喝水|水喝/i, /排便|大便|便秘/i],
  "试感和停止方式": [/试感|试一下|小范围|先试/i, /停止|停下|随时停|叫停/i],
};

const STATIC_GENERIC_RELEASE_SINGLE_QUESTIONS = {
  "持续时间": /多久|多长时间|持续|几天|几个月|几年/i,
  "开始时间": /什么时候|何时|哪天|刚开始|开始时间/i,
  "产后时间": /产后.{0,6}(?:多久|时间)|生完.{0,6}多久|几个月/i,
  "伴随症状": /伴随|其他.{0,8}(?:不适|症状|反应)|有没有.{0,12}(?:麻|无力|发热|胸痛|胸闷|不舒服)/i,
  "门店": /门店|哪家店|哪个店|城市|地区|在哪里/i,
  "券名": /券名|券的名称|什么券|哪张券|券.{0,5}截图/i,
  "贵在哪里": /贵.{0,8}(?:哪|什么|原因|顾虑)|在意.{0,8}(?:价格|效果|预算)/i,
  "竞品包含内容": /竞品|别家|楼下|对方.{0,6}(?:包含|包括)|包了什么|做几次/i,
  "使用体验": /使用体验|用着|用了.{0,6}(?:感觉|觉得)|舒服|效果/i,
  "疼痛程度": /疼痛|疼|痛.{0,6}(?:程度|几分|多严重)|\d+\s*分/i,
  "感觉": /什么感觉|怎么痛|哪种感觉|感觉.{0,6}(?:像|是)/i,
  "进食饮水": /进食|吃饭|吃东西|早饭|空腹|饮水|喝水|喝不下/i,
  "变化": /变化|加重|变重|变大|扩大|更痛|更疼|越来越|减轻|好转|严重/i,
  "检查": /检查|报告|查过|复查/i,
  "症状": /症状|不适|哪里难受|痛|痒|灼|异味|分泌物/i,
  "测量": /测量|称重|什么时候称|早上|晚上/i,
  "其他指标": /其他指标|腰围|体围|体脂|除了体重/i,
  "餐次": /餐次|早餐|早饭|晚餐|一天几顿|怎么吃/i,
  "反应": /反应|不耐受|不舒服|过敏|红肿/i,
  "身体状态": /身体|状态|不舒服|乏力|头晕|精神/i,
  "用药": /用药|药物|吃药|服药|注射|打针/i,
  "特殊情况": /特殊情况|备孕|怀孕|哺乳|孕期/i,
  "病史": /病史|以前得过|慢性病|基础病|结石|高血压/i,
  "执行": /怎么.{0,6}(?:用|打|执行)|每天|频次|按计划/i,
  "营养": /营养|进食|吃得|食量|胃口/i,
  "复诊": /复诊|回诊|看过医生|定期检查/i,
  "怎么吃": /怎么吃|怎么喝|一天几袋|什么时候喝|代餐/i,
  "旧产品": /旧产品|以前的|哪个牌子|谁家|买了多久/i,
  "不适位置": /不适|哪里|位置|部位|钢圈|肩带|压痛/i,
  "主要问题": /主要|最想|哪个问题|困扰|诉求|目标/i,
  "目标": /目标|最想|想改善|想解决|在意|诉求/i,
  "既往产品": /既往|以前|之前|用过.{0,8}(?:产品|护肤品)|什么产品/i,
  "护肤": /护肤|刷酸|酸类|产品|昨晚用/i,
  "其他反应": /其他.{0,8}(?:反应|不适|症状)|眼周|呼吸|肿/i,
  "皮肤状态": /皮肤|皮肤状态|晒伤|暴晒|发红|破损/i,
  "皮肤": /皮肤|发红|红肿|表面|触痛/i,
  "既往反应": /既往|以前|之前|反应|红肿|过敏/i,
  "面部状态": /面部|脸型|脸.{0,5}(?:瘦|凹)|太阳穴|容量/i,
  "既往项目": /既往|以前|之前|做过.{0,8}(?:项目|填充|医美)|最近做/i,
  "既往史": /既往|以前|之前|激光|反黑|治疗过/i,
  "防晒": /防晒|暴晒|晒太阳|户外/i,
  "既往注射": /既往|以前|之前|注射|填充|打过什么/i,
  "眼部症状": /眼部|眼睛|视力|视物|模糊/i,
  "性生活": /性生活|性经历|伴侣|频率/i,
  "产后功能": /产后|盆底|漏尿|功能|憋不住/i,
  "使用产品": /使用.{0,6}(?:产品|洗液|药)|用了什么|洗液/i,
  "出血": /出血|流血|血性/i,
};

const STATIC_GENERIC_RELEASE_ACTIONS = {
  "堆叠项目": /项目.{0,28}项目|(?:所有|全部|全套|一整套|很多|多个).{0,8}项目/i,
  "直接承诺": /承诺|保证|肯定|一定|绝对|(?:可以|能).{0,8}(?:叠加|一起用)/i,
  "施压成交": /今天必须|现在就|马上.{0,6}(?:付款|购买|买|定)|不买.{0,8}(?:后悔|没有)|逼|必须买/i,
  "贬低原品牌": /原品牌.{0,8}(?:不好|没效|差|垃圾)|别的牌子.{0,8}(?:不好|没效|差)/i,
  "道歉并重新介绍": /抱歉|不好意思|是我.{0,6}(?:太快|没听清)|重新介绍|我是.{0,10}(?:顾问|负责|接待)/i,
  "继续解释套餐": /套餐|卡项|办卡/i,
  "建议继续做": /继续做|再做一次|加量|打透|照常做/i,
  "谈钱": /钱|价格|费用|浪费|退款/i,
  "否定按摩": /按摩.{0,8}(?:没用|无效|不好|不行)|不要.{0,5}按摩/i,
  "提医疗治疗": /医疗|治疗|医院|医生|就医/i,
  "说越热越好": /越热越好|热一点.{0,8}(?:更好|有效)|温度越高/i,
  "提出小范围试用": /小范围|小面积|先试用|试用一下/i,
  "提出试感和停止方式": /(?=.*(?:试感|试一下|小范围|先试))(?=.*(?:停止|停下|随时停|叫停))/i,
  "说继续": /继续做|继续操作|照常做|再做|加量/i,
  "承诺项目": /承诺|保证|一定|肯定|(?:能|可以).{0,8}(?:治好|解决|改善)/i,
  "承诺快速效果": /快速|马上|很快|一个月.{0,8}(?:减|瘦)|承诺.{0,8}(?:减|瘦)/i,
  "要求运动": /必须|要求|每天|每周|运动|锻炼/i,
  "直接推荐填充": /直接.{0,6}填充|现在.{0,6}填充|今天.{0,6}填充|建议.{0,6}填充/i,
  "直接推荐": /直接推荐|马上.{0,6}(?:用|做|开始)|就用这个|建议你.{0,8}(?:用|做|买)/i,
  "只建议观察": /再观察|先观察|回家观察|等一等|暂时不用处理/i,
  "给具体加量": /加量|多喝.{0,4}(?:一袋|两袋|\d+袋)|增加.{0,6}(?:用量|剂量)/i,
  "说正常": /正常反应|正常现象|这很正常|没问题|没事/i,
  "承诺不勒": /保证.{0,8}不勒|一定.{0,8}不勒|绝对.{0,8}不勒|不会勒/i,
  "默认组合": /两个.{0,8}(?:一起|组合)|组合.{0,8}(?:做|项目)|都给你安排/i,
  "安排马上做": /马上做|立即做|现在做|今天就做|当天做/i,
  "承诺一次": /一次.{0,8}(?:去净|解决|治好|有效)|保证.{0,8}一次|永久/i,
  "直接教凝胶用量": /凝胶.{0,10}(?:用量|剂量|次|毫升|克|次数)|每次.{0,8}凝胶/i,
};

function staticInformationReleaseRuleParts(rule) {
  const text = String(rule || "").trim();
  const delimiter = text.indexOf("时，");
  if (delimiter < 0) return ["", ""];
  return [text.slice(0, delimiter).replace(/^员工/, "").trim(), text.slice(delimiter + 2).replace(/[。.\s]+$/, "").trim()];
}

function staticEmployeeAffirmativelyAsksReleaseQuestion(employeeMessage, pattern) {
  const message = String(employeeMessage || "").trim();
  const flags = pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`;
  const matcher = new RegExp(pattern.source, flags);
  let match;
  while ((match = matcher.exec(message))) {
    const before = message.slice(0, match.index);
    const after = message.slice(match.index + match[0].length);
    const clausePrefix = before.split(/[，。；！？,.;!?]/).at(-1) || "";
    const clauseSuffix = after.split(/[，。；！？,.;!?]/)[0] || "";
    const clause = `${clausePrefix}${match[0]}${clauseSuffix}`;
    const deniedBefore = /(?:不是|并非).{0,8}(?:在)?(?:问|询问|追问|了解|确认).{0,8}$|(?:不|没|没有|无需|无须|不用|不必|不要|并不|不想|暂不|别).{0,4}(?:问|询问|追问|了解|确认).{0,8}$/i.test(clausePrefix);
    const deniedAfter = /^(?:先|就|我们|现在|暂时)?.{0,4}(?:不问|别问|不用问|无需问|无须问|不必问|不需要问)/i.test(clauseSuffix);
    if (!deniedBefore && !deniedAfter && STATIC_GENERIC_RELEASE_ASK_MARKERS.test(clause)) return true;
    if (!match[0].length) matcher.lastIndex += 1;
  }
  return false;
}

function staticEmployeeTriggersInformationReleaseRule(employeeMessage, rule) {
  const [condition] = staticInformationReleaseRuleParts(rule);
  const employee = String(employeeMessage || "").trim();
  if (!condition || !employee) return false;
  if (/^(?:问|询问|追问)/.test(condition)) {
    if (!STATIC_GENERIC_RELEASE_ASK_MARKERS.test(employee)) return false;
    const core = condition.replace(/^(?:问|询问|追问)/, "").replace(/^[“\"']|[”\"']$/g, "").trim();
    const compound = STATIC_GENERIC_RELEASE_COMPOUND_QUESTIONS[core];
    if (compound) return compound.every((pattern) => staticEmployeeAffirmativelyAsksReleaseQuestion(employee, pattern));
    const pattern = STATIC_GENERIC_RELEASE_SINGLE_QUESTIONS[core];
    if (pattern) return staticEmployeeAffirmativelyAsksReleaseQuestion(employee, pattern);
    const tokens = core.split(/和|及|、/).filter((token) => token.length >= 2);
    return Boolean(tokens.length) && tokens.every((token) => staticEmployeeAffirmativelyAsksReleaseQuestion(
      employee,
      new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"),
    ));
  }
  const pattern = STATIC_GENERIC_RELEASE_ACTIONS[condition];
  return pattern ? staticHasAffirmativeEmployeeMatch(employee, pattern) : false;
}

function staticInformationReleaseReply(rule) {
  const [, disclosure] = staticInformationReleaseRuleParts(rule);
  if (!disclosure) return "";
  const quoted = [...disclosure.matchAll(/[“\"]([^”\"]+)[”\"]/g)].map((match) => match[1]);
  if (quoted.length) {
    const text = String(quoted[0]).trim().replace(/[。！？!?]+$/, "");
    return `${text}${/[？?]/.test(quoted[0]) ? "？" : "。"}`;
  }
  const naturalResponses = [
    [/发送截图.*名称模糊/i, "我只能发一张截图，不过上面的名称有点模糊。"],
    [/顾客更反感/i, "你这样催我，我更不想现在决定了。"],
    [/顾客终止对话/i, "那我先不考虑了。"],
    [/顾客态度缓和/i, "好，那你先说说看。"],
    [/顾客愿意继续/i, "可以，那我们先小范围试试看。"],
    [/顾客马上同意/i, "那我今天就再做一次吧。"],
    [/顾客表示胸闷更明显/i, "我现在感觉胸闷更明显了。"],
    [/顾客表示害怕/i, "这么热我有点害怕，先停一下吧。"],
    [/顾客要求加热出更多汗/i, "那再加热一点，让我多出些汗吧。"],
    [/顾客说自己没看病/i, "我没有去医院看过，也没有诊断。"],
    [/顾客追问具体斤数/i, "那一个月具体能减多少斤？"],
    [/顾客说产品来自网络/i, "这个产品是我从网上买的。"],
    [/顾客说越来越严重/i, "可我感觉越来越严重了。"],
    [/顾客问是否能喝两袋/i, "那我可以一次喝两袋吗？"],
    [/顾客要求下周继续/i, "那我下周还可以继续做吗？"],
    [/顾客追问能否保证/i, "那你能保证一定不会勒吗？"],
    [/顾客说只想选一个/i, "我只想选一个项目，不想两个一起做。"],
    [/顾客要求写进合同/i, "那可以把这个保证写进合同吗？"],
    [/顾客问当天能否做/i, "那我今天可以直接做吗？"],
    [/顾客拒绝/i, "这个细节我不想回答。"],
  ];
  const natural = naturalResponses.find(([pattern]) => pattern.test(disclosure));
  if (natural) return natural[1];
  const payload = disclosure.replace(/^(?:顾客)?(?:说明|回答|说|表示|追问|要求)/, "").replace(/^[，,\s]+/, "").trim();
  if (!payload) return "我还想再了解清楚一点。";
  if (/^\d+分$/.test(payload)) return `大概${payload}。`;
  return `我这边的情况是：${payload.replace(/。$/, "")}。`;
}

function staticCompactReleaseText(value) {
  return String(value || "").trim().replace(/^(?:顾客|客户|她|他)/, "").replace(/[\s，,。.；;:：！!？?“”\"'、]/g, "");
}

function staticTextHasNewHiddenFragment(candidate, scenario, history = []) {
  const candidateCompact = staticCompactReleaseText(candidate);
  if (!candidateCompact) return false;
  const visibleCompact = staticCompactReleaseText(history.filter((item) => item?.role === "assistant").map((item) => item.content || "").join(" "));
  const disclosures = (scenario?.information_release_rules || []).map((rule) => staticInformationReleaseRuleParts(rule)[1]);
  const sources = [...(scenario?.hidden_information || []), ...disclosures];
  for (const source of sources) {
    const sourceCompact = staticCompactReleaseText(source);
    if (!sourceCompact) continue;
    for (let size = Math.min(10, sourceCompact.length); size >= 4; size -= 1) {
      for (let index = 0; index <= sourceCompact.length - size; index += 1) {
        const fragment = sourceCompact.slice(index, index + size);
        if (candidateCompact.includes(fragment) && !visibleCompact.includes(fragment)) return true;
      }
    }
    for (const pattern of [STATIC_GENERIC_RELEASE_NUMBER_FACTS, STATIC_GENERIC_RELEASE_SHORT_FACTS]) {
      pattern.lastIndex = 0;
      for (const match of sourceCompact.matchAll(pattern)) {
        const fragment = staticCompactReleaseText(match[0]);
        if (fragment && candidateCompact.includes(fragment) && !visibleCompact.includes(fragment)) return true;
      }
    }
    for (const match of String(source || "").matchAll(/[“\"]([^”\"]+)[”\"]/g)) {
      const fragment = staticCompactReleaseText(match[1]);
      if (fragment.length >= 2 && candidateCompact.includes(fragment) && !visibleCompact.includes(fragment)) return true;
    }
  }
  return false;
}

function staticGenericInformationReleaseReply(candidateReply, scenario, history = [], employeeMessage = "") {
  const rules = scenario?.information_release_rules || [];
  if (!rules.length) return "";
  const visibleCompact = staticCompactReleaseText(history.filter((item) => item?.role === "assistant").map((item) => item.content || "").join(" "));
  for (const rule of rules) {
    if (!staticEmployeeTriggersInformationReleaseRule(employeeMessage, rule)) continue;
    const reply = staticInformationReleaseReply(rule);
    if (reply && !visibleCompact.includes(staticCompactReleaseText(reply))) return reply;
  }
  // Rule-bearing scenarios never pass model-authored text through.  Semantic
  // paraphrases are otherwise able to evade exact hidden-fragment matching.
  const safetyFallback = staticSafetyFlowCustomerReply(scenario, history, employeeMessage);
  if (safetyFallback) return safetyFallback;
  const fallbackEmployee = STATIC_GENERIC_RELEASE_DENIED_QUESTION.test(String(employeeMessage || "")) ? "" : employeeMessage;
  return staticCustomerFallback(scenario, history, fallbackEmployee);
}

function staticCustomerFallback(scenario, history = [], employeeMessage = "") {
  const persona = scenario?.persona || {};
  const goal = String(persona.goal || "我现在这个困扰").trim();
  const employee = String(employeeMessage || "").trim();
  const safetyFlowReply = staticSafetyFlowCustomerReply(scenario, history, employee);
  if (safetyFlowReply) return safetyFlowReply;
  if (/我错了|说错了|不好意思|抱歉/.test(employee)) return `没关系，你重新给我讲清楚就行。我主要还是想解决${goal}。`;
  if (/不能做|做不了|没什么不同|没区别|都一样|不适合/.test(employee)) return `那我有点没听明白，我主要是${goal}，想知道还有没有别的办法。`;
  if (/多久|多长时间|什么时候开始/.test(employee)) return "有一阵子了，最近感觉比以前明显一些。";
  if (/哪里|哪个部位|什么位置/.test(employee)) return `主要就是${goal}，其他地方我暂时没太留意。`;
  if (/测量时间.{0,12}(?:不一样|不同)|结果.{0,10}(?:不一样|不同)|同一(?:时间|条件)/.test(employee)) return "明白了，那我之后尽量在相近时间、相近条件下测量。这样记录几天后再一起判断效果呢？";
  if (/不能直接说明|不能保证|连续趋势|测量条件|数据记录|再判断|再评估/.test(employee)) return "我明白，单次体重上涨不一定代表没有效果。那我们记录多久、达到什么变化时再一起判断呢？";
  if (String(scenario?.module_id || "") === "MOD-05" && /复测|记录|饮食|睡眠|运动|三到七天|一周后|相近时间|跟进/.test(employee)) return "好，那我先按相近时间复测，也把饮食、睡眠和运动记下来。到时候如果还是不降，我们再一起看看，可以吗？";
  if (staticEmployeeMessageNeedsCustomerClarification(history, employee)) return staticCustomerClarificationReply(scenario, history);
  const objections = scenario?.hidden_objections || [];
  const userTurns = staticHiddenObjectionIndex(history);
  if (userTurns >= objections.length) {
    const genericReplies = [`这些专业的我不太懂，我主要就是想解决${goal}。`, "我现在没有别的问题了，就是还没完全放心。", "那我先听到这里，想清楚以后再决定。", "我还得再想想，现在不想马上决定。", "我听明白一点了，不过心里还是有些犹豫。", "我主要担心的还是自己的情况到底能不能改善。"];
    return genericReplies[(userTurns - objections.length) % genericReplies.length];
  }
  const objection = objections[userTurns];
  if (/评分|员工|设置/.test(String(objection))) return "我最担心的是过程中会不会太痛或不舒服，能不能随时停下来？";
  const templates = {
    "怕疼": "我比较怕疼，过程中会不会很难受？",
    "太贵": "我也有点担心价格会不会太高。",
    "一次有没有用": "我还担心做一次看不到什么变化。",
    "时间": "我平时工作很忙，能安排出来的时间不多。",
    "固定斤数": "我还是很在意到底能不能瘦到自己想要的样子。",
    "价格": "我还要考虑预算，太贵的话可能不会做。",
    "成分/过敏": "我以前皮肤用东西容易不舒服，所以有点担心过敏。",
    "怕设备不安全": "我很怕烫，也担心过程中会不舒服。",
    "医院太贵": "我就是觉得去医院太贵了，所以才想先来问问。",
    "怕手术": "我一想到可能要做手术就很害怕。",
    "怕没效果": "我最怕花了钱却没什么变化。",
    "不信任": "我现在还不太放心，想先听你讲明白。",
    "一次见效": "我还担心做一次是不是看不出变化。",
    "疗效证据": "我以前试过不少方法都没坚持住，怕这次也没用。",
    "不想控制饮食": "如果还要管得特别严格，我可能坚持不了。",
    "回家考虑": "我还不想现在决定，想回去再考虑一下。",
    "药品身份": "我就是不确定这个到底算不算药，心里有点怕。",
    "疾病风险": "我有血糖问题，最担心会不会对身体有影响。",
    "价值不清": "我现在还没听明白贵在哪里。",
    "不愿回答问题": "我不太想说太多私人的事情。",
    "担心隐私": "我最在意的是隐私，不能接受的话我就不做。",
    "担心被强推": "我不希望一来就被一直推着买东西。",
    "担心异常": "我就是担心今天更酸痛是不是不正常。",
    "想继续购买": "如果这次没什么问题，我原本还想继续做。",
    "设备真伪": "我也分不清设备有什么区别，怕花冤枉钱。",
    "服务差异": "我看不出你们和别家到底差在哪里。",
  };
  const naturalObjection = String(objection || "").trim();
  const fallbackObjection = /^(?:担心|害怕|想|不想|在意|觉得|担忧)/.test(naturalObjection)
    ? `我现在主要还是${naturalObjection}`
    : `我现在主要还是担心${naturalObjection}`;
  return templates[objection] || `${fallbackObjection}，其他专业的我也不太懂。`;
}

function invalidStaticCustomerReply(reply) {
  const questionCount = (reply.match(/[？?]/g) || []).length;
  return !reply || reply.length > 100 || TEST_INTERNAL_MARKERS.test(reply) || CUSTOMER_ROLE_DRIFT_MARKERS.test(reply) || questionCount > 1;
}

function staticCustomerReplyNeedsContextRepair(reply, employeeMessage) {
  const text = String(reply || "").trim();
  const employee = String(employeeMessage || "").trim();
  if (!text || !employee) return false;
  const planOrExplanation = /测量时间.{0,16}(?:不一样|不同)|结果.{0,12}(?:不一样|不同)|同一(?:时间|条件)|相近时间|复测|记录.{0,12}(?:饮食|睡眠|运动|数据)|连续趋势|三到七天|一周后|先把.{0,10}记录|再一起判断/.test(employee);
  if (!planOrExplanation) return false;
  if (/(?:这些专业的我不太懂|主要还是(?:想|担心|希望)|先听懂再决定|还没完全放心)/.test(text)) return true;
  const acknowledgment = /明白|好的|好，那|原来|我会|我先|听起来|可以|接受|理解/.test(text);
  return /[？?]/.test(text) && !acknowledgment && text.length <= 48;
}

function normalizeStaticCustomerReply(reply, scenario, history = [], employeeMessage = "") {
  let normalized = String(reply || "").trim();
  if ((scenario?.information_release_rules || []).length) {
    // A rule-bearing scenario always resolves to one normalized release group
    // or a deterministic fallback; model-authored text never crosses the gate.
    if (scenario?.id === "SCN-CEX-M03-S01") return staticPointWaveReleaseReply(scenario, history, employeeMessage, normalized);
    return staticGenericInformationReleaseReply(normalized, scenario, history, employeeMessage);
  }
  const safetyFlowReply = staticSafetyFlowCustomerReply(scenario, history, employeeMessage);
  if (safetyFlowReply) return safetyFlowReply;
  const safetyDecision = staticTrainingSafetyDecision(scenario, history, employeeMessage);
  if (safetyDecision?.level === "critical" && /(?:好的|好|明白|可以).{0,16}(?:去检查|就医|先不做|暂停|帮我记录|联系负责人)/i.test(normalized)) {
    return "我还是不放心，你刚才这样说到底是什么意思？";
  }
  if (staticEmployeeMessageNeedsCustomerClarification(history, employeeMessage)) return staticCustomerClarificationReply(scenario, history);
  const previous = history.filter((item) => item?.role === "assistant").map((item) => String(item.content || "").trim());
  const repeated = previous.some((item) => normalized === item || (normalized.length >= 18 && item.length >= 18 && normalized.slice(0, 18) === item.slice(0, 18)));
  if (repeated || invalidStaticCustomerReply(normalized) || normalized === String(scenario?.opening || "").trim()) normalized = staticCustomerFallback(scenario, history, employeeMessage);
  if (staticCustomerReplyNeedsContextRepair(normalized, employeeMessage)) normalized = staticCustomerFallback(scenario, history, employeeMessage);
  return normalized;
}

function normalizeStaticTestTurn(result, scenario, history = [], employeeMessage = "") {
  const normalized = result && typeof result === "object" ? result : {};
  const reply = normalizeStaticCustomerReply(normalized.reply, scenario, history, employeeMessage);
  const emotions = new Set(["curious", "hesitant", "concerned", "relieved", "neutral"]);
  return { reply, emotion: emotions.has(normalized.emotion) ? normalized.emotion : "neutral", should_continue: normalized.should_continue !== false };
}

function staticAssessmentFailureMatches(history = []) {
  const matches = new Map();
  const add = (code, message) => {
    if (!matches.has(code)) matches.set(code, `员工原话：“${String(message || "").trim().slice(0, 180)}”`);
  };
  const continuePattern = /可以(?:继续)?做|还可以做|继续做|继续操作|接着做(?:完)?|照常(?:做|操作)|再做一次|把.{0,4}(?:项目|体验|操作)?做完|做完再说|加量|加大|安排项目|先体验|正常(?:反应|现象|的)?|没(?:啥|什么)?问题|没事|没关系|不要紧|不碍事|不用停|不必停|没必要暂停|忍一忍|坚持一下/i;
  const refusalPattern = /不想|拒绝|不要触碰|不拍照|不愿意|别问了|回家考虑|和家人商量/i;
  const pressurePattern = /必须|今天就|现在就|一定要|不能拒绝|不买|不做.{0,8}(?:后悔|更严重)|别告诉|隐瞒/i;
  let priorCustomerText = "";
  let priorCustomerHasRedFlag = false;
  let priorCustomerHasDiscomfort = false;
  history.forEach((item) => {
    const message = String(item?.content || "").trim();
    if (!message) return;
    if (item?.role === "assistant") {
      priorCustomerText += ` ${message}`;
      const affirmed = staticAffirmedCustomerText(message);
      if (STATIC_TRAINING_RED_FLAG_PATTERN.test(affirmed)) priorCustomerHasRedFlag = true;
      if (STATIC_TRAINING_DISCOMFORT_PATTERN.test(affirmed)) priorCustomerHasDiscomfort = true;
      return;
    }
    if (item?.role !== "user") return;
    if (staticCriticalHits(message).length || staticHasAffirmativeEmployeeMatch(message, /(?:建议|应该|可以).{0,10}(?:停药|换药|剂量|口服|注射)/i)) add("CF-02", message);
    const unsafeContinuation = staticHasAffirmativeEmployeeMatch(message, continuePattern);
    // Only customer facts visible before this employee turn can trigger a
    // failure. A red flag disclosed by a later customer reply never travels
    // backwards into an earlier score.
    if (unsafeContinuation && priorCustomerHasRedFlag) add("CF-01", message);
    if (staticHasAffirmativeEmployeeMatch(message, pressurePattern) && refusalPattern.test(priorCustomerText)) add("CF-03", message);
    if (unsafeContinuation && priorCustomerHasDiscomfort) add("CF-04", message);
  });
  return [...matches].map(([code, evidence]) => ({ code, evidence }));
}

function detectStaticAssessmentFailures(history = []) {
  return staticAssessmentFailureMatches(history).map((item) => item.code);
}

function staticFallbackEmployeeEvidence(dimensionId, history = []) {
  const employeeMessages = history.filter((item) => item?.role === "user" && String(item.content || "").trim()).map((item) => String(item.content).trim());
  const patterns = {
    D1: /理解|您好|谢谢|可以吗/i,
    D2: /了解|多久|目标|作息|饮食|活动|尝试|影响|担心/i,
    D3: /不能|不承诺|不保证|边界|个体差异|复盘/i,
    D4: /时间|预算|选择|安排|目标|方案/i,
    D5: /理解|担心|顾虑|不能保证|选择|您看/i,
    D6: /安全|健康|暂停|停止|不舒服|医疗|评估/i,
    D7: /下一步|愿意|安排|复盘|确认|跟进/i,
  };
  const selected = [...employeeMessages].reverse().find((message) => (patterns[dimensionId] || /./).test(message)) || employeeMessages.at(-1) || "";
  return selected ? `员工原话：“${selected.slice(0, 180)}”` : "对话中未体现";
}

function staticEvidenceUsesCustomerOnlyText(evidence, history = []) {
  const employeeText = history.filter((item) => item?.role === "user").map((item) => item.content || "").join(" ");
  const customerMessages = history.filter((item) => item?.role === "assistant").map((item) => String(item.content || "").replace(/\s+/g, ""));
  return customerMessages.some((message) => {
    for (let index = 0; index <= message.length - 8; index += 1) {
      const fragment = message.slice(index, index + 8);
      if (evidence.includes(fragment) && !employeeText.includes(fragment)) return true;
    }
    return false;
  });
}

function staticEvidenceIsGroundedInEmployee(evidence, history = []) {
  if (String(evidence || "").includes("对话中未体现")) return true;
  const employeeMessages = history
    .filter((item) => item?.role === "user" && String(item.content || "").trim())
    .map((item) => String(item.content).trim());
  if (!employeeMessages.length) return false;
  const quoted = [...String(evidence || "").matchAll(/[“"]([^”"]+)[”"]/g)].map((match) => match[1].trim()).filter(Boolean);
  if (quoted.length) return quoted.some((value) => employeeMessages.some((message) => message.includes(value)));
  const compact = (value) => String(value || "").replace(/[\s，,。.；;:：！!？?“”"'、]/g, "");
  const evidenceCompact = compact(evidence);
  return employeeMessages.some((message) => {
    const messageCompact = compact(message);
    if (messageCompact.length < 6) return Boolean(messageCompact) && evidenceCompact.includes(messageCompact);
    for (let index = 0; index <= messageCompact.length - 6; index += 1) {
      if (evidenceCompact.includes(messageCompact.slice(index, index + 6))) return true;
    }
    return false;
  });
}

const STATIC_ASSESSMENT_SPECIFIC_ADVICE = /(?:古方|口服|注射|用药|药品|药物|剂量|停换药|停药|停用|换药|更换药物|隔天一次|每天\s*\d+\s*次)/i;
const STATIC_ASSESSMENT_CONCRETE_ADVICE = /(?:\d+(?:\.\d+)?\s*(?:mg|g|ml|毫克|克|毫升|片|粒|支|单位))|(?:(?:每天|每日|每周|每次|隔天|早晚|睡前|餐前|餐后).{0,8}(?:\d+|一|两|二|三|四|五|六|七|八|九|十).{0,3}次)|(?:(?:口服|注射).{0,12}(?:\d+|一|两|二|三|四|五|六|七|八|九|十)\s*(?:次|片|粒|支|毫升|毫克|mg|ml))/i;
const STATIC_ASSESSMENT_SAFE_ADVICE_BOUNDARY = /(?:(?:具体)?(?:口服|注射|用药|药品|药物|剂量|停换药|停药|停用|换药|更换药物)[^，,。；;！？!?\n]{0,18}(?:交由|由|请|需|需要|应|应该|须|必须)[^，,。；;！？!?\n]{0,10}(?:医生|医师|药师|医疗机构)[^，,。；;！？!?\n]{0,14}(?:评估|决定|指导|核实|开具|处方))|(?:(?:医生|医师|药师|医疗机构)[^，,。；;！？!?\n]{0,14}(?:评估|决定|指导|核实|开具|处方)[^，,。；;！？!?\n]{0,18}(?:口服|注射|用药|药品|药物|剂量|停换药|停药|停用|换药|更换药物))|(?:(?:门店|我们|员工)[^，,。；;！？!?\n]{0,8}(?:不能|不可|不会|不应|不得|不建议|不提供|不决定|不调整|无权)[^，,。；;！？!?\n]{0,14}(?:给出?|提供|建议|决定|调整|安排)?(?:具体)?(?:口服|注射|用药|药品|药物|剂量|停换药|停药|停用|换药|更换药物))|(?:(?:不能|不可|不要|不得|不建议|避免)[^，,。；;！？!?\n]{0,8}(?:自行|擅自)[^，,。；;！？!?\n]{0,5}(?:停换药|停药|停用|换药|更换药物|调整用药))|(?:(?:口服|注射|用药|药品|药物|剂量|停换药|停药|停用|换药|更换药物)[^，,。；;！？!?\n]{0,8}(?:遵医嘱|按医嘱))/gi;
const STATIC_ASSESSMENT_COMMENT_BOUNDARY = "员工尚未把顾客顾虑转化为可执行的下一步。建议先澄清时间、预算和服务偏好，再给出门店当前已核验且符合安全边界的选择。";
const STATIC_ASSESSMENT_IMPROVEMENT_BOUNDARY = "不要替顾客直接选择具体产品或使用安排；先核验适用条件和门店当前标准，再提供非医疗、可选择的下一步。";
const STATIC_ASSESSMENT_STRENGTH_BOUNDARY = "完成了基本沟通；涉及医疗决定时仍需明确门店边界，并交由医生或药师评估。";
const STATIC_ASSESSMENT_FAILURE_REASON_BOUNDARY = "员工表达涉及未经核验的具体用药或使用安排，应明确门店边界并交由医生或药师评估。";
const STATIC_ASSESSMENT_SUMMARY_BOUNDARY = "本轮需要加强需求分析和个性化表达。后续重点练习在不承诺结果、不擅自补充具体产品或使用安排的前提下，把顾客顾虑转化为可执行的服务下一步。";

function staticAssessmentAdviceNeedsSanitizing(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!STATIC_ASSESSMENT_SPECIFIC_ADVICE.test(text)) return false;
  return text.split(/[。；;！？!?\n]+/).some((sentence) => {
    if (!STATIC_ASSESSMENT_SPECIFIC_ADVICE.test(sentence)) return false;
    // Concrete amounts and frequencies are never repeated in an assessment,
    // even when the same sentence also contains a disclaimer.
    if (STATIC_ASSESSMENT_CONCRETE_ADVICE.test(sentence)) return true;
    const remainder = sentence.replace(STATIC_ASSESSMENT_SAFE_ADVICE_BOUNDARY, "");
    return STATIC_ASSESSMENT_SPECIFIC_ADVICE.test(remainder);
  });
}

function sanitizeStaticAssessmentAdvice(result) {
  if (!result || typeof result !== "object") return result;
  (result.dimension_scores || []).forEach((dimension) => {
    if (dimension && typeof dimension === "object" && staticAssessmentAdviceNeedsSanitizing(dimension.comment)) {
      dimension.comment = STATIC_ASSESSMENT_COMMENT_BOUNDARY;
    }
  });
  [
    ["strengths", STATIC_ASSESSMENT_STRENGTH_BOUNDARY],
    ["improvements", STATIC_ASSESSMENT_IMPROVEMENT_BOUNDARY],
  ].forEach(([key, fallback]) => {
    if (Array.isArray(result[key])) {
      result[key] = result[key].map((item) => (staticAssessmentAdviceNeedsSanitizing(item) ? fallback : item));
    }
  });
  (result.critical_failures || []).forEach((failure) => {
    if (failure && typeof failure === "object" && staticAssessmentAdviceNeedsSanitizing(failure.reason)) {
      failure.reason = STATIC_ASSESSMENT_FAILURE_REASON_BOUNDARY;
    }
  });
  if (staticAssessmentAdviceNeedsSanitizing(result.summary)) result.summary = STATIC_ASSESSMENT_SUMMARY_BOUNDARY;
  return result;
}

function normalizeStaticAssessment(result, history = [], rubric = {}) {
  const normalized = result && typeof result === "object" ? result : {};
  const specs = rubric.dimensions || [];
  const provided = new Map((Array.isArray(normalized.dimension_scores) ? normalized.dimension_scores : []).filter((item) => item?.id).map((item) => [item.id, item]));
  const dimensionScores = specs.map((spec) => {
    const item = provided.get(spec.id) || {};
    const maxScore = Number(spec.weight || spec.max_score || 0);
    const rawScore = Number(item.score);
    const score = Number.isFinite(rawScore) ? Math.max(0, Math.min(maxScore, Math.round(rawScore))) : 0;
    let evidence = String(item.evidence || "").trim();
    if (!evidence || staticEvidenceUsesCustomerOnlyText(evidence, history) || !staticEvidenceIsGroundedInEmployee(evidence, history)) {
      evidence = staticFallbackEmployeeEvidence(spec.id, history);
    }
    return { id: spec.id, name: spec.name, score, max_score: maxScore, evidence, comment: String(item.comment || "需要在下一轮对话中补充可验证表现。") };
  });
  const failureSpecs = new Map((rubric.critical_failures || []).map((item) => [item.code, item]));
  const detectedFailures = new Map(staticAssessmentFailureMatches(history).map((item) => [item.code, item.evidence]));
  const detectedFailureCodes = new Set(detectedFailures.keys());
  // A model may over-interpret a careful safety refusal as a failure.  Critical
  // caps are accepted only when the employee's own wording matches a local rule.
  const modelFailures = new Map((Array.isArray(normalized.critical_failures) ? normalized.critical_failures : []).filter((item) => failureSpecs.has(item?.code) && detectedFailureCodes.has(item.code)).map((item) => [item.code, item]));
  detectedFailureCodes.forEach((code) => { if (!modelFailures.has(code)) modelFailures.set(code, { code, evidence: detectedFailures.get(code) }); });
  const criticalFailures = [...modelFailures].map(([code, item]) => {
    const spec = failureSpecs.get(code);
    return { code, reason: item.reason || spec.rule, evidence: detectedFailures.get(code) || item.evidence || "员工原话触发了需要重点改进的规则。", score_cap: spec.score_cap };
  });
  let totalScore = dimensionScores.reduce((sum, item) => sum + item.score, 0);
  if (criticalFailures.length) totalScore = Math.min(totalScore, ...criticalFailures.map((item) => Number(item.score_cap)));
  const cleanList = (value, fallback) => Array.isArray(value) && value.filter(Boolean).length ? value.filter(Boolean).slice(0, 4) : fallback;
  return sanitizeStaticAssessmentAdvice({
    total_score: totalScore,
    dimension_scores: dimensionScores,
    critical_failures: criticalFailures,
    strengths: cleanList(normalized.strengths, ["完成了本轮顾客沟通。"]),
    improvements: cleanList(normalized.improvements, ["下一轮请围绕顾客原话补齐需求分析、安全边界和可执行下一步。"]),
    next_training_scene: normalized.next_training_scene || "",
    summary: normalized.summary || "评分已按本轮员工实际表达生成。",
  });
}

function normalizeStaticResult(result, mode, action, scenario, history, rubric, message, query = "", route = {}) {
  let normalized = result && typeof result === "object" ? result : {};
  if (mode === "training") {
    const fallback = staticMockProgressive(mode, action, scenario, history, rubric, message);
    normalized.customer_reply = normalizeStaticCustomerReply(normalized.customer_reply || fallback.customer_reply, scenario, history, message);
    normalized.feedback = normalizeStaticTrainingFeedback(normalized, scenario, history, rubric, message, normalized.customer_reply);
  }
  if (mode === "test" && action === "turn") normalized = normalizeStaticTestTurn(normalized, scenario, history, message);
  if (mode === "test" && action === "finish") normalized = normalizeStaticAssessment(normalized, history, rubric);
  if (mode === "qa") normalized = normalizeStaticQaResult(normalized, message, query, route, history);
  return normalized;
}

function cleanStaticHistory(history = [], limit = 7) {
  return history.filter((item) => ["user", "assistant"].includes(item?.role) && String(item.content || "").trim()).map((item) => ({ role: item.role, content: String(item.content).trim() })).slice(-limit);
}

async function staticApi(path, body) {
  const data = await loadStaticData();
  if (path === "/api/bootstrap") {
    return { ok: true, scenarios: data.scenarios, models: AVAILABLE_MODELS, knowledge: { rag_documents: data.documents.length, common_qa: data.commonQa.length, scenarios: data.scenarios.length }, rubric: { total: data.rubric.total, dimensions: data.rubric.dimensions || [] } };
  }
  if (path === "/api/health") return { ok: true, api_configured: Boolean(state.apiKey), mock_mode: !state.apiKey, model: state.model, models: AVAILABLE_MODELS, knowledge: { rag_documents: data.documents.length, common_qa: data.commonQa.length } };
  if (path !== "/api/chat") throw new Error("静态模式不支持该接口");

  const mode = body.mode || "qa";
  const action = body.action || "turn";
  const apiKey = body.api_key || state.apiKey;
  const model = body.model || state.model;
  const scenario = data.scenarios.find((item) => item.id === body.scenario_id) || data.scenarios[0];
  const message = body.message || "";
  const history = body.history || [];
  const query = mode === "qa" ? staticQaQuery(message, history) : [...history.slice(-8).map((item) => item.content), message].join(" ");
  const commonQaMatch = mode === "qa"
    ? (matchStaticCommonQa(message, data.commonQa) || (query !== message ? matchStaticCommonQa(query, data.commonQa) : null))
    : null;
  const route = staticRouteCustomerQuestion(query, data.methodology);
  let docs = staticRetrieve(query, data.documents, 8, route, mode !== "qa");
  if (commonQaMatch && mode === "qa") {
    docs = docs.filter((document) => document.metadata?.doc_type !== "common_qa");
  }
  // Keep interactive prompts compact so multi-turn responses remain reliable
  // on the static Pages build while retrieval/citations stay unchanged.
  const context = docs.slice(0, mode === "training" ? 4 : 8).map((item) => `${item.metadata?.title || item.document_id}\n${String(item.text || "").slice(0, mode === "training" ? 650 : 1200)}`).join("\n\n");
  if (!apiKey) {
    if (mode === "qa" && commonQaMatch) {
      const result = normalizeStaticQaResult({
        answer: commonQaMatch.row.approved_answer,
        uncertainties: [],
        recommended_action: "如需继续了解，可打开下方对应课程学习；涉及当前价格、门店政策或个体适用性时，请再核对有效版本。",
        faq_match: publicStaticCommonQaMatch(commonQaMatch),
      }, message, query, route, history);
      result.answer = commonQaMatch.row.approved_answer;
      result.faq_match = publicStaticCommonQaMatch(commonQaMatch);
      const faqReference = staticCommonQaCourseReference(commonQaMatch.row);
      const references = uniqueStaticReferences([faqReference, ...docs.map(publicStaticDocument)].filter(Boolean));
      return { ok: true, mode, result, citations: references.slice(0, 3), retrieved: references, meta: { mock: true, model, common_qa: true } };
    }
    const rawResult = mode === "qa" ? staticKnowledgeQaResponse(message, route, docs) : staticMockProgressive(mode, action, scenario, history, data.rubric, message);
    const result = normalizeStaticResult(rawResult, mode, action, scenario, history, data.rubric, message, query, route);
    return { ok: true, mode, result, citations: mode === "qa" ? docs.slice(0, 3).map(publicStaticDocument) : [], retrieved: mode === "qa" ? docs.map(publicStaticDocument) : [], meta: { mock: true, model } };
  }

  const dialogue = cleanStaticHistory(history);
  const turnNumber = dialogue.filter((item) => item.role === "user").length + 1;
  const safety = "不得诊断疾病、承诺治愈或固定效果、推荐药品剂量或停药；遇到红旗症状时优先停止项目并建议医疗评估。";
  const routeContext = staticRouteContext(route);
  if (mode === "training") {
    // The customer and coach have intentionally different information
    // boundaries.  In particular, the coach request is created before and
    // independently of this turn's customer reply, so feedback used by
    // "修改这次回答" can never depend on a future disclosure.
    const customerSystem = `你只扮演情景陪练中的模拟顾客，不是教练、客服助手或评分员。\n隐藏场景（不得整段泄露）：${JSON.stringify(staticCustomerScenario(scenario))}\n${LIMITED_CUSTOMER_POLICY}\n开场白已经展示，当前是员工第 ${turnNumber} 轮回复。只回应员工最新一句；绝不重复开场或旧回复。只有员工本轮表达直接命中 information_release_rules 中某一个条件时，才能透露该条对应的一条信息；每轮最多透露一个新事实，不得提前带出后续事实。遇到已知红旗症状且员工给出暂停或就医方向时，必须留在安全处置流程，只表示理解或追问暂停、记录、联系负责人等安排，不得跳回怕疼、价格或项目效果等常规异议。不得出现考核、评分、知识库、方法路由、隐藏异议、must_test、员工应该等幕后词。严格输出 JSON：{"customer_reply":"顾客下一句话"}。`;
    const coachSystem = `你只是门店员工情景训练教练，不扮演顾客。${safety}\n公开场景：${JSON.stringify(staticPublicTrainingScenario(scenario))}\n当前是员工第 ${turnNumber} 轮回复。history 中 role=user 是员工，role=assistant 是本轮前顾客已经说出的公开信息。你只能评价这些回合前公开对话和员工最新一句；你不会获得且不得猜测任何未公开的剧情、评分参考或本轮尚未生成的顾客回复。每轮只指出一个最重要问题，feedback 需结合员工本轮原话。suggested_reply 是对员工本轮原话的直接改写，点击“修改这次回答”后应能在同一份回合前历史上直接发送；不得写“您刚补充/您又说”或引用本轮之后才可能出现的信息。对已知服务后疼痛加重，若员工直接说正常、没问题、微损伤自我修复、会变轻或继续加量，level 必须为 critical。对回合前已知麻木等新症状，仅说重视和就医但未暂停、记录上报时为 needs_work；完整停止、不诊断、记录上报和医疗分流才可为 good，危险矛盾表达永远优先。严格输出 JSON：{"feedback":{"level":"good|needs_work|critical","issue":"...","why":"...","method_step":"...","knowledge_focus":"...","suggested_reply":"...","next_goal":"..."}}。\n方法路由：\n${routeContext}\n相关知识库：\n${context}`;
    const trainingMessages = [...dialogue, { role: "user", content: message }];
    const [customerSettled, coachSettled] = await Promise.allSettled([
      callStaticModel(customerSystem, trainingMessages, model, apiKey, 0.55, 500, 45000),
      callStaticModel(coachSystem, trainingMessages, model, apiKey, 0.2, 950, 45000),
    ]);
    const customerModelResult = customerSettled.status === "fulfilled" ? customerSettled.value : null;
    const coachModelResult = coachSettled.status === "fulfilled" ? coachSettled.value : null;
    if (!customerModelResult && !coachModelResult) {
      throw new Error("模拟顾客与训练教练均未返回可用结果，请稍后重试。");
    }
    const localFallback = staticMockProgressive("training", "turn", scenario, history, data.rubric, message);
    const customerContent = customerModelResult?.content || "";
    const coachContent = coachModelResult?.content || "";
    const customerPayload = customerModelResult
      ? (extractStaticJson(customerContent) || { customer_reply: customerContent })
      : { customer_reply: localFallback.customer_reply };
    const coachPayload = coachModelResult
      ? (extractStaticJson(coachContent) || {})
      : { feedback: localFallback.feedback };
    let result = {
      customer_reply: customerPayload.customer_reply || customerPayload.reply || customerContent,
      feedback: coachPayload.feedback && typeof coachPayload.feedback === "object" ? coachPayload.feedback : coachPayload,
    };
    result = normalizeStaticResult(result, mode, action, scenario, history, data.rubric, message, query, route);
    const customerUsage = customerModelResult?.meta?.usage || {};
    const coachUsage = coachModelResult?.meta?.usage || {};
    const usage = {};
    new Set([...Object.keys(customerUsage), ...Object.keys(coachUsage)]).forEach((key) => {
      const customerValue = Number(customerUsage[key]);
      const coachValue = Number(coachUsage[key]);
      if (Number.isFinite(customerValue) || Number.isFinite(coachValue)) usage[key] = (Number.isFinite(customerValue) ? customerValue : 0) + (Number.isFinite(coachValue) ? coachValue : 0);
    });
    return {
      ok: true,
      mode,
      result,
      citations: [],
      retrieved: [],
      meta: {
        model: coachModelResult?.meta?.model || customerModelResult?.meta?.model || model,
        usage,
        mock: false,
        calls: 2,
        roles: ["customer", "coach"],
        degraded: !customerModelResult || !coachModelResult,
        fallback_roles: [
          ...(!customerModelResult ? ["customer"] : []),
          ...(!coachModelResult ? ["coach"] : []),
        ],
      },
    };
  }
  let system;
  let messages;
  let temperature = 0.3;
  let maxTokens = 1800;
  if (mode === "test" && action === "turn") {
    system = `你只扮演实战考核中的模拟顾客，不是教练、客服助手或评分员。\n隐藏场景（不得泄露）：${JSON.stringify(staticCustomerScenario(scenario))}\n${LIMITED_CUSTOMER_POLICY}\n开场白已经展示，当前是员工第 ${turnNumber} 轮回复。只回应员工最新一句；绝不重复开场或原样重复旧回复；每轮最多透露一个员工问到的新背景或异议。不得出现考核、评分、知识库、方法路由、隐藏异议、must_test、员工应该等幕后词。\n回答相关性契约（优先于普通顾虑推进）：先判断员工是在提问、解释、确认还是安排下一步；第一句话必须承接同一个主题，不能突然跳到价格、项目原理或另一个顾虑。员工一句话中有多个明确问题时，按原顺序逐项回应；已回答的事实不重复，尚未掌握的内容明确说“我没留意/不太清楚”，不能只回答一个问题后换话题。员工解释数据或效果时，先回应这段解释，再提出一个与当前主题直接相关的顾虑；没有新问题时，不得凭空开启新的异议。员工给出具体方案、时间、记录方式或下一步安排时，先确认听懂、接受、犹豫或追问一个具体细节，不能只说“这些专业的我不懂”并退回旧顾虑。若员工刚解释“测量时间、条件或结果不同”，必须先回应测量安排，再提出判断周期问题。顾客可以继续提问，但必须遵循“先回应、后追问”：先用一句话确认理解、接受、犹豫或具体不清楚之处，再提出最多一个与员工刚才内容直接相关的问题，禁止跳过回应直接抛出新问题。每轮自检：回复中至少有一个短语对应员工最新问题或动作；否则改写为“我还没听明白，您刚才问的是……对吗？”这类澄清。\n严格输出 JSON：{"reply":"顾客下一句话","emotion":"curious|hesitant|concerned|relieved|neutral","should_continue":true}。`;
    messages = [...dialogue, { role: "user", content: message }];
    temperature = 0.55;
  } else if (mode === "test" && action === "finish") {
    system = `你是企业培训考核官，只输出考后评分报告，不再扮演顾客。history 中 role=user 才是员工，role=assistant 是顾客，绝不能混淆。严格按评分表输出恰好 7 个维度；id、name、max_score 必须一致；evidence 只能引用员工原话或写“对话中未体现”；total_score 等于各维度 score 之和，再应用关键失败封顶。必须严格按对话时序逐轮评价：一句员工原话只能使用它之前已出现的顾客信息，后来顾客才透露的信息不得追溯扣分。后续的正确补救不能抹去先前已经发生的关键失败；顾客明确说“没有/否认”的症状不得当作已出现。每个 evidence 和 comment 不超过 35 个汉字；strengths 与 improvements 各最多 3 条，每条不超过 30 个汉字。${safety}\n严格输出 JSON：{"total_score":0,"dimension_scores":[{"id":"D1","name":"...","score":0,"max_score":10,"evidence":"...","comment":"..."}],"critical_failures":[],"strengths":[],"improvements":[],"next_training_scene":"...","summary":"..."}。`;
    messages = [{ role: "user", content: `评分表：${JSON.stringify(data.rubric)}\n公开场景：${JSON.stringify(staticPublicTrainingScenario(scenario))}\n员工完整对话：${JSON.stringify(cleanStaticHistory(body.history || [], 40))}` }];
    temperature = 0.1;
    maxTokens = 1800;
  } else {
    system = `你是企业知识库中的顾客接待助手。只基于给定的方法路由和资料直接回答顾客当前问题。${safety}\n这是连续对话，必须结合最近问题和上一轮回答理解“这个、那、它、怎么办”等指代，但只回答当前这一问，不要机械重复上一轮。先承接问题，只补一个必要信息，再给已核验内容、边界和一个可执行下一步。严格输出 JSON：{"answer":"...","uncertainties":[],"recommended_action":"..."}。`;
    messages = [...dialogue, { role: "user", content: `顾客当前问题：${message}\n方法路由：\n${routeContext}\n相关知识库：\n${context}` }];
  }
  if (mode === "qa" && commonQaMatch) {
    const result = normalizeStaticQaResult({
      answer: commonQaMatch.row.approved_answer,
      uncertainties: [],
      recommended_action: "",
      faq_match: publicStaticCommonQaMatch(commonQaMatch),
    }, message, query, route, history);
    result.answer = commonQaMatch.row.approved_answer;
    result.faq_match = publicStaticCommonQaMatch(commonQaMatch);
    const faqReference = staticCommonQaCourseReference(commonQaMatch.row);
    const references = uniqueStaticReferences([faqReference, ...docs.map(publicStaticDocument)].filter(Boolean));
    return { ok: true, mode, result, citations: references.slice(0, 3), retrieved: references, meta: { mock: true, model, common_qa: true } };
  }
  const timeoutMs = mode === "test" && action === "finish" ? 60000 : 45000;
  const modelResult = await callStaticModel(system, messages, model, apiKey, temperature, maxTokens, timeoutMs);
  if (mode === "qa" && commonQaMatch) {
    const result = normalizeStaticQaResult({
      answer: commonQaMatch.row.approved_answer,
      uncertainties: [],
      recommended_action: "如需继续了解，可打开下方对应课程学习；涉及当前价格、门店政策或个体适用性时，请再核对有效版本。",
      faq_match: publicStaticCommonQaMatch(commonQaMatch),
    }, message, query, route, history);
    result.answer = commonQaMatch.row.approved_answer;
    result.faq_match = publicStaticCommonQaMatch(commonQaMatch);
    const faqReference = staticCommonQaCourseReference(commonQaMatch.row);
    const references = uniqueStaticReferences([faqReference, ...docs.map(publicStaticDocument)].filter(Boolean));
    return { ok: true, mode, result, citations: references.slice(0, 3), retrieved: references, meta: { mock: true, model, common_qa: true } };
  }
  let result = extractStaticJson(modelResult.content) || (mode === "test" && action === "turn" ? { reply: modelResult.content, emotion: "neutral", should_continue: true } : { answer: modelResult.content, uncertainties: [], recommended_action: "" });
  result = normalizeStaticResult(result, mode, action, scenario, history, data.rubric, message, query, route);
  return { ok: true, mode, result, citations: mode === "qa" ? docs.slice(0, 3).map(publicStaticDocument) : [], retrieved: mode === "qa" ? docs.map(publicStaticDocument) : [], meta: { ...modelResult.meta, mock: false } };
}

async function api(path, body) {
  if (STATIC_PAGES) return staticApi(path, body);
  const response = await fetch(path, body ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  } : undefined);
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || "请求失败");
  return data;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[char]);
}

function showToast(message, error = false) {
  els.toast.textContent = message;
  els.toast.classList.toggle("error", error);
  els.toast.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => els.toast.classList.add("hidden"), 3600);
}

function moduleById(moduleId) {
  return state.modules.find((module) => module.id === moduleId) || state.modules[0] || null;
}

function exactModuleById(moduleId) {
  return state.modules.find((module) => module.id === moduleId) || null;
}

function realExamById(examId) {
  return state.realExamBank?.exams?.find((exam) => exam.id === examId) || null;
}

function routeItemById(route, itemId) {
  if (!itemId) return null;
  if (route === "exam/objective") return exactModuleById(itemId) || realExamById(itemId);
  return exactModuleById(itemId);
}

function isRealExam(exam) {
  return Boolean(exam && Array.isArray(exam.questions));
}

function activeModuleId() {
  if (state.route === "learning/course") return state.learningModuleId;
  if (state.route === "learning/practice") return state.practiceModuleId;
  if (state.route === "exam/objective") return state.objectiveModuleId;
  if (state.route === "exam/simulation") return state.simulationModuleId;
  return null;
}

function activeModule() {
  return moduleById(activeModuleId());
}

function moduleCourses(moduleId) {
  return state.courses.filter((course) => course.module_id === moduleId).sort((a, b) => a.order - b.order);
}

function moduleGroups(moduleId) {
  return state.catalogIndex.find((item) => item.module_id === moduleId)?.groups || [];
}

const COURSE_DOMAIN_MODULES = {
  onboarding: "MOD-01", company: "MOD-01", reception: "MOD-02", sales_skills: "MOD-02",
  point_wave: "MOD-03", point_wave_ops: "MOD-03", professional_qa: "MOD-03", training_video: "MOD-03",
  super_v: "MOD-04", point_wave_super_v: "MOD-04",
  beauty: "MOD-08", beauty_ops: "MOD-08",
  slimming: "MOD-05", slimming_reception: "MOD-05", slimming_product: "MOD-05", slimming_science: "MOD-05",
  objections: "MOD-02", comparison: "MOD-02",
  safety: "MOD-01", service_safety: "MOD-01", operations: "MOD-01", product_ops: "MOD-01",
};

const COMMON_QA_COURSE_FALLBACKS = {
  "COURSE-FAQ-POINT-WAVE-001": "COURSE-MOD-03-02",
  "COURSE-FAQ-SUPER-V-001": "COURSE-MOD-04-02",
  "COURSE-FAQ-SLIMMING-001": "COURSE-MOD-05-03",
  "COURSE-FAQ-OBJECTION-001": "COURSE-MOD-02-04",
  "COURSE-FAQ-SAFETY-001": "COURSE-MOD-06-02",
  "COURSE-FAQ-BEAUTY-001": "COURSE-MOD-09-03",
};

const courseSearchTermCache = new Map();

function searchableTerms(value) {
  const text = String(value || "").toLowerCase();
  const terms = new Set(text.match(/[a-z0-9_]{2,}|[\u4e00-\u9fff]/gi) || []);
  for (let index = 0; index < text.length - 1; index += 1) {
    const pair = text.slice(index, index + 2);
    if (/^[\u4e00-\u9fff]{2}$/.test(pair)) terms.add(pair);
  }
  return terms;
}

function courseSearchTerms(course) {
  if (!courseSearchTermCache.has(course.id)) {
    courseSearchTermCache.set(course.id, searchableTerms(JSON.stringify(course)));
  }
  return courseSearchTermCache.get(course.id);
}

function bestReferenceCourse(candidates, reference) {
  if (!candidates.length) return null;
  if (candidates.length === 1) return candidates[0];
  const metadata = reference.metadata || {};
  const referenceTerms = searchableTerms(`${metadata.title || ""} ${metadata.section_title || ""} ${reference.title || ""} ${reference.text || ""}`);
  return candidates.reduce((best, course) => {
    const score = [...referenceTerms].reduce((total, term) => total + (courseSearchTerms(course).has(term) ? 1 : 0), 0);
    return !best || score > best.score ? { course, score } : best;
  }, null)?.course || candidates[0];
}

function resolveReferenceCourse(reference = {}) {
  const metadata = reference.metadata || {};
  const requestedId = reference.course_id || metadata.course_id;
  if (requestedId) {
    const direct = state.courses.find((course) => course.id === requestedId)
      || state.courses.find((course) => course.id === COMMON_QA_COURSE_FALLBACKS[requestedId]);
    if (direct) return direct;
  }

  const documentId = String(reference.document_id || "");
  const documentCourseId = documentId.startsWith("COURSE-")
    ? documentId.replace(/-SECTION-\d+$/, "")
    : documentId ? `COURSE-${documentId}` : "";
  if (documentCourseId) {
    const direct = state.courses.find((course) => course.id === documentCourseId);
    if (direct) return direct;
  }

  const title = String(reference.title || metadata.title || "").trim();
  const titleMatch = state.courses.find((course) => course.title === title);
  if (titleMatch) return titleMatch;

  const sourceIds = new Set([
    ...(Array.isArray(reference.source_ids) ? reference.source_ids : []),
    ...(Array.isArray(metadata.source_ids) ? metadata.source_ids : []),
    ...String(reference.source_id || metadata.source_id || "").split(","),
  ].map((item) => String(item).trim()).filter(Boolean));
  if (sourceIds.size) {
    const sourceMatches = state.courses.filter((course) => (course.source_ids || []).some((sourceId) => sourceIds.has(sourceId)));
    if (sourceMatches.length) return bestReferenceCourse(sourceMatches, reference);
  }

  const moduleId = metadata.module_id || COURSE_DOMAIN_MODULES[metadata.domain] || COURSE_DOMAIN_MODULES[reference.domain];
  if (moduleId) return bestReferenceCourse(state.courses.filter((course) => course.module_id === moduleId), reference);
  return null;
}

function routePath(route = state.route, moduleId = state.routeModuleId) {
  return `#${route}${moduleId ? `/${moduleId}` : ""}`;
}

function parseRouteHash(hash = window.location.hash) {
  let raw;
  try {
    raw = decodeURIComponent(String(hash || "").replace(/^#/, "")).replace(/^\/+|\/+$/g, "");
  } catch {
    return { route: "learning", moduleId: null, invalid: true };
  }
  raw = LEGACY_ROUTES[raw] || raw || "learning";
  if (VALID_ROUTES.has(raw)) return { route: raw, moduleId: null, invalid: false };
  const activity = [...VALID_ROUTES]
    .filter((route) => ROUTE_CONFIG[route].screen === "activity")
    .sort((a, b) => b.length - a.length)
    .find((route) => raw.startsWith(`${route}/`));
  if (!activity) return { route: "learning", moduleId: null, invalid: true };
  const moduleId = raw.slice(activity.length + 1);
  if (!routeItemById(activity, moduleId)) return { route: activity, moduleId: null, invalid: true };
  return { route: activity, moduleId, invalid: false };
}

function activityModuleStats(route, module) {
  if (route === "learning/course") {
    return `${moduleGroups(module.id).length} 个章节 · ${moduleCourses(module.id).length} 节课程`;
  }
  if (route === "exam/objective") {
    const exam = objectiveExamById(module.id);
    return `${examQuestions(exam).length} 道题${isRealExam(exam) ? ` · 满分 ${examTotalPoints(exam)} 分` : ""}`;
  }
  return `${moduleScenarios(module.id).length} 个顾客场景`;
}

function renderModuleGateway() {
  const config = ROUTE_CONFIG[state.route];
  els.gatewayTag.textContent = config.tag;
  els.gatewayTitle.textContent = config.gatewayTitle || `选择${config.title}模块`;
  els.gatewayDescription.textContent = config.description;
  els.gatewayBack.dataset.route = config.parent;
  const moduleCards = state.modules.map((module) => `
    <button class="module-route-card" data-module-id="${escapeHtml(module.id)}">
      <span>模块 ${String(module.order).padStart(2, "0")}</span>
      <h3>${escapeHtml(module.title)}</h3>
      <p>${escapeHtml(activityModuleStats(state.route, module))}</p>
      <b>${escapeHtml(config.action)} →</b>
    </button>`).join("");
  const realExams = state.route === "exam/objective" ? state.realExamBank?.exams || [] : [];
  if (!realExams.length) {
    els.moduleRouteGrid.classList.remove("grouped");
    els.moduleRouteGrid.innerHTML = moduleCards;
    return;
  }
  const realExamCards = realExams.map((exam, index) => `
    <button class="module-route-card real-exam-card" data-module-id="${escapeHtml(exam.id)}">
      <span>真实考试 ${String(index + 1).padStart(2, "0")}</span>
      <h3>${escapeHtml(exam.title)}</h3>
      <p>${examQuestions(exam).length} 道题 · 满分 ${examTotalPoints(exam)} 分</p>
      <b>进入考试 →</b>
    </button>`).join("");
  els.moduleRouteGrid.classList.add("grouped");
  els.moduleRouteGrid.innerHTML = `
    <section class="module-route-group">
      <div class="module-route-group-head"><div><span>知识模块测试</span><h3>按知识模块巩固学习成果</h3></div><b>${state.modules.length} 个模块</b></div>
      <div class="module-route-list">${moduleCards}</div>
    </section>
    <section class="module-route-group real-exam-group">
      <div class="module-route-group-head"><div><span>真实考试</span><h3>按原试卷完成正式答题</h3></div><b>${realExams.length} 套试卷</b></div>
      <p class="real-exam-note">填空题由系统判分；问答题提交后显示原卷答案，由监考人按题目分值录入得分。</p>
      <div class="module-route-list">${realExamCards}</div>
    </section>`;
}

function conversationCopy() {
  if (state.route === "exam/simulation") {
    return {
      kicker: "模拟顾客考核",
      conversation: "独立接待模拟顾客",
      hint: "至少完成 4 轮对话后可结束考核",
      placeholder: "输入你准备对顾客说的话…",
      finish: "完成考核并查看结果",
    };
  }
  const copy = modeCopy[state.mode];
  return {
    kicker: copy.kicker,
    conversation: copy.conversation,
    hint: copy.hint,
    placeholder: state.mode === "qa" ? "输入顾客的问题，例如：做一次就一定有效吗？" : "输入你准备对顾客说的话…",
    finish: "结束陪练并查看报告",
  };
}

function renderRoute() {
  const config = ROUTE_CONFIG[state.route] || ROUTE_CONFIG.learning;
  const workspace = config.screen === "workspace" || (config.screen === "activity" && Boolean(state.routeModuleId));
  const gateway = config.screen === "activity" && !state.routeModuleId;
  const routeItem = workspace && state.routeModuleId ? routeItemById(state.route, state.routeModuleId) : null;
  const realObjectiveExam = state.route === "exam/objective" && isRealExam(routeItem);
  state.mode = config.mode;
  els.modeButtons.forEach((button) => button.classList.toggle("active", button.dataset.route === config.area));
  els.modeBreadcrumb.textContent = config.nav;
  els.pageTitle.textContent = routeItem?.title || config.title;
  els.pageDescription.textContent = realObjectiveExam
    ? `完成 ${examQuestions(routeItem).length} 道正式试题，提交后按原卷答案批阅并查看成绩。`
    : workspace && state.routeModuleId ? config.workspaceDescription || config.description : config.pageDescription || config.description;
  els.learningHubPage.classList.toggle("hidden", state.route !== "learning");
  els.assessmentHubPage.classList.toggle("hidden", state.route !== "exam");
  els.moduleGatewayPage.classList.toggle("hidden", !gateway);
  els.learningPage.classList.toggle("hidden", !(state.route === "learning/course" && workspace));
  els.trainingPage.classList.toggle("hidden", !(state.route === "learning/practice" && workspace));
  els.testPage.classList.toggle("hidden", !(["exam/objective", "exam/simulation"].includes(state.route) && workspace));
  els.qaPage.classList.toggle("hidden", state.route !== "qa");
  const showConversation = state.route === "qa" || ((state.route === "learning/practice" || state.route === "exam/simulation") && workspace);
  els.conversationStage.classList.toggle("hidden", !showConversation);
  els.finish.classList.toggle("hidden", state.route === "qa");
  const conversation = conversationCopy();
  els.conversationAvatar.textContent = state.mode === "qa" ? "AI" : "客";
  els.conversationKicker.textContent = conversation.kicker;
  els.conversationTitle.textContent = conversation.conversation;
  els.composerHint.textContent = conversation.hint;
  els.input.placeholder = conversation.placeholder;
  if (els.clearChat) els.clearChat.textContent = state.route === "qa" ? "新对话" : state.route === "exam/simulation" ? "重新考核" : "重新练习";
  if (!state.ended) els.finish.textContent = conversation.finish;
  if (gateway) renderModuleGateway();
  if (state.route === "exam/objective" && workspace) {
    const exam = activeExamModule();
    const realExam = isRealExam(exam);
    els.testRouteBack.dataset.route = "exam/objective";
    els.testRouteTag.textContent = realExam ? "真实考试" : "知识考试";
    els.testRouteTitle.textContent = realExam ? exam.title : "模块知识考试";
    els.testRouteDescription.textContent = realExam
      ? `完成全部 ${examQuestions(exam).length} 题后提交；填空题自动判分，问答题按原卷答案批阅。`
      : "完成全部 14 题后交卷，即可查看成绩、答案和解析。";
  } else if (state.route === "exam/simulation" && workspace) {
    els.testRouteBack.dataset.route = "exam/simulation";
    els.testRouteTag.textContent = "实战对话";
    els.testRouteTitle.textContent = "模拟顾客考核";
    els.testRouteDescription.textContent = "请像真实接待一样完成至少 4 轮对话，结束后查看评分和改进建议。";
  }
}

function renderModuleOptions() {
  const options = state.modules.map((module) => `<option value="${module.id}">${String(module.order).padStart(2, "0")} · ${escapeHtml(module.title)}</option>`).join("");
  els.learningSelect.innerHTML = options;
  els.practiceSelect.innerHTML = options;
  els.testSelect.innerHTML = options;
  els.learningSelect.value = state.learningModuleId;
  els.practiceSelect.value = state.practiceModuleId;
  els.testSelect.value = state.route === "exam/simulation" ? state.simulationModuleId : state.objectiveModuleId;
}

function renderCourseSummary(summary) {
  const items = String(summary || "").split(/[；;]\s*/).map((item) => item.trim()).filter(Boolean);
  return items.length > 1
    ? `<ul class="course-summary-points">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : `<p>${escapeHtml(items[0] || "请根据当前课程内容学习，并以最新标准为准。")}</p>`;
}

function renderLearning() {
  const module = moduleById(state.learningModuleId);
  if (!module) return;
  const groups = moduleGroups(module.id);
  const courses = moduleCourses(module.id);
  const moduleDescription = String(module.description || "").trim();
  els.learningSummary.innerHTML = `
    <div><span>正在学习</span><h3>${escapeHtml(module.title)}</h3>${moduleDescription && moduleDescription !== module.title ? `<p>${escapeHtml(moduleDescription)}</p>` : ""}</div>
    <div class="summary-count"><strong>${groups.length}</strong><span>个章节</span><strong>${courses.length}</strong><span>节课程</span></div>`;
  els.learningChapters.innerHTML = groups.map((group, index) => {
    // Prefer the stable group id, but fall back to the catalog's explicit course_ids.
    // This keeps the learning page usable when a refreshed catalog changes group labels.
    const groupCourseIds = new Set(Array.isArray(group.course_ids) ? group.course_ids : []);
    const groupCourses = courses.filter((course) => course.group_id === group.group_id || groupCourseIds.has(course.id));
    const groupDescription = String(group.description || "").trim();
    return `<article class="chapter-card">
      <div class="chapter-head"><div class="chapter-number">${String(index + 1).padStart(2, "0")}</div><div><h3>${escapeHtml(group.title)}</h3>${groupDescription && groupDescription !== group.title ? `<p>${escapeHtml(groupDescription)}</p>` : ""}</div><span>${groupCourses.length} 节</span></div>
      <div class="chapter-courses">${groupCourses.map((course) => `
        <button class="course-preview" data-course-id="${escapeHtml(course.id)}" data-course-title="${escapeHtml(course.title)}">
          <span class="course-type">${course.kind === "objection" ? "接待案例" : "专业课程"} · ${course.estimated_minutes} 分钟</span>
          <strong>${escapeHtml(course.title)}</strong>${renderCourseSummary(course.summary)}<i>打开课程 →</i>
        </button>`).join("")}</div>
    </article>`;
  }).join("");
  bindCourseButtons(els.learningChapters);
}

function renderLearningValue(value) {
  if (Array.isArray(value)) {
    if (value.every((item) => item && typeof item === "object" && "label" in item)) {
      return `<div class="learning-kv">${value.map((item) => `<div class="learning-kv-row"><b>${escapeHtml(item.label)}</b>${renderLearningValue(item.content)}</div>`).join("")}</div>`;
    }
    return `<ul class="course-points">${value.map((item) => `<li>${typeof item === "object" ? renderLearningValue(item) : escapeHtml(item)}</li>`).join("")}</ul>`;
  }
  if (value && typeof value === "object") {
    const imageKeys = new Set(["image_url", "image_alt", "secondary_image_url", "secondary_image_alt"]);
    const entries = Object.entries(value).filter(([key]) => !imageKeys.has(key));
    const figures = [
      value.image_url ? { url: value.image_url, alt: value.image_alt || "课程操作示意图" } : null,
      value.secondary_image_url ? { url: value.secondary_image_url, alt: value.secondary_image_alt || "课程操作示意图" } : null,
    ].filter(Boolean);
    return `${entries.length ? `<div class="learning-kv">${entries.map(([key, item]) => `<div class="learning-kv-row"><b>${escapeHtml(key)}</b>${renderLearningValue(item)}</div>`).join("")}</div>` : ""}${figures.length ? `<div class="course-figures">${figures.map((figure) => `<figure><img src="${escapeHtml(figure.url)}" alt="${escapeHtml(figure.alt)}" loading="lazy"><figcaption>${escapeHtml(figure.alt)}</figcaption></figure>`).join("")}</div>` : ""}`;
  }
  return `<p>${escapeHtml(value)}</p>`;
}

function resetCourseModalScroll() {
  const backdrop = $("course-modal");
  [backdrop, backdrop.querySelector(".course-modal"), els.courseModalContent].forEach((container) => {
    if (!container) return;
    container.scrollTop = 0;
    container.scrollLeft = 0;
  });
}

function openCourse(courseId, title) {
  const course = resolveReferenceCourse({ course_id: courseId, title });
  if (!course) {
    showToast("暂未找到对应课程，可先参考当前回答。", true);
    return;
  }
  resetCourseModalScroll();
  const module = moduleById(course.module_id);
  els.courseModalContent.innerHTML = `
    <div class="course-modal-breadcrumb">${escapeHtml(module?.title || "学习模块")} <span>›</span> ${escapeHtml(course.group_title || "课程")}</div>
    <div class="course-modal-header"><span>${course.kind === "objection" ? "接待案例" : "专业课程"} · 约 ${course.estimated_minutes} 分钟</span><h2 id="course-modal-title">${escapeHtml(course.title)}</h2><p>${escapeHtml(course.summary)}</p></div>
    <div class="course-sections">${course.sections.map((section) => `<section class="course-section"><h3>${escapeHtml(section.title)}</h3>${renderLearningValue(section.content)}</section>`).join("")}</div>`;
  openModal("course-modal");
  resetCourseModalScroll();
  requestAnimationFrame(resetCourseModalScroll);
}

function bindCourseButtons(root) {
  root.querySelectorAll("[data-course-id], [data-course-title]").forEach((button) => {
    button.addEventListener("click", () => openCourse(button.dataset.courseId, button.dataset.courseTitle));
  });
}

function moduleScenarios(moduleId = activeModuleId()) {
  const ids = moduleById(moduleId)?.scenario_ids || [];
  const linked = ids.map((id) => state.scenarios.find((scenario) => scenario.id === id)).filter(Boolean);
  return linked.length ? linked : state.scenarios.filter((scenario) => scenario.module_id === moduleId);
}

function selectScenario() {
  const choices = moduleScenarios();
  const selected = choices[state.scenarioIndex % Math.max(choices.length, 1)] || state.scenarios[0] || null;
  const examDetail = state.examBank?.modules?.flatMap((item) => item.scenarios || []).find((item) => item.id === selected?.id);
  state.scenario = examDetail ? { ...selected, ...examDetail } : selected;
}

function activeExamModule() {
  return objectiveExamById(state.objectiveModuleId);
}

function objectiveExamById(examId) {
  return state.examBank?.modules?.find((item) => item.id === examId) || realExamById(examId);
}

function objectiveAnswerKey(question) {
  return question.id;
}

function examQuestions(exam) {
  if (!exam) return [];
  if (isRealExam(exam)) return exam.questions.map((question) => ({
    ...question,
    type: question.type === "subjective" ? "short_answer" : question.type,
    points: Number(question.points || 0),
  }));
  return [
    ...(exam.fill_blanks || []).map((question) => ({
      ...question,
      type: "fill_blank",
      section: "填空题",
      points: 2,
      answer_parts: [{ answer: question.answers?.[0] || "", aliases: question.answers?.slice(1) || [] }],
      reference_answer: (question.answers || []).join(" / "),
    })),
    ...(exam.choices || []).map((question) => ({
      ...question,
      type: question.kind === "multiple" ? "multiple" : "single",
      section: "选择题",
      points: 4,
      reference_answer: (question.answers || []).join("、"),
    })),
  ];
}

function examTotalPoints(exam) {
  return examQuestions(exam).reduce((total, question) => total + Number(question.points || 0), 0);
}

function formatPoints(value) {
  const number = Math.round(Number(value || 0) * 100) / 100;
  return Number.isInteger(number) ? String(number) : String(number.toFixed(2)).replace(/0+$/, "").replace(/\.$/, "");
}

function normalizedAnswerParts(question) {
  return (question.answer_parts || []).map((part, index) => {
    if (typeof part === "string") return { index: index + 1, answer: part, aliases: [] };
    if (Array.isArray(part)) return { index: index + 1, answer: part[0] || "", aliases: part.slice(1) };
    return { index: part.index || index + 1, answer: part.answer || "", aliases: part.aliases || [] };
  });
}

function normalizedExamText(value) {
  const text = String(value || "").normalize("NFKC").trim();
  const numericLike = /^[\d一二三四五六七八九十百千万半点.\-—–－~～至到\/\s]+$/.test(text);
  if (numericLike) {
    return text.replace(/\s/g, "").replace(/[—–－~～至]/g, "-").toLowerCase();
  }
  return text.replace(/[，、；。,.!?！？：:\s（）()《》“”"'‘’\-—_\/]/g, "").toLowerCase();
}

function answerMatches(actual, answer, aliases = []) {
  const normalized = normalizedExamText(actual);
  return [answer, ...aliases].some((candidate) => normalized === normalizedExamText(candidate));
}

function questionReferenceAnswer(question) {
  if (question.reference_answer) return question.reference_answer;
  if (question.type === "fill_blank") return normalizedAnswerParts(question).map((part) => part.answer).join("；");
  return (question.answers || []).join("、");
}

function questionAnswerText(question, value) {
  if (question.type === "fill_blank") return (Array.isArray(value) ? value : [value]).map((item) => String(item || "").trim()).filter(Boolean).join("；");
  if (["single", "multiple"].includes(question.type)) return (Array.isArray(value) ? value : [value]).filter(Boolean).join("、");
  return String(value || "").trim();
}

function questionIsAnswered(question, value) {
  if (question.type === "fill_blank") {
    const parts = normalizedAnswerParts(question);
    const values = Array.isArray(value) ? value : [value];
    return parts.length > 0 && parts.every((part, index) => String(values[index] || "").trim());
  }
  if (["single", "multiple"].includes(question.type)) return Array.isArray(value) && value.length > 0;
  return Boolean(String(value || "").trim());
}

function examSectionGroups(questions) {
  const groups = [];
  questions.forEach((question) => {
    const title = question.section || (question.type === "short_answer" ? "问答题" : "考试题");
    let group = groups.find((item) => item.title === title);
    if (!group) {
      group = { title, questions: [] };
      groups.push(group);
    }
    group.questions.push(question);
  });
  return groups;
}

function objectiveAnswers(moduleId = state.objectiveModuleId) {
  if (!moduleId) return {};
  state.objectiveAnswersByModule[moduleId] ||= {};
  return state.objectiveAnswersByModule[moduleId];
}

function objectiveScore(moduleId = state.objectiveModuleId) {
  return moduleId ? state.objectiveScoresByModule[moduleId] || null : null;
}

function simulationScores(moduleId = state.simulationModuleId) {
  if (!moduleId) return {};
  state.simulationScoresByModule[moduleId] ||= {};
  return state.simulationScoresByModule[moduleId];
}

function renderObjectiveQuestion(question, index, answers, score) {
  const key = objectiveAnswerKey(question);
  const result = score?.results?.[key];
  const value = answers[key];
  const reviewedClass = typeof result?.correct === "boolean" ? (result.correct ? "is-correct" : "is-wrong") : "";
  let control = "";
  if (question.type === "fill_blank") {
    const parts = normalizedAnswerParts(question);
    const values = Array.isArray(value) ? value : [value];
    control = `<div class="fill-answer-grid">${parts.map((part, partIndex) => `
      <label class="fill-answer-part"><span>${parts.length > 1 ? `第 ${partIndex + 1} 空` : "你的答案"}</span><input type="text" data-exam-fill="${escapeHtml(key)}" data-part-index="${partIndex}" value="${escapeHtml(values[partIndex] || "")}" placeholder="请输入答案" ${score ? "disabled" : ""}></label>`).join("")}</div>`;
  } else if (["single", "multiple"].includes(question.type)) {
    const selected = new Set(Array.isArray(value) ? value : []);
    control = `<div class="exam-options">${(question.options || []).map((option) => `<label class="exam-option"><input type="${question.type === "multiple" ? "checkbox" : "radio"}" name="${escapeHtml(key)}" value="${escapeHtml(option.key)}" data-exam-choice="${escapeHtml(key)}" ${selected.has(option.key) ? "checked" : ""} ${score ? "disabled" : ""}><b>${escapeHtml(option.key)}</b>${escapeHtml(option.text)}</label>`).join("")}</div>`;
  } else {
    control = `<textarea class="exam-short-answer" data-exam-short="${escapeHtml(key)}" rows="5" placeholder="请写下完整回答" ${score ? "disabled" : ""}>${escapeHtml(value || "")}</textarea>`;
  }

  let review = "";
  if (score) {
    const answerLabel = question.type === "short_answer" ? "原卷参考答案" : "正确答案";
    const explanation = question.explanation ? `<p class="answer-explanation"><b>解析</b>${escapeHtml(question.explanation)}</p>` : "";
    const manualValue = score.manualScores?.[key];
    const manualScore = question.type === "short_answer" ? `
      <label class="manual-score"><span>本题得分</span><span><input type="number" min="0" max="${Number(question.points || 0)}" step="0.5" data-manual-score="${escapeHtml(key)}" value="${manualValue ?? ""}" ${score.stage === "complete" ? "disabled" : ""}> / ${formatPoints(question.points)} 分</span></label>` : `<span class="auto-score">自动得分：${formatPoints(result?.earned || 0)} / ${formatPoints(question.points)} 分</span>`;
    review = `<div class="answer-review"><span>你的回答：${escapeHtml(result?.actual || "未作答")}</span><em><b>${answerLabel}</b>${escapeHtml(questionReferenceAnswer(question))}</em>${explanation}${manualScore}</div>`;
  }

  const typeLabel = question.type === "short_answer" ? "问答" : question.type === "multiple" ? "多选" : question.type === "single" ? "单选" : "填空";
  return `<article class="exam-question ${reviewedClass}" data-question-id="${escapeHtml(key)}"><div class="exam-question-title"><span>${index + 1}. ${escapeHtml(question.prompt)}</span><small>${typeLabel} · ${formatPoints(question.points)} 分</small></div>${control}${review}</article>`;
}

function renderObjectiveExam() {
  const exam = activeExamModule();
  if (!exam) return "";
  const answers = objectiveAnswers();
  const score = objectiveScore();
  const questions = examQuestions(exam);
  const totalPoints = examTotalPoints(exam);
  const manualQuestions = questions.filter((question) => question.type === "short_answer");
  let questionNumber = 0;
  const sections = examSectionGroups(questions).map((group) => {
    const sectionPoints = group.questions.reduce((sum, question) => sum + Number(question.points || 0), 0);
    const content = group.questions.map((question) => renderObjectiveQuestion(question, questionNumber++, answers, score)).join("");
    return `<details open><summary>${escapeHtml(group.title)}（${group.questions.length} 题，共 ${formatPoints(sectionPoints)} 分）</summary><div class="exam-question-list">${content}</div></details>`;
  }).join("");
  const realExam = isRealExam(exam);
  const sourceNote = realExam ? `<div class="real-exam-source-note"><strong>真实考试说明</strong><p>${escapeHtml(exam.score_note || "题目、答案和分值按原卷录入。")} 问答题提交后显示原卷答案，由监考或培训人员录入本题得分。</p>${state.realExamBank?.notice ? `<p>${escapeHtml(state.realExamBank.notice)}</p>` : ""}</div>` : "";
  let reveal = "";
  if (score?.stage === "review") {
    reveal = `<div class="exam-result exam-review-pending" tabindex="-1"><strong>答题已提交，进入批阅</strong><p>请对照每道问答题的原卷答案，在“本题得分”中录入 0 至该题满分；全部录入后即可查看总成绩。</p></div>`;
  } else if (score?.stage === "complete") {
    const percentage = totalPoints ? Math.round((score.score / totalPoints) * 100) : 0;
    const detail = manualQuestions.length
      ? `填空或选择题自动得分 ${formatPoints(score.autoScore)} 分，问答题批阅得分 ${formatPoints(score.manualScore)} 分。`
      : `答对 ${score.correct}/${questions.length} 题。下方已标出你的答案、正确答案和解析。`;
    reveal = `<div class="exam-result" tabindex="-1"><strong>本次得分：${formatPoints(score.score)}/${formatPoints(totalPoints)}（${percentage}%）</strong><p>${detail}</p></div>`;
  }
  const action = !score
    ? `<button class="exam-submit" data-submit-objective>${manualQuestions.length ? "提交答卷并开始批阅" : "交卷并查看成绩"}</button>`
    : score.stage === "review"
      ? `<button class="exam-submit" data-finalize-objective>完成批阅并查看成绩</button>`
      : `<button class="exam-restart" data-reset-objective>再考一次</button>`;
  return `<section class="objective-exam ${realExam ? "real-objective-exam" : ""}"><div class="exam-section-head"><span>共 ${questions.length} 题 · 满分 ${formatPoints(totalPoints)} 分</span><h3>${realExam ? escapeHtml(exam.title) : "开始答题"}</h3><p>${manualQuestions.length ? "请独立完成全部题目；提交前不会显示标准答案。" : "完成所有题目后交卷，即可查看成绩和详细解析。"}</p></div>${sourceNote}${sections}${action}${reveal}</section>`;
}

function scoreObjectiveExam() {
  const exam = activeExamModule();
  if (!exam) return;
  const answers = objectiveAnswers();
  let autoScore = 0;
  let correct = 0;
  const all = examQuestions(exam);
  const unanswered = all.filter((question) => !questionIsAnswered(question, answers[objectiveAnswerKey(question)]));
  if (unanswered.length) {
    showToast(`还有 ${unanswered.length} 题未作答，完成后再交卷。`, true);
    const firstKey = objectiveAnswerKey(unanswered[0]);
    els.testScenario.querySelector(`[data-exam-fill="${firstKey}"], [data-exam-choice="${firstKey}"], [data-exam-short="${firstKey}"]`)?.focus();
    return;
  }
  const results = {};
  all.forEach((question) => {
    const key = objectiveAnswerKey(question);
    const actualAnswer = answers[key];
    if (question.type === "short_answer") {
      results[key] = { correct: null, earned: null, actual: questionAnswerText(question, actualAnswer) };
      return;
    }
    let earned = 0;
    let isCorrect = false;
    if (question.type === "fill_blank") {
      const parts = normalizedAnswerParts(question);
      const values = Array.isArray(actualAnswer) ? actualAnswer : [actualAnswer];
      let correctParts = 0;
      if (question.order_sensitive === false) {
        const unmatched = [...values];
        parts.forEach((part) => {
          const matchedIndex = unmatched.findIndex((value) => answerMatches(value, part.answer, part.aliases));
          if (matchedIndex >= 0) {
            correctParts += 1;
            unmatched.splice(matchedIndex, 1);
          }
        });
      } else {
        correctParts = parts.filter((part, index) => answerMatches(values[index], part.answer, part.aliases)).length;
      }
      earned = parts.length ? Number(question.points || 0) * (correctParts / parts.length) : 0;
      isCorrect = correctParts === parts.length;
    } else {
      const expected = new Set((question.answers || []).map((item) => String(item)));
      const actual = new Set(Array.isArray(actualAnswer) ? actualAnswer.map((item) => String(item)) : []);
      isCorrect = expected.size === actual.size && [...expected].every((item) => actual.has(item));
      earned = isCorrect ? Number(question.points || 0) : 0;
    }
    earned = Math.round(earned * 100) / 100;
    autoScore += earned;
    if (isCorrect) correct += 1;
    results[key] = { correct: isCorrect, earned, actual: questionAnswerText(question, actualAnswer) };
  });
  const hasManual = all.some((question) => question.type === "short_answer");
  state.objectiveScoresByModule[state.objectiveModuleId] = {
    stage: hasManual ? "review" : "complete",
    score: hasManual ? null : autoScore,
    autoScore,
    manualScore: 0,
    correct,
    results,
    manualScores: {},
  };
  renderScenarioFrame();
  els.testScenario.querySelector(".exam-result")?.focus();
}

function finalizeObjectiveReview() {
  const exam = activeExamModule();
  const score = objectiveScore();
  if (!exam || score?.stage !== "review") return;
  const manualQuestions = examQuestions(exam).filter((question) => question.type === "short_answer");
  const missing = manualQuestions.filter((question) => !Object.prototype.hasOwnProperty.call(score.manualScores || {}, question.id));
  if (missing.length) {
    showToast(`还有 ${missing.length} 道问答题未录入得分。`, true);
    els.testScenario.querySelector(`[data-manual-score="${missing[0].id}"]`)?.focus();
    return;
  }
  const invalid = manualQuestions.find((question) => {
    const value = Number(score.manualScores[question.id]);
    return !Number.isFinite(value) || value < 0 || value > Number(question.points || 0);
  });
  if (invalid) {
    showToast(`“${invalid.prompt}”的得分应在 0 到 ${formatPoints(invalid.points)} 分之间。`, true);
    els.testScenario.querySelector(`[data-manual-score="${invalid.id}"]`)?.focus();
    return;
  }
  score.manualScore = Math.round(manualQuestions.reduce((sum, question) => sum + Number(score.manualScores[question.id]), 0) * 100) / 100;
  score.score = Math.round((score.autoScore + score.manualScore) * 100) / 100;
  score.stage = "complete";
  renderScenarioFrame();
  els.testScenario.querySelector(".exam-result")?.focus();
}

function bindObjectiveExam(root) {
  root.querySelectorAll("[data-exam-fill]").forEach((input) => input.addEventListener("input", () => {
    const key = input.dataset.examFill;
    const values = Array.isArray(objectiveAnswers()[key]) ? [...objectiveAnswers()[key]] : [];
    values[Number(input.dataset.partIndex || 0)] = input.value;
    objectiveAnswers()[key] = values;
  }));
  root.querySelectorAll("[data-exam-short]").forEach((input) => input.addEventListener("input", () => { objectiveAnswers()[input.dataset.examShort] = input.value; }));
  root.querySelectorAll("[data-exam-choice]").forEach((input) => input.addEventListener("change", () => {
    const key = input.dataset.examChoice;
    const checked = [...root.querySelectorAll(`[data-exam-choice="${key}"]:checked`)].map((item) => item.value);
    objectiveAnswers()[key] = checked;
  }));
  root.querySelectorAll("[data-manual-score]").forEach((input) => input.addEventListener("input", () => {
    const score = objectiveScore();
    if (!score || input.value === "") {
      if (score) delete score.manualScores[input.dataset.manualScore];
      return;
    }
    score.manualScores[input.dataset.manualScore] = Number(input.value);
  }));
  root.querySelector("[data-submit-objective]")?.addEventListener("click", scoreObjectiveExam);
  root.querySelector("[data-finalize-objective]")?.addEventListener("click", finalizeObjectiveReview);
  root.querySelector("[data-reset-objective]")?.addEventListener("click", () => {
    delete state.objectiveAnswersByModule[state.objectiveModuleId];
    delete state.objectiveScoresByModule[state.objectiveModuleId];
    renderScenarioFrame();
    els.testScenario.querySelector("input, textarea")?.focus();
  });
}

function renderScenarioFrame() {
  if (state.mode !== "training" && state.mode !== "test") return;
  if (state.route === "exam/objective") {
    els.testScenario.classList.add("objective-only");
    els.testScenario.innerHTML = renderObjectiveExam();
    bindObjectiveExam(els.testScenario);
    return;
  }
  const module = activeModule();
  const scenario = state.scenario;
  const target = state.mode === "test" ? els.testScenario : els.trainingScenario;
  target.classList.remove("objective-only");
  if (!module || !scenario) {
    target.innerHTML = `<div class="scenario-empty">这个模块暂时没有可用场景，请先选择其他模块。</div>`;
    return;
  }
  const isSimulation = state.route === "exam/simulation";
  const scores = isSimulation ? simulationScores() : {};
  const scenarioChoices = moduleScenarios();
  const scenarioNumber = Math.max(1, scenarioChoices.findIndex((item) => item.id === scenario.id) + 1);
  const scenarioAction = isSimulation ? `下一个场景 · ${scenarioNumber}/${scenarioChoices.length}` : "换个场景";
  const focusLabel = isSimulation ? "接待重点" : "练习重点";
  const scenarioStatus = isSimulation ? `<div class="exam-ai-status">考核进度：已完成 ${Object.keys(scores).length}/${moduleScenarios().length} 个场景${scores[scenario.id] != null ? ` · 本场得分：${scores[scenario.id]}/100` : ""}</div>` : "";
  target.innerHTML = `
    <div class="scenario-main">
      <div class="scenario-title-row"><div><span>${isSimulation ? "考核场景" : "陪练场景"}</span><h3>${escapeHtml(scenario.title || scenario.goal || module.title)}</h3></div><button class="change-scenario" data-random-scenario>${scenarioAction} ↗</button></div>
      <div class="scenario-opening"><span>顾客开场</span><p>“${escapeHtml(scenario.opening)}”</p></div>
      ${isSimulation && scenario.task ? `<p class="scenario-task"><b>你的任务：</b>${escapeHtml(scenario.task)}</p>` : ""}${scenarioStatus}
    </div>
    <div class="scenario-focus"><span>${focusLabel}</span><ul>${module.objectives.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>`;
  target.querySelector("[data-random-scenario]")?.addEventListener("click", randomScenario);
}

function changePracticeModule(moduleId) {
  if (!exactModuleById(moduleId)) return;
  navigateRoute(state.route, moduleId);
}

function randomScenario() {
  const choices = moduleScenarios();
  if (!choices.length) return;
  const hasUnfinishedWork = state.history.some((item) => item.role === "user") && !state.ended;
  if (hasUnfinishedWork && !window.confirm("切换后将清空当前对话，是否继续？")) return;
  state.scenarioIndex = (state.scenarioIndex + 1) % choices.length;
  selectScenario();
  renderScenarioFrame();
  resetSession();
}

function resetSession() {
  if (state.mode === "learning" || state.route === "exam/objective" || !els.conversationStage) return;
  state.requestSerial += 1;
  state.busy = false;
  state.history = [];
  state.ended = false;
  setRevisionState(false);
  els.input.value = "";
  els.input.disabled = false;
  els.send.disabled = false;
  els.finish.disabled = true;
  els.finish.textContent = conversationCopy().finish;
  els.turnCount.textContent = "0 轮对话";
  if (state.mode === "qa") {
    els.messages.innerHTML = `<div class="empty-state"><div class="empty-symbol">问</div><h3>输入一个顾客问题</h3><p>接待助手会提供参考回答，并推荐相关课程供你继续学习。</p></div>`;
    return;
  }
  const opening = state.scenario?.opening || "您好，我想先了解一下你们的项目。";
  els.messages.innerHTML = "";
  addMessage("assistant", opening, "AI 顾客");
  state.history.push({ role: "assistant", content: opening });
}

function addMessage(role, text, label, coach = null) {
  els.messages.querySelector(".empty-state")?.remove();
  const row = document.createElement("div");
  row.className = `message-row ${role === "user" ? "user" : ""}`;
  const avatar = role === "user" ? (state.mode === "qa" ? "客" : "我") : (state.mode === "qa" ? "AI" : "客");
  row.innerHTML = `<div class="avatar">${avatar}</div><div class="bubble-wrap"><div class="speaker">${escapeHtml(label)}</div><div class="bubble">${escapeHtml(text)}</div>${coach ? renderCoach(coach) : ""}</div>`;
  els.messages.appendChild(row);
  els.messages.scrollTop = els.messages.scrollHeight;
  return row;
}

function renderCoach(coach) {
  const level = coach.level || "needs_work";
  const label = level === "good" ? "本轮表现不错" : level === "critical" ? "需要立即调整" : "再优化一下";
  const methodology = coach.method_step || coach.knowledge_focus ? `<div class="coach-method"><div><span>接待步骤</span><strong>${escapeHtml(coach.method_step || "按接待流程继续")}</strong></div><div><span>需要用到的知识</span><strong>${escapeHtml(coach.knowledge_focus || "围绕顾客当前问题回答")}</strong></div></div>` : "";
  return `<div class="coach-card ${level}"><div class="coach-title">${label}</div>${methodology}<p><b>可改进之处：</b>${escapeHtml(coach.issue || "")}</p><p><b>为什么：</b>${escapeHtml(coach.why || "")}</p><div class="coach-suggestion"><span>可以这样说</span>${escapeHtml(coach.suggested_reply || "")}</div><div class="coach-next">下一步：${escapeHtml(coach.next_goal || "继续完成需求分析")}</div><div class="coach-actions"><button type="button" class="revise-turn-button" aria-label="修改这次回答">↺ 修改这次回答</button></div></div>`;
}

function setRevisionState(active, turnNumber = 0) {
  state.revising = Boolean(active);
  document.querySelector(".composer-wrap")?.classList.toggle("is-revising", state.revising);
  if (state.revising) {
    els.composerHint.textContent = `正在修改第 ${turnNumber || 1} 轮，重新发送后将更新反馈`;
    els.input.placeholder = "修改你的回复，发送后将更新本轮反馈…";
  } else if (modeCopy[state.mode]) {
    const copy = conversationCopy();
    els.composerHint.textContent = copy.hint;
    els.input.placeholder = copy.placeholder;
  }
}

function updateTrainingEditActions() {
  const buttons = [...els.messages.querySelectorAll(".revise-turn-button")];
  buttons.forEach((button, index) => {
    const available = state.mode === "training" && !state.busy && !state.ended && !state.revising && index === buttons.length - 1;
    button.hidden = !available;
    button.disabled = !available;
  });
}

function reviseLastTrainingTurn() {
  if (state.mode !== "training" || state.busy || state.ended || state.revising) return;
  const assistantTurn = state.history.at(-1);
  const employeeTurn = state.history.at(-2);
  if (assistantTurn?.role !== "assistant" || employeeTurn?.role !== "user") return;
  const rows = [...els.messages.querySelectorAll(".message-row:not(.typing-row)")];
  const assistantRow = rows.at(-1);
  const employeeRow = rows.at(-2);
  if (!assistantRow?.querySelector(".coach-card") || !employeeRow?.classList.contains("user")) return;

  state.history.splice(-2, 2);
  assistantRow.remove();
  employeeRow.remove();
  const turnNumber = state.history.filter((item) => item.role === "user").length + 1;
  setRevisionState(true, turnNumber);
  els.turnCount.textContent = `${turnNumber - 1} 轮对话`;
  els.finish.disabled = true;
  els.input.value = employeeTurn.content;
  els.input.focus();
  els.input.setSelectionRange(els.input.value.length, els.input.value.length);
  updateTrainingEditActions();
  showToast(`已撤回第 ${turnNumber} 轮，修改后发送即可重新评价。`);
}

function addTyping() {
  const row = document.createElement("div");
  row.className = "message-row typing-row";
  const status = state.mode === "qa" ? "接待助手正在查找回答…" : "模拟顾客正在回复…";
  row.innerHTML = `<div class="avatar">${state.mode === "qa" ? "AI" : "客"}</div><div class="bubble-wrap"><div class="speaker">${status}</div><div class="bubble typing"><i></i><i></i><i></i></div></div>`;
  els.messages.appendChild(row);
  els.messages.scrollTop = els.messages.scrollHeight;
  return row;
}

function requestContextKey() {
  return `${state.route}:${state.routeModuleId || ""}:${state.scenario?.id || ""}`;
}

function requestHistory(mode = state.mode, moduleId = activeModuleId()) {
  if (mode === "qa") return [...state.history];
  const module = exactModuleById(moduleId);
  return [{ role: "system", content: `本轮模块：${module?.title || "综合接待"}。目标：${(module?.objectives || []).join("；")}` }, ...state.history];
}

async function sendMessage() {
  const message = els.input.value.trim();
  if (!message || state.busy || state.ended) return;
  const modeSnapshot = state.mode;
  const moduleSnapshot = activeModuleId();
  const scenarioSnapshot = state.scenario?.id;
  const contextSnapshot = requestContextKey();
  const requestId = ++state.requestSerial;
  const isCurrentRequest = () => requestId === state.requestSerial && contextSnapshot === requestContextKey();
  const wasRevising = state.revising;
  const revisedTurnNumber = state.history.filter((item) => item.role === "user").length + 1;
  state.busy = true;
  els.send.disabled = true;
  els.input.value = "";
  const priorHistory = requestHistory(modeSnapshot, moduleSnapshot);
  const userRow = addMessage("user", message, modeSnapshot === "qa" ? "顾客问题" : "我（员工）");
  state.history.push({ role: "user", content: message });
  if (wasRevising) els.composerHint.textContent = `正在重新评价第 ${revisedTurnNumber} 轮…`;
  updateTrainingEditActions();
  const typing = addTyping();
  try {
    const data = await api("/api/chat", {
      mode: modeSnapshot,
      action: "turn",
      message,
      history: priorHistory,
      scenario_id: scenarioSnapshot,
      api_key: state.apiKey,
      model: state.model,
    });
    typing.remove();
    if (!isCurrentRequest()) return;
    updateApiStatus(data.meta);
    if (modeSnapshot === "training") {
      const result = data.result;
      addMessage("assistant", result.customer_reply || "顾客暂时没有继续说。", "AI 顾客", result.feedback);
      state.history.push({ role: "assistant", content: result.customer_reply || "" });
      setRevisionState(false);
    } else if (modeSnapshot === "test") {
      const result = data.result;
      addMessage("assistant", result.reply || "顾客暂时没有继续说。", "AI 顾客");
      state.history.push({ role: "assistant", content: result.reply || "" });
    } else {
      renderQAAnswer(data.result, data.retrieved || [], data.citations || []);
      state.history.push({ role: "assistant", content: data.result.answer || "" });
    }
    const turns = state.history.filter((item) => item.role === "user").length;
    els.turnCount.textContent = `${turns} 轮对话`;
    if (modeSnapshot !== "qa") els.finish.disabled = modeSnapshot === "test" ? turns < 4 : turns < 1;
  } catch (error) {
    typing.remove();
    if (!isCurrentRequest()) return;
    userRow.remove();
    if (state.history.at(-1)?.role === "user" && state.history.at(-1)?.content === message) state.history.pop();
    els.input.value = message;
    if (wasRevising) setRevisionState(true, revisedTurnNumber);
    showToast(error.message, true);
  } finally {
    if (!isCurrentRequest()) return;
    state.busy = false;
    if (!state.ended) els.send.disabled = false;
    updateTrainingEditActions();
    els.input.focus();
  }
}

function renderQAAnswer(result, retrieved, citations) {
  const row = addMessage("assistant", result.answer || "暂时没有找到足够依据。", "AI 接待助手");
  if (result.faq_match) {
    row.querySelector(".bubble-wrap").insertAdjacentHTML("beforeend", `<div class="answer-faq-match"><span>优先命中常见问答标准答案</span><p>匹配问题：${escapeHtml(result.faq_match.question || "相似常见问题")}</p></div>`);
  }
  const route = result.route || {};
  const supportingModules = Array.isArray(route.supporting_modules) ? route.supporting_modules : [];
  const routeModules = [route.primary_module, ...supportingModules].filter(Boolean);
  if (route.intent || routeModules.length) {
    row.querySelector(".bubble-wrap").insertAdjacentHTML("beforeend", `<div class="answer-method"><div class="answer-method-head"><span>顾客关注</span><strong>${escapeHtml(route.intent || "一般需求咨询")}</strong></div><div class="answer-method-route"><span>参考模块</span><p>${escapeHtml(routeModules.join(" · ") || "新客接待与需求洞察")}</p></div>${route.method_step ? `<div class="answer-method-step"><span>建议回应步骤</span><p>${escapeHtml(route.method_step)}</p></div>` : ""}</div>`);
  }
  if (result.recommended_action) {
    row.querySelector(".bubble-wrap").insertAdjacentHTML("beforeend", `<div class="answer-next-action"><span>接待建议</span><p>${escapeHtml(result.recommended_action)}</p></div>`);
  }
  const references = retrieved.length ? retrieved : citations.map((item) => ({ course_id: item.course_id, title: item.label, module: item.module, chapter: item.chapter }));
  const resolvedReferences = references.map((item) => ({ item, course: resolveReferenceCourse(item) }));
  const unique = resolvedReferences.filter(({ item, course }, index, all) => {
    const key = course?.id || item.title;
    return key && all.findIndex((candidate) => (candidate.course?.id || candidate.item.title) === key) === index;
  }).slice(0, 5);
  const referenceHtml = unique.length ? unique.map(({ item, course }) => {
    const module = course ? moduleById(course.module_id) : null;
    const title = course?.title || item.title;
    const moduleLabel = module?.short_name || module?.title || item.module || "知识模块";
    const chapter = course?.group_title || item.chapter || "";
    if (!course) {
      return `<div class="answer-reference answer-reference-unavailable"><span>${escapeHtml(moduleLabel)}${chapter ? ` · ${escapeHtml(chapter)}` : ""}</span><strong>${escapeHtml(title)}</strong><i>参考资料</i></div>`;
    }
    return `<button class="answer-reference" data-course-id="${escapeHtml(course.id)}" data-course-title="${escapeHtml(course.title)}"><span>${escapeHtml(moduleLabel)}${chapter ? ` · ${escapeHtml(chapter)}` : ""}</span><strong>${escapeHtml(course.title)}</strong><i>查看课程 →</i></button>`;
  }).join("") : `<div class="reference-empty">本次回答参考了通用接待与安全规范。</div>`;
  row.querySelector(".bubble-wrap").insertAdjacentHTML("beforeend", `<div class="answer-basis"><div class="answer-basis-title"><span>相关知识与课程</span><small>打开课程查看详情</small></div><div class="answer-reference-list">${referenceHtml}</div></div>`);
  bindCourseButtons(row);
}

async function finishSession() {
  const userTurns = state.history.filter((item) => item.role === "user").length;
  const minimumTurns = state.route === "exam/simulation" ? 4 : 1;
  if (state.mode === "qa" || state.busy || state.ended) return;
  if (userTurns < minimumTurns) {
    showToast(`再完成 ${minimumTurns - userTurns} 轮对话，即可查看结果。`, true);
    return;
  }
  const modeSnapshot = state.mode;
  const moduleSnapshot = activeModuleId();
  const scenarioSnapshot = state.scenario?.id;
  const contextSnapshot = requestContextKey();
  const requestId = ++state.requestSerial;
  const isCurrentRequest = () => requestId === state.requestSerial && contextSnapshot === requestContextKey();
  state.busy = true;
  updateTrainingEditActions();
  els.finish.disabled = true;
  els.finish.textContent = "正在生成评分结果…";
  els.input.disabled = true;
  els.send.disabled = true;
  const typing = addTyping();
  try {
    const data = await api("/api/chat", {
      mode: "test",
      action: "finish",
      history: requestHistory(modeSnapshot, moduleSnapshot),
      scenario_id: scenarioSnapshot,
      api_key: state.apiKey,
      model: state.model,
    });
    typing.remove();
    if (!isCurrentRequest()) return;
    renderAssessment(data.result);
    updateApiStatus(data.meta);
    state.ended = true;
    els.input.disabled = true;
    els.send.disabled = true;
    els.finish.textContent = "评分完成";
  } catch (error) {
    typing.remove();
    if (!isCurrentRequest()) return;
    els.finish.disabled = false;
    els.finish.textContent = conversationCopy().finish;
    els.input.disabled = false;
    els.send.disabled = false;
    showToast(error.message, true);
  } finally {
    if (!isCurrentRequest()) return;
    state.busy = false;
    updateTrainingEditActions();
  }
}

function renderAssessment(result) {
  if (state.route === "exam/simulation" && state.scenario?.id) {
    simulationScores()[state.scenario.id] = Number(result.total_score || 0);
    renderScenarioFrame();
  }
  const card = document.createElement("div");
  card.className = "assessment-card";
  const dimensions = (result.dimension_scores || []).map((item) => `<div class="score-row"><div class="score-row-head"><span>${escapeHtml(item.name)}</span><strong>${escapeHtml(item.score)}<i>/${escapeHtml(item.max_score)}</i></strong></div><small><b>评分依据</b>${escapeHtml(item.evidence || "对话中未体现")}<br><b>表现说明</b>${escapeHtml(item.comment || "")}</small></div>`).join("");
  const critical = (result.critical_failures || []).map((item) => `<div><b>${escapeHtml(item.code)}</b> ${escapeHtml(item.reason)}${item.evidence ? `<br><small>${escapeHtml(item.evidence)}</small>` : ""}</div>`).join("");
  const scenario = state.scenario || {};
  const standardAnswer = state.route === "exam/simulation" && scenario.reference_answer ? `<div class="report-block standard-answer"><label>参考回答与关键要点</label><p>${escapeHtml(scenario.reference_answer)}</p><ul>${(scenario.must_test || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : "";
  const reportTitle = state.mode === "training" ? "本次陪练报告" : "模拟接待考核结果";
  card.innerHTML = `<div class="assessment-header"><div><span>${reportTitle}</span><p>${escapeHtml(result.summary || "本次对话评分已完成。")}</p></div><strong>${escapeHtml(result.total_score ?? 0)}<i>/100</i></strong></div><div class="score-rows">${dimensions}</div>${critical ? `<div class="critical-block"><b>需要重点改进</b><br>${critical}</div>` : ""}<div class="report-columns"><div class="report-block"><label>做得好的地方</label><p>${escapeHtml((result.strengths || []).join("；") || "继续保持完整沟通。")}</p></div><div class="report-block improve"><label>下次重点练习</label><p>${escapeHtml((result.improvements || []).join("；") || "继续练习需求分析和异议处理。")}</p></div>${standardAnswer}</div>`;
  els.messages.appendChild(card);
  els.messages.scrollTop = els.messages.scrollHeight;
}

function updateApiStatus(meta = {}, health = null) {
  if (meta.mock === false) state.apiVerified = true;
  if (!state.apiKey) state.apiVerified = false;
  const connected = state.apiVerified || Boolean(health?.api_configured);
  els.apiStatus.textContent = connected ? "在线 AI 已就绪" : state.apiKey ? "在线 AI 待连接" : "演示模式";
}

function openModal(id) {
  const backdrop = $(id);
  if (document.activeElement instanceof HTMLElement) modalReturnFocus.set(id, document.activeElement);
  backdrop.classList.remove("hidden");
  backdrop.scrollTop = 0;
  backdrop.querySelector(".modal")?.scrollTo(0, 0);
  document.body.classList.add("modal-open");
  requestAnimationFrame(() => backdrop.querySelector(".modal-close, input, select, button")?.focus());
}

function closeModal(id) {
  if (id === "course-modal") resetCourseModalScroll();
  $(id).classList.add("hidden");
  if (!document.querySelector(".modal-backdrop:not(.hidden)")) document.body.classList.remove("modal-open");
  const trigger = modalReturnFocus.get(id);
  modalReturnFocus.delete(id);
  if (trigger?.isConnected) trigger.focus();
}

function renderModelOptions() {
  const models = [...state.models];
  if (!models.some((item) => item.id === state.model)) models.unshift({ id: state.model, label: `${state.model} · 已保存` });
  const options = models.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</option>`).join("");
  $("model-name").innerHTML = options;
  $("model-name").value = state.model;
}

function selectModel(model, notify = true) {
  if (!model) return;
  state.model = model;
  localStorage.setItem("kbai_model", state.model);
  renderModelOptions();
  if (notify) showToast(`已切换模型：${state.models.find((item) => item.id === model)?.label || model}`);
}

function openSettings() {
  $("api-key").value = state.apiKey;
  renderModelOptions();
  openModal("settings-modal");
}

async function saveSettings() {
  const candidateKey = $("api-key").value.trim();
  const candidateModel = $("model-name").value.trim() || DEFAULT_MODEL;
  const saveButton = $("save-settings");
  if (!candidateKey) {
    state.apiKey = "";
    state.model = candidateModel;
    state.apiVerified = false;
    localStorage.removeItem("kbai_api_key");
    localStorage.setItem("kbai_model", state.model);
    updateApiStatus({ mock: true });
    closeModal("settings-modal");
    showToast("已进入演示模式。");
    return;
  }
  saveButton.disabled = true;
  saveButton.textContent = "正在连接…";
  els.apiStatus.textContent = "正在连接在线 AI";
  try {
    const validation = await api("/api/chat", {
      mode: "qa",
      action: "turn",
      message: "你好，请确认连接。",
      history: [],
      api_key: candidateKey,
      model: candidateModel,
    });
    if (validation.meta?.mock !== false) throw new Error("API 未返回真实模型结果");
    state.apiKey = candidateKey;
    state.model = candidateModel;
    state.apiVerified = true;
    localStorage.setItem("kbai_api_key", state.apiKey);
    localStorage.setItem("kbai_model", state.model);
    updateApiStatus(validation.meta);
    closeModal("settings-modal");
    showToast("在线 AI 已连接，设置已保存。");
  } catch (error) {
    state.apiVerified = false;
    els.apiStatus.textContent = state.apiKey ? "在线 AI 待连接" : "演示模式";
    showToast(`在线 AI 连接失败，请检查 API Key 或稍后重试。${error.message ? `（${error.message}）` : ""}`, true);
  } finally {
    saveButton.disabled = false;
    saveButton.textContent = "保存并验证";
  }
}

function navigateRoute(route, moduleId = null, options = {}) {
  const { updateHistory = true, replace = false, focus = true } = options;
  const config = ROUTE_CONFIG[route];
  if (!config) return navigateRoute("learning", null, { updateHistory, replace, focus });
  const validModuleId = config.screen === "activity" && moduleId && routeItemById(route, moduleId) ? moduleId : null;
  const nextPath = routePath(route, validModuleId);
  const previousContext = requestContextKey();
  state.requestSerial += 1;
  state.busy = false;
  state.route = route;
  state.routeModuleId = validModuleId;
  state.mode = config.mode;
  if (route === "learning/course") state.learningModuleId = validModuleId;
  if (route === "learning/practice") state.practiceModuleId = validModuleId;
  if (route === "exam/objective") {
    state.objectiveModuleId = validModuleId;
    state.testModuleId = validModuleId;
  }
  if (route === "exam/simulation") {
    state.simulationModuleId = validModuleId;
    state.testModuleId = validModuleId;
  }
  document.querySelectorAll(".typing-row").forEach((row) => row.remove());
  els.input.disabled = false;
  els.send.disabled = false;
  renderModuleOptions();
  renderRoute();
  if (validModuleId && route === "learning/course") renderLearning();
  if (validModuleId && route === "exam/objective") renderScenarioFrame();
  if (validModuleId && (route === "learning/practice" || route === "exam/simulation")) {
    state.scenarioIndex = 0;
    selectScenario();
    renderScenarioFrame();
    resetSession();
  } else if (route === "qa" && previousContext !== requestContextKey()) {
    resetSession();
  }
  if (updateHistory && window.location.hash !== nextPath) {
    window.history[replace ? "replaceState" : "pushState"](null, "", nextPath);
  } else if (!updateHistory && window.location.hash !== nextPath) {
    window.history.replaceState(null, "", nextPath);
  }
  window.scrollTo({ top: 0, behavior: focus ? "smooth" : "auto" });
  if (focus) {
    els.pageTitle.setAttribute("tabindex", "-1");
    els.pageTitle.focus({ preventScroll: true });
  }
}

function syncRouteFromLocation(focus = true) {
  const parsed = parseRouteHash();
  if (parsed.route === state.route && parsed.moduleId === state.routeModuleId && !parsed.invalid) return;
  navigateRoute(parsed.route, parsed.moduleId, { updateHistory: false, focus });
  if (parsed.invalid) showToast("这个链接无法打开，已返回可选择的页面。", true);
}

async function boot() {
  try {
    const [bootstrap, moduleData, catalogData, health, examBank, realExamBank] = await Promise.all([
      api("/api/bootstrap"),
      fetch(staticAsset("learning_modules.json")).then((response) => response.json()),
      fetch(staticAsset("learning_catalog.json")).then((response) => response.json()),
      api("/api/health"),
      fetch(staticAsset("data/comprehensive_exam_bank.json")).then((response) => response.json()),
      fetch(staticAsset("data/real_exam_bank.json")).then((response) => response.json()),
    ]);
    state.scenarios = bootstrap.scenarios || [];
    state.modules = moduleData.modules || [];
    state.courses = catalogData.courses || [];
    state.catalogIndex = catalogData.module_index || [];
    state.knowledge = bootstrap.knowledge || {};
    state.examBank = examBank;
    state.realExamBank = realExamBank;
    state.models = bootstrap.models?.length ? bootstrap.models : AVAILABLE_MODELS;
    renderModelOptions();
    els.healthNumber.textContent = state.knowledge.rag_documents || 172;
    renderModuleOptions();
    const requested = parseRouteHash();
    navigateRoute(requested.route, requested.moduleId, { updateHistory: false, focus: false });
    if (requested.invalid) showToast("这个链接无法打开，已返回可选择的页面。", true);
    updateApiStatus({}, health);
  } catch (error) {
    showToast(`页面数据加载失败，请刷新后重试。${error.message ? `（${error.message}）` : ""}`, true);
  }
}

document.addEventListener("click", (event) => {
  const routeButton = event.target.closest("[data-route]");
  if (!routeButton) return;
  const route = routeButton.dataset.route;
  if (!VALID_ROUTES.has(route)) return;
  navigateRoute(route);
});
els.moduleRouteGrid.addEventListener("click", (event) => {
  const moduleButton = event.target.closest("[data-module-id]");
  if (moduleButton) navigateRoute(state.route, moduleButton.dataset.moduleId);
});
window.addEventListener("popstate", () => syncRouteFromLocation());
window.addEventListener("hashchange", () => syncRouteFromLocation());
els.learningSelect.addEventListener("change", () => {
  state.learningModuleId = els.learningSelect.value;
  renderLearning();
});
els.practiceSelect.addEventListener("change", () => changePracticeModule(els.practiceSelect.value));
els.testSelect.addEventListener("change", () => changePracticeModule(els.testSelect.value));
els.send.addEventListener("click", sendMessage);
els.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});
els.finish.addEventListener("click", finishSession);
els.messages.addEventListener("click", (event) => {
  if (event.target.closest(".revise-turn-button")) reviseLastTrainingTurn();
});
$("clear-chat").addEventListener("click", resetSession);
$("open-settings").addEventListener("click", openSettings);
$("model-name").addEventListener("change", () => selectModel($("model-name").value, false));
$("save-settings").addEventListener("click", saveSettings);
$("demo-mode").addEventListener("click", () => {
  state.apiKey = "";
  $("api-key").value = "";
  saveSettings();
});
document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => closeModal(button.dataset.close)));
document.querySelectorAll(".modal-backdrop").forEach((modal) => modal.addEventListener("click", (event) => {
  if (event.target === modal) closeModal(modal.id);
}));
document.addEventListener("keydown", (event) => {
  const activeModal = document.querySelector(".modal-backdrop:not(.hidden)");
  if (event.key === "Escape") {
    document.querySelectorAll(".modal-backdrop:not(.hidden)").forEach((modal) => closeModal(modal.id));
    return;
  }
  if (event.key !== "Tab" || !activeModal) return;
  const focusable = [...activeModal.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')].filter((item) => item.offsetParent !== null);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable.at(-1);
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
});
document.querySelectorAll("[data-question]").forEach((button) => button.addEventListener("click", () => {
  els.input.value = button.dataset.question;
  els.conversationStage.scrollIntoView({ behavior: "smooth", block: "start" });
  els.input.focus();
}));

boot();
