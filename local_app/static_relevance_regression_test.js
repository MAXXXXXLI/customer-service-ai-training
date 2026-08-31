"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const appPath = path.join(__dirname, "static", "app.js");
const source = fs.readFileSync(appPath, "utf8");
const boundary = source.indexOf('\ndocument.addEventListener("click"');
if (boundary < 0) throw new Error("无法定位 app.js 启动边界");

const element = () => ({
  classList: { add() {}, remove() {}, toggle() {} },
  dataset: {}, style: {}, value: "", textContent: "", innerHTML: "",
});
const context = {
  console,
  localStorage: { getItem() { return ""; }, setItem() {}, removeItem() {} },
  document: { getElementById() { return element(); }, querySelectorAll() { return []; }, querySelector() { return null; } },
  window: { location: { hostname: "localhost", hash: "" } },
  location: { hostname: "localhost", hash: "" },
  setTimeout,
  clearTimeout,
};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(
  `${source.slice(0, boundary)}\n;globalThis.__relevanceTest = {`
    + "normalizeStaticQaResult, staticQaAnswerIsRelevant, staticQaAnswerIsCurrentTurnRelevant, staticQaNeedsPositiveCustomerVoiceRepair, "
    + "normalizeStaticCustomerReply, normalizeStaticTestTurn, normalizeStaticTrainingFeedback, "
    + "staticTrainingMessageIsRelevant, staticTrainingSuggestedReplyFallback, staticTrainingSuggestedReplyIsRelevant, staticTrainingSuggestedReplyNeedsPositiveRepair, staticTrainingFeedbackIsCurrentTurnRelevant, "
    + "POINT_WAVE_PAIN_CONTEXT_REPLY, renderCoach};",
  context,
  { filename: appPath },
);
const helpers = context.__relevanceTest;

const greenCoachMarkup = helpers.renderCoach({
  level: "good",
  issue: "本轮已回应顾客问题。",
  why: "表达清楚且承接自然。",
  method_step: "回应当前问题",
  knowledge_focus: "顾客当前顾虑",
  suggested_reply: "这段替换话术不应在绿色结果中展示。",
  next_goal: "继续承接下一轮对话。",
});
if (/可以这样说|这段替换话术/.test(greenCoachMarkup)) {
  throw new Error(`绿色反馈仍显示替换话术：${greenCoachMarkup}`);
}
const needsWorkCoachMarkup = helpers.renderCoach({
  level: "needs_work",
  issue: "还需要回应顾客当前问题。",
  why: "先承接当前顾虑。",
  method_step: "回应当前问题",
  knowledge_focus: "当前顾虑",
  suggested_reply: "我先回应您刚才问的内容。",
  next_goal: "继续承接下一轮对话。",
});
if (!/可以这样说|我先回应您刚才问的内容/.test(needsWorkCoachMarkup)) {
  throw new Error(`非绿色反馈缺少替换话术：${needsWorkCoachMarkup}`);
}

const ordinaryNegative = /(?:不是|不能|不要|不应|不建议|不把.{0,16}(?:当作|说成|解释成)|无法|不可|不先|不急着|不直接|不替(?:您|你)?|不安排|不操作|不销售|不继续|不做|不承诺|不保证)/i;
const priceRoute = {
  intent_id: "INTENT-PRICE",
  intent_label: "价格咨询",
  primary_module_id: "MOD-07",
  primary_module: "局部塑形",
  recommended_next: "核对当前价格。",
};
const generalRoute = {
  intent_id: "INTENT-INFORMATION",
  intent_label: "一般咨询",
  primary_module_id: "MOD-03",
  primary_module: "点阵波",
  recommended_next: "先确认想了解的内容。",
};

