# WeKnora Lite SQLite 官方迁移修复

WeKnora `v0.7.2`（commit `3d5d8bfcdfeeea266b292b71cea616847af28d0f`）的 Lite SQLite 迁移只到版本 2，但同版本运行代码已依赖后续表和列。官方问题记录为 [Tencent/WeKnora#2158](https://github.com/Tencent/WeKnora/issues/2158)。

本目录固定保存官方于 2026-08-20 合并的修复提交 [`71fe7f31ee7f4eaced1827b6a83c93dc41e5f204`](https://github.com/Tencent/WeKnora/commit/71fe7f31ee7f4eaced1827b6a83c93dc41e5f204) 中的 SQLite 迁移，并补齐该提交父版本已有的 `000003`、`000004`，使迁移序列从 v0.7.2 的版本 2 连续升级到版本 11。

这些文件只修复 SQLite schema，不替换 v0.7.2 的 API 或二进制源码。`prepare_release.sh` 会先核验 `SHA256SUMS` 和文件集合，再把它们加入固定标签源码的 `migrations/sqlite/`。`verify.sh` 会要求运行数据库为 `version=11, dirty=0`，并逐项核验官方问题涉及的表和列。
