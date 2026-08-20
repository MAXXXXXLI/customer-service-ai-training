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
      fetch("./data/scoring_rubric.json").then((response) => response.json()),
      fetch("./data/customer_service_methodology.json").then((response) => response.json()),
      fetch("./data/comprehensive_exam_bank.json").then((response) => response.json()),
    ]).then(([scenarios, documents, rubric, methodology, examBank]) => ({ scenarios, documents, rubric, methodology, examBank }));
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

const STATIC_NEGATED_RED_FLAG_PATTERN = /(?:没有|并没有|并无|未出现|未发生|不伴有?|否认)(?:明显|持续|进行性|新发|突然)?(?:胸痛|胸闷|气短|呼吸困难|晕厥|昏厥|出冷汗|突发剧痛|突然剧痛|腿麻|手麻|麻木|无力|大小便异常|会阴麻木|发热|红肿)(?:(?:、|或|和|及|以及)(?:明显|持续|进行性|新发|突然)?(?:胸痛|胸闷|气短|呼吸困难|晕厥|昏厥|出冷汗|突发剧痛|突然剧痛|腿麻|手麻|麻木|无力|大小便异常|会阴麻木|发热|红肿))*/gi;

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

function staticRetrieve(query, documents, limit = 8, route = null) {
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

const STATIC_CRITICAL_PATTERNS = [
  /治愈|根治|治好|包治/,
  /百分百|100%|替代手术|不需要看医生|不反弹/,
  /(?:一定|肯定|保证).{0,8}(?:有效|见效|缓解|改善|结果|减重|减肥)/,
  /(?:停药|换药|口服|注射|剂量)/,
];

function staticCriticalHits(message) {
  const text = String(message || "");
  return STATIC_CRITICAL_PATTERNS.filter((pattern) => {
    const match = text.match(pattern);
    if (!match) return false;
    const prefix = text.slice(Math.max(0, match.index - 14), match.index);
    return !/(?:不能|不可|不应|无法|不得|不会|不做|避免|禁止|拒绝).{0,10}$/.test(prefix);
  }).map((pattern) => pattern.source);
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
      ? "点阵波不能替代手术、医疗诊断或医生制定的治疗方案。您还提到明确疾病或麻木症状，今天应先停止项目与销售推进，并由医疗机构评估；若麻木或无力持续、加重，或伴随大小便异常、会阴麻木等情况，请及时就医或联系急救。"
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

const TRAINING_NEW_FACT_MARKERS = ["手麻", "腿麻", "发麻", "麻木", "无力", "胸痛", "呼吸困难", "晕厥", "头晕", "发热", "红肿", "灼热", "设备异常"];

function staticFeedbackUsesNewCustomerFact(feedback, customerReply, history = [], message = "") {
  const knownBeforeReply = `${history.map((item) => item?.content || "").join(" ")} ${message}`;
  const critique = `${feedback.issue || ""} ${feedback.why || ""}`;
  return TRAINING_NEW_FACT_MARKERS.some((marker) => String(customerReply || "").includes(marker) && !knownBeforeReply.includes(marker) && critique.includes(marker));
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
  if (staticCriticalHits(message).length) feedback.level = "critical";
  if (!staticCriticalHits(message).length && staticFeedbackUsesNewCustomerFact(feedback, customerReply, history, message)) {
    feedback.level = "needs_work";
    feedback.issue = "你已承接顾客当前担心并追问变化；下一轮需要优先处理顾客刚刚补充的新情况。";
    feedback.why = "本轮反馈只评价你说话时已经掌握的信息，不能因为顾客在回复中首次透露的情况倒扣本轮表现。";
    feedback.method_step = "承接新信息并完成安全确认";
    feedback.knowledge_focus = "服务后变化、红旗症状与必要分流";
    feedback.suggested_reply = "您刚刚补充的情况需要优先重视，我们先暂停后续安排，再确认出现时间、范围和是否正在加重。";
    feedback.next_goal = "下一轮只处理顾客新透露的信息，并给出安全、可执行的下一步。";
  }
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

function staticCustomerFallback(scenario, history = [], employeeMessage = "") {
  const persona = scenario?.persona || {};
  const goal = String(persona.goal || "我现在这个困扰").trim();
  const employee = String(employeeMessage || "").trim();
  if (/我错了|说错了|不好意思|抱歉/.test(employee)) return `没关系，你重新给我讲清楚就行。我主要还是想解决${goal}。`;
  if (/不能做|做不了|没什么不同|没区别|都一样|不适合/.test(employee)) return `那我有点没听明白，我主要是${goal}，想知道还有没有别的办法。`;
  if (/多久|多长时间|什么时候开始/.test(employee)) return "有一阵子了，最近感觉比以前明显一些。";
  if (/哪里|哪个部位|什么位置/.test(employee)) return `主要就是${goal}，其他地方我暂时没太留意。`;
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
  return templates[objection] || `我现在主要还是担心${objection}，其他专业的我也不太懂。`;
}

function invalidStaticCustomerReply(reply) {
  const questionCount = (reply.match(/[？?]/g) || []).length;
  return !reply || reply.length > 100 || TEST_INTERNAL_MARKERS.test(reply) || CUSTOMER_ROLE_DRIFT_MARKERS.test(reply) || questionCount > 1;
}

function normalizeStaticCustomerReply(reply, scenario, history = [], employeeMessage = "") {
  let normalized = String(reply || "").trim();
  if (staticEmployeeMessageNeedsCustomerClarification(history, employeeMessage)) return staticCustomerClarificationReply(scenario, history);
  const previous = history.filter((item) => item?.role === "assistant").map((item) => String(item.content || "").trim());
  const repeated = previous.some((item) => normalized === item || (normalized.length >= 18 && item.length >= 18 && normalized.slice(0, 18) === item.slice(0, 18)));
  if (repeated || invalidStaticCustomerReply(normalized) || normalized === String(scenario?.opening || "").trim()) normalized = staticCustomerFallback(scenario, history, employeeMessage);
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
  const redFlagPattern = /胸痛|胸闷|气短|呼吸困难|晕厥|昏厥|突发剧痛|突然剧痛|进行性麻木|腿麻|手麻|麻木|无力|发热红肿|红肿发热/i;
  const discomfortPattern = /疼|痛|灼热|烫|头晕|不舒服|设备异常|设备报警/i;
  const continuePattern = /继续做|继续操作|照常做|再做一次|加量|加大|安排项目|先体验|正常反应|正常现象|没事|不用停|不必停|忍一忍|坚持一下/i;
  const safetyStopPattern = /暂停|停止|先不|不要继续|不再继续|医疗|就医|医院|医生|评估|转介|急救/i;
  const refusalPattern = /不想|拒绝|不要触碰|不拍照|不愿意|别问了|回家考虑|和家人商量/i;
  const pressurePattern = /必须|今天就|现在就|一定要|不能拒绝|不买|不做.{0,8}(?:后悔|更严重)|别告诉|隐瞒/i;
  let priorCustomerText = "";
  history.forEach((item) => {
    const message = String(item?.content || "").trim();
    if (!message) return;
    if (item?.role === "assistant") {
      priorCustomerText += ` ${message}`;
      return;
    }
    if (item?.role !== "user") return;
    if (staticCriticalHits(message).length || /(?:建议|应该|可以).{0,10}(?:停药|换药|剂量|口服|注射)/i.test(message)) add("CF-02", message);
    const unsafeContinuation = continuePattern.test(message) && !safetyStopPattern.test(message);
    if (unsafeContinuation && (redFlagPattern.test(message) || redFlagPattern.test(priorCustomerText))) add("CF-01", message);
    if (pressurePattern.test(message) && refusalPattern.test(priorCustomerText)) add("CF-03", message);
    if (unsafeContinuation && (discomfortPattern.test(message) || discomfortPattern.test(priorCustomerText))) add("CF-04", message);
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
    if (!evidence || staticEvidenceUsesCustomerOnlyText(evidence, history)) evidence = staticFallbackEmployeeEvidence(spec.id, history);
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
  return {
    total_score: totalScore,
    dimension_scores: dimensionScores,
    critical_failures: criticalFailures,
    strengths: cleanList(normalized.strengths, ["完成了本轮顾客沟通。"]),
    improvements: cleanList(normalized.improvements, ["下一轮请围绕顾客原话补齐需求分析、安全边界和可执行下一步。"]),
    next_training_scene: normalized.next_training_scene || "",
    summary: normalized.summary || "评分已按本轮员工实际表达生成。",
  };
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
    return { ok: true, scenarios: data.scenarios, models: AVAILABLE_MODELS, knowledge: { rag_documents: data.documents.length, scenarios: data.scenarios.length }, rubric: { total: data.rubric.total, dimensions: data.rubric.dimensions || [] } };
  }
  if (path === "/api/health") return { ok: true, api_configured: Boolean(state.apiKey), mock_mode: !state.apiKey, model: state.model, models: AVAILABLE_MODELS, knowledge: { rag_documents: data.documents.length } };
  if (path !== "/api/chat") throw new Error("静态模式不支持该接口");

  const mode = body.mode || "qa";
  const action = body.action || "turn";
  const apiKey = body.api_key || state.apiKey;
  const model = body.model || state.model;
  const scenario = data.scenarios.find((item) => item.id === body.scenario_id) || data.scenarios[0];
  const message = body.message || "";
  const history = body.history || [];
  const query = mode === "qa" ? staticQaQuery(message, history) : [...history.slice(-8).map((item) => item.content), message].join(" ");
  const route = staticRouteCustomerQuestion(query, data.methodology);
  const docs = staticRetrieve(query, data.documents, 8, route);
  // Keep interactive prompts compact so multi-turn responses remain reliable
  // on the static Pages build while retrieval/citations stay unchanged.
  const context = docs.slice(0, mode === "training" ? 4 : 8).map((item) => `${item.metadata?.title || item.document_id}\n${String(item.text || "").slice(0, mode === "training" ? 650 : 1200)}`).join("\n\n");
  if (!apiKey) {
    const result = normalizeStaticResult(staticMockProgressive(mode, action, scenario, history, data.rubric, message), mode, action, scenario, history, data.rubric, message, query, route);
    return { ok: true, mode, result, citations: mode === "qa" ? docs.slice(0, 3).map(publicStaticDocument) : [], retrieved: mode === "qa" ? docs.map(publicStaticDocument) : [], meta: { mock: true, model } };
  }

  const dialogue = cleanStaticHistory(history);
  const turnNumber = dialogue.filter((item) => item.role === "user").length + 1;
  const safety = "不得诊断疾病、承诺治愈或固定效果、推荐药品剂量或停药；遇到红旗症状时优先停止项目并建议医疗评估。";
  const routeContext = staticRouteContext(route);
  let system;
  let messages;
  let temperature = 0.3;
  let maxTokens = 1800;
  if (mode === "training") {
    system = `你是门店员工情景训练教练，同时维持一个自然、连续的顾客角色。${safety}\n顾客可知场景：${JSON.stringify(staticCustomerScenario(scenario))}\n${LIMITED_CUSTOMER_POLICY}\n当前是员工第 ${turnNumber} 轮回复。顾客下一句话必须承接员工最新表达，不得重复开场或忽略历史。customer_reply 只能使用顾客可知信息；下面的方法路由和专业知识只供 feedback 使用，绝不能写进 customer_reply。每轮只指出一个最重要问题；feedback 必须引用员工本轮原话，并且只能评价员工说话前已经知道的信息，绝不能因为 customer_reply 本轮首次透露的新情况倒扣员工本轮表现。严格输出 JSON：{"customer_reply":"顾客下一句话","feedback":{"level":"good|needs_work|critical","issue":"...","why":"...","method_step":"...","knowledge_focus":"...","suggested_reply":"...","next_goal":"..."}}。\n方法路由：\n${routeContext}\n相关知识库：\n${context}`;
    messages = [...dialogue, { role: "user", content: message }];
    temperature = 0.35;
    maxTokens = 1200;
  } else if (mode === "test" && action === "turn") {
    system = `你只扮演实战考核中的模拟顾客，不是教练、客服助手或评分员。\n隐藏场景（不得泄露）：${JSON.stringify(staticCustomerScenario(scenario))}\n${LIMITED_CUSTOMER_POLICY}\n开场白已经展示，当前是员工第 ${turnNumber} 轮回复。只回应员工最新一句；绝不重复开场或原样重复旧回复；每轮最多透露一个员工问到的新背景或异议。不得出现考核、评分、知识库、方法路由、隐藏异议、must_test、员工应该等幕后词。严格输出 JSON：{"reply":"顾客下一句话","emotion":"curious|hesitant|concerned|relieved|neutral","should_continue":true}。`;
    messages = [...dialogue, { role: "user", content: message }];
    temperature = 0.55;
  } else if (mode === "test" && action === "finish") {
    system = `你是企业培训考核官，只输出考后评分报告，不再扮演顾客。history 中 role=user 才是员工，role=assistant 是顾客，绝不能混淆。严格按评分表输出恰好 7 个维度；id、name、max_score 必须一致；evidence 只能引用员工原话或写“对话中未体现”；total_score 等于各维度 score 之和，再应用关键失败封顶。每个 evidence 和 comment 不超过 35 个汉字；strengths 与 improvements 各最多 3 条，每条不超过 30 个汉字。${safety}\n严格输出 JSON：{"total_score":0,"dimension_scores":[{"id":"D1","name":"...","score":0,"max_score":10,"evidence":"...","comment":"..."}],"critical_failures":[],"strengths":[],"improvements":[],"next_training_scene":"...","summary":"..."}。`;
    messages = [{ role: "user", content: `评分表：${JSON.stringify(data.rubric)}\n场景：${JSON.stringify(scenario)}\n员工完整对话：${JSON.stringify(cleanStaticHistory(body.history || [], 40))}` }];
    temperature = 0.1;
    maxTokens = 1800;
  } else {
    system = `你是企业知识库中的顾客接待助手。只基于给定的方法路由和资料直接回答顾客当前问题。${safety}\n这是连续对话，必须结合最近问题和上一轮回答理解“这个、那、它、怎么办”等指代，但只回答当前这一问，不要机械重复上一轮。先承接问题，只补一个必要信息，再给已核验内容、边界和一个可执行下一步。严格输出 JSON：{"answer":"...","uncertainties":[],"recommended_action":"..."}。`;
    messages = [...dialogue, { role: "user", content: `顾客当前问题：${message}\n方法路由：\n${routeContext}\n相关知识库：\n${context}` }];
  }
  const timeoutMs = mode === "test" && action === "finish" ? 60000 : 45000;
  const modelResult = await callStaticModel(system, messages, model, apiKey, temperature, maxTokens, timeoutMs);
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
    const direct = state.courses.find((course) => course.id === requestedId);
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
