# Beta.4 版本与发布收口计划

日期：2026-10-24。状态：**本地收口已完成，见[验收](27-beta4-local-release-acceptance.md)；远端操作未授权、未执行**。

## 目标与当前证据

把已在本地验收的累计改动整理为 `1.0.0-beta.4`，完成可追溯提交和新版本便携版验收。冻结新功能，不继续扩大 G5 缓存或引入数据库。

- 当前分支 `codex/beta4-progress-result-loop`，HEAD 为 `7ff61e7568a324b9d2e7a31161ff0b7927ca3f9b`。本轮 `git ls-remote --heads origin main` 返回同一提交，Beta.4 标签查询没有匹配项。执行前必须重查；未以标签查询代替 Release API 检查。
- 工作区包含大量已修改和未跟踪文件，HEAD 不能代表全部候选输入。不得清空工作区、整体 stash、强制重置或覆盖其他改动。
- [源码与客户端验收](24-source-review-client-acceptance.md) 的完整回归为 1381 passed、3 skipped；[隔离候选](25-isolated-portable-acceptance.md) 已通过打包验证，但版本仍为 Beta.3。这两项是历史验收证据，不能代替修改版本后的新检查。
- 版本定义位于 [product_info.py](../../product_info.py:20)，页面占位版本位于 [index.html](../../frontend/index.html:26)。本计划不修改它们。

## 本版本纳入范围

| 面向用户的结果 | 实现边界与验证依据 |
|---|---|
| 进度、排队、耗时与保守预估 | 沿用 G0 实现。缺少依据时显示阶段或未知，不虚构百分比和 ETA；配置已填写不代表认证或目录权限验证成功 |
| 更清楚的来源、结果保存与导出入口 | 沿用 G1；目录/文件打开继续使用已有受限接口，Markdown/ZIP 导出保持兼容 |
| 失败后显式复用转录，提交结果不明时先查询 | [main.py](../../backend/main.py:1515) 的查询与恢复管线；不自动重试付费生成，不宣称跨进程全局幂等 |
| 原转录时间区间对照、阅读目录与文本查找 | [transcript.py](../../backend/transcript.py:22) 的版本标识和区间定位；相邻文本重叠不能证明模型陈述真实 |
| 历史读取去重、手动刷新与过期响应保护 | [main.py](../../backend/main.py:1106) 默认继续新鲜读取；不声称已达到 300ms 目标 |
| 本机请求边界与原生客户端兼容 | [S0 验收](23-local-request-security-acceptance.md)；严格 Host/Origin/Fetch Metadata、关闭代理头信任，保留原生无 Origin 与 SSE |
| 便携测试只探测自己启动的服务 | [portable_smoke_common.ps1](../../scripts/portable_smoke_common.ps1:3)，不得回退探测其他同版本实例 |

保留 `product=Video2Knowledge`、`service=VideoToNo`、`api_compat=1`，新版本字符串为 `1.0.0-beta.4`。不迁移任务、模板或工作区格式，不改变一条视频生成一个 Markdown 的约定。

以下能力仅作为内部开发资产保留：G4 合成样例/规则检查/人工评审表、诊断字段合同、发布证据比较，以及显式测试替换才启用的历史缓存。不得包装为产品质量评分、已验证模型准确率、默认缓存加速或自动遥测。缓存模块仍有导入与失效依赖，不能直接删除文件来“排除实验功能”。

## 执行步骤与提交边界

### A. 固定清单与依赖

1. 重新读取适用规则、状态、tracked/unstaged/staged/untracked 清单；检查已有暂存内容，禁止一键 `git add .`。
2. 将每个文件标记为产品实现、测试、开发工具、文档或忽略的本地产物。排除 `.env`、workspace、凭据、真实笔记、模型、临时二进制及浏览器数据。
3. 检查关键导入：`task_repository` 与 `history_cache`、本机请求测试客户端、性能测试与 benchmark 脚本，以及 G4 工具对 G3 transcript 接口的依赖。
4. 保留 docs/quality 原始结果及其源码摘要，不将历史报告中的版本或哈希改写为 Beta.4。

### B. 整理为三个可验证提交

累计实现跨同一 main/UI/测试文件交织，不能按 G0、G1 名称强行拆出无法运行的中间状态。建议提交边界：

1. `feat: complete the reliable local note workflow`
   - 累计 backend、frontend、launcher、对应回归、tests/local_client、浏览器与历史基准脚本，以及两个便携 smoke 和共享归属检查。
   - 包含运行导入所需的实验缓存模块，但默认列表维持新鲜读取。
2. `test: add offline quality and release evidence tooling`
   - evaluate_notes、合成 fixtures、笔记评测与跨工具发布证据测试。实施时发现历史 benchmark 依赖 release_evidence → diagnostic_contract/quality_io，三个共享工具及诊断测试须进入提交 1；跨工具测试调用 evaluate_notes，随提交 2。依赖由独立暂存快照测试确认。
   - 必须在提交 1 后：[evaluate_notes.py](../../scripts/evaluate_notes.py:14) 导入新增 transcript 接口。
3. `chore: prepare Video2Knowledge beta.4`
   - 统一版本、发布工作流、README/设计/产品/状态文档和合成截图；历史阶段报告作为开发证据保留。
   - 页面版本和静态资源缓存标识同步更新；测试断言不得机械全局替换历史 Beta.3 证据。

每个待提交快照都在独立临时目录验证，不能用包含后续未提交文件的主工作区测试证明中间提交完整。若依赖检查证明需要调整分组，记录原因并保持最终范围；不强行拆分补丁。只有获得本地提交授权后才暂存、提交，不 amend 既有历史。

### C. 版本、文档与发布门禁