const offTopicQa = "我喜欢看电影，周末去吃饭。";
if (helpers.staticQaAnswerIsRelevant(offTopicQa, "点阵波是什么？", "点阵波是什么？", generalRoute)) {
  throw new Error("静态 QA 把电影/吃饭内容误判为当前问题相关");
}
const repairedQa = helpers.normalizeStaticQaResult(
  { answer: offTopicQa, uncertainties: [], recommended_action: "" },
  "点阵波是什么？",
  "点阵波是什么？",
  generalRoute,
  [],
);
if (/电影|吃饭/.test(repairedQa.answer) || !/(?:项目|想了解|已核验)/.test(repairedQa.answer)) {
  throw new Error(`静态 QA 未把答非所问改回当前问题：${JSON.stringify(repairedQa)}`);
}

const shortFollowUpContext = "冰雕一次多少钱？那要多久？";
if (helpers.staticQaAnswerIsCurrentTurnRelevant(
  "费用会随城市和门店变化，请告诉我城市和门店。",
  "那要多久？",
  shortFollowUpContext,
  generalRoute,
)) {
  throw new Error("QA 短追问错误继承了上一轮价格话题");
}
if (!helpers.staticQaAnswerIsCurrentTurnRelevant(
  "我会结合具体项目和当前安排为您核对可用时间。",
  "那要多久？",
  shortFollowUpContext,
  generalRoute,
)) {
  throw new Error("QA 短追问没有保留当前的时间问题");
}
const durationAfterPrice = helpers.normalizeStaticQaResult(
  { answer: "价格和活动会随城市和门店变化，请告诉我城市和门店。", uncertainties: [], recommended_action: "" },
  "那要多久？",
  shortFollowUpContext,
  priceRoute,
  [],
);
if (!/需要多久|体验大约需要多久|多久能观察到变化/.test(durationAfterPrice.answer)
  || /价格和活动会随城市和门店变化/.test(durationAfterPrice.answer)
  || !/体验时长|阶段变化/.test(durationAfterPrice.recommended_action)) {
  throw new Error(`静态 QA 的时长追问仍被旧价格路由带偏：${JSON.stringify(durationAfterPrice)}`);
}

const positiveResult = helpers.normalizeStaticQaResult(
  { answer: "不能保证一次见效，也不建议您期待固定结果。", uncertainties: [], recommended_action: "" },
  "冰雕一次多久能看到效果？",
  "冰雕一次多久能看到效果？",
  { ...generalRoute, intent_id: "INTENT-RESULT" },
  [],
);
if (ordinaryNegative.test(positiveResult.answer) || !/(?:指标|记录|阶段|变化)/.test(positiveResult.answer)) {
  throw new Error(`普通 QA 未改为正向可执行表达：${JSON.stringify(positiveResult)}`);
}
if (!helpers.staticQaNeedsPositiveCustomerVoiceRepair("不能保证一次见效。", "一次见效吗？", "一次见效吗？", { ...generalRoute, intent_id: "INTENT-RESULT" }, false)) {
  throw new Error("普通 QA 的不必要否定没有触发表达修复");
}

const redFlag = helpers.normalizeStaticQaResult(
  { answer: "我喜欢看电影。", uncertainties: [], recommended_action: "" },
  "点阵波做完后胸痛怎么办？",
  "点阵波做完后胸痛怎么办？",
  { ...generalRoute, intent_id: "INTENT-RED-FLAG", stop_sales: true },
  [],
);
if (!/(?:停止|急救|医疗机构|就医)/.test(redFlag.answer)) {
  throw new Error(`红旗安全分流被相关性/语气闸门覆盖：${JSON.stringify(redFlag)}`);
}

const priceScenario = {
  id: "SCN-PRICE-TEST",
  module_id: "MOD-07",
  opening: "你们这个冰雕一次多少钱？我主要担心预算。",
  persona: { goal: "局部塑形" },
  hidden_objections: ["价格"],
};
const priceHistory = [{ role: "assistant", content: priceScenario.opening }];
const customerAfterOffTopicEmployee = helpers.normalizeStaticCustomerReply(
  "好啊，我喜欢看电影。",
  priceScenario,
  priceHistory,
  "今天天气很好，周末去看电影吧？",
);
if (/电影|天气/.test(customerAfterOffTopicEmployee) || !/(?:没听明白|冰雕|预算|费用)/.test(customerAfterOffTopicEmployee)) {
  throw new Error(`陪练顾客跟随了员工的无关话题：${customerAfterOffTopicEmployee}`);
}

