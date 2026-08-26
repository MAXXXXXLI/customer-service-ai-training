"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { execFileSync } = require("node:child_process");

const appPath = path.join(__dirname, "static", "app.js");
const source = fs.readFileSync(appPath, "utf8");
const boundary = source.indexOf('\ndocument.addEventListener("click"');
if (boundary < 0) throw new Error("无法定位 app.js 启动边界");

const element = () => ({
  classList: { add() {}, remove() {}, toggle() {} },
  dataset: {},
  style: {},
  value: "",
  textContent: "",
  innerHTML: "",
});
const context = {
  console,
  localStorage: { getItem() { return ""; }, setItem() {}, removeItem() {} },
  document: {
    getElementById() { return element(); },
    querySelectorAll() { return []; },
    querySelector() { return null; },
  },
  window: { location: { hostname: "localhost", hash: "" } },
  location: { hostname: "localhost", hash: "" },
  setTimeout,
  clearTimeout,
};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(
  `${source.slice(0, boundary)}\n;globalThis.__safetyTestExports = {`
    + "staticAffirmedCustomerText, staticCriticalHits, staticTrainingMessageHasUnsafeContradiction, "
    + "staticTrainingMessageHasSafeDirection, staticTrainingMessageHasCompleteSafeClosure, "
    + "staticTrainingSafetyDecision, staticAssessmentFailureMatches, staticAssessmentAdviceNeedsSanitizing, "
    + "sanitizeStaticAssessmentAdvice, staticEvidenceIsGroundedInEmployee, normalizeStaticAssessment, normalizeStaticQaResult, "
    + "POINT_WAVE_BEST_REPLY, staticPointWaveBestCommonQa, normalizeStaticCustomerReply};",
  context,
  { filename: appPath },
);

const helpers = context.__safetyTestExports;
const redFlagHistory = [{ role: "assistant", content: "我现在胸痛，手臂也开始发麻。" }];
const failuresFor = (message) => helpers
  .staticAssessmentFailureMatches([...redFlagHistory, { role: "user", content: message }])
  .map((item) => item.code);

const negated = helpers.staticAffirmedCustomerText("我没手麻，也没胸痛，只想问价格。");
if (/手麻|胸痛/.test(negated)) throw new Error(`口语否定症状未清除：${negated}`);
const mixed = helpers.staticAffirmedCustomerText("我没有胸痛但手麻越来越重。");
if (/胸痛/.test(mixed) || !/手麻/.test(mixed)) throw new Error(`分句症状归因错误：${mixed}`);
for (const message of ["没有手臂发麻", "没有任何胸痛", "无胸痛"]) {
  const affirmed = helpers.staticAffirmedCustomerText(message);
  if (/手(?:臂)?(?:发)?麻|胸痛/.test(affirmed)) throw new Error(`症状否定未清除：${message} => ${affirmed}`);
}
if (!/无力/.test(helpers.staticAffirmedCustomerText("无力越来越明显"))) throw new Error("肯定的无力被否定规则误清除");

const canonicalReleaseHistory = [{ role: "assistant", content: "昨晚开始疼，今天更重。手臂新麻了。" }];
const canonicalPartial = helpers.staticTrainingSafetyDecision(
  {}, canonicalReleaseHistory, "这个需要重视，建议您就医检查。",
);
if (canonicalPartial?.level !== "needs_work") {
  throw new Error(`规范化释放短句“手臂新麻了”未进入安全状态：${JSON.stringify(canonicalPartial)}`);
}