- 全量搜索旧版本，逐处区分运行时、测试 fixture 和历史证据。PE 数字版本保持产品既定规则，产品字符串与产物名必须为 Beta.4。
- 重写中英文 README 的当前能力、快速开始和已知限制，移走首屏堆叠的内部 G 阶段报告；保留六模板、归属、语言入口及明确的数据流向说明。
- PRD/DESIGN/DECISIONS/PROJECT_STATUS/TODO/PROJECT_SNAPSHOT 同步本地通过、候选通过、公开发布三个状态，不把上一版 DeepSeek 有限验收扩大为本版所有 Provider 验收。
- 重拍首页、进度/结果、历史或原转录对照的必要合成截图；标明 Beta.4，禁止私人路径、Key 或用户任务。
- `.github/workflows/release.yml` 当前在构建后直接执行 `gh release create --prerelease`。改为 **Draft Pre-release**，先验收该 Draft 的实际资产，再显式公开。Beta.4 发布说明覆盖新增行为和安全兼容边界。
- CI 使用 Python 3.11，本机候选使用现有 Python 3.13；两者产物不能共享验收结论或摘要。修改工作流后补静态门禁，实际 Actions 是否成功以远端结果为准。

## 本地验收顺序

1. 先针对版本/启动器、安全边界、恢复/转录、历史与前端运行相关测试；再运行完整 `.venv\Scripts\python.exe -m pytest -q -rs`。不得低于已有覆盖，不得新增跳过；逐项核对三个现有 Windows 符号链接权限跳过。
2. 执行 `node --check frontend/script.js`、截图及各 verify 脚本语法检查、`.venv\Scripts\python.exe -m pip check`、`git diff --check`，并检查暂存和未跟踪文件。
3. 使用合成数据验证 1440×900、1024×768、390×844 与亮/暗/系统主题九组组合；覆盖键盘焦点、设置关闭后焦点返回、无页面级横向滚动、结果操作、刷新乱序和原转录对照。不读取用户工作区。
4. 用现有 PyInstaller 6.22.3 和 `.venv`，在新的隔离 source/dist 构建 `Video2Knowledge-1.0.0-beta.4-portable.exe`。构建输入逐文件计算摘要并关联完整提交；不覆盖旧 dist、不把 Beta.3 EXE 改名充当新构建。
5. 核对新 EXE 名称、图标、Windows VersionInfo、大小、SHA-256；写新 `SHA256SUMS.txt`。旧候选 `f293e960…` 仅为历史证据。
6. 精确归属的隔离服务验证健康版本/产品/兼容字段/portable，分别验证新旧工作区环境变量，静态资源、六模板、历史分页/收藏重启、按需读取、来源预检、恢复与原转录对照。Host/Origin/metadata 拒绝与同源/原生 HTTP/MCP SDK SSE 均需通过。
7. SAPI 合成短中文 WAV，使用已缓存 Whisper small、CPU、离线 HF 完成 HTTP ASR，检查 JSON/MD/SRT/归档；直接 worker 协议或等效可核查证据确认实际模型、CPU 和退出码。缓存不全即停止，不下载。
8. 只结束本次精确进程，删除临时 WAV/工作区，保留无隐私候选和报告。无真实 LLM、飞书、媒体下载、登录或凭据使用。

通过后记录检查时间、源码/输入摘要、测试结果、跳过原因、构建环境、EXE 全量哈希和清理结果。若源码或构建输入再变更，重跑受影响验证并重新构建，不能沿用旧资产验收。

## 远端发布流程，须另行授权

1. 查询远端 main、目标标签及 Release API。远端推进或名称冲突即停止，不自动 rebase、不移动标签。
2. 本地候选全部通过后，快进合入 main 并推送，创建并推送注释标签 `v1.0.0-beta.4`，标签固定指向已验收提交。
3. 默认等待修改后的工作流生成 Draft Pre-release。若自动流程未启动，只在获授权后手工创建缺失的 Draft 并上传已验收本地资产；禁止与工作流并行抢建或覆盖资产。
4. 下载 Draft 的实际 EXE 和校验文件，核对 GitHub digest、文件哈希和大小。在同一隔离合同下重跑打包客户端/安全/历史与离线 ASR。CI 产物与本地产物不同，必须验收下载到的那一份。
5. 下载资产验收通过才公开 Draft，回读标签目标、prerelease 状态、非 draft、资产摘要与名称。失败时保持 Draft，记录证据；只修复缺失步骤，不删除远端历史或移动标签。
6. 单独提交、推送公开发布证据，发布标签不随之移动。

## 授权与停止条件

用户随后“授权继续”已明确授权本地版本/工作流修改、暂存与聚焦提交、合成截图、隔离构建和缓存 ASR。远端推送、标签及发布仍需另行授权。

- 下一段本地执行需明确包含：版本与工作流修改、合成截图、隔离构建/缓存 ASR、聚焦暂存及本地提交。只用现有依赖，不安装或升级。
- 远端执行需单独明确包含：快进 main、push、注释标签、Draft/资产创建下载、验收后公开，以及发布证据推送。
- 两段均不包含真实 LLM、读取 Key、下载模型/媒体、平台登录、飞书写入、强推、仓库改名或新功能。
- 新安全缺陷、数据损失、测试新增跳过、候选摘要不符、外部推进或需要未授权依赖时停止对应分支，先记录具体证据，不能降低门禁。

## 完成标准

- 本地准备完成：版本一致、三个或经说明调整的完整提交可独立验证、新 Beta.4 候选和全部本地门禁通过；明确尚未发布。
- 公开阶段完成：实际下载的发布资产通过验收，Release 公开为 Pre-release，远端状态与摘要回读一致，证据文档已提交。
- 性能 300ms、清洁 Windows 新机、真实 Provider/平台普遍兼容均保持未达成或未验证，不列为发布成果。