const changedQuestionHistory = [
  { role: "assistant", content: "冰雕一次多少钱？" },
  { role: "user", content: "价格会随城市和门店变化。" },
  { role: "assistant", content: "那要多久？" },
];
if (helpers.staticTrainingMessageIsRelevant(
  "价格会随城市、门店和日期变化，我为您核对。",
  changedQuestionHistory,
  priceScenario,
)) {
  throw new Error("陪练评分仍把上一轮价格当作当前的“多久”问题");
}
if (!helpers.staticTrainingMessageIsRelevant(
  "我会结合具体项目和当前安排为您核对大概需要多久。",
  changedQuestionHistory,
  priceScenario,
)) {
  throw new Error("陪练评分没有承接当前的时间问题");
}
const changedQuestionFallback = helpers.staticTrainingSuggestedReplyFallback(priceScenario, changedQuestionHistory);
if (!/多久|指标|项目|持续时间|可选方式/.test(changedQuestionFallback) || /价格和活动会随/.test(changedQuestionFallback)) {
  throw new Error(`教练建议话术把上一轮价格带回当前时间追问：${changedQuestionFallback}`);
}
if (helpers.staticTrainingSuggestedReplyIsRelevant(
  "价格和活动会随城市、门店和日期变化。",
  priceScenario,
  changedQuestionHistory,
)) {
  throw new Error("教练建议话术错误接受了上一轮价格答案");
}

const necessaryFollowUpFeedback = {
  issue: "可以先确认顾客希望多久看到阶段变化。",
  why: "持续时间能帮助把下一步说明得更具体。",
  method_step: "补充一个持续时间问题。",
  knowledge_focus: "持续时间与当前目标。",
  suggested_reply: "您希望大概多久看到阶段变化？",
  next_goal: "根据顾客对时间的回答继续说明。",
};
if (!helpers.staticTrainingFeedbackIsCurrentTurnRelevant(
  necessaryFollowUpFeedback,
  "您更在意总价还是优惠？",
  priceHistory,
  priceScenario,
)) {
  throw new Error("训练教练把必要的时间追问误判为换题");
}

const durationScenario = {
  id: "SCN-DURATION-TEST",
  module_id: "MOD-01",
  opening: "我最近肩膀有点不舒服，想了解有没有适合我的体验。",
  persona: { goal: "肩膀不舒服" },
  hidden_objections: ["时间"],
};
const durationHistory = [{ role: "assistant", content: durationScenario.opening }];
const durationReply = helpers.normalizeStaticCustomerReply(
  "我喜欢看电影，周末也想去吃饭。",
  durationScenario,
  durationHistory,
  "这种不舒服持续多久了？",
);
if (/电影|吃饭/.test(durationReply) || !/(?:有一阵子|最近|这几天|持续)/.test(durationReply)) {
  throw new Error(`陪练顾客没有回答员工当前的时长问题：${durationReply}`);
}
const testTurn = helpers.normalizeStaticTestTurn(
  { reply: "好啊，我们去看电影。", emotion: "curious", should_continue: true },
  durationScenario,
  durationHistory,
  "这种不舒服持续多久了？",
);
if (/电影/.test(testTurn.reply) || !/(?:有一阵子|最近|这几天|持续)/.test(testTurn.reply)) {
  throw new Error(`考试模拟顾客没有承接员工当前问题：${JSON.stringify(testTurn)}`);
}

const coachFeedback = helpers.normalizeStaticTrainingFeedback(
  {
    feedback: {
      level: "good",
      issue: "表达不错。",
      why: "表达清楚。",
      method_step: "回应顾客。",
      knowledge_focus: "价格。",
      suggested_reply: "您有不舒服时先停止项目并尽快去医院。",
      next_goal: "继续沟通。",
    },
  },
  priceScenario,
  priceHistory,
  {},
  "您更在意总价还是优惠？",
);
if (!/(?:价格|费用|预算|城市|门店)/.test(coachFeedback.suggested_reply) || /不舒服|去医院/.test(coachFeedback.suggested_reply)) {
  throw new Error(`训练教练的建议话术没有回到顾客当前价格问题：${JSON.stringify(coachFeedback)}`);
}