const pointWaveScenario = {
  id: "SCN-CEX-M03-S01",
  module_id: "MOD-03",
  title: "点阵波打完更痛",
  task: "使用点阵波模块批准的服务后反应最佳回答",
  opening: "我昨天做完点阵波，今天比原来更痛。你们是不是把我打坏了？",
};
const pointWaveApproved = helpers.staticTrainingSafetyDecision(
  pointWaveScenario,
  [{ role: "assistant", content: pointWaveScenario.opening }],
  helpers.POINT_WAVE_BEST_REPLY,
);
if (pointWaveApproved?.level !== "good" || pointWaveApproved.suggested_reply !== helpers.POINT_WAVE_BEST_REPLY) {
  throw new Error(`点阵波固定最佳回答未通过：${JSON.stringify(pointWaveApproved)}`);
}
const pointWaveAfterRedFlag = helpers.staticTrainingSafetyDecision(
  pointWaveScenario,
  [...canonicalReleaseHistory],
  helpers.POINT_WAVE_BEST_REPLY,
);
if (pointWaveAfterRedFlag?.level !== "critical") {
  throw new Error(`红旗公开后不应继续套用点阵波固定话术：${JSON.stringify(pointWaveAfterRedFlag)}`);
}
const forcedPointWaveFaq = helpers.staticPointWaveBestCommonQa(
  "点振波理疗后更酸痛是不是正常",
  [{ id: "FAQ-XLS-0002", approved_answer: helpers.POINT_WAVE_BEST_REPLY }],
);
if (forcedPointWaveFaq?.selection !== "point_wave_best_answer" || forcedPointWaveFaq.answer !== helpers.POINT_WAVE_BEST_REPLY) {
  throw new Error(`点阵波相似问法未固定命中：${JSON.stringify(forcedPointWaveFaq)}`);
}

const pointWaveInSessionScenario = {
  id: "SCN-CEX-M03-S02",
  module_id: "MOD-03",
  opening: "这个太痛了，但你们说痛就是不通，我是不是必须忍几分钟？",
  information_release_rules: [
    "员工问疼痛程度时，回答8分。",
    "员工问感觉时，说明“像电到一样”。",
    "员工谈钱时，顾客说“我怕浪费”。",
  ],
};
const pointWaveOpening = [{ role: "assistant", content: pointWaveInSessionScenario.opening }];
const loweredReply = helpers.normalizeStaticCustomerReply(
  "无关回复",
  pointWaveInSessionScenario,
  pointWaveOpening,
  "辛苦您忍几分钟，如果实在很痛，我可以把力度调低一些。",
);
if (loweredReply !== "好的那把能量调低一些") throw new Error(`静态站降能量回复错误：${loweredReply}`);
const enduredReply = helpers.normalizeStaticCustomerReply(
  "无关回复",
  pointWaveInSessionScenario,
  pointWaveOpening,
  "辛苦您再忍一会儿试试。",
);
if (enduredReply !== "好的那我再忍一会儿试试") throw new Error(`静态站忍耐回复错误：${enduredReply}`);

for (const message of [
  "您是不是还想继续做？",
  "我不会把它当成正常现象，也不会继续做。",
  "我不认为这是正常现象，今天先暂停。",
  "继续做的话会不会让情况变得更加严重呢？",
  "我不把这说成正常反应，今天先暂停。",
  "这不算正常反应，今天先暂停。",
  "不是让您继续做，我们今天先暂停。",
  "难道这是正常反应？今天先暂停。",
  "难道还能继续做？我们今天先暂停。",
  "是否正常还不能判断，今天先暂停。",
  "不一定可以做，先暂停。",
  "绝不意味着可以继续做。",
]) {
  const failures = failuresFor(message);
  if (failures.includes("CF-01") || failures.includes("CF-04")) {
    throw new Error(`疑问或否定被当作继续服务：${message} => ${failures.join(",")}`);
  }
  if (helpers.staticTrainingSafetyDecision({}, redFlagHistory, message)?.level === "critical") {
    throw new Error(`疑问或安全否定被训练判为 critical：${message}`);
  }
}

for (const message of [
  "我们提供的不是医疗治疗，不会治疗疾病。",
  "具体剂量必须由医生决定，门店不能建议。",
]) {
  if (helpers.staticCriticalHits(message).length) throw new Error(`安全医疗边界被误拦截：${message}`);
  if (failuresFor(message).includes("CF-02")) throw new Error(`安全医疗边界误触发 CF-02：${message}`);
}

