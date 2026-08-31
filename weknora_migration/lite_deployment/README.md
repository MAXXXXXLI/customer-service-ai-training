# WeKnora Lite 原生部署（Ubuntu 22.04）

这套文件部署项目已经确定的 PoC 形态：WeKnora `v0.7.2` Lite、SQLite FTS5 + sqlite-vec、SiliconFlow 远程模型、现有培训应用，并且不使用 Docker。API/二进制固定到官方标签提交 `3d5d8bfcdfeeea266b292b71cea616847af28d0f`；该标签的 Lite SQLite schema 存在官方确认的缺口，因此只回移官方已合并提交 `71fe7f31ee7f4eaced1827b6a83c93dc41e5f204` 中的 SQLite `000003`–`000011` 迁移，最终 schema 版本固定为 11。构建工具固定为 Go `1.26.0` 与 Node.js `22.23.2`。默认并发参数按 4 核 8 GB 主机收敛，并建立 8 GiB swap。

## 边界与端口

- WeKnora 同时提供管理 UI 和 API，但只监听 `127.0.0.1:8080`。
- 现有培训应用只监听 `127.0.0.1:8787`，浏览器问题、答题、陪练、评分等前端逻辑不改。
- Nginx 模板只代理培训应用到 TCP 80，并强制 Basic Auth；它显式拒绝 `/api/v1/`、`/health`、`/swagger/` 和 `/weknora/`，不代理 WeKnora。
- `prepare_server.sh` 首次执行不启动 Nginx，也不创建公网入口。只有人工运行 `enable_public_entry.sh` 才会开放培训应用；若入口以前已显式启用，重跑准备脚本会在校验后重载它。
- 个人验证推荐只使用 SSH 双隧道：本地 `18080` 转发培训应用 `8787`，本地 `18081` 转发 WeKnora `8080`。这样不开放 80/8080/8787 也能完整自测。

在本地电脑执行一条长连接（把用户名和服务器地址替换为实际值）：

```bash
ssh -N \
  -L 18080:127.0.0.1:8787 \
  -L 18081:127.0.0.1:8080 \
  USER@SERVER
```

保持该 SSH 连接运行，然后在本地浏览器打开：

- 培训应用：`http://127.0.0.1:18080`
- WeKnora 管理页：`http://127.0.0.1:18081`

当前只做个人效果验证时，不要运行 `enable_public_entry.sh`，云安全组也不需要开放 TCP 80。只保留受限制的 SSH 入口即可。

Basic Auth 在纯 HTTP 上不会加密密码，只适合短期验证。云安全组应把 80 限制为可信源 IP；8080 和 8787 不得放行。SSH 端口也应限制来源。正式对外使用时应补域名和 HTTPS，而不是继续使用明文 Basic Auth。

## 服务器目录

```text
/opt/training-kb/
├── current -> releases/<release-id>
├── previous -> releases/<release-id>
└── releases/
    └── <release-id>/
        ├── RELEASE_MANIFEST.env
        ├── RELEASE.sha256
        ├── weknora/
        └── training-app/

/var/lib/training-kb/weknora/   # SQLite 与上传文件，weknora-lite 用户独占
/etc/training-kb/*.env          # root:root 0600
/var/backups/training-kb/       # root:root 0700
```

代码版本通过 `releases/<id>` 与 `current` 原子软链发布；状态数据不放在 release 内，因此切换代码不会覆盖知识库。WeKnora 和培训应用分别使用 `weknora-lite`、`training-app` 两个无登录权限的系统用户。

## 1. 上传项目

GitHub 仓库不包含被 `.gitignore` 排除的私有 `weknora_migration/bundle/`。应从可信电脑通过 SSH/rsync 把完整项目和 bundle 传到服务器，例如 `/srv/customer-service-ai-training`。不要把任何 API Key 提交到 GitHub。

全新 Ubuntu 的 `/srv` 由 root 持有，而且可能没有预装 rsync。先在本机执行一次：