const driftedCoachFeedback = helpers.normalizeStaticTrainingFeedback(
  {
    feedback: {
      level: "needs_work",
      issue: "顾客疼痛时应暂停并就医。",
      why: "疼痛需要优先处理。",
      method_step: "暂停操作。",
      knowledge_focus: "疼痛与就医。",
      suggested_reply: "先暂停项目并去医院。",
      next_goal: "下一轮继续确认疼痛。",
    },
  },
  priceScenario,
  priceHistory,
  {},
  "您更在意总价还是优惠？",
);
if (!/(?:当前问题|刚才提出的重点)/.test(driftedCoachFeedback.issue)
  || !/(?:价格|费用|预算|城市|门店)/.test(driftedCoachFeedback.suggested_reply)) {
  throw new Error(`训练教练的整段反馈没有回到当前价格问题：${JSON.stringify(driftedCoachFeedback)}`);
}

const pointWaveScenario = {
  id: "SCN-CEX-M03-S01",
  module_id: "MOD-03",
  title: "点阵波打完更痛",
  task: "优先暂停后续项目，完成必要问询、记录升级和医疗分流。",
  opening: "我昨天做完点阵波，今天比原来更痛。你们是不是把我打坏了？",
  persona: { goal: "点阵波打完更痛" },
  hidden_objections: ["担心异常"],
  information_release_rules: ["员工问时间和变化时，说明“昨晚开始，今天更重”。"],
};
const pointWaveFeedback = helpers.normalizeStaticTrainingFeedback(
  { feedback: { level: "needs_work", issue: "新客接待要先完成需求分析。", why: "先问清目标。", method_step: "需求分析", knowledge_focus: "客户目标", suggested_reply: "这种情况大概持续多久？", next_goal: "继续了解目标。" } },
  pointWaveScenario,
  [{ role: "assistant", content: pointWaveScenario.opening }],
  {},
  "不是",
);
for (const key of ["issue", "why", "method_step", "knowledge_focus", "next_goal"]) {
  if (/新客接待|需求分析|客户目标/.test(pointWaveFeedback[key])) {
    throw new Error(`点阵波服务后异常反馈回退成泛主题：${key} => ${pointWaveFeedback[key]}`);
  }
}
if (!/点阵波|异常|暂停|记录|医疗/.test(pointWaveFeedback.issue + pointWaveFeedback.why + pointWaveFeedback.method_step + pointWaveFeedback.knowledge_focus + pointWaveFeedback.next_goal)
  || !pointWaveFeedback.suggested_reply.includes("作为需要跟进的异常反应处理")
  || /我先不把|我先不急着/.test(pointWaveFeedback.suggested_reply)) {
  throw new Error(`点阵波服务后异常反馈没有使用正向安全承接：${JSON.stringify(pointWaveFeedback)}`);
}

const pointWaveHypothesisFeedback = helpers.normalizeStaticTrainingFeedback(
  { feedback: { level: "good", issue: "表达不错。", why: "表达清楚。", method_step: "回应顾客。", knowledge_focus: "服务安排。", suggested_reply: "如果手臂发麻，就尽快去医院。", next_goal: "继续沟通。" } },
  pointWaveScenario,
  [{ role: "assistant", content: pointWaveScenario.opening }],
  {},
  "如果之后手臂发麻，请尽快到医疗机构评估。",
);
if (pointWaveHypothesisFeedback.suggested_reply !== helpers.POINT_WAVE_PAIN_CONTEXT_REPLY
  || /顾客已经表达点阵波服务后疼痛加重，本轮“如果/.test(pointWaveHypothesisFeedback.issue)
  || /有没有麻木|无力、发热、红肿/.test(pointWaveHypothesisFeedback.suggested_reply)) {
  throw new Error(`点阵波假设性红旗被写成顾客既有事实：${JSON.stringify(pointWaveHypothesisFeedback)}`);
}

