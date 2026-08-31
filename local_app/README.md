# 秀域 AI 训练中心 · 本地验证版

这是基于 `knowledge_base/` 的门店员工 AI 学习、训练和考核平台。

## 三个核心功能区

- 学习与陪练：首页先选择“课程学习”或“情景陪练”，再通过独立的模块中间页进入内容。学习页只展示所选模块的章节与课程；陪练页展示模拟顾客和即时纠正。
- 实战考核：首页将“客观题考试”和“模拟顾客考核”分成两个独立入口，再选择模块。客观题提交后显示分数、本人答案、标准答案和解析；模拟顾客考核通过 AI 多轮对话完成主观题评分。
- 智能接待：使用者扮演顾客，AI 从完整知识库检索后进行回答和接待；每次回答下方展示对应模块、章节和参考课程，点击可直接打开课程学习。

课程采用三级目录：10 个学习模块 → 10 个主题章节 → 43 节具体课程。员工先选择功能，再选择模块，最后进入对应课程、陪练或考试；课程标题和回答依据均使用员工可理解的名称，不显示原始文件名或内部检索编号。模块定义位于 `knowledge_base/learning_modules.json`，完整课程目录位于 `knowledge_base/learning_catalog.json`。

## 启动

在项目根目录执行：

```powershell
python .\local_app\server.py
```

然后打开 <http://127.0.0.1:8787>。

第一次可以不配置 Key，网站会进入演示模式。要调用 SiliconFlow，可在启动前设置：

```powershell
$env:SILICONFLOW_API_KEY = "你的 API Key"
$env:SILICONFLOW_MODEL = "Qwen/Qwen3.5-35B-A3B"
python .\local_app\server.py
```

也可以在网站“模型设置”中临时输入 Key。Key 只由本地服务转发到 SiliconFlow，不写入知识库文件。

## 讯飞在线语音合成（后端接口）

后端提供 `POST /api/tts`，由服务器调用讯飞流式 WebSocket TTS，浏览器只接收音频，不接触讯飞凭据。请求示例：

```json
{
  "text": "我先帮您记录当前情况，再说明下一步安排。",
  "voice_name": "x4_xiaoyan",
  "speed": 50,
  "volume": 50,
  "pitch": 50,
  "audio_format": "mp3"
}
```

成功时返回 `audio/mpeg`（或 `audio/L16; rate=16000` 的 PCM），并带有 `X-TTS-Cache`、`X-TTS-Format` 等非敏感响应头。 `GET /api/tts/status` 只返回是否已配置、默认音色和限制，不返回任何密钥。

将 `weknora_migration/lite_deployment/templates/training.env.example` 中的 `IFLYTEK_TTS_*` 项复制到服务器的 `/etc/training-kb/training.env` 后再填写。推荐使用控制台的 APIPassword；也可以填写完整的 APP_ID、API_KEY、API_SECRET 进行 HMAC 签名。真实 `training.env` 必须保持 `root:root`、`0600`，不要把密钥放到前端、Git、命令行参数或聊天记录中。单次文本上限严格小于 8000 个 UTF-8 字节，服务端按来源地址限流并使用有上限的短期内存缓存。

## 讯飞语音输入（语音转文字）

三个对话入口——智能接待、情景陪练和模拟接待考核——共用输入框右侧的“语音输入”按钮。点击开始录音，再次点击停止；浏览器会把单声道音频转换为 16 kHz PCM，交给本应用的 `POST /api/asr` 后端代理。后端以讯飞流式语音听写（IAT）协议转写，结果只回填到输入框，员工可以检查或修改后再发送；不会自动把语音内容提交给 AI。

接口只接受 `audio_base64`（16-bit、little-endian PCM）与 `sample_rate: 16000`，单次录音最长 30 秒、最大原始音频 960000 字节，并按来源地址限流。`GET /api/asr/status` 与 `/api/health` 仅返回是否完成配置、采样率和时长上限，绝不返回凭据。

在讯飞控制台为同一应用启用“语音听写（流式版）”。IAT 必须使用 APPID、APIKey 与 APISecret 的完整 HMAC 三元组；TTS 的 APIPassword 不能用于语音输入。可填独立 `IFLYTEK_IAT_*`，也可以留空让它复用完整的 `IFLYTEK_TTS_APP_ID/API_KEY/API_SECRET`。浏览器和静态文件中不存放任何讯飞凭据。若纯 GitHub Pages 静态页没有受保护的应用后端，语音按钮会保持不可用，避免把鉴权或音频错误地发送到第三方；将页面部署在本应用后端的 HTTPS 入口即可启用。

## 当前验证边界

当前检索使用轻量词项和中文双字匹配，适合先验证学习路径、Prompt、评分与引用。后续接入向量数据库时可以保留同一套 JSONL 结构、模块体系和三套系统 Prompt。

`SRC-007` 视频转写仍是自动识别初稿；疗效、医学、药品、价格和营销承诺相关内容，上线前需要人工回听并由合规负责人确认。