for (const message of [
  "不用停，接着做完",
  "不用停，照常操作",
  "今天还是把项目做完吧",
  "没必要暂停，做完再说",
  "明天还可以做",
  "如果缓解，明天可以做",
  "没问题",
  "没啥问题",
  "没什么问题",
  "不要紧",
  "不碍事",
  "不能判断原因但明天还可以做",
]) {
  const failures = failuresFor(message);
  if (!failures.includes("CF-01") || !failures.includes("CF-04")) throw new Error(`危险肯定句未触发考核失败：${message} => ${failures.join(",")}`);
  if (helpers.staticTrainingSafetyDecision({}, redFlagHistory, message)?.level !== "critical") throw new Error(`危险肯定句未被训练判为 critical：${message}`);
}

for (const message of [
  "这个项目可以治疗糖尿病。",
  "这个项目可以治疗 糖尿病。",
  "这种情况可能涉及神经损伤。",
  "门店不能判断原因但这个项目可以治疗疾病。",
]) {
  if (!helpers.staticCriticalHits(message).length) throw new Error(`医疗化表达未拦截：${message}`);
  if (!failuresFor(message).includes("CF-02")) throw new Error(`医疗化表达未触发 CF-02：${message}`);
}
for (const message of ["这个项目不可以治疗糖尿病。", "这种情况是否可能涉及神经损伤？"]) {
  if (helpers.staticCriticalHits(message).length) throw new Error(`安全否定或疑问被误拦截：${message}`);
}

const contradictoryFailures = failuresFor("今天先暂停；如果缓解，明天可以继续做。");
if (!contradictoryFailures.includes("CF-01") || !contradictoryFailures.includes("CF-04")) {
  throw new Error(`危险矛盾未保留关键失败：${contradictoryFailures.join(",")}`);
}

for (const message of [
  "我不会记录也不会上报负责人，但建议就医。",
  "不用暂停，别记录或上报，更不建议就医。",
]) {
  if (helpers.staticTrainingMessageHasCompleteSafeClosure(message)) throw new Error(`否定动作被当作完整闭环：${message}`);
  const decision = helpers.staticTrainingSafetyDecision({}, redFlagHistory, message);
  if (decision?.level !== "critical") throw new Error(`明确拒绝安全动作未判 critical：${message}`);
}

const complete = "今天先暂停所有项目，我们不在店内判断原因。我会记录并上报负责人，建议尽快就医。";
if (!helpers.staticTrainingMessageHasCompleteSafeClosure(complete)) throw new Error("完整安全闭环未识别");
if (helpers.staticTrainingSafetyDecision({}, redFlagHistory, complete)?.level !== "good") throw new Error("完整安全闭环未判 good");

const plain = (value) => JSON.parse(JSON.stringify(value));
const unsafeAssessment = {
  total_score: 65,
  dimension_scores: [
    { id: "D1", name: "接待", score: 8, max_score: 10, evidence: "员工原话：建议口服两片。", comment: "建议每天口服2次，每次10mg。" },
    { id: "D2", name: "边界", score: 9, max_score: 10, evidence: "员工原话：交由医生评估。", comment: "具体剂量交由医生评估，门店不建议给剂量。" },
  ],
  critical_failures: [
    { code: "CF-02", reason: "可以先停药，明天换药。", evidence: "员工原话：可以先停药。", score_cap: 59 },
  ],
  strengths: ["主动建议改为注射。", "已说明停换药应由开药医生决定。"],
  improvements: ["建议先停药，明天更换药物。", "用药需遵医嘱，门店不提供用药安排。"],
  next_training_scene: "SCN-TEST",
  summary: "可以把注射剂量调整为10mg。",
};