```bash
ssh tencent-weknora \
  'sudo apt-get update && sudo apt-get install -y rsync ca-certificates && sudo install -d -o ubuntu -g ubuntu -m 0750 /srv/customer-service-ai-training'
```

再从交付包目录上传：

```bash
rsync -a --delete \
  ./project/customer-service-ai-training/ \
  tencent-weknora:/srv/customer-service-ai-training/
```

## 2. 准备 Ubuntu 主机

```bash
cd /srv/customer-service-ai-training/weknora_migration/lite_deployment
sudo ./scripts/prepare_server.sh
```

脚本会幂等完成以下操作：

- 校验 Ubuntu 22.04 和 CPU 架构；
- 从 go.dev 与 nodejs.org 下载固定版本，并校验此目录固定的官方 SHA-256；
- 安装 GCC、`libsqlite3-dev`、SQLite FTS5、Nginx、Python 等依赖；
- 创建并启用恰好 8 GiB 的 `/swapfile`，重复执行不会重复写 `/etc/fstab`；
- 创建两个独立服务用户和状态目录；
- 生成新的 `SYSTEM_AES_KEY`（恰好 32 ASCII 字节）与 JWT 随机值到 `/etc/training-kb/weknora.env`，不打印密钥；v0.7.2 Go 主程序不再读取废弃的 `TENANT_AES_KEY`；
- 创建 `/etc/training-kb/training.env` 空密钥模板；
- 安装 systemd unit 和未启用的 Nginx 配置。

如果已有 `/swapfile` 不是恰好 8 GiB 或不是有效 swap，脚本会停止，避免覆盖未知文件。

## 3. 构建并原子发布

```bash
sudo ./scripts/prepare_release.sh /srv/customer-service-ai-training
```

脚本从官方标签检出源码并再次核对完整 commit，校验随交付包固定的官方 SQLite 修复文件 SHA-256，再运行 `npm ci`，并以 `CGO_ENABLED=1` 和 `sqlite_fts5` 构建 Lite。为适配 4 核 8 GB，Node 构建内存上限为 3 GiB，Go 构建并行度为 2；SQLite 运行任务池 `CONCURRENCY_POOL_SIZE` 固定为 1，避免批量导入时并发写竞争。它只把运行所需的 `local_app/`、`knowledge_base/` 和固定 WeKnora 产物放入新 release，将整个 release 固定为 `root:root` 且移除组/其他用户写权限，生成全文件 SHA-256 后才切换 `current`。发布激活、回滚与独立备份共用非阻塞互斥锁，防止多个管理操作交叉改写软链或备份出不一致状态；激活或健康检查失败时，会把原 `current` 和原 `previous` 两个软链一起恢复，重启原 release 并再做一次基本验证，不会把“只恢复软链但服务未恢复”误报成成功。

首次发布后两个服务已经运行，但培训检索仍会因空的运行 Key 保持 fail-closed。这是有意的，不会退回旧的本地 RAG。

## 4. 配置与导入知识库

通过 SSH 隧道打开 WeKnora，配置 SiliconFlow 的 Chat、Embedding 和 Rerank 模型。随后使用迁移目录现有的验证、模型配置和导入工具，把 Runtime 内容导入 Lite 的单一空间。Lite 不提供标准版双 Tenant；`KB-AUDIT-RAW` 不应导入这台面向效果验证的运行实例。

首次填写 SiliconFlow Key 时，优先使用隐藏输入的原子写入工具；密钥不会回显或进入命令参数：

```bash
sudo python3 ./scripts/set_siliconflow_key.py
```

在服务器上运行迁移工具时，必须显式使用 WeKnora 的服务器本机端口；`18081` 只是个人电脑上的 SSH 隧道端口：

```bash
cd /srv/customer-service-ai-training/weknora_migration
export WEKNORA_URL=http://127.0.0.1:8080
python3 verify_bundle.py
```

导入完成并创建仅含 `retrieve` 权限、非空知识库 allow-list 的 API Key 后：

