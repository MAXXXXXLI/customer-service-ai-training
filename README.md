# 秀域 AI 训练中心

这是一个基于 Python 标准库和原生前端的本地 Web 应用，包含：

- 学习课程目录与课程详情
- 顾客接待训练与 AI 对话演练
- 实战考核与评分报告
- 基于本地知识库的智能接待演示

## 本地运行

要求：Python 3.10+

```powershell
python .\local_app\server.py
```

然后打开 <http://127.0.0.1:8787>。

默认情况下应用使用演示模式，不需要 API Key。若要连接 SiliconFlow，可在启动前设置：

```powershell
$env:SILICONFLOW_API_KEY = "你的 API Key"
$env:SILICONFLOW_MODEL = "Qwen/Qwen3.5-35B-A3B"
python .\local_app\server.py
```

也可以参考 [`local_app/.env.example`](local_app/.env.example)。API Key 只应通过环境变量或页面临时配置提供，不要提交到 Git。

## GitHub Pages 发布

仓库包含 GitHub Actions 工作流。推送到 `main` 后，工作流会自动把静态网页发布到 GitHub Pages。访问 Pages 地址后，在“模型设置”中输入你自己的 SiliconFlow API Key；Key 只保存在当前浏览器的本地存储，并由浏览器直接发送给 SiliconFlow。

GitHub 仓库页面地址和实际可使用的 Pages 地址不同：仓库用于查看代码，Pages 地址用于打开应用。

## 项目结构

```text
local_app/       Web 服务、前端页面和静态资源
knowledge_base/  应用运行时使用的知识库数据
```

项目中的原始培训资料、视频处理流水线、缓存和大文件未纳入版本库；它们不是启动网页所必需的。
