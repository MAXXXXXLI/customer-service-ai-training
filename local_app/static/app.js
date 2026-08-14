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
  model: localStorage.getItem("kbai_model") || "Qwen/Qwen3.5-35B-A3B",
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
    title: "先把知识学明白，再进入模拟练习",
    description: "选择一个知识模块，只查看该模块的章节和详细课程内容。",
    kicker: "",
    conversation: "",
    hint: "",
  },
  training: {
    nav: "学习与陪练 / 情景陪练",
    title: "在真实顾客情景中，把标准练成自然表达",
    description: "选择知识模块和顾客情景，在每轮回答后获得即时纠正与推荐话术。",
    kicker: "情景陪练",
    conversation: "与 AI 顾客练习",
    hint: "每轮回答后提供一个关键改进点",
  },
  test: {
    nav: "实战考核",
    title: "用一段完整对话，检验真实接待能力",
    description: "选择模块、确认考核场景，然后在无提示状态下完成整段顾客沟通。",
    kicker: "实战考核",
    conversation: "无提示顾客对话",
    hint: "考核过程中不会出现任何提示",
  },
  qa: {
    nav: "智能接待",
    title: "让 AI 成为随时在线的顾客接待助手",
    description: "你扮演顾客直接提问，AI 调用完整企业知识库进行回答和接待。",
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

async function callStaticModel(system, user, model, apiKey, temperature) {
  const response = await fetch("https://api.siliconflow.cn/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${apiKey}` },
    body: JSON.stringify({
      model, messages: [{ role: "system", content: system }, { role: "user", content: user }],
      temperature, top_p: 0.7, max_tokens: 1600, enable_thinking: false, stream: false,
    }),
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
      scenario?.opening || "我最近有点困扰，想先了解一下你们的项目。",
      "我最担心的是做了没效果，而且价格也不能太高。你会怎么建议？",
      "如果需要先做适用性确认我可以配合，但我想知道下一步怎么安排。",
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

function normalizeStaticResult(result, mode, action, scenario, history, rubric, message) {
  let normalized = result && typeof result === "object" ? result : {};
  if (mode === "training") {
    const fallback = staticMockProgressive(mode, action, scenario, history, rubric, message);
    normalized.customer_reply = normalized.customer_reply || fallback.customer_reply;
    normalized.feedback = { ...fallback.feedback, ...(normalized.feedback || {}) };
    if (staticCriticalHits(message).length) normalized.feedback.level = "critical";
  }
  if (mode === "test" && action === "turn") {
    const fallback = staticMockProgressive(mode, action, scenario, history, rubric, message);
    normalized.reply = normalized.reply || fallback.reply;
    normalized.emotion = normalized.emotion || fallback.emotion;
    normalized.should_continue = normalized.should_continue !== false;
  }
  if (mode === "test" && action === "finish" && !Array.isArray(normalized.dimension_scores)) {
    normalized = { ...staticMockProgressive(mode, action, scenario, history, rubric, message), ...normalized };
  }
  if (mode === "test" && action === "finish" && !normalized.dimension_scores.length) {
    normalized = { ...normalized, dimension_scores: staticMockProgressive(mode, action, scenario, history, rubric, message).dimension_scores };
  }
  return normalized;
}

async function staticApi(path, body) {
  const data = await loadStaticData();
  if (path === "/api/bootstrap") {
    return { ok: true, scenarios: data.scenarios, knowledge: { rag_documents: data.documents.length, scenarios: data.scenarios.length }, rubric: { total: data.rubric.total, dimensions: data.rubric.dimensions || [] } };
  }
  if (path === "/api/health") return { ok: true, api_configured: Boolean(state.apiKey), mock_mode: !state.apiKey, model: state.model, knowledge: { rag_documents: data.documents.length } };
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

  let system = "你是顾客服务培训平台的 AI。只基于给定知识库回答，不诊断疾病、不承诺疗效、不推荐处方药；遇到胸痛、呼吸困难、晕厥等红旗症状时先建议停止项目并寻求医疗评估。请严格返回 JSON，不要 Markdown。";
  if (mode === "training") system += " 你扮演顾客，并同时评价员工回复。返回 customer_reply 和 feedback（level、issue、why、suggested_reply、next_goal、method_step、knowledge_focus）。";
  else if (mode === "test" && action === "turn") system += " 你扮演顾客。返回 reply、emotion、should_continue。不要泄露场景设定。";
  else if (mode === "test" && action === "finish") system += " 你是考核评分员。根据对话和评分表返回 total_score、dimension_scores、critical_failures、strengths、improvements、summary。";
  else system += " 返回 answer、uncertainties、recommended_action。";
  const user = `场景：${JSON.stringify(scenario)}\n历史对话：${JSON.stringify(body.history || [])}\n员工/顾客最新消息：${message}\n评分表：${JSON.stringify(data.rubric)}\n相关知识库：\n${context}`;
  const modelResult = await callStaticModel(system, user, model, apiKey, mode === "test" ? 0.6 : 0.3);
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
  const dimensions = (result.dimension_scores || []).map((item) => `<div class="score-row"><span>${escapeHtml(item.name)}</span><strong>${escapeHtml(item.score)}<i>/${escapeHtml(item.max_score)}</i></strong></div>`).join("");
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

function saveSettings() {
  state.apiKey = $("api-key").value.trim();
  state.model = $("model-name").value.trim() || "Qwen/Qwen3.5-35B-A3B";
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
$("open-settings").addEventListener("click", () => {
  $("api-key").value = state.apiKey;
  $("model-name").value = state.model;
  openModal("settings-modal");
});
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