```bash
sudoedit /etc/training-kb/training.env
sudo chmod 0600 /etc/training-kb/training.env
sudo chown root:root /etc/training-kb/training.env
sudo systemctl restart training-app.service
```

至少填写：

```text
SILICONFLOW_API_KEY=<服务器端模型调用密钥>
WEKNORA_RETRIEVE_API_KEY=<仅 retrieve 权限的运行密钥>
WEKNORA_KB_IDS=<允许培训应用检索的非空 KB ID，多个用逗号分隔>
```

可选的讯飞在线语音合成也由后端代理：填写模板中的 IFLYTEK_TTS_* 项后，
POST /api/tts 返回 MP3 或 PCM 音频；未配置时安全返回 503。凭据只存于
服务器的 0600 env，不会下发到浏览器。推荐使用讯飞控制台的 APIPassword，
也可以填写 APP_ID/API_KEY/API_SECRET 让后端生成 HMAC 签名。契约回归：
python3 local_app/iflytek_tts_regression_test.py。

语音输入使用同一应用的讯飞流式语音听写（IAT）服务：浏览器最多录制 30 秒，
在本机转换为 16 kHz 单声道 PCM 后调用受保护的 `POST /api/asr`；服务端完成
HMAC 鉴权并把文字回填到共享对话输入框，员工确认后才会发送给智能接待、陪练
或模拟考核。必须在讯飞控制台启用“语音听写（流式版）”。IAT 只接受完整的
APPID/APIKey/APISecret，不能复用仅供 TTS 使用的 APIPassword；可在
`IFLYTEK_IAT_*` 中单独填写，或留空复用完整的 `IFLYTEK_TTS_*` HMAC 三元组。
`GET /api/asr/status` 仅返回非敏感的配置状态。契约回归：
`python3 local_app/iflytek_asr_regression_test.py` 与
`node local_app/static_voice_input_regression_test.js`。

首次配置可在服务器交互终端执行（输入内容不会回显，也不会进入命令参数）：

```bash
sudo -H python3 /srv/customer-service-ai-training/weknora_migration/lite_deployment/scripts/set_iflytek_tts_credentials.py
sudo systemctl restart training-app.service
curl -fsS http://127.0.0.1:8787/api/tts/status
```

若语音听写使用独立的 IAT 凭据，在同一个安全终端执行：

```bash
sudo -H python3 /srv/customer-service-ai-training/weknora_migration/lite_deployment/scripts/set_iflytek_asr_credentials.py
sudo systemctl restart training-app.service
curl -fsS http://127.0.0.1:8787/api/asr/status
```

该工具的 APIKey/APISecret 输入不会回显，也不会进入命令参数。若 IAT 与 TTS
使用同一套完整 HMAC 三元组，不必填写独立 IAT 字段，重启后检查
`/api/asr/status` 即可。

终端用户不需要填写任何 API；凭据只保存在服务器 `/etc/training-kb/training.env`（root:root、0600）。

密钥只存在服务器的 0600 env 和 WeKnora 加密数据库中，不应出现在命令行、聊天记录、Git 或浏览器代码里。

## 5. 验证

```bash
sudo ./scripts/verify.sh --basic
sudo ./scripts/verify.sh
```

`--basic` 验证固定版本、release 哈希、systemd 用户、环境文件权限、SQLite 模式、进程和端口绑定。首次发布尚未配置 Runtime Key 时，它还要求培训应用准确返回 fail-closed 的结构化 HTTP 503；配置完成后则要求健康检查为 HTTP 200。若已启用 Nginx，验证会按入口类型选择端口：Quick Tunnel 检查源站只绑定 `127.0.0.1:8088` 且匿名请求返回 401，自有域名 HTTPS 和旧的 80 端口入口也分别检查 Basic Auth。严格模式要求三个运行配置非空、健康提供方为 WeKnora，并实际调用一次检索，确认返回结果没有越出 `WEKNORA_KB_IDS`。

