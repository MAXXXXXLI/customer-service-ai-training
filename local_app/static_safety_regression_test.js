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
    + "staticTrainingSafetyDecision, staticAssessmentFailureMatches, staticAssessmentRedFlagWithoutCompleteSafeClosure, staticAssessmentAdviceNeedsSanitizing, "
    + "sanitizeStaticAssessmentAdvice, staticEvidenceIsGroundedInEmployee, normalizeStaticAssessment, normalizeStaticQaResult, "
    + "POINT_WAVE_BEST_REPLY, POINT_WAVE_IN_SESSION_PAUSE_REPLY, POINT_WAVE_POST_SERVICE_PAIN_REPLY, staticPointWaveBestCommonQa, normalizeStaticCustomerReply, "
    + "isStaticPointWaveAftercareQuery, isStaticPointWaveAftercareResolved, staticPointWaveAftercareKind, "
    + "staticAffirmedSafetyText, staticRouteCustomerQuestion, staticQaQuery, staticCurrentPointWaveAftercareResolved, "
    + "staticQaNeedsDeterministicSafety, staticTrainingFeedbackUsesCustomerOnlyText, staticTrainingSuggestedReplyNeedsRepair, staticTrainingSuggestedReplyIsRelevant, "
    + "normalizeStaticTrainingFeedback, staticPublicRecommendedAction, staticFaqAnswerNeedsCustomerVoiceRepair, staticFaqCustomerVoiceFallback, staticApi, "
    + "mergePointWaveFaqExam, examQuestions, keywordAnswerScore};"
    + "globalThis.__setSafetyData=(data)=>{staticDataPromise=Promise.resolve(data);};"
    + "globalThis.__failSafetyModel=()=>{callStaticModel=async()=>{throw new Error('simulated outage');};};",
  context,
  { filename: appPath },
);

const helpers = context.__safetyTestExports;
const methodology = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "knowledge_base", "customer_service_methodology.json"), "utf8"));
const scenarios = fs.readFileSync(path.join(__dirname, "..", "knowledge_base", "scenario_library.jsonl"), "utf8").trim().split(/\n+/).map((line) => JSON.parse(line));
const rubric = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "knowledge_base", "scoring_rubric.json"), "utf8"));

const rawFaqSource = "这个问题涉及点阵波服务后的观察和升级，应按当前课程与流程处理。";
const faqFallback = helpers.staticFaqCustomerVoiceFallback({ row: { question: "点阵波后更痛怎么办？" } });
if (!helpers.staticFaqAnswerNeedsCustomerVoiceRepair(rawFaqSource)
  || helpers.staticFaqAnswerNeedsCustomerVoiceRepair(faqFallback)
  || !faqFallback.includes("我先") || !faqFallback.includes("您")) {
  throw new Error(`FAQ 原文未被隔离为员工对客话术：${faqFallback}`);
}

const keywordFixture = {
  id: "FAQ-M03-TEST",
  points: 8,
  minimum_groups: 2,
  keyword_groups: [
    { id: "position", label: "项目定位", terms: ["物理刺激", "门店体验"] },
    { id: "boundary", label: "不判断原因", terms: ["不判断原因", "不能诊断"] },
    { id: "pause", label: "暂停升级", terms: ["暂停", "停止"], required: true },
  ],
};
const keywordPassed = helpers.keywordAnswerScore(keywordFixture, "这是物理刺激类门店体验，出现加重时先停止，门店不能诊断。");
if (!keywordPassed.correct || keywordPassed.earned !== 8 || keywordPassed.matched_count !== 3) {
  throw new Error(`FAQ 关键词同义判定失败：${JSON.stringify(keywordPassed)}`);
}
const keywordMissingRequired = helpers.keywordAnswerScore(keywordFixture, "这是物理刺激类项目，门店不能判断原因。");
if (keywordMissingRequired.correct || keywordMissingRequired.earned >= 8) {
  throw new Error(`FAQ 关键词必选安全组未生效：${JSON.stringify(keywordMissingRequired)}`);
}

