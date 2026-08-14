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
  mode: "learning",
  modules: [],
  courses: [],
  catalogIndex: [],
  scenarios: [],
  learningModuleId: null,
  practiceModuleId: null,
  testModuleId: null,
  scenarioIndex: 0,
  scenario: null,
  history: [],
  apiKey: localStorage.getItem("kbai_api_key") || "",
  model: localStorage.getItem("kbai_model") || DEFAULT_MODEL,
  models: [...AVAILABLE_MODELS],
  busy: false,
  ended: false,
  knowledge: {},
};

const $ = (id) => document.getElementById(id);
const els = {
  modeButtons: document.querySelectorAll(".mode-button"),
  modeBreadcrumb: $("mode-breadcrumb"),
  pageTitle: $("page-title"),
  pageDescription: $("page-description"),
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
};

const modeCopy = {
  learning: {
    nav: "学习与陪练 / 课程学习",
    title: "课程学习",
    description: "学习标准课程与服务知识。",
    kicker: "",
    conversation: "",
    hint: "",
  },
  training: {
    nav: "学习与陪练 / 情景陪练",
    title: "情景陪练",
    description: "模拟顾客对话，即时纠正表达。",
    kicker: "情景陪练",
    conversation: "与 AI 顾客练习",
    hint: "每轮回答后提供一个关键改进点",
  },
  test: {
    nav: "实战考核",
    title: "实战考核",
    description: "完成无提示对话，查看考核评分。",
    kicker: "实战考核",
    conversation: "无提示顾客对话",
    hint: "考核过程中不会出现任何提示",
  },
  qa: {
    nav: "智能接待",
    title: "智能接待",
    description: "基于企业知识库回答顾客问题。",
    kicker: "AI 顾客接待",
    conversation: "请问您想了解什么？",
    hint: "回答后可打开参考课程继续学习",
  },
};

const VALID_MODES = new Set(["learning", "training", "test", "qa"]);

const STATIC_PAGES = window.location.hostname.endsWith(".github.io");
const staticAsset = (name) => STATIC_PAGES ? `./${name}` : `/static/${name}`;
let staticDataPromise = null;

