"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const appPath = path.join(__dirname, "static", "app.js");
const source = fs.readFileSync(appPath, "utf8");
const boundary = source.indexOf('\ndocument.addEventListener("click"');
if (boundary < 0) throw new Error("无法定位 app.js 启动边界");

const element = () => ({ classList: { add() {}, remove() {}, toggle() {} }, dataset: {}, style: {}, value: "", textContent: "", innerHTML: "" });
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
  `${source.slice(0, boundary)}\n;globalThis.__qaTest = { staticPostServiceAdverseEvent, normalizeStaticQaResult, staticQaQuery, staticPublicRecommendedAction, staticQaAnswerNeedsEmployeeVoiceRepair, staticQaCustomerVoiceFallback, staticFaqCustomerVoiceFallback };`,
  context,
  { filename: appPath },
);
const helpers = context.__qaTest;

for (const question of [
  "我做完线雕后脸肿了怎么办？", "水光后起了很多红疹怎么办？", "水光后起了红疹，可能是产品问题吗？",
  "纳米喷射后眼周肿痛怎么办？", "热玛吉后火辣辣的怎么办？", "冰雕后红了一片", "线雕完脸不对称",
  "热玛吉后起水泡", "水光后流脓了", "皮秒后脸很痒", "玻尿酸后脸肿了", "肉毒后眼皮肿了",
  "超声炮后起水泡", "光子后脸很红", "激光后渗液",
  "水光后起荨麻疹怎么办？", "水光后起风团怎么办？", "热玛吉后皮肤破溃怎么办？",
  "肉毒后眼睑下垂怎么办？", "玻尿酸后皮肤发白怎么办？", "水光后发烧怎么办？",
  "水光后喉咙发紧怎么办？", "线雕后发炎怎么办？", "线雕后硬结怎么办？",
]) {
  if (!helpers.staticPostServiceAdverseEvent(question)) throw new Error(`静态端漏掉服务后异常：${question}`);
}
for (const question of [
  "如果做完线雕后脸肿怎么办？", "线雕后没有红肿，正常吗？", "我担心水光后会不会过敏。",
  "朋友说点阵波做完更痛，我想了解它是什么",
  "水光做完已经不红了，正常吗？", "水光做完红肿已经消了，正常吗？",
  "热玛吉后火辣辣已经好了，正常吗？", "玻尿酸后肿胀已经消退了，正常吗？",
]) {
  if (helpers.staticPostServiceAdverseEvent(question)) throw new Error(`静态端把假设/否认当真实异常：${question}`);
}
if (!helpers.staticPostServiceAdverseEvent("水光做完红肿已经消了，但今天又肿了")) throw new Error("静态端漏掉症状复发");

const query = helpers.staticQaQuery("副作用呢？", [{ role: "user", content: "超V热动力适合我吗？" }]);
if (!query.includes("超V") || !query.includes("副作用")) throw new Error(`静态端丢失项目追问上下文：${query}`);
for (const current of ["喉咙发紧怎么办？", "发烧了怎么办？", "起风团怎么办？", "眼睑下垂怎么办？", "皮肤发白怎么办？", "破溃怎么办？"]) {
  const contextual = helpers.staticQaQuery(current, [{ role: "user", content: "我昨天做了水光。" }]);
  if (!contextual.includes("水光")) throw new Error(`静态端丢失服务后异常上下文：${current} => ${contextual}`);
}

const route = { intent_id: "INTENT-SUITABILITY", primary_module_id: "MOD-07", recommended_next: "先确认项目。" };
const invented = "请告诉我肚子脂肪的触感，以便我做进一步评估。";
const normal = helpers.normalizeStaticQaResult({ answer: "冰雕属于局部塑形项目。", uncertainties: [], recommended_action: invented }, "冰雕适合吗？", "冰雕适合吗？", route, []);
if (normal.recommended_action !== helpers.staticPublicRecommendedAction(route) || normal.recommended_action === invented) throw new Error(`静态端泄露模型推荐动作：${JSON.stringify(normal)}`);

for (const answer of [
  "冰雕能消除内脏脂肪，通常三天就能见效，建议每周做三次。",
  "您这种情况最适合做冰雕，建议直接做十次。",
  "冰雕可以让脂肪细胞永久消失，通常一周内看到明显腰围变化。",
]) {
  const result = helpers.normalizeStaticQaResult({ answer, uncertainties: [], recommended_action: "继续了解。" }, "冰雕适合我吗？", "冰雕适合我吗？", route, []);
  if (result.answer === answer || /内脏脂肪|十次|永久消失|三天就能见效/.test(result.answer)) throw new Error(`静态端泄露无依据模型回答：${JSON.stringify(result)}`);
}

