"use strict";

// Browser-independent regression tests for the microphone-to-PCM handoff.
// They deliberately do not call iFlytek: credentials stay exclusively in the
// backend client and are covered by iflytek_asr_regression_test.py.

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const appPath = path.join(__dirname, "static", "app.js");
const indexPath = path.join(__dirname, "static", "index.html");
const source = fs.readFileSync(appPath, "utf8");
const indexHtml = fs.readFileSync(indexPath, "utf8");
const boundary = source.indexOf('\ndocument.addEventListener("click"');
if (boundary < 0) throw new Error("无法定位 app.js 启动边界");

function element() {
  return {
    classList: { add() {}, remove() {}, toggle() {} },
    dataset: {}, style: {}, value: "", textContent: "", innerHTML: "", disabled: false,
    setAttribute() {}, focus() {}, setSelectionRange() {}, addEventListener() {},
  };
}

const context = {
  console,
  localStorage: { getItem() { return ""; }, setItem() {}, removeItem() {} },
  document: { getElementById() { return element(); }, querySelectorAll() { return []; }, querySelector() { return null; } },
  window: {
    location: { hostname: "localhost", hash: "" },
    isSecureContext: true,
    navigator: {},
    btoa(value) { return Buffer.from(value, "binary").toString("base64"); },
  },
  location: { hostname: "localhost", hash: "" },
  setTimeout,
  clearTimeout,
  Buffer,
};
context.window.window = context.window;
vm.createContext(context);
vm.runInContext(
  `${source.slice(0, boundary)}\n;globalThis.__voiceTest = {`
    + "VOICE_SAMPLE_RATE, VOICE_MAX_DURATION_SECONDS, mergeVoiceSamples, resampleFloat32ToPcm16, pcm16ToBase64, appendVoiceTranscript, voiceInputUnavailableMessage, state, els};",
  context,
  { filename: appPath },
);

const helpers = context.__voiceTest;
if (helpers.VOICE_SAMPLE_RATE !== 16000 || helpers.VOICE_MAX_DURATION_SECONDS !== 30) {
  throw new Error("语音输入的采样率或时长上限与后端契约不一致");
}

const pcmSummary = vm.runInContext(`
  const a = new Float32Array([-1, -0.5]);
  const b = new Float32Array([0, 0.5, 1]);
  const merged = mergeVoiceSamples([a, b]);
  const identity = resampleFloat32ToPcm16(merged, 16000);
  const downsampled = resampleFloat32ToPcm16(new Float32Array([0, 0.2, 0.4, 0.6, 0.8, 1]), 48000);
  const base64 = pcm16ToBase64(new Int16Array([0, 32767, -32768]));
  ({ merged: Array.from(merged), identity: Array.from(identity), downsampled: Array.from(downsampled), base64 });
`, context);

if (JSON.stringify(pcmSummary.merged) !== JSON.stringify([-1, -0.5, 0, 0.5, 1])) {
  throw new Error(`录音片段合并错误：${JSON.stringify(pcmSummary.merged)}`);
}
if (pcmSummary.identity[0] !== -32768 || pcmSummary.identity.at(-1) !== 32767) {
  throw new Error(`PCM16 量化没有保留边界：${JSON.stringify(pcmSummary.identity)}`);
}
if (pcmSummary.downsampled.length !== 2) {
  throw new Error(`48kHz 到 16kHz 重采样长度错误：${JSON.stringify(pcmSummary.downsampled)}`);
}
if (pcmSummary.base64 !== "AAD/fwCA") {
  throw new Error(`PCM base64 编码错误：${pcmSummary.base64}`);
}

helpers.els.input.value = "我想先说";
helpers.appendVoiceTranscript("点阵波后更疼怎么办");
if (helpers.els.input.value !== "我想先说，点阵波后更疼怎么办") {
  throw new Error(`语音转写没有安全地写入共享输入框：${helpers.els.input.value}`);
}
helpers.els.input.value = "";
helpers.appendVoiceTranscript("顾客现在有麻木");
if (helpers.els.input.value !== "顾客现在有麻木") {
  throw new Error("空输入框写入转写内容失败");
}

if (!source.includes('api("/api/asr"')) throw new Error("前端未调用受保护的 /api/asr 后端接口");
if (!source.includes('modeSnapshot') || !source.includes('function sendMessage')) throw new Error("共享输入框的三种对话模式发送路径缺失");
if (!source.includes('STATIC_PAGES || !voiceCaptureSupported()')) throw new Error("静态页面未明确阻止将语音请求发往无后端环境");
if (!indexHtml.includes('id="voice-input-button"')) throw new Error("语音输入按钮未接入页面");

console.log("static voice input regression: PASS");
