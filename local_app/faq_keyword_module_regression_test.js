"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.join(__dirname, "..");
const appPath = path.join(__dirname, "static", "app.js");
const source = fs.readFileSync(appPath, "utf8");
const boundary = source.indexOf('\ndocument.addEventListener("click"');
if (boundary < 0) throw new Error("无法定位 app.js 启动边界");

const element = () => ({
  classList: { add() {}, remove() {}, toggle() {} },
  dataset: {}, style: {}, value: "", textContent: "", innerHTML: "",
  setAttribute() {}, focus() {}, querySelector() { return null; }, querySelectorAll() { return []; },
});
const context = {
  console,
  localStorage: { getItem() { return ""; }, setItem() {}, removeItem() {} },
  document: {
    getElementById() { return element(); },
    querySelectorAll() { return []; },
    querySelector() { return null; },
  },
  window: { location: { hostname: "localhost", hash: "" }, history: { pushState() {}, replaceState() {} }, scrollTo() {} },
  location: { hostname: "localhost", hash: "" },
  setTimeout,
  clearTimeout,
};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(
  `${source.slice(0, boundary)}\n;globalThis.__faqKeywordModuleExports = {`
    + "state, els, normalizeFaqKeywordExamBanks, faqKeywordExamByModuleId, faqKeywordQuestions, routeItemById, parseRouteHash, examQuestions, keywordAnswerScore, renderModuleGateway, renderFaqKeywordExam, faqKeywordAnswers, faqKeywordScore, scoreFaqKeywordExam};",
  context,
  { filename: appPath },
);

const helpers = context.__faqKeywordModuleExports;
const bank = JSON.parse(fs.readFileSync(path.join(root, "knowledge_base", "point_wave_faq_exam.json"), "utf8"));
const indexHtml = fs.readFileSync(path.join(__dirname, "static", "index.html"), "utf8");

helpers.state.modules = [
  { id: "MOD-01", order: 1, title: "企业与接待基础" },
  { id: "MOD-03", order: 3, title: "点阵波与疼痛服务" },
];
helpers.state.faqKeywordExamBanks = helpers.normalizeFaqKeywordExamBanks(bank);
helpers.state.faqKeywordModuleId = "MOD-03";
helpers.state.route = "exam/faq-keywords";

if (helpers.state.faqKeywordExamBanks.length !== 1 || helpers.faqKeywordExamByModuleId("MOD-03")?.title !== "点阵波 FAQ 关键词问答") {
  throw new Error("FAQ 关键词题库未正确加载为独立模块数据");
}
const questions = helpers.faqKeywordQuestions("MOD-03");
if (questions.length !== 8 || !questions.every((question) => question.type === "keyword_answer" && question.points === 10)) {
  throw new Error(`FAQ 关键词题目结构错误：${JSON.stringify(questions.map((question) => [question.id, question.type, question.points]))}`);
}
if (!helpers.routeItemById("exam/faq-keywords", "MOD-03") || helpers.routeItemById("exam/faq-keywords", "MOD-01")) {
  throw new Error("FAQ 关键词路由没有只开放已配置题库的模块");
}
helpers.renderModuleGateway();
if (!helpers.els.moduleRouteGrid.innerHTML.includes("点阵波与疼痛服务") || helpers.els.moduleRouteGrid.innerHTML.includes("企业与接待基础")) {
  throw new Error(`FAQ 关键词模块入口未按题库范围过滤：${helpers.els.moduleRouteGrid.innerHTML}`);
}
context.window.location.hash = "#exam/faq-keywords/MOD-03";
const parsedRoute = helpers.parseRouteHash();
if (parsedRoute.route !== "exam/faq-keywords" || parsedRoute.moduleId !== "MOD-03" || parsedRoute.invalid) {
  throw new Error(`FAQ 关键词独立链接无法解析：${JSON.stringify(parsedRoute)}`);
}