const pointWaveKeywordExam = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "knowledge_base", "point_wave_faq_exam.json"), "utf8"));
const naturalKeywordAnswers = {
  "FAQ-M03-K01": "点阵波是局部重复机械刺激的门店体验，可能有敲击、震动和酸胀感，不能代替医学诊断，也不能保证固定效果。",
  "FAQ-M03-K02": "立即暂停，不强迫继续，询问疼痛程度和性质、麻木无力等伴随症状，顾客可以随时停止，异常时通知负责人。",
  "FAQ-M03-K03": "不能把加重解释成有效，问清什么时候开始、程度和变化并记录，暂停服务并联系负责人，建议及时医疗评估。",
  "FAQ-M03-K04": "按工作方式、刺激范围、体验、风险和复测比较，按摩也有放松价值，医院冲击波属于医疗流程，不能凭参数推断效果。",
  "FAQ-M03-K05": "先确认两项都和目标相关，分别说明震动和热感并分别取得同意，可先试感，不能耐受就停止，用相同动作复测。",
  "FAQ-M03-K06": "问部位、时间、诱因和活动影响，有无麻木无力，不在门店诊断；突发剧痛或进行性麻木无力时优先医疗评估。",
  "FAQ-M03-K07": "不能现场试错，先确认诊断、手术和植入物，核验当前SOP并请有资质人员判断，异常时优先医疗评估，不能建议停药。",
  "FAQ-M03-K08": "先明确目标和记录基线，用同一动作复测；结果有个体差异，不能保证固定效果、次数和时间，疾病治疗目标交由医疗人员评估。",
};
for (const question of pointWaveKeywordExam.questions) {
  const score = helpers.keywordAnswerScore(question, naturalKeywordAnswers[question.id]);
  if (!score.correct || score.earned !== question.points) {
    throw new Error(`FAQ 自然近义回答未判正确：${question.id} => ${JSON.stringify(score)}`);
  }
}
for (const [questionId, unsafeAnswer] of Object.entries({
  "FAQ-M03-K02": "虽然不舒服但是必须坚持，疼痛越明显效果越好，继续做完。",
  "FAQ-M03-K03": "这是正常反应，回去等第二天就会消失，不用暂停也不用就医。",
  "FAQ-M03-K08": "肯定三次见效，保证固定时间就能治疗好。",
})) {
  const question = pointWaveKeywordExam.questions.find((item) => item.id === questionId);
  const score = helpers.keywordAnswerScore(question, unsafeAnswer);
  if (score.correct) throw new Error(`FAQ 危险反向回答被误判正确：${questionId} => ${JSON.stringify(score)}`);
}
const contradictoryKeywordAnswer = "虽然参考说要先暂停、不能强迫继续、顾客可以随时停止，但实际我们不暂停，必须继续做完。疼痛程度和麻木无力不用问，直接做完后再通知负责人。";
const contradictoryKeywordScore = helpers.keywordAnswerScore(
  pointWaveKeywordExam.questions.find((item) => item.id === "FAQ-M03-K02"),
  contradictoryKeywordAnswer,
);
if (contradictoryKeywordScore.correct || contradictoryKeywordScore.earned !== 0 || !contradictoryKeywordScore.safety_blocked) {
  throw new Error(`FAQ 安全关键词不能掩盖危险反向指令：${JSON.stringify(contradictoryKeywordScore)}`);
}
const redFlagHistory = [{ role: "assistant", content: "我现在胸痛，手臂也开始发麻。" }];
const discomfortHistory = [{ role: "assistant", content: "我做完项目后很疼，能不能先停？" }];
const failuresFor = (message) => helpers
  .staticAssessmentFailureMatches([...redFlagHistory, { role: "user", content: message }])
  .map((item) => item.code);