const pythonSanitizer = [
  "import json, sys",
  "import server",
  "payload = json.load(sys.stdin)",
  "json.dump(server.sanitize_assessment_advice(payload), sys.stdout, ensure_ascii=False)",
].join("\n");
const pythonCommand = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
const serverSanitized = JSON.parse(execFileSync(pythonCommand, ["-X", "utf8", "-c", pythonSanitizer], {
  cwd: __dirname,
  input: JSON.stringify(unsafeAssessment),
  encoding: "utf8",
}));
const staticSanitized = plain(helpers.sanitizeStaticAssessmentAdvice(plain(unsafeAssessment)));
if (JSON.stringify(staticSanitized) !== JSON.stringify(serverSanitized)) {
  throw new Error(`前后端结业报告清洗结果不一致\nstatic=${JSON.stringify(staticSanitized)}\nserver=${JSON.stringify(serverSanitized)}`);
}

const sanitizedAdviceView = JSON.stringify({
  comments: staticSanitized.dimension_scores.map((item) => item.comment),
  reasons: staticSanitized.critical_failures.map((item) => item.reason),
  strengths: staticSanitized.strengths,
  improvements: staticSanitized.improvements,
  summary: staticSanitized.summary,
});
if (/10mg|每天口服|先停药|改为注射/.test(sanitizedAdviceView)) {
  throw new Error(`具体医疗安排仍出现在静态报告：${JSON.stringify(staticSanitized)}`);
}
for (const safeText of [
  "具体剂量交由医生评估，门店不建议给剂量。",
  "停换药应由开药医生决定。",
  "用药需遵医嘱，门店不提供用药安排。",
]) {
  if (!JSON.stringify(staticSanitized).includes(safeText)) throw new Error(`安全边界表达被误删：${safeText}`);
  if (helpers.staticAssessmentAdviceNeedsSanitizing(safeText)) throw new Error(`安全边界表达被误判：${safeText}`);
}
for (const mixedText of [
  "门店不能给剂量，但可以先停药。",
  "具体剂量交由医生评估，但建议改为注射。",
]) {
  if (!helpers.staticAssessmentAdviceNeedsSanitizing(mixedText)) throw new Error(`安全前缀掩盖了后续越界建议：${mixedText}`);
}

const normalizedAssessment = plain(helpers.normalizeStaticAssessment(
  {
    dimension_scores: [{ id: "D1", score: 8, evidence: "员工原话：我已经暂停并上报负责人。", comment: "建议注射三次。" }],
    critical_failures: [],
    strengths: ["完成沟通。"],
    improvements: ["可以把剂量改成5mg。"],
    summary: "建议隔天一次。",
  },
  [{ role: "user", content: "我先了解一下您的情况。" }],
  { dimensions: [{ id: "D1", name: "接待", weight: 10 }], critical_failures: [] },
));
if (/注射三次|5mg|隔天一次/.test(JSON.stringify(normalizedAssessment))) {
  throw new Error(`normalizeStaticAssessment 未执行报告清洗：${JSON.stringify(normalizedAssessment)}`);
}
if (!normalizedAssessment.dimension_scores[0].evidence.includes("我先了解一下您的情况")) {
  throw new Error(`虚构的员工证据未回退到真实原话：${JSON.stringify(normalizedAssessment)}`);
}

const contextualDiseaseAnswer = helpers.normalizeStaticQaResult(
  {},
  "这个项目可以治疗糖尿病吗？",
  "点阵波能替代手术吗？ 这个项目可以治疗糖尿病吗？",
  { stop_sales: true },
  [{ role: "user", content: "点阵波能替代手术吗？" }],
);
if (/您还提到明确疾病或麻木症状/.test(contextualDiseaseAnswer.answer || "")) {
  throw new Error(`跨轮 QA 不应凭空属性症状：${contextualDiseaseAnswer.answer}`);
}

console.log(JSON.stringify({
  status: "passed",
  checks: {
    symptom_negation_is_clause_aware: true,
    questions_and_negations_are_not_continuation: true,
    medical_claim_rules_match_server: true,
    contradictory_continuation_is_not_hidden_by_pause: true,
    denied_safety_actions_are_not_counted: true,
    complete_safety_closure_is_good: true,
    assessment_sanitizer_matches_server: true,
    safe_medical_boundaries_are_preserved: true,
    safe_prefix_cannot_hide_later_medical_advice: true,
    static_assessment_normalization_sanitizes_report: true,
  },
}));