const ordinaryExamQuestions = helpers.examQuestions({
  fill_blanks: [{ id: "F-01", prompt: "填空", answers: ["答案"] }],
  choices: [{ id: "C-01", prompt: "选择", answers: ["A"], options: [{ key: "A", text: "答案" }] }],
  faq_keyword_answers: bank.questions,
});
if (ordinaryExamQuestions.length !== 2 || ordinaryExamQuestions.some((question) => question.type === "keyword_answer")) {
  throw new Error("FAQ 关键词题仍混入客观题考试");
}

const initialMarkup = helpers.renderFaqKeywordExam();
if (!/FAQ 关键词问答/.test(initialMarkup) || !initialMarkup.includes(questions[0].prompt) || /参考安全回答/.test(initialMarkup)) {
  throw new Error("FAQ 独立答题页未正确呈现，或交卷前泄露参考回答");
}
if (!/data-route="exam\/faq-keywords"/.test(indexHtml)) {
  throw new Error("实战考核首页缺少 FAQ 关键词问答入口");
}

const naturalAnswers = {
  "FAQ-M03-K01": "点阵波是局部重复机械刺激的门店体验，可能有敲击、震动和酸胀感，不能代替医学诊断，也不能保证固定效果。",
  "FAQ-M03-K02": "立即暂停，不强迫继续，询问疼痛程度和性质、麻木无力等伴随症状，顾客可以随时停止，异常时通知负责人。",
  "FAQ-M03-K03": "不能把加重解释成有效，问清什么时候开始、程度和变化并记录，暂停服务并联系负责人，建议及时医疗评估。",
  "FAQ-M03-K04": "按工作方式、刺激范围、体验、风险和复测比较，按摩也有放松价值，医院冲击波属于医疗流程，不能凭参数推断效果。",
  "FAQ-M03-K05": "先确认两项都和目标相关，分别说明震动和热感并分别取得同意，可先试感，不能耐受就停止，用相同动作复测。",
  "FAQ-M03-K06": "问部位、时间、诱因和活动影响，有无麻木无力，不在门店诊断；突发剧痛或进行性麻木无力时优先医疗评估。",
  "FAQ-M03-K07": "不能现场试错，先确认诊断、手术和植入物，核验当前SOP并请有资质人员判断，异常时优先医疗评估，不能建议停药。",
  "FAQ-M03-K08": "先明确目标和记录基线，用同一动作复测；结果有个体差异，不能保证固定效果、次数和时间，疾病治疗目标交由医疗人员评估。",
};
Object.assign(helpers.faqKeywordAnswers(), naturalAnswers);
helpers.scoreFaqKeywordExam();
const complete = helpers.faqKeywordScore();
if (complete?.stage !== "complete" || complete.score !== 80 || complete.correct !== 8) {
  throw new Error(`FAQ 独立关键词计分失败：${JSON.stringify(complete)}`);
}
const reviewedMarkup = helpers.renderFaqKeywordExam();
if (!/本次得分：80\/80 分/.test(reviewedMarkup) || !/关键词判定/.test(reviewedMarkup) || !/参考安全回答/.test(reviewedMarkup)) {
  throw new Error("FAQ 交卷后未展示得分、关键词判定和参考回答");
}

const unsafe = helpers.keywordAnswerScore(
  questions.find((question) => question.id === "FAQ-M03-K02"),
  "虽然要暂停，但我们还是必须继续做完，麻木无力不用问。",
);
if (unsafe.correct || unsafe.earned !== 0 || !unsafe.safety_blocked) {
  throw new Error(`FAQ 独立模块没有复用安全硬规则：${JSON.stringify(unsafe)}`);
}

console.log(JSON.stringify({
  status: "passed",
  route: "exam/faq-keywords/MOD-03",
  questions: questions.length,
  total_points: complete.score,
  ordinary_exam_questions: ordinaryExamQuestions.length,
  safety_block: true,
}, null, 2));