## 6. 可选：受保护的公网入口

默认仍推荐 SSH 双隧道。若需要把培训页面交给别人短期验收，只选下面两种方案之一。两种方案都只代理 `127.0.0.1:8787` 的培训应用，不代理 WeKnora `127.0.0.1:8080`，并且都使用 Basic Auth。凭据只保存在 root-only `0600` 文件 `/etc/training-kb/public-access.json`。

### 6.1 短期调试：Cloudflare Quick Tunnel

不需要域名，也不需要在腾讯云放行 80/443；服务器主动建立出站隧道：

```bash
sudo ./scripts/enable_quick_tunnel.sh
sudo systemctl status training-quick-tunnel.service --no-pager
sudo cat /var/lib/training-tunnel/public-url.txt
```

脚本会安装 Cloudflare 官方 `cloudflared` 软件源、生成随机 Basic Auth 密码，并把 Nginx 源站仅绑定到 `127.0.0.1:8088`。如果明确需要任何人无需登录即可访问，可改用 `sudo ./scripts/enable_quick_tunnel.sh --anonymous`；匿名模式仍只代理培训应用，不代理 WeKnora，并对 `/api/` 启用每访客限速、并发限制和 512 KiB 请求体上限。Quick Tunnel 是 Cloudflare 的测试功能：URL 在隧道重建后可能变更，没有生产 SLA，不应作为正式网站地址。本脚本依赖当时 Cloudflare 官方 APT 源内容，因此也不是完全离线、固定字节级可复现的供应链路径。

### 6.2 长期入口：自有域名 + HTTPS

先把域名 A 记录指向服务器公网 IP，并在云防火墙临时允许 TCP 80/443，然后执行：

```bash
sudo ./scripts/enable_public_entry.sh kb.example.com
```

脚本使用 Certbot 申请 HTTPS 证书，开启 80 跳转 443，并保留 Basic Auth。UFW 不能替代腾讯云防火墙；不得在任何一层开放 8080/8787。

切换入口前先停掉旧方案，并把旧凭据文件作为 root-only 历史文件留存，让新方案生成新凭据：

```bash
sudo systemctl disable --now training-quick-tunnel.service 2>/dev/null || true
sudo mv /etc/training-kb/public-access.json \
  /etc/training-kb/public-access.previous.json
```

若从自有域名改回 Quick Tunnel，同样先停 Nginx 的公网 80/443 入口、撤销云防火墙规则，再运行 `enable_quick_tunnel.sh`。

## 7. 备份与回滚

```bash
sudo ./scripts/backup.sh
sudo ./scripts/rollback.sh
```

备份会短暂停止两个服务，保存 SQLite/上传文件、两个 0600 env、systemd/Nginx 配置以及当前 release 的 manifest 与哈希清单，再原子生成权限 0600 的 tarball 与 SHA-256。完成或中途失败后，脚本都会按操作前状态重启服务并等待健康端点；恢复失败会显式返回错误，不会静默报告备份成功。备份包含密钥，应复制到加密的异机存储。

回滚默认先备份，再把 `current` 原子切换到 `previous`，启动并做基本验证；失败会同时恢复操作前的 `current` 和 `previous`。也可以指定已存在的 release ID：

```bash
sudo ./scripts/rollback.sh 20260826xxxxxx-abcdef123456
```

回滚只切换同一固定 WeKnora commit 的应用 release，不自动倒退 SQLite 数据。需要恢复历史数据时，应先停服务、核对备份 SHA-256，再由管理员从备份恢复；不要把未知版本数据库覆盖到运行实例。

## 本地静态检查

```bash
./scripts/static_check.sh
```

该检查覆盖全部 Bash 语法、固定用户和端口、Nginx 不代理 WeKnora，以及目录内没有形似真实的 SiliconFlow/WeKnora 密钥。它还会运行本地 fixture，验证 Quick Tunnel 的 `127.0.0.1:8088`/401 门禁和发布失败时两个 release 软链的恢复语义。
