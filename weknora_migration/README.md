# 秀域 / 春语知识库迁移包（WeKnora v0.7.2）

本目录把当前项目的最新知识资产整理成一套可重复生成、可审计、可审批、可导入的 WeKnora 迁移包。它包含数据分层、源快照、部署锁定、模型创建、双租户导入、FAQ 审批发布、最小权限密钥和回归验证，不是只有选型建议。

当前迁移包版本：`2026-08-27-weknora-v6`。

## 最终选型

首选 [Tencent WeKnora](https://github.com/Tencent/WeKnora)，生产固定在 [v0.7.2](https://github.com/Tencent/WeKnora/releases/tag/v0.7.2) / `3d5d8bfcdfeeea266b292b71cea616847af28d0f`，不使用 `latest` 或 `main`。

它适合本项目的原因：中文管理界面完整，同时支持文档库、FAQ 直答、混合检索、重排、引用、多标签和 REST API；现有培训系统可以继续保留 FAQ 精确匹配、安全闸门、陪练与评分逻辑，只把检索层替换为 WeKnora。

同期评估过的现代方案包括 [RAGFlow](https://github.com/infiniflow/ragflow)、[Onyx](https://github.com/onyx-dot-app/onyx)、[Open Notebook](https://github.com/lfnovo/open-notebook)、[SurfSense](https://github.com/MODSetter/SurfSense)、[PandaWiki](https://github.com/chaitin/PandaWiki) 和 [DocsGPT](https://github.com/arc53/DocsGPT)。它们分别更偏重重型解析、跨应用企业搜索、个人研究、持续网页情报、公开帮助中心或开发者问答；本项目更需要中文治理、FAQ 状态控制、服务端接入和内部资料隔离，因此选择 WeKnora。

### 现代方案适配对比

| 方案 | 最适合的场景 | 对本项目的适配 | 本次结论 |
|---|---|---:|---|
| WeKnora v0.7.2 | 中文内部知识库、FAQ、引用问答、API 接入、私有部署 | 很高 | 首选；继续做现有培训前端的检索后端 |
| RAGFlow | 扫描 PDF、复杂表格、版面解析质量优先 | 高 | 作为重型解析基准或第二阶段增强；部署资源与运维更重 |
| Onyx | 企业连接器、跨 SaaS 搜索、大团队协作 | 中高 | 若未来主要需求转为连接 SharePoint、Slack 等再评估；CE/EE 能力边界需逐项核对 |
| Open Notebook | 个人研究、笔记、播客、多模型 NotebookLM 体验 | 中 | 适合个人学习，不适合作为本项目的员工/顾客/审计治理主平台 |
| SurfSense | 实时网页、社媒、视频情报与自动简报 | 中 | 适合外部舆情支线；官方仍标注未达到 production-ready，且含混合许可证目录 |
| PandaWiki | 对外产品文档、帮助中心、公开站点 | 中 | 若只做公开顾客帮助中心会很顺手，但不负责本项目的内部培训与审计隔离 |
| DocsGPT | 开发者文档助手、嵌入式问答、API | 中 | 适合作为轻量开发者助手；当前治理需求仍需较多自建 |

选择不是只看 GitHub 热度，而是按本项目的六个硬条件：中文资料、FAQ 直答与问法别名、员工/顾客/安全/审计隔离、审核后才能发布、可由现有系统经 REST 调用、模型可走国内 API 且服务器无需 GPU。若未来核心资料变成大量扫描件，应保留 WeKnora 作为治理与服务层，再单独评估 RAGFlow 或 MinerU 解析链路，而不必重做整个权限和审批体系。

## 五库、双租户结构

| 租户 | 知识库 | 类型 | 导入内容 | 首次状态 |
|---|---|---|---|---|
| Runtime | `KB-STAFF-COURSES` | document | 43 课、知识卡增量、安全重写的异议训练、分类目录，共 45 文档 | 员工可用 |
| Runtime | `KB-CUSTOMER-PROVISIONAL` | faq | 43 条当前 FAQ，加历史 105 个 covered 主问题及 5 个别名折叠成 6 条，共 49 条 | 全部停用、待签字；其中 1 条阻止发布 |
| Runtime | `KB-SAFETY-POLICY` | document | 合规规则、服务流、回答顺序、主题、意图、关键失败，共 1 文档 | 仅员工/后台；待具名审核后再讨论顾客开放 |
| Runtime | `KB-SAFETY-BOUNDARY` | faq | 536 个 boundary-only 问法折叠成 9 个唯一边界答案 | 全部停用、待双人审核 |
| Audit | `KB-AUDIT-RAW` | document | 当前资料、历史抽取、待审视频、缺材料题、考试、报告和分类源，共 73 文档 | 独立租户，仅管理员/审核人 |

之所以是五库，是因为 WeKnora 的 document 和 FAQ 需要不同物理库；之所以是双租户，是因为 WeKnora v0.7.2 的知识库创建接口没有 `access_policy` / ACL 字段。本包中的 `access_policy` 是治理意图，不是服务端授权。审计库靠独立 Tenant 隔离，Runtime 内部再靠非空、精确的 KB allow-list API Key 隔离。

普通员工和顾客不应直接进入 WeKnora 管理 UI。管理 UI 只给管理员和审核人；普通用户通过业务后端使用 scoped retrieve Key。WeKnora 的空 `knowledge_base_ids` 代表“全部可见库”，绝不能用空列表表达“无权限”。

## 已完成的数据整理

- 正式课程权威源锁定为 `knowledge_base/秀域企业完整知识库_高密度整合版_2026年8月.md`。
- 精确规模：10 模块、43 课、129 小节、931 正文段、516 分钟、43 张知识卡、86 个卡内练习问题。
- 没有重复上传 `knowledge_cards.content`、129 个课程 RAG 副本或 43 个 FAQ RAG 副本。
- 两份 8 月 24 日 DOCX 只生成 taxonomy：2 个体系、10 模块、43 课、424 个叶标题，不作为第二份事实正文向量化。
- 历史 1,031 个 FAQ 分为：105 `covered`、536 `boundary_only`、390 `material_missing`。390 个缺材料问题只进审计库。
- `FAQ-XLS-0002` 作为独立稳定 ID 携带 5 个别名进入待审 FAQ；由于业务建议话术与当前安全课程存在冲突，它被标记为高风险、必须独立双审且 `publication_blocked=true`，审批脚本无条件拒绝将其发布。
- 43 个视频复核项全部保持 `pending_review=true`、`excluded_from_customer_rag=true`；考试答案、场景隐藏答案与评分点都只进审计库。
- `OB-001` 的过期促销话术不进入运行库。
- 旧 `source_registry.json` 有 35 个来源；本包通过 `source_registry_extension.json` 补登权威源后有效来源为 36 个。
- 源快照共 72 文件：当前工作区 33（含点阵波 FAQ 关键词考试源）、两份 taxonomy DOCX 2、当前可取得的 SRC-035 原始 XLS 1、历史交付包抽取稿 36。清单只记录 `project/`、`source_inputs/` 逻辑路径，不泄露工作站绝对路径；历史抽取稿不冒充已经找回的原 PPT / Word / PDF / MP4。

## 目录内工具

- `build_bundle.py`：从当前项目、两份 DOCX、历史交付包和可取得原件重建五库包。
- `bundle/`：生成后的完整迁移数据、源快照与哈希清单；已被 `.gitignore` 排除，禁止推送到公开 GitHub。
- `verify_bundle.py`：验证权威源复现、数量、哈希、去重、行号、问答映射、风险隔离和确定性重建。
- `setup_models.py`：幂等创建 SiliconFlow Embedding / Rerank / KnowledgeQA 模型，不把上游密钥写入收据。
- `import_bundle.py`：按 Runtime / Audit 两个 Tenant 走 REST 导入，支持幂等状态、FAQ 缺陷补丁、回读和检索验收。
- `approve_faq.py`：按完整审批清单、内容哈希、审核人、日期和双审规则逐条发布 FAQ，并保存远端快照摘要。
- `setup_access_keys.py`：创建并验证 `full_access=false`、`capabilities=[retrieve]`、非空 KB allow-list 的运行 Key。
- `deployment/`：固定五个默认镜像 digest 的 Linux 部署配置、安全自举、运行态断言和注册锁定脚本。
- `tests/test_import_bundle.py`：用本地仿真 v0.7.2 API 测试模型、双租户导入、幂等重跑、审批和权限配置。

## 1. 从零重建并验证

```bash
cd /path/to/customer-service-ai-training
python3 weknora_migration/build_bundle.py
python3 weknora_migration/verify_bundle.py --rebuild-check
python3 -m unittest discover -s weknora_migration/tests -v
```

当前正式结果：`4,132` 项 bundle 检查通过，临时目录从零重建后逐文件哈希一致；`16` 个本地合约测试通过。验证内容包括课程精确复现、1,031 个历史问答逐题映射、顾客 FAQ 196 种问法、阻止发布的高风险业务建议例外、视频/考试/场景泄漏扫描、来源路径可携带性、不可变导入快照、远端文档 exact-set、双 Tenant、FAQ 全停用、审批发布、最小权限 Key、失败回滚和幂等重跑。

服务器交接包若同时携带四个外部原件，可通过便携路径再次做完整确定性重建：

```bash
export WEKNORA_SOURCE_INPUT_DIR=/path/to/source_inputs
python3 verify_bundle.py --rebuild-check
```

## 2. 部署 WeKnora

当前 Mac 只有 8 GB 内存、约 37 GiB 可用磁盘且未安装 Docker，不适合承载正式 WeKnora。建议：

- Ubuntu 22.04 / 24.04 x86_64
- 正式：8 vCPU / 32 GB RAM / 200 GB NVMe
- PoC 下限：4 vCPU / 16 GB RAM / 100 GB SSD
- 模型走 SiliconFlow API，无需 GPU
- Docker Engine 28+、支持 `config --format` / `up --wait` 的 Compose 插件、Python 3.9+、Git、curl、OpenSSL

把本迁移目录安全传到服务器后：

```bash
cd /path/to/weknora_migration
./deployment/prepare_server.sh /opt/weknora-v0.7.2
```

脚本会在全新绝对路径检出并校验官方 commit，在 `umask 077` 下生成密钥，以 digest 固定 UI / App / DocReader / ParadeDB / Redis，固定 Compose 项目名和空 profiles，清除 shell 对 `.env` 的覆盖，并断言只有前端与 API 绑定 `127.0.0.1:18080/18081`。数据库、Redis 和 DocReader 不发布宿主机端口。服务、健康状态、运行镜像和 HTTP 都通过后才报告成功。

脚本失败不会删除 checkout、数据库卷或知识数据；如服务可能已启动，只停止 App 和前端以关闭入口。

通过 SSH 隧道打开管理页：

```bash
ssh -L 18080:127.0.0.1:18080 <server>
```

创建第一个 Owner 后，如需平台级设置，可把 checkout 的 `.env` 中 `WEKNORA_BOOTSTRAP_SYSTEM_ADMIN_EMAIL` 设为该 Owner 邮箱；它只提升已存在用户，不创建账号。随后锁定注册：

```bash
./deployment/lock_registration.sh /opt/weknora-v0.7.2
```

锁定脚本只在 `GET /api/v1/auth/config` 返回 `invite_only`，且空的 `POST /api/v1/auth/register` 返回 `403` 时成功。数据库中的 `system_settings.auth.registration_mode` 优先于 `.env`；若仍是 `self_serve`，脚本会停止 App / 前端并失败关闭，需系统管理员修正数据库设置后重跑。

当前 Mac 没有 Docker，因此真实 `pull/up` 必须在目标 Linux 上完成；本地已通过 Shell 语法、Python 编译、官方 Compose 静态对照及 validator 正负向合成测试。

## 3. 模型配置

| 用途 | 默认模型 | 对应配置 |
|---|---|---|
| Embedding | `BAAI/bge-m3` | 1024 维，`source=remote`，`provider=siliconflow` |
| Rerank | `BAAI/bge-reranker-v2-m3` | SiliconFlow `/rerank` |
| KnowledgeQA / Summary | `Qwen/Qwen3.5-35B-A3B` | 中文问答；上线前用当前 SiliconFlow 账户做连通测试 |

模型是 Tenant 级资源，Runtime 和 Audit Tenant 各执行一次：

```bash
cd /path/to/weknora_migration
export WEKNORA_URL='http://127.0.0.1:18081'
export WEKNORA_API_KEY='<this-tenant temporary migration key>'
export SILICONFLOW_API_KEY='<siliconflow key>'
python3 setup_models.py
```

迁移 Key 需要 `manage_models`、`manage_kbs`、`ingest`、`retrieve`；用完应撤销。`model_ids.json` 只保存 WeKnora 模型 ID，不保存 SiliconFlow Key。不要把模型 `source` 写成 `siliconflow`，正确值是 `source=remote`，并在 `parameters.provider` 写 `siliconflow`。

## 4. 双租户导入

先查看两个计划：

```bash
python3 import_bundle.py --scope runtime
python3 import_bundle.py --scope audit
```

先导 Runtime。必须显式写预期 Tenant ID，防止拿错 Key：

```bash
export WEKNORA_API_KEY='<runtime migration key>'
export WEKNORA_EXPECTED_TENANT_ID='<runtime tenant id>'
export WEKNORA_EMBEDDING_MODEL_ID='<runtime embedding id>'
export WEKNORA_SUMMARY_MODEL_ID='<runtime chat id>'
python3 import_bundle.py --scope runtime --apply
```

再切换到不同的 Audit Tenant：

```bash
export WEKNORA_API_KEY='<audit migration key>'
export WEKNORA_EXPECTED_TENANT_ID='<audit tenant id>'
export WEKNORA_EMBEDDING_MODEL_ID='<audit embedding id>'
export WEKNORA_SUMMARY_MODEL_ID='<audit chat id>'
python3 import_bundle.py --scope audit --apply
```

Runtime 导入 46 个文档和 58 条 FAQ；Audit 导入 73 个文档。两个 Tenant ID 必须不同，Audit 导入必须先看到通过的 Runtime 收据。状态与收据分别写入：

- `import_state.runtime.json` / `import_receipt.runtime.json`
- `import_state.audit.json` / `import_receipt.audit.json`

收据同时绑定 bundle version、`bundle_manifest.json` SHA-256、服务器 URL 和 Tenant ID，不能跨版本、跨服务器或跨 Tenant 复用。

导入器先复制出只读、一次性的 bundle 快照，并只从该快照校验和上传，避免校验后文件被改写。它还会：拒绝含糊的同名库；验证库类型、模型和分块配置；逐文档核对 KB、MD5 与 bundle 元数据，并要求远端文档 exact-set；轮询文档到 `completed`；对 FAQ 先 dry-run 再 replace，且 dry-run 不取得知识库管理权；修复 v0.7.2 批量 FAQ 新建时丢失 `is_recommended` 的已知问题；回读全部 FAQ；做单库正向/停用负向检索测试。已有同名库默认不接管，`--adopt-existing-kbs` 和 `--replace-existing-faq` 都需要显式授权。

## 5. FAQ 审批与发布

导入器永远按 bundle 的安全默认值导入：顾客 49 条和边界 9 组全部停用。不要直接在 WeKnora UI 批量打开。`FAQ-XLS-0002` 即使在审批文件中填为 `approved`，发布器也会因 `publication_blocked=true` 拒绝变更远端状态。

把模板复制到被忽略的审核目录后填写：

```bash
mkdir -p review_inputs
cp bundle/customer_approved/approval_template.jsonl review_inputs/customer.jsonl
cp bundle/safety_boundary/approval_template.jsonl review_inputs/safety-boundary.jsonl
```

每一行必须保留 `external_id` 和 `content_sha256`，并填写 `decision=approved|rejected|pending`。批准项必须有 `review_owner`、`last_verified_at`、`effective_from`、`expires_on`；5 条可发布的高风险当前 FAQ 和全部 9 组安全边界还必须有不同的 `secondary_review_owner`。另有 1 条高风险业务建议例外 `FAQ-XLS-0002` 虽然保留双审要求，但当前阻止发布。日期按 Asia/Shanghai 的 `YYYY-MM-DD` 解释，未来生效或已过期都拒绝发布。

使用 Runtime Tenant 中同时具备目标 KB `retrieve + ingest` 权限的短期审批 Key：

```bash
export WEKNORA_API_KEY='<runtime approval key>'

python3 approve_faq.py --scope customer --approvals review_inputs/customer.jsonl
python3 approve_faq.py --scope customer --approvals review_inputs/customer.jsonl --apply

python3 approve_faq.py --scope safety-boundary --approvals review_inputs/safety-boundary.jsonl
python3 approve_faq.py --scope safety-boundary --approvals review_inputs/safety-boundary.jsonl --apply
```

发布器要求审批文件覆盖当前全部 external ID；先对真实 FAQ payload 重新计算 hash、检查日期和双审，再验证服务器/Tenant/KB/完整远端内容。远端变更前先原子写入 `status=applying`，使旧 passed 收据失效；之后按 FAQ 数字 ID 精确写 flags，最后重读 exact set、内容、flags 并生成 canonical snapshot 收据。`pending` 或 `rejected` 会保持/恢复停用；写入、回读、中断或收据落盘失败时会尝试把目标 FAQ 库全部停用，并记录 fail-close 是否完整成功。

`KB-SAFETY-POLICY` 当前也缺具名责任人与核验日期，因此只进入员工 Key，不进入顾客 Key；现有应用层确定性安全闸门继续生效。若未来要开放该文档给顾客，应先增加独立的政策审批发布流程。

## 6. 创建最小权限运行 Key

完成 Runtime 与 Audit 两次导入后，先创建员工 Key：

```bash
export WEKNORA_OWNER_JWT='<short-lived runtime-owner access token>'
python3 setup_access_keys.py --apply
```

顾客 FAQ 至少一条审核通过后才可创建顾客 Key：

```bash
python3 setup_access_keys.py \
  --create-customer \
  --customer-approval-receipt approval_receipt.customer.json \
  --apply
```

只有安全边界也已审核时，才加入两个 Key 的白名单：

```bash
python3 setup_access_keys.py \
  --create-customer \
  --customer-approval-receipt approval_receipt.customer.json \
  --include-boundary \
  --boundary-approval-receipt approval_receipt.safety-boundary.json \
  --apply
```

脚本会在发 Key 当天重新检查审批有效期，并把 Key 到期时间上限锁到所有依赖批准项中最早的 `expires_on`；然后用 Owner JWT 全量回读 FAQ，要求现场快照与审批收据完全一致。创建出的 Key 必须 `scope_type=tenant`、`full_access=false`、仅含 `retrieve`、KB allow-list 非空且精确。它还会做允许库正向检索、批准 FAQ chunk 命中、顾客到员工越权、Runtime 到 Audit 越权、写操作拒绝和到期时间回读，并在发 Key 后再次核对 FAQ 快照。新 Key 验收失败会撤销；若发 Key 期间审批快照漂移，所有受影响的本轮管理 Key（包括复用 Key）都会被撤销以保持 fail-closed。

明文 Key 只写到权限 `0600` 的 `runtime_access_keys.json`，不打印到终端、不放浏览器、不提交 Git。员工初始白名单是 `STAFF + SAFETY-POLICY`；顾客白名单只有已审核的 `CUSTOMER`，边界审核后才追加 `SAFETY-BOUNDARY`。

## 7. 分块与检索配置

| 库 | chunk | overlap | 策略 | parent-child |
|---|---:|---:|---|---|
| STAFF | 512 | 80 | heading | 4096 / 384 |
| CUSTOMER | 300 | 0 | FAQ question+answer / separate aliases | 关闭 |
| SAFETY-POLICY | 512 | 80 | heading | 关闭 |
| SAFETY-BOUNDARY | 300 | 0 | FAQ question-only / separate aliases | 关闭 |
| AUDIT | 1000 | 150 | auto | 4096 / 512 |

建议首版 Agent 参数：

```text
agent_mode=quick-answer
temperature=0.1
embedding_top_k=50
keyword_threshold=0.30
vector_threshold=0.15
rerank_top_k=10
rerank_threshold=0.20
faq_priority_enabled=true
faq_direct_answer_threshold=0.85
faq_score_boost=1.2
citation_enabled=true
web_search_enabled=false
fallback_strategy=fixed
```

员工 Agent 初始绑定 `STAFF + SAFETY-POLICY`；安全边界审批后可追加 `SAFETY-BOUNDARY`。顾客 Agent 只绑定已审核的 `CUSTOMER`，边界审批后可追加 `SAFETY-BOUNDARY`。`AUDIT-RAW` 永不绑定普通员工或顾客 Agent。

## 8. 现有培训系统接入

浏览器不能持有 WeKnora 或 SiliconFlow 长期 Key。业务服务端用 scoped retrieve Key 调用：

```http
POST /api/v1/knowledge-search
X-API-Key: <retrieve-only key>
Content-Type: application/json

{
  "query": "服务中胸闷头晕怎么办",
  "knowledge_base_ids": ["<an ID already inside this key's allow-list>"]
}
```

推荐流程：

```text
问题路由
 → FAQ 精确匹配
 → 确定性安全闸门
 → WeKnora retrieve-only 检索
 → 强制补入安全规则
 → 生成与引用映射
 → 输出后安全检查
```

WeKnora 不取代现有的红旗信号、医疗越权、动态价格核验和缺材料拒答。检索失败时回退到已有确定性 FAQ / 安全回答，不放开自由生成。

## 9. 现网安全事项

当前 GitHub Pages 工作流仍可能公开 RAG、1,031 个历史 QA、评分规则、真实考题和场景隐藏信息；浏览器代码还可能把 SiliconFlow Key 存入 `localStorage` 并直接调上游。本迁移包没有擅自改变现网或发布方式。正式切换前必须：

- 把员工系统迁入带登录的服务端，模型 Key 只保存在服务端。
- 停止 Pages 复制内部知识、考题、隐藏信息和 Prompt。
- 不提交 `bundle/`、`.env`、状态、收据、审核输入或明文 Key。
- 评估已经进入公开 Git 历史的内部数据；删除当前文件不能撤回历史公开内容。

## 当前唯一未完成步骤

本地整理、生成器、部署配置、导入器、审批器、权限 Key 工具和回归验证均已完成。当前没有可用的 Linux WeKnora 服务器、两个 Tenant、迁移 Key 和模型 ID，因此尚未对真实服务执行 `--apply`。下一步是在目标 Linux 上运行部署脚本，然后依次完成 Runtime 导入、Audit 导入、业务审批与 scoped Key 验收。