function parseJsonl(text) {
  return text.split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

async function loadStaticData() {
  if (!staticDataPromise) {
    staticDataPromise = Promise.all([
      fetch("./data/scenario_library.jsonl").then((response) => response.text()).then(parseJsonl),
      fetch("./data/rag_documents.jsonl").then((response) => response.text()).then(parseJsonl),
      fetch("./data/scoring_rubric.json").then((response) => response.json()),
    ]).then(([scenarios, documents, rubric]) => ({ scenarios, documents, rubric }));
  }
  return staticDataPromise;
}

function publicStaticDocument(document) {
  const metadata = document.metadata || {};
  return {
    document_id: document.document_id,
    title: metadata.title || document.document_id || "知识库资料",
    module: metadata.module || metadata.domain || "知识库",
    chapter: metadata.chapter || "",
  };
}

function staticRetrieve(query, documents, limit = 8) {
  const text = String(query || "").toLowerCase();
  const terms = [...new Set(text.match(/[a-z0-9_]{2,}|[\u4e00-\u9fff]{2}/gi) || [])];
  return documents.map((document) => {
    const haystack = `${document.text || ""} ${JSON.stringify(document.metadata || {})}`.toLowerCase();
    const score = terms.reduce((total, term) => total + (haystack.includes(term) ? 1 : 0), 0);
    return { document, score };
  }).filter((item) => item.score > 0).sort((a, b) => b.score - a.score).slice(0, limit).map((item) => item.document);
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

async function callStaticModel(system, messages, model, apiKey, temperature, maxTokens = 1800) {
  const payload = {
    model, messages: [{ role: "system", content: system }, ...messages],
    temperature, top_p: 0.7, max_tokens: maxTokens, response_format: { type: "json_object" }, stream: false,
  };
  if (model.startsWith("Qwen/Qwen3") || model.includes("DeepSeek-V3.2") || model.startsWith("Pro/zai-org/GLM-5")) payload.enable_thinking = false;
  const response = await fetch("https://api.siliconflow.cn/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${apiKey}` },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(`SiliconFlow API ${response.status}: ${data.error?.message || "请求失败"}`);
  return { content: data.choices?.[0]?.message?.content || "", meta: { model: data.model || model, usage: data.usage || {} } };
}

function staticMock(mode, action, scenario) {
  if (mode === "training") return {
    customer_reply: "我主要是肩颈总是紧，偶尔会头晕，想先了解一下你们怎么判断适不适合。",
    feedback: { level: "needs_work", issue: "还可以继续追问顾客的目标、持续时间和影响。", why: "先完成需求分析，再介绍项目。", method_step: "了解目标并完成问题定位", knowledge_focus: "目标、持续时间、影响和安全信息", suggested_reply: "这种情况大概持续多久了？对工作或睡眠有影响吗？", next_goal: "下一轮先问清目标、持续时间和影响。" },
  };
  if (mode === "test" && action === "turn") return { reply: scenario?.opening || "我最近有点困扰，想先了解一下你们的项目。", emotion: "hesitant", should_continue: true };
  if (mode === "test" && action === "finish") return { total_score: 72, dimension_scores: [], critical_failures: [], strengths: ["完成了基本接待并保持对话连续"], improvements: ["先问清目标、持续时间、影响和顾虑，再介绍项目"], summary: "演示评分：流程已走通，配置 API Key 后可使用模型评分。" };
  return { answer: "当前是演示模式。保存 SiliconFlow API Key 后，就能生成基于知识库的正式回答。", uncertainties: ["请以门店当前价格、项目标签和合规版本为准。"], recommended_action: "先核对门店当前版本的价格、频次和适用边界。" };
}

const STATIC_CRITICAL_PATTERNS = ["保证治愈", "百分百", "包治", "替代手术", "不需要看医生", "停药", "口服", "注射", "剂量", "不反弹"];

function staticCriticalHits(message) {
  const text = String(message || "");
  return STATIC_CRITICAL_PATTERNS.filter((pattern) => text.includes(pattern));
}

function staticMockProgressive(mode, action, scenario, history = [], rubric = null, message = "") {
  const userTurns = history.filter((item) => item?.role === "user").length;
  if (mode === "training") {
    const customerReplies = [
      "我主要是肩颈总是紧，偶尔会头晕，想先了解一下你们怎么判断适不适合。",
      "大概有半年了，久坐后更明显，最近睡眠也受了一点影响。",
      "我比较担心做了没效果，而且价格也不能太高。你会怎么建议？",
    ];
    const strong = ["了解", "多久", "哪里", "感受", "目标", "担心", "方便", "预算", "疼", "病史"].some((word) => String(message).includes(word));
    const critical = staticCriticalHits(message).length > 0;
    return {
      customer_reply: customerReplies[Math.min(userTurns, customerReplies.length - 1)],
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
    const replies = [
      "我最担心的是做了没效果，而且价格也不能太高。你会怎么建议？",
      "如果需要先做适用性确认我可以配合，但我想知道下一步怎么安排。",
      "我大概明白了，你能把最适合我现在情况的下一步说具体一点吗？",
    ];
    return { reply: replies[Math.min(userTurns, replies.length - 1)], emotion: userTurns > 0 ? "concerned" : "hesitant", should_continue: true };
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

const TEST_INTERNAL_MARKERS = /考核|评分|知识库|方法路由|隐藏异议|must_test|员工应该|培训教练/i;

function staticTestFallback(scenario, history = []) {
  const objections = scenario?.hidden_objections || [];
  const userTurns = history.filter((item) => item?.role === "user").length;
  const objection = objections[Math.min(userTurns, Math.max(objections.length - 1, 0))] || "下一步安排";
  const templates = {
    "怕疼": "我比较怕疼，如果过程中不舒服，你们会怎么处理？",
    "太贵": "我也有点担心价格，能先说说需要怎么评估和安排吗？",
    "一次有没有用": "那一次大概能观察什么，怎么判断是不是适合继续？",
    "时间": "我平时工作很忙，如果时间有限，下一步怎么安排会更实际？",
    "固定斤数": "我还是很在意能不能达到固定斤数，你们通常怎么和顾客确定目标？",
    "价格": "我还需要考虑预算，能先告诉我确认方案前要了解哪些信息吗？",
    "成分/过敏": "我之前有过敏经历，具体成分和适用性会怎么确认？",
    "怕设备不安全": "我最担心设备安全，过程中如果过热或不舒服能马上停吗？",
  };
  return templates[objection] || `我现在最在意的是${objection}，你能针对这个问题再说明一下吗？`;
}

function normalizeStaticTestTurn(result, scenario, history = []) {
  const normalized = result && typeof result === "object" ? result : {};
  let reply = String(normalized.reply || "").trim();
  const previous = history.filter((item) => item?.role === "assistant").map((item) => String(item.content || "").trim());
  const repeated = previous.some((item) => reply === item || (reply.length >= 18 && item.length >= 18 && reply.slice(0, 18) === item.slice(0, 18)));
  if (!reply || repeated || TEST_INTERNAL_MARKERS.test(reply) || reply === String(scenario?.opening || "").trim()) reply = staticTestFallback(scenario, history);
  const emotions = new Set(["curious", "hesitant", "concerned", "relieved", "neutral"]);
  return { reply, emotion: emotions.has(normalized.emotion) ? normalized.emotion : "neutral", should_continue: normalized.should_continue !== false };
}

function detectStaticAssessmentFailures(history = []) {
  const employeeText = history.filter((item) => item?.role === "user").map((item) => item.content || "").join(" ");
  const failures = [];
  if (staticCriticalHits(employeeText).length || /(?:建议|应该|可以).{0,10}(?:停药|换药|剂量|口服|注射)/i.test(employeeText)) failures.push("CF-02");
  return failures;
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
  const modelFailures = new Map((Array.isArray(normalized.critical_failures) ? normalized.critical_failures : []).filter((item) => failureSpecs.has(item?.code)).map((item) => [item.code, item]));
  detectStaticAssessmentFailures(history).forEach((code) => { if (!modelFailures.has(code)) modelFailures.set(code, { code, evidence: "员工原话触发安全与合规规则。" }); });
  const criticalFailures = [...modelFailures].map(([code, item]) => {
    const spec = failureSpecs.get(code);
    return { code, reason: item.reason || spec.rule, evidence: item.evidence || "员工原话触发关键失败项。", score_cap: spec.score_cap };
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

function normalizeStaticResult(result, mode, action, scenario, history, rubric, message) {
  let normalized = result && typeof result === "object" ? result : {};
  if (mode === "training") {
    const fallback = staticMockProgressive(mode, action, scenario, history, rubric, message);
    normalized.customer_reply = normalized.customer_reply || fallback.customer_reply;
    normalized.feedback = { ...fallback.feedback, ...(normalized.feedback || {}) };
    if (staticCriticalHits(message).length) normalized.feedback.level = "critical";
  }
  if (mode === "test" && action === "turn") normalized = normalizeStaticTestTurn(normalized, scenario, history);
  if (mode === "test" && action === "finish") normalized = normalizeStaticAssessment(normalized, history, rubric);
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
  const query = [...(body.history || []).slice(-8).map((item) => item.content), message].join(" ");
  const docs = staticRetrieve(query, data.documents);
  const context = docs.map((item) => `${item.metadata?.title || item.document_id}\n${String(item.text || "").slice(0, 1200)}`).join("\n\n");
  if (!apiKey) return { ok: true, mode, result: staticMockProgressive(mode, action, scenario, body.history || [], data.rubric, message), citations: docs.slice(0, 3).map(publicStaticDocument), retrieved: docs.map(publicStaticDocument), meta: { mock: true, model } };

  const dialogue = cleanStaticHistory(body.history || []);
  const turnNumber = dialogue.filter((item) => item.role === "user").length + 1;
  const safety = "不得诊断疾病、承诺治愈或固定效果、推荐药品剂量或停药；遇到红旗症状时优先停止项目并建议医疗评估。";
  let system;
  let messages;
  let temperature = 0.3;
  let maxTokens = 1800;
  if (mode === "training") {
    system = `你是门店员工情景训练教练，同时维持一个自然、连续的顾客角色。${safety}\n当前场景：${JSON.stringify(scenario)}\n当前是员工第 ${turnNumber} 轮回复。顾客下一句话必须承接员工最新表达，不得重复开场或忽略历史。每轮只指出一个最重要问题；feedback 必须引用员工本轮原话。严格输出 JSON：{"customer_reply":"顾客下一句话","feedback":{"level":"good|needs_work|critical","issue":"...","why":"...","method_step":"...","knowledge_focus":"...","suggested_reply":"...","next_goal":"..."}}。\n相关知识库：\n${context}`;
    messages = [...dialogue, { role: "user", content: message }];
    temperature = 0.35;
  } else if (mode === "test" && action === "turn") {
    system = `你只扮演实战考核中的模拟顾客，不是教练、客服助手或评分员。${safety}\n隐藏场景（不得泄露）：${JSON.stringify(scenario)}\n开场白已经展示，当前是员工第 ${turnNumber} 轮回复。只回应员工最新一句，每轮 1—3 句；绝不重复开场或原样重复旧回复；每轮最多透露一个员工问到的新背景或异议。不得出现考核、评分、知识库、方法路由、隐藏异议、must_test、员工应该等幕后词。严格输出 JSON：{"reply":"顾客下一句话","emotion":"curious|hesitant|concerned|relieved|neutral","should_continue":true}。`;
    messages = [...dialogue, { role: "user", content: message }];
    temperature = 0.55;
  } else if (mode === "test" && action === "finish") {
    system = `你是企业培训考核官，只输出考后评分报告，不再扮演顾客。history 中 role=user 才是员工，role=assistant 是顾客，绝不能混淆。严格按评分表输出恰好 7 个维度；id、name、max_score 必须一致；evidence 只能引用员工原话或写“对话中未体现”；total_score 等于各维度 score 之和，再应用关键失败封顶。${safety}\n严格输出 JSON：{"total_score":0,"dimension_scores":[{"id":"D1","name":"...","score":0,"max_score":10,"evidence":"...","comment":"..."}],"critical_failures":[],"strengths":[],"improvements":[],"next_training_scene":"...","summary":"..."}。`;
    messages = [{ role: "user", content: `评分表：${JSON.stringify(data.rubric)}\n场景：${JSON.stringify(scenario)}\n员工完整对话：${JSON.stringify(cleanStaticHistory(body.history || [], 40))}\n相关知识库：\n${context}` }];
    temperature = 0.1;
    maxTokens = 3200;
  } else {
    system = `你是企业知识库中的顾客接待助手。只基于给定资料直接回答顾客当前问题。${safety}\n先承接问题，只补一个必要信息，再给已核验内容、边界和一个可执行下一步。严格输出 JSON：{"answer":"...","uncertainties":[],"recommended_action":"..."}。\n相关知识库：\n${context}`;
    messages = [{ role: "user", content: message }];
  }
  const modelResult = await callStaticModel(system, messages, model, apiKey, temperature, maxTokens);
  let result = extractStaticJson(modelResult.content) || (mode === "test" && action === "turn" ? { reply: modelResult.content, emotion: "neutral", should_continue: true } : { answer: modelResult.content, uncertainties: [], recommended_action: "" });
  result = normalizeStaticResult(result, mode, action, scenario, body.history || [], data.rubric, message);
  if (mode === "qa") result.route = { intent: "一般需求咨询", primary_module: "新客接待与需求洞察", method_step: "先确认目标和必要安全信息，再解释选择" };
  return { ok: true, mode, result, citations: docs.slice(0, 3).map(publicStaticDocument), retrieved: docs.map(publicStaticDocument), meta: { ...modelResult.meta, mock: false } };
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

function activeModuleId() {
  return state.mode === "test" ? state.testModuleId : state.practiceModuleId;
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

function renderMode() {
  const copy = modeCopy[state.mode];
  els.modeButtons.forEach((button) => button.classList.toggle("active", button.dataset.mode === state.mode));
  els.modeBreadcrumb.textContent = copy.nav;
  els.pageTitle.textContent = copy.title;
  els.pageDescription.textContent = copy.description;
  els.learningPage.classList.toggle("hidden", state.mode !== "learning");
  els.trainingPage.classList.toggle("hidden", state.mode !== "training");
  els.testPage.classList.toggle("hidden", state.mode !== "test");
  els.qaPage.classList.toggle("hidden", state.mode !== "qa");
  els.conversationStage.classList.toggle("hidden", state.mode === "learning");
  els.finish.classList.toggle("hidden", state.mode === "qa" || state.mode === "learning");
  els.conversationAvatar.textContent = state.mode === "qa" ? "AI" : "客";
  els.conversationKicker.textContent = copy.kicker;
  els.conversationTitle.textContent = copy.conversation;
  els.composerHint.textContent = copy.hint;
  els.input.placeholder = state.mode === "qa" ? "以顾客身份输入你的问题…" : "输入你会对顾客说的话…";
}

function renderModuleOptions() {
  const options = state.modules.map((module) => `<option value="${module.id}">${String(module.order).padStart(2, "0")} · ${escapeHtml(module.title)}</option>`).join("");
  els.learningSelect.innerHTML = options;
  els.practiceSelect.innerHTML = options;
  els.testSelect.innerHTML = options;
  els.learningSelect.value = state.learningModuleId;
  els.practiceSelect.value = state.practiceModuleId;
  els.testSelect.value = state.testModuleId;
}

function renderLearning() {
  const module = moduleById(state.learningModuleId);
  if (!module) return;
  const groups = moduleGroups(module.id);
  const courses = moduleCourses(module.id);
  els.learningSummary.innerHTML = `
    <div><span>当前学习模块</span><h3>${escapeHtml(module.title)}</h3><p>${escapeHtml(module.description)}</p></div>
    <div class="summary-count"><strong>${groups.length}</strong><span>个章节</span><strong>${courses.length}</strong><span>节课程</span></div>`;
  els.learningChapters.innerHTML = groups.map((group, index) => {
    const groupCourses = courses.filter((course) => course.group_id === group.group_id);
    return `<article class="chapter-card">
      <div class="chapter-head"><div class="chapter-number">${String(index + 1).padStart(2, "0")}</div><div><h3>${escapeHtml(group.title)}</h3><p>${escapeHtml(group.description)}</p></div><span>${groupCourses.length} 节</span></div>
      <div class="chapter-courses">${groupCourses.map((course) => `
        <button class="course-preview" data-course-title="${escapeHtml(course.title)}">
          <span class="course-type">${course.kind === "objection" ? "话术案例" : "标准课程"} · ${course.estimated_minutes} 分钟</span>
          <strong>${escapeHtml(course.title)}</strong><small>${escapeHtml(course.summary)}</small><i>打开课程 →</i>
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

function openCourseByTitle(title) {
  const course = state.courses.find((item) => item.title === title);
  if (!course) {
    showToast("这条依据暂时没有对应的独立课程。", true);
    return;
  }
  const module = moduleById(course.module_id);
  els.courseModalContent.innerHTML = `
    <div class="course-modal-breadcrumb">${escapeHtml(module?.title || "学习模块")} <span>›</span> ${escapeHtml(course.group_title || "课程")}</div>
    <div class="course-modal-header"><span>${course.kind === "objection" ? "话术案例" : "标准课程"} · 约 ${course.estimated_minutes} 分钟</span><h2 id="course-modal-title">${escapeHtml(course.title)}</h2><p>${escapeHtml(course.summary)}</p></div>
    <div class="course-sections">${course.sections.map((section) => `<section class="course-section"><h3>${escapeHtml(section.title)}</h3>${renderLearningValue(section.content)}</section>`).join("")}</div>`;
  openModal("course-modal");
}

function bindCourseButtons(root) {
  root.querySelectorAll("[data-course-title]").forEach((button) => {
    button.addEventListener("click", () => openCourseByTitle(button.dataset.courseTitle));
  });
}

function moduleScenarios(moduleId = activeModuleId()) {
  const ids = moduleById(moduleId)?.scenario_ids || [];
  return ids.map((id) => state.scenarios.find((scenario) => scenario.id === id)).filter(Boolean);
}

function selectScenario() {
  const choices = moduleScenarios();
  state.scenario = choices[state.scenarioIndex % Math.max(choices.length, 1)] || state.scenarios[0] || null;
}

function renderScenarioFrame() {
  if (state.mode !== "training" && state.mode !== "test") return;
  const module = activeModule();
  const scenario = state.scenario;
  const target = state.mode === "test" ? els.testScenario : els.trainingScenario;
  if (!module || !scenario) {
    target.innerHTML = `<div class="scenario-empty">当前模块暂未配置场景。</div>`;
    return;
  }
  const focusLabel = state.mode === "test" ? "考核重点" : "本轮练习重点";
  target.innerHTML = `
    <div class="scenario-main">
      <div class="scenario-title-row"><div><span>${state.mode === "test" ? "考核场景" : "陪练场景"}</span><h3>${escapeHtml(scenario.goal || module.title)}</h3></div><button class="change-scenario" data-random-scenario>换一个场景 ↗</button></div>
      <div class="persona-tags"><span>${escapeHtml(scenario.age)} 岁</span><span>${escapeHtml(scenario.gender)}</span><span>${escapeHtml(scenario.occupation || "顾客")}</span><span>${escapeHtml(scenario.style || "自然沟通")}</span></div>
      <div class="scenario-opening"><span>顾客开场</span><p>“${escapeHtml(scenario.opening)}”</p></div>
    </div>
    <div class="scenario-focus"><span>${focusLabel}</span><ul>${module.objectives.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>`;
  target.querySelector("[data-random-scenario]")?.addEventListener("click", randomScenario);
}

function changePracticeModule(moduleId) {
  if (state.mode === "test") state.testModuleId = moduleId;
  else state.practiceModuleId = moduleId;
  state.scenarioIndex = 0;
  selectScenario();
  renderScenarioFrame();
  resetSession();
}

function randomScenario() {
  const choices = moduleScenarios();
  if (!choices.length) return;
  state.scenarioIndex = (state.scenarioIndex + 1) % choices.length;
  selectScenario();
  renderScenarioFrame();
  resetSession();
}

function resetSession() {
  if (state.mode === "learning") return;
  state.history = [];
  state.ended = false;
  els.input.disabled = false;
  els.send.disabled = false;
  els.finish.disabled = true;
  els.finish.textContent = "结束并查看报告";
  els.turnCount.textContent = "0 轮对话";
  if (state.mode === "qa") {
    els.messages.innerHTML = `<div class="empty-state"><div class="empty-symbol">问</div><h3>请像顾客一样开始提问</h3><p>AI 会依据企业知识库进行回答，并在回答后提供可继续学习的参考课程。</p></div>`;
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
  const label = level === "good" ? "这一轮做得好" : level === "critical" ? "需要立即纠正" : "这一轮可以更好";
  const methodology = coach.method_step || coach.knowledge_focus ? `<div class="coach-method"><div><span>本轮方法节点</span><strong>${escapeHtml(coach.method_step || "按接待流程继续")}</strong></div><div><span>调用知识重点</span><strong>${escapeHtml(coach.knowledge_focus || "围绕顾客当前问题回答")}</strong></div></div>` : "";
  return `<div class="coach-card ${level}"><div class="coach-title">${label}</div>${methodology}<p><b>问题：</b>${escapeHtml(coach.issue || "")}</p><p><b>判断：</b>${escapeHtml(coach.why || "")}</p><div class="coach-suggestion"><span>推荐下一句</span>${escapeHtml(coach.suggested_reply || "")}</div><div class="coach-next">下一步：${escapeHtml(coach.next_goal || "继续完成需求分析")}</div></div>`;
}

function addTyping() {
  const row = document.createElement("div");
  row.className = "message-row typing-row";
  row.innerHTML = `<div class="avatar">${state.mode === "qa" ? "AI" : "客"}</div><div class="bubble-wrap"><div class="speaker">AI 正在思考</div><div class="bubble typing"><i></i><i></i><i></i></div></div>`;
  els.messages.appendChild(row);
  els.messages.scrollTop = els.messages.scrollHeight;
  return row;
}

function requestHistory() {
  if (state.mode === "qa") return [...state.history];
  const module = activeModule();
  return [{ role: "system", content: `本轮模块：${module?.title || "综合接待"}。目标：${(module?.objectives || []).join("；")}` }, ...state.history];
}

async function sendMessage() {
  const message = els.input.value.trim();
  if (!message || state.busy || state.ended) return;
  state.busy = true;
  els.send.disabled = true;
  els.input.value = "";
  const priorHistory = requestHistory();
  addMessage("user", message, state.mode === "qa" ? "你（顾客）" : "员工");
  state.history.push({ role: "user", content: message });
  const typing = addTyping();
  try {
    const data = await api("/api/chat", {
      mode: state.mode,
      action: "turn",
      message,
      history: priorHistory,
      scenario_id: state.scenario?.id,
      api_key: state.apiKey,
      model: state.model,
    });
    typing.remove();
    updateApiStatus(data.meta);
    if (state.mode === "training") {
      const result = data.result;
      addMessage("assistant", result.customer_reply || "顾客暂时没有继续说。", "AI 顾客", result.feedback);
      state.history.push({ role: "assistant", content: result.customer_reply || "" });
    } else if (state.mode === "test") {
      const result = data.result;
      addMessage("assistant", result.reply || "顾客暂时没有继续说。", "AI 顾客");
      state.history.push({ role: "assistant", content: result.reply || "" });
    } else {
      renderQAAnswer(data.result, data.retrieved || [], data.citations || []);
      state.history.push({ role: "assistant", content: data.result.answer || "" });
    }
    const turns = state.history.filter((item) => item.role === "user").length;
    els.turnCount.textContent = `${turns} 轮对话`;
    if (state.mode !== "qa") els.finish.disabled = turns < 1;
  } catch (error) {
    typing.remove();
    showToast(error.message, true);
  } finally {
    state.busy = false;
    if (!state.ended) els.send.disabled = false;
    els.input.focus();
  }
}

function renderQAAnswer(result, retrieved, citations) {
  const row = addMessage("assistant", result.answer || "暂时没有找到足够依据。", "AI 接待助手");
  const route = result.route || {};
  const supportingModules = Array.isArray(route.supporting_modules) ? route.supporting_modules : [];
  const routeModules = [route.primary_module, ...supportingModules].filter(Boolean);
  if (route.intent || routeModules.length) {
    row.querySelector(".bubble-wrap").insertAdjacentHTML("beforeend", `<div class="answer-method"><div class="answer-method-head"><span>本轮问题定位</span><strong>${escapeHtml(route.intent || "一般需求咨询")}</strong></div><div class="answer-method-route"><span>主要调用</span><p>${escapeHtml(routeModules.join(" · ") || "新客接待与需求洞察")}</p></div>${route.method_step ? `<div class="answer-method-step"><span>回答顺序</span><p>${escapeHtml(route.method_step)}</p></div>` : ""}</div>`);
  }
  if (result.recommended_action) {
    row.querySelector(".bubble-wrap").insertAdjacentHTML("beforeend", `<div class="answer-next-action"><span>建议下一步</span><p>${escapeHtml(result.recommended_action)}</p></div>`);
  }
  const references = retrieved.length ? retrieved : citations.map((item) => ({ title: item.label, module: item.module, chapter: item.chapter }));
  const unique = references.filter((item, index, all) => item.title && all.findIndex((candidate) => candidate.title === item.title) === index).slice(0, 5);
  const referenceHtml = unique.length ? unique.map((item) => `
    <button class="answer-reference" data-course-title="${escapeHtml(item.title)}">
      <span>${escapeHtml(item.module || "知识模块")}${item.chapter ? ` · ${escapeHtml(item.chapter)}` : ""}</span>
      <strong>${escapeHtml(item.title)}</strong><i>查看课程 →</i>
    </button>`).join("") : `<div class="reference-empty">本轮主要依据安全与接待通用规则。</div>`;
  row.querySelector(".bubble-wrap").insertAdjacentHTML("beforeend", `<div class="answer-basis"><div class="answer-basis-title"><span>本轮回答依据</span><small>点击继续学习</small></div><div class="answer-reference-list">${referenceHtml}</div></div>`);
  bindCourseButtons(row);
}

async function finishSession() {
  const userTurns = state.history.filter((item) => item.role === "user").length;
  if (state.mode === "qa" || state.busy || state.ended || userTurns < 1) return;
  state.busy = true;
  els.finish.disabled = true;
  els.finish.textContent = "正在生成报告…";
  const typing = addTyping();
  try {
    const data = await api("/api/chat", {
      mode: "test",
      action: "finish",
      history: requestHistory(),
      scenario_id: state.scenario?.id,
      api_key: state.apiKey,
      model: state.model,
    });
    typing.remove();
    renderAssessment(data.result);
    updateApiStatus(data.meta);
    state.ended = true;
    els.input.disabled = true;
    els.send.disabled = true;
    els.finish.textContent = "报告已生成";
  } catch (error) {
    typing.remove();
    els.finish.disabled = false;
    els.finish.textContent = "结束并查看报告";
    showToast(error.message, true);
  } finally {
    state.busy = false;
  }
}

function renderAssessment(result) {
  const card = document.createElement("div");
  card.className = "assessment-card";
  const dimensions = (result.dimension_scores || []).map((item) => `<div class="score-row"><div class="score-row-head"><span>${escapeHtml(item.name)}</span><strong>${escapeHtml(item.score)}<i>/${escapeHtml(item.max_score)}</i></strong></div><small><b>对话证据</b>${escapeHtml(item.evidence || "对话中未体现")}<br><b>评分判断</b>${escapeHtml(item.comment || "")}</small></div>`).join("");
  const critical = (result.critical_failures || []).map((item) => `<div><b>${escapeHtml(item.code)}</b> ${escapeHtml(item.reason)}${item.evidence ? `<br><small>${escapeHtml(item.evidence)}</small>` : ""}</div>`).join("");
  card.innerHTML = `<div class="assessment-header"><div><span>${state.mode === "training" ? "陪练结束报告" : "实战考核报告"}</span><p>${escapeHtml(result.summary || "本轮已完成评分。")}</p></div><strong>${escapeHtml(result.total_score ?? 0)}<i>/100</i></strong></div><div class="score-rows">${dimensions}</div>${critical ? `<div class="critical-block"><b>关键失败项</b><br>${critical}</div>` : ""}<div class="report-columns"><div class="report-block"><label>做得好的地方</label><p>${escapeHtml((result.strengths || []).join("；") || "继续保持完整沟通。")}</p></div><div class="report-block improve"><label>下一轮重点改进</label><p>${escapeHtml((result.improvements || []).join("；") || "继续练习需求分析和异议处理。")}</p></div></div>`;
  els.messages.appendChild(card);
  els.messages.scrollTop = els.messages.scrollHeight;
}

function updateApiStatus(meta = {}, health = null) {
  const connected = meta.mock === false || Boolean(state.apiKey) || Boolean(health?.api_configured);
  els.apiStatus.textContent = connected ? "SiliconFlow 已连接" : "演示模式";
}

function openModal(id) {
  $(id).classList.remove("hidden");
  document.body.classList.add("modal-open");
}

function closeModal(id) {
  $(id).classList.add("hidden");
  if (!document.querySelector(".modal-backdrop:not(.hidden)")) document.body.classList.remove("modal-open");
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

function saveSettings() {
  state.apiKey = $("api-key").value.trim();
  state.model = $("model-name").value.trim() || DEFAULT_MODEL;
  localStorage.setItem("kbai_api_key", state.apiKey);
  localStorage.setItem("kbai_model", state.model);
  updateApiStatus({ mock: !state.apiKey });
  closeModal("settings-modal");
  showToast(state.apiKey ? "模型设置已保存。" : "已切换为本地演示模式。");
}

function switchMode(mode, updateHistory = true) {
  if (!VALID_MODES.has(mode)) return;
  state.mode = mode;
  state.scenarioIndex = 0;
  if (updateHistory && window.location.hash !== `#${mode}`) {
    window.history.pushState(null, "", `#${mode}`);
  }
  renderMode();
  if (mode === "training" || mode === "test") {
    selectScenario();
    renderScenarioFrame();
    resetSession();
  } else if (mode === "qa") {
    resetSession();
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function boot() {
  try {
    const [bootstrap, moduleData, catalogData, health] = await Promise.all([
      api("/api/bootstrap"),
      fetch(staticAsset("learning_modules.json")).then((response) => response.json()),
      fetch(staticAsset("learning_catalog.json")).then((response) => response.json()),
      api("/api/health"),
    ]);
    state.scenarios = bootstrap.scenarios || [];
    state.modules = moduleData.modules || [];
    state.courses = catalogData.courses || [];
    state.catalogIndex = catalogData.module_index || [];
    state.knowledge = bootstrap.knowledge || {};
    state.models = bootstrap.models?.length ? bootstrap.models : AVAILABLE_MODELS;
    renderModelOptions();
    const firstModuleId = state.modules[0]?.id || null;
    state.learningModuleId = firstModuleId;
    state.practiceModuleId = firstModuleId;
    state.testModuleId = firstModuleId;
    const requestedMode = window.location.hash.slice(1);
    state.mode = VALID_MODES.has(requestedMode) ? requestedMode : "learning";
    if (window.location.hash !== `#${state.mode}`) {
      window.history.replaceState(null, "", `#${state.mode}`);
    }
    els.healthNumber.textContent = state.knowledge.rag_documents || 175;
    renderModuleOptions();
    renderLearning();
    renderMode();
    if (state.mode === "training" || state.mode === "test") {
      selectScenario();
      renderScenarioFrame();
      resetSession();
    } else if (state.mode === "qa") {
      resetSession();
    }
    updateApiStatus({}, health);
  } catch (error) {
    showToast(`本地服务初始化失败：${error.message}`, true);
  }
}

els.modeButtons.forEach((button) => button.addEventListener("click", () => switchMode(button.dataset.mode)));
window.addEventListener("popstate", () => {
  const requestedMode = window.location.hash.slice(1);
  switchMode(VALID_MODES.has(requestedMode) ? requestedMode : "learning", false);
});
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
  if (event.key === "Escape") document.querySelectorAll(".modal-backdrop:not(.hidden)").forEach((modal) => closeModal(modal.id));
});
document.querySelectorAll("[data-question]").forEach((button) => button.addEventListener("click", () => {
  els.input.value = button.dataset.question;
  els.conversationStage.scrollIntoView({ behavior: "smooth", block: "start" });
  els.input.focus();
}));

boot();