for (const [message, route, raw] of [
  ["超V副作用有哪些？", { intent_id: "INTENT-INFORMATION", primary_module_id: "MOD-04" }, "超V需要结合现行SOP判断，出现异常时应立即停止并按异常流程处理。"],
  ["我做完线雕后胸闷怎么办？", { intent_id: "INTENT-RED-FLAG", primary_module_id: "MOD-09", stop_sales: true }, "现在先停止项目和销售沟通，不在门店判断原因。"],
  ["司美格鲁肽怎么停？", { intent_id: "INTENT-DRUG", primary_module_id: "MOD-06" }, "药品适用性不能仅凭聊天判断，门店不能给剂量。"],
  ["背部发凉是不是肾不好？", { intent_id: "INTENT-INFORMATION", primary_module_id: "MOD-03" }, "背部发凉不能据此判断器官功能，也不能由门店作疾病诊断。"],
]) {
  if (!helpers.staticQaAnswerNeedsEmployeeVoiceRepair(raw)) throw new Error(`静态端未识别流程口吻：${raw}`);
  const repaired = helpers.staticQaCustomerVoiceFallback(message, message, route);
  if (!/[我我们]/.test(repaired) || /知识库|SOP|按流程|不在门店|当前课程/.test(repaired)) {
    throw new Error(`静态端未改成员工对客口吻：${message} => ${repaired}`);
  }
}

const directPointWaveAnswer = "点阵波是以局部重复机械刺激为主的体验项目，体验中可能感到敲击、振动或酸胀。";
if (helpers.staticQaAnswerNeedsEmployeeVoiceRepair(directPointWaveAnswer)) {
  throw new Error(`静态端把正常的知识性直答误判为需要模板修复：${directPointWaveAnswer}`);
}
const directPointWaveResult = helpers.normalizeStaticQaResult(
  { answer: directPointWaveAnswer, uncertainties: [], recommended_action: "继续了解。" },
  "点阵波的原理是什么？",
  "点阵波的原理是什么？",
  { intent_id: "INTENT-INFORMATION", primary_module_id: "MOD-03" },
  [],
);
if (directPointWaveResult.answer !== directPointWaveAnswer) {
  throw new Error(`静态端覆盖了与当前问题相关的正常直答：${JSON.stringify(directPointWaveResult)}`);
}

const pointWaveFaq = {
  row: {
    id: "FAQ-XLS-0007",
    question: "点阵波的原理是什么",
    approved_answer: "点阵波是以局部重复机械刺激为主的门店体验项目，顾客可能感到敲击、振动或酸胀。开始前应问清部位、持续时间、近期变化、外伤和麻木无力等风险信息，从可接受程度开始并允许随时暂停；只能复盘当次体感和动作变化，不能宣称治疗疾病或保证效果。",
  },
};
const pointWaveFaqAnswer = helpers.staticFaqCustomerVoiceFallback(pointWaveFaq);
if (!/局部重复机械刺激/.test(pointWaveFaqAnswer)
  || !/敲击、振动或酸胀/.test(pointWaveFaqAnswer)
  || /最想了解的是感受、适用性还是服务后的变化/.test(pointWaveFaqAnswer)) {
  throw new Error(`静态端把 FAQ-XLS-0007 的受控答案替换成了泛化模板：${pointWaveFaqAnswer}`);
}
const pointWaveFaqResult = helpers.normalizeStaticQaResult(
  { answer: pointWaveFaqAnswer, uncertainties: [], recommended_action: "继续了解。", faq_controlled_answer: true },
  pointWaveFaq.row.question,
  pointWaveFaq.row.question,
  { intent_id: "INTENT-INFORMATION", primary_module_id: "MOD-03" },
  [],
);
if (!/局部重复机械刺激/.test(pointWaveFaqResult.answer)) {
  throw new Error(`静态端在最终规范化时覆盖了 FAQ-XLS-0007：${JSON.stringify(pointWaveFaqResult)}`);
}

process.stdout.write(JSON.stringify({ status: "passed" }) + "\n");