const delayedRedFlagReply = "我理解您很担心，先了解一下不舒服多久了；但为了安全，我不能判断原因。您先回家睡一觉，明天再说。";
if (!failuresFor(delayedRedFlagReply).includes("CF-01")) {
  throw new Error("胸痛/气短后推迟到明天未触发 CF-01");
}
if (helpers.staticTrainingSafetyDecision({}, redFlagHistory, delayedRedFlagReply)?.level !== "critical") {
  throw new Error("胸痛/气短后推迟到明天未判为培训 critical");
}
for (const unsafeRecovery of [
  "建议回家热敷。",
  "先冰敷观察48小时。",
  "建议先回去休息两天。",
  "先忍一忍，继续做完。",
]) {
  if (helpers.staticTrainingSafetyDecision({}, discomfortHistory, unsafeRecovery)?.level !== "critical") {
    throw new Error(`已知服务后不适的危险处置未判 training critical：${unsafeRecovery}`);
  }
  const failures = helpers.staticAssessmentFailureMatches([
    ...discomfortHistory,
    { role: "user", content: unsafeRecovery },
  ]).map((item) => item.code);
  if (!failures.includes("CF-04")) {
    throw new Error(`已知服务后不适的危险处置未判 assessment CF-04：${unsafeRecovery} => ${failures.join(",")}`);
  }
}
if (!helpers.staticCriticalHits("你这是颈椎病，先给你安排几个治疗项目。").length) {
  throw new Error("静态端直接疾病诊断未触发高风险拦截");
}
if (helpers.staticCriticalHits("您不是颈椎病，门店不能诊断。").length) {
  throw new Error("静态端疾病诊断边界被误拦截");
}

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
if (pointWaveAfterRedFlag?.level !== "needs_work") {
  throw new Error(`红旗公开后复述一般安全话术应判为需要改进，并直接承接已知异常：${JSON.stringify(pointWaveAfterRedFlag)}`);
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
if (loweredReply !== "我已经很痛了，能不能先停下来？") throw new Error(`静态站降能量必须先暂停：${loweredReply}`);
const enduredReply = helpers.normalizeStaticCustomerReply(
  "无关回复",
  pointWaveInSessionScenario,
  pointWaveOpening,
  "辛苦您再忍一会儿试试。",
);
if (enduredReply !== "我已经很痛了，能不能先停下来？") throw new Error(`静态站不能接受继续忍耐：${enduredReply}`);
const lowerOnlyDecision = helpers.staticTrainingSafetyDecision(
  pointWaveInSessionScenario,
  pointWaveOpening,
  "我先把能量调低一些。",
);
if (lowerOnlyDecision?.level !== "needs_work" || lowerOnlyDecision.suggested_reply !== helpers.POINT_WAVE_IN_SESSION_PAUSE_REPLY) {
  throw new Error(`明显疼痛时只降能量不能判通过：${JSON.stringify(lowerOnlyDecision)}`);
}
const lowerThenContinueDecision = helpers.staticTrainingSafetyDecision(
  pointWaveInSessionScenario,
  pointWaveOpening,
  "我把能量调低一些，您再继续感受一下。",
);
if (lowerThenContinueDecision?.level !== "critical" || lowerThenContinueDecision.suggested_reply !== helpers.POINT_WAVE_IN_SESSION_PAUSE_REPLY) {
  throw new Error(`降能量后继续感受未被安全拦截：${JSON.stringify(lowerThenContinueDecision)}`);
}
const feelingReply = helpers.normalizeStaticCustomerReply(
  "我现在主要还是想尽快处理，其他专业的我也不太懂。",
  pointWaveInSessionScenario,
  pointWaveOpening,
  "我先暂停一下。现在是酸胀、刺痛，还是像电到一样？",
);
if (feelingReply !== "像电到一样。") throw new Error(`静态站疼痛感觉回复错误：${feelingReply}`);
const companionReply = helpers.normalizeStaticCustomerReply(
  "我比较怕疼，过程中会不会很难受？",
  pointWaveInSessionScenario,
  pointWaveOpening,
  "收到，8分属于明显疼痛，我们今天不再继续操作。现在有没有麻木、无力、明显肿胀、发热，或者疼痛还在加重？",
);
if (!companionReply.includes("没有麻木") || !companionReply.includes("没有继续加重")) throw new Error(`静态站伴随情况回复错误：${companionReply}`);
const closureReply = helpers.normalizeStaticCustomerReply(
  "我现在主要还是想尽快处理，其他专业的我也不太懂。",
  pointWaveInSessionScenario,
  pointWaveOpening,
  "我们已经停止今天的操作。我会记录本次部位和反应，并请负责人马上复核；如果持续加重，建议尽快由医疗机构评估。",
);
if (!closureReply.includes("今天就先不做") || !closureReply.includes("负责人")) throw new Error(`静态站安全安排承接错误：${closureReply}`);

const notContinueFailures = helpers.staticAssessmentFailureMatches([
  { role: "assistant", content: "现在疼痛大概8分。" },
  { role: "user", content: "收到，我们今天不再继续操作，我先确认有没有麻木或无力。" },
]).map((item) => item.code);
if (notContinueFailures.includes("CF-04")) throw new Error(`“不再继续操作”被误判：${notContinueFailures.join(",")}`);

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

const ordinaryScenario = scenarios.find((item) => item.id === "SCN-CEX-M01-S01");
const ordinaryHistory = [{ role: "assistant", content: ordinaryScenario.opening }];
const weakEmployee = "好的，我知道了，那我们先做一次看看吧。";
const normalizedWeakRecommendation = plain(helpers.normalizeStaticTrainingFeedback(
  {
    feedback: {
      level: "good",
      issue: "回答很好。",
      why: "模型认为可以继续。",
      method_step: "安排项目",
      knowledge_focus: "项目安排",
      suggested_reply: weakEmployee,
      next_goal: "成交。",
    },
  },
  ordinaryScenario,
  ordinaryHistory,
  rubric,
  weakEmployee,
));
if (normalizedWeakRecommendation.suggested_reply === weakEmployee) {
  throw new Error(`静态模型不能用 good 自证并复用员工坏回答：${JSON.stringify(normalizedWeakRecommendation)}`);
}

for (const badReply of [
  "我先了解X问题，再给您推荐Y项目，后续安排Z次体验。",
  "您最在意价格吗？还是最在意效果？我们马上安排。",
  "设备能精准控制作用深度并促进局部循环，所以很适合您。",
  "您可以服用布洛芬缓解，今天先休息，明天再继续体验。",
  "建议话术：员工应该调用对应QA，再根据评分给出下一轮回复。",
]) {
  const feedback = plain(helpers.normalizeStaticTrainingFeedback(
    { feedback: { level: "needs_work", issue: "需改进。", why: "需回应顾虑。", suggested_reply: badReply } },
    ordinaryScenario,
    ordinaryHistory,
    rubric,
    weakEmployee,
  ));
  if (/X问题|Y项目|Z次|精准控制|促进局部循环|服用布洛芬|建议话术|调用对应QA/.test(feedback.suggested_reply)
    || feedback.suggested_reply === weakEmployee) {
    throw new Error(`静态推荐回答未修复：${badReply} => ${JSON.stringify(feedback)}`);
  }
}

const staticRouteMatrix = new Map([
  ["冰雕有什么副作用？", ["INTENT-SUITABILITY", "MOD-07"]],
  ["超V有什么副作用？", ["INTENT-SUITABILITY", "MOD-04"]],
  ["热玛吉有什么副作用？", ["INTENT-SUITABILITY", "MOD-09"]],
  ["点阵波有什么副作用？", ["INTENT-SUITABILITY", "MOD-03"]],
  ["纳米喷射有什么副作用？", ["INTENT-SUITABILITY", "MOD-08"]],
  ["磁波内雕有什么副作用？", ["INTENT-SUITABILITY", "MOD-08"]],
  ["智能提拉有什么副作用？", ["INTENT-SUITABILITY", "MOD-08"]],
  ["头皮养护有什么副作用？", ["INTENT-SUITABILITY", "MOD-08"]],
  ["超声炮有什么副作用？", ["INTENT-SUITABILITY", "MOD-09"]],
  ["司美格鲁肽有什么副作用？", ["INTENT-DRUG", "MOD-06"]],
]);
for (const [question, expected] of staticRouteMatrix) {
  const route = helpers.staticRouteCustomerQuestion(question, methodology);
  if (route.intent_id !== expected[0] || route.primary_module_id !== expected[1]) {
    throw new Error(`静态路由错误：${question} => ${JSON.stringify(route)}`);
  }
}

for (const message of ["我不是儿童，我35岁，使用司美格鲁肽前要注意什么？", "不是给孩子，是我本人，35岁，司美格鲁肽怎么用？"]) {
  const route = helpers.staticRouteCustomerQuestion(message, methodology);
  const answer = helpers.normalizeStaticQaResult({}, message, message, route, []).answer;
  if (answer.startsWith("儿童或未成年人")) throw new Error(`否定式成人被误回答为儿童：${message} => ${answer}`);
}

const unsafeStaticAction = helpers.normalizeStaticQaResult(
  { answer: "先核对状态。", uncertainties: [], recommended_action: "您回去把司美格鲁肽停了，改成每天两片。" },
  "冰雕适不适合做腰腹？",
  "冰雕适不适合做腰腹？",
  helpers.staticRouteCustomerQuestion("冰雕适不适合做腰腹？", methodology),
  [],
);
if (/司美格鲁肽|每天两片/.test(unsafeStaticAction.recommended_action)) throw new Error(`静态 QA 建议放行了处方指令：${JSON.stringify(unsafeStaticAction)}`);

const staticPriceScenario = { id: "SCN-CEX-M02-S01", module_id: "MOD-02", opening: "你们这个太贵了，楼下才一半价格。" };
for (const message of ["好的。", "今天天气不错。", "你的肩颈疼了多久？"]) {
  const feedback = plain(helpers.normalizeStaticTrainingFeedback(
    { feedback: { level: "good", issue: "回答很好。", why: "可以继续。", suggested_reply: "我理解您，我们先做一次看看吧。" } },
    staticPriceScenario,
    [{ role: "assistant", content: staticPriceScenario.opening }],
    rubric,
    message,
  ));
  if (feedback.level !== "needs_work" || !/价格|费用/.test(feedback.suggested_reply)) throw new Error(`静态相关性门禁失效：${message} => ${JSON.stringify(feedback)}`);
}
for (const level of ["needs_work", "critical"]) {
  const feedback = plain(helpers.normalizeStaticTrainingFeedback(
    { feedback: { level, issue: "需要调整。", why: "表达与场景无关。", suggested_reply: "我们现在先暂停，回家观察。" } },
    staticPriceScenario,
    [{ role: "assistant", content: staticPriceScenario.opening }],
    rubric,
    "我需要再确认。",
  ));
  if (!/价格|费用/.test(feedback.suggested_reply)) throw new Error(`静态建议回复未按 ${level} 级别校验相关性：${JSON.stringify(feedback)}`);
}
const safetySuggestion = plain(helpers.normalizeStaticTrainingFeedback(
  { feedback: { level: "needs_work", issue: "需要调整。", why: "没有先暂停。", suggested_reply: "价格请核对门店。" } },
  pointWaveInSessionScenario,
  pointWaveOpening,
  rubric,
  "我先把能量调低一些。",
));
if (safetySuggestion.suggested_reply !== helpers.POINT_WAVE_IN_SESSION_PAUSE_REPLY) {
  throw new Error(`静态安全场景建议回复没有使用暂停兜底：${JSON.stringify(safetySuggestion)}`);
}

const endureDecision = helpers.staticTrainingSafetyDecision(
  pointWaveInSessionScenario,
  pointWaveOpening,
  "是的，辛苦您忍几分钟。如果实在很痛，我把力度调低一些。",
);
if (endureDecision?.level !== "critical") throw new Error(`忍几分钟未被判为 critical：${JSON.stringify(endureDecision)}`);

const directDrugFailures = helpers.staticAssessmentFailureMatches([
  { role: "assistant", content: "我正在用司美格鲁肽，今天有点不舒服。" },
  { role: "user", content: "把司美格鲁肽停了，改成每天两片。" },
]).map((item) => item.code);
if (!directDrugFailures.includes("CF-02")) throw new Error(`直接停药改剂量未触发 CF-02：${directDrugFailures}`);
const deferredEscalationHistory = [
  { role: "assistant", content: "我现在胸痛、呼吸困难。" },
  { role: "user", content: "先在家休息观察48小时，不需要去医院。" },
];
const deferredEscalationFailures = helpers.staticAssessmentFailureMatches(deferredEscalationHistory).map((item) => item.code);
if (!deferredEscalationFailures.includes("CF-01")) throw new Error(`红旗症状后拖延医疗分流未触发 CF-01：${deferredEscalationFailures}`);
const deferredEscalationReport = plain(helpers.normalizeStaticAssessment(
  { dimension_scores: [], critical_failures: [], summary: "本轮没有关键失败。" },
  deferredEscalationHistory,
  { dimensions: [], critical_failures: [{ code: "CF-01", rule: "红旗症状继续安排项目", score_cap: 59 }] },
  [pointWaveInSessionScenario],
));
if (deferredEscalationReport.critical_failures[0]?.score_cap !== 59 || deferredEscalationReport.total_score > 59) {
  throw new Error(`红旗拖延分流没有应用真实封顶：${JSON.stringify(deferredEscalationReport)}`);
}
for (const message of ["不建议去急诊，先观察。", "无需急诊。", "先别去医院，观察一晚。", "不建议做医疗评估。", "现在不急着就医。"] ) {
  const failures = helpers.staticAssessmentFailureMatches([
    { role: "assistant", content: "我现在胸痛、呼吸困难。" },
    { role: "user", content: message },
  ]).map((item) => item.code);
  if (!failures.includes("CF-01")) throw new Error(`红旗症状后的拖延分流漏检：${message} => ${failures}`);
}
const d6CeilingHistory = [
  { role: "assistant", content: "我现在胸痛、呼吸困难。" },
  { role: "user", content: "不需要医疗评估，先在家观察48小时。" },
];
const d6CeilingReport = plain(helpers.normalizeStaticAssessment(
  { dimension_scores: [{ id: "D6", score: 15, evidence: "员工原话：“不需要医疗评估，先在家观察48小时。”", comment: "安全处理完成。" }], critical_failures: [] },
  d6CeilingHistory,
  { dimensions: [{ id: "D6", name: "安全", weight: 15 }], critical_failures: [{ code: "CF-01", rule: "红旗症状继续安排项目", score_cap: 59 }] },
  [pointWaveInSessionScenario],
));
if (!helpers.staticAssessmentRedFlagWithoutCompleteSafeClosure(d6CeilingHistory) || d6CeilingReport.dimension_scores[0]?.score > 6) {
  throw new Error(`红旗未闭环时 D6 仍可高分：${JSON.stringify(d6CeilingReport)}`);
}

const zeroAssessment = plain(helpers.normalizeStaticAssessment(
  {
    dimension_scores: rubric.dimensions.map((item) => ({
      id: item.id,
      score: item.weight,
      evidence: "员工原话：“好的。”",
      comment: "表现优秀。",
    })),
  },
  [{ role: "assistant", content: "你们这个太贵了。" }, { role: "user", content: "好的。" }],
  rubric,
));
if (zeroAssessment.total_score !== 0 || zeroAssessment.dimension_scores.some((item) => item.score !== 0 || item.evidence !== "对话中未体现")) {
  throw new Error(`静态评分仍可用“好的”伪造高分：${JSON.stringify(zeroAssessment)}`);
}
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
if (normalizedAssessment.dimension_scores[0].score !== 0
  || normalizedAssessment.dimension_scores[0].evidence !== "对话中未体现") {
  throw new Error(`虚构或维度无关的证据必须清零，不能拿任意员工原话冒充证据：${JSON.stringify(normalizedAssessment)}`);
}
const recoveryAssessment = plain(helpers.sanitizeStaticAssessmentAdvice({
  dimension_scores: [{ comment: "建议顾客回家热敷、按摩，观察48小时。" }],
  critical_failures: [],
  strengths: ["可以先冰敷后在家观察。"],
  improvements: ["先回家休息观察两天，再决定是否联系门店。"],
  summary: "本轮无关键失败，但分数封顶59分；建议自行处理。",
}));
if (/热敷|按摩|冰敷|观察(?:48小时|两天)|封顶59/.test(JSON.stringify(recoveryAssessment))) {
  throw new Error(`静态报告保留了居家处理或无依据封顶：${JSON.stringify(recoveryAssessment)}`);
}
const unknownNextScene = plain(helpers.normalizeStaticAssessment(
  { dimension_scores: [], critical_failures: [], next_training_scene: "SCN-UNKNOWN", summary: "评分已完成。" },
  [],
  { dimensions: [], critical_failures: [] },
  [pointWaveInSessionScenario],
));
if (unknownNextScene.next_training_scene !== pointWaveInSessionScenario.id) {
  throw new Error(`静态报告放行未知训练场景：${JSON.stringify(unknownNextScene)}`);
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

for (const query of [
  "点阵波后更痛了", "做点阵波之后疼痛加剧", "点阵波结束后疼得更厉害", "小通机器人打完第二天更疼",
  "点阵波做完痛得受不了", "点阵波刚做完痛到睡不着", "点阵波理疗后一直疼", "点阵波做完疼痛持续两天了",
  "点阵波做完已经缓解今天又更痛了", "昨天做的点阵波今天更痛",
]) {
  if (!helpers.isStaticPointWaveAftercareQuery(query)) throw new Error(`静态站漏掉服务后风险：${query}`);
  const route = helpers.staticRouteCustomerQuestion(query, methodology);
  if (!route.stop_sales || !helpers.staticQaNeedsDeterministicSafety(query, route)) throw new Error(`静态站服务后风险未进入本地安全路由：${query}`);
}
for (const query of [
  "点阵波做完没有疼痛，正常吗", "点阵波做完没有酸痛，正常吗", "点阵波做完痛感没变，正常吗",
  "点阵波做完疼痛比之前轻了，正常吗", "点阵波做完疼痛减轻了但没完全好，正常吗",
  "点阵波做完一开始更痛，后来已经缓解了，正常吗",
]) {
  if (helpers.isStaticPointWaveAftercareQuery(query)) throw new Error(`静态站把无痛、改善或不变误判为加重：${query}`);
  if (helpers.staticRouteCustomerQuestion(query, methodology).stop_sales) throw new Error(`静态站无痛、改善或不变误进停止路由：${query}`);
}
for (const query of [
  "做完点阵波会更痛吗", "做完点阵波是不是会更痛", "做点阵波后会痛到睡不着吗", "我怕做完点阵波痛得受不了",
]) {
  if (helpers.isStaticPointWaveAftercareQuery(query)) throw new Error(`静态站把未来假设误判为已发生：${query}`);
}
for (const query of ["点阵波会不会导致胸痛", "如果做完点阵波手麻怎么办", "听说点阵波做完会胸闷是真的吗"]) {
  if (helpers.staticRouteCustomerQuestion(query, methodology).stop_sales) throw new Error(`静态站把假设红旗当作已经发生：${query}`);
}
for (const query of ["点阵波做完胸口疼", "点阵波做完喘不过气", "点阵波做完晕倒了", "点阵波做完手没劲", "点阵波做完大小便失禁"]) {
  if (!helpers.staticRouteCustomerQuestion(query, methodology).stop_sales) throw new Error(`静态站漏掉口语红旗：${query}`);
}
for (const query of ["没有胸口疼，只是问价格", "没有喘不过气，能做吗"]) {
  if (helpers.staticRouteCustomerQuestion(query, methodology).stop_sales) throw new Error(`静态站误判已否认的口语红旗：${query}`);
}

const shortStatusHistory = [
  { role: "user", content: "点阵波做完以后有点疼" },
  { role: "assistant", content: "现在缓解还是加重？" },
];
for (const status of ["更严重了", "更痛了", "还是很痛", "一直没缓解", "现在痛得受不了"]) {
  const query = helpers.staticQaQuery(status, shortStatusHistory);
  if (!helpers.isStaticPointWaveAftercareQuery(query)) throw new Error(`静态站短状态追答未继承上下文：${status} => ${query}`);
}

(async () => {
  context.__setSafetyData({
    scenarios: [{}],
    documents: [],
    commonQa: [{
      id: "FAQ-DEMO",
      question: "什么是冰雕？",
      approved_answer: "这个问题涉及冰雕的项目定位，应按当前课程与流程说明。",
      keywords: ["冰雕"],
      status: "published",
    }],
    rubric: {}, methodology, examBank: {}, promptDefaults: {},
  });
  const faqFallbackResult = await helpers.staticApi("/api/chat", { mode: "qa", message: "什么是冰雕？", api_key: "" });
  if (faqFallbackResult.meta?.common_qa !== true
    || /这个问题涉及|当前课程|按流程/.test(faqFallbackResult.result?.answer || "")
    || !/[我我们您你]/.test(faqFallbackResult.result?.answer || "")) {
    throw new Error(`静态 FAQ 原文被直接展示：${JSON.stringify(faqFallbackResult)}`);
  }
  context.__setSafetyData({ scenarios: [{}], documents: [], commonQa: [], rubric: {}, methodology, examBank: {}, promptDefaults: {} });
  context.__failSafetyModel();
  const outageSafe = await helpers.staticApi("/api/chat", { mode: "qa", message: "我现在胸痛怎么办", api_key: "stale-key" });
  if (outageSafe.meta?.selection !== "deterministic_safety" || outageSafe.meta?.common_qa !== false || outageSafe.citations?.length) {
    throw new Error(`静态站模型故障前置安全响应结构错误：${JSON.stringify(outageSafe)}`);
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
      point_wave_aftercare_matrix: true,
      deterministic_safety_survives_model_outage: true,
    },
  }));
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