const postServiceScenario = {
  id: "SCN-AFTERCARE-TEST",
  module_id: "MOD-07",
  opening: "我昨天做完冰雕后一直很疼，现在想问怎么办。",
  persona: { goal: "服务后疼痛" },
};
const postServiceFeedback = helpers.normalizeStaticTrainingFeedback(
  { feedback: { level: "needs_work", issue: "新客接待要先完成需求分析。", why: "先问清目标。", method_step: "需求分析", knowledge_focus: "客户目标", suggested_reply: "这种情况大概持续多久？", next_goal: "继续了解目标。" } },
  postServiceScenario,
  [{ role: "assistant", content: postServiceScenario.opening }],
  {},
  "不是",
);
if (/新客接待|需求分析|客户目标/.test(postServiceFeedback.issue + postServiceFeedback.why + postServiceFeedback.method_step + postServiceFeedback.knowledge_focus + postServiceFeedback.next_goal)
  || !/(?:服务后|不适|暂停|异常)/.test(postServiceFeedback.issue + postServiceFeedback.why + postServiceFeedback.method_step + postServiceFeedback.knowledge_focus + postServiceFeedback.next_goal)) {
  throw new Error(`普通服务后异常反馈回退成泛主题：${JSON.stringify(postServiceFeedback)}`);
}

const positiveCoachFeedback = helpers.normalizeStaticTrainingFeedback(
  {
    feedback: {
      level: "good",
      issue: "表达不错。",
      why: "表达清楚。",
      method_step: "回应顾客。",
      knowledge_focus: "效果预期。",
      suggested_reply: "不能保证一次见效，也不要期待固定结果。",
      next_goal: "继续沟通。",
    },
  },
  { ...durationScenario, opening: "做一次有没有用？我怕花钱没变化。" },
  [{ role: "assistant", content: "做一次有没有用？我怕花钱没变化。" }],
  {},
  "我会先了解您的目标，再说明记录方式。",
);
if (ordinaryNegative.test(positiveCoachFeedback.suggested_reply) || !/(?:目标|指标|记录|复盘|阶段)/.test(positiveCoachFeedback.suggested_reply)) {
  throw new Error(`训练教练的普通建议话术未改为正向表达：${JSON.stringify(positiveCoachFeedback)}`);
}

const pointWaveMultiturnHistory = [
  { role: "assistant", content: "我昨天做完点阵波，今天比原来更痛。你们是不是把我打坏了？" },
  { role: "user", content: "我先为您暂停后续安排，并记录疼痛从什么时候开始、现在是否还在加重。" },
  { role: "assistant", content: "昨晚开始，今天更重。" },
];
const pointWaveMultiturnEmployee = "现在还有麻木、无力或发热吗？";
const pointWaveMultiturnCustomer = helpers.normalizeStaticCustomerReply(
  "我比较怕疼，过程中会不会很难受？",
  pointWaveScenario,
  pointWaveMultiturnHistory,
  pointWaveMultiturnEmployee,
);
if (/怕疼，过程中/.test(pointWaveMultiturnCustomer)
  || !/(?:麻木|无力|发热|没留意)/.test(pointWaveMultiturnCustomer)) {
  throw new Error(`多轮顾客没有回答最新伴随症状问题：${pointWaveMultiturnCustomer}`);
}
const pointWaveMultiturnFeedback = helpers.normalizeStaticTrainingFeedback(
  { feedback: { level: "good", suggested_reply: helpers.POINT_WAVE_BEST_REPLY } },
  pointWaveScenario,
  pointWaveMultiturnHistory,
  {},
  pointWaveMultiturnEmployee,
);
if (!/麻木/.test(pointWaveMultiturnFeedback.suggested_reply)
  || !/今天先为您暂停后续安排/.test(pointWaveMultiturnFeedback.suggested_reply)
  || pointWaveMultiturnFeedback.suggested_reply === helpers.POINT_WAVE_BEST_REPLY) {
  throw new Error(`多轮教练建议仍复读第一轮：${JSON.stringify(pointWaveMultiturnFeedback)}`);
}

process.stdout.write(JSON.stringify({ status: "passed" }) + "\n");
