# G0 源码本地验收记录

日期：2026-10-22。执行方式：主对话直接实现，未调用 worker 或子智能体，未切换模型。

## 结论与边界

G0.1–G0.4 的代码修复、自动化回归与隔离浏览器验收已通过。当前仍是未发布工作区，运行时版本保持 `1.0.0-beta.3`，不代表已生成新的便携版。

- 分支：`codex/beta4-progress-result-loop`。
- HEAD：`7ff61e7568a324b9d2e7a31161ff0b7927ca3f9b`，未改变。
- 保留进入阶段时已有的 13 个 tracked 修改与设计文档；未 stage、commit、push、tag、build 或 release。
- 没有安装依赖、下载媒体/模型、访问真实 Provider、读取已有 Key、平台登录或飞书写入。
- 一视频对应一 Markdown、模板和任务请求格式、下载/ASR 引擎、目的地与发布管线保持原合同。

## 修复与证明

| 检查点 | 复现的问题 | 修复与证据 |
|---|---|---|
| G0.1 | 同归档目录 `.exe/.lnk/.url/.html` 被作为结果打开；resolve 隐去 junction；校验后替换未拦截 | 只选 `.md`，检查解析前各级目录、重解析点、硬链接与身份；打开前复查；非法归档回退安全内部文件；无法确定时固定 404。真实 Windows junction 与硬链接、模拟 reparse 组件及文件替换均有回归，系统打开全部 mock |
| G0.1 兼容 | 默认目的地可以合法存储为 null；旧清单无关 runtime 字段可能损坏 | null 继续表示默认归档；打开未预加载结果只读取安全清单摘要，不加载完整笔记或解析无关计时字段 |
| G0.2 | 多 P 下一页下载重置到 25%；未知总时长误显示百分比；前页/反序/取消后的回调覆盖状态 | 累计仅包含需 ASR 的页，未知总量不映射当前页百分比；回调令牌限定当前转录阶段，忽略重复/倒序事件；非有限数值不进入 JSON；取消、结束及前端停止立即清除 ETA |
| G0.2 文案 | ETA 容易被理解为整项任务耗时 | 明示“转录阶段预计剩余”，保持范围与设备速度提示；未知总时长显示已转录时间；Paraformer 不承诺测量型 ETA |
| G0.3 | Key 已提供被说成可用；路径已填被说成就绪；pending 未计数；旧平台提示跨输入残留 | Key 连接/权限未验证、目录未验证可写；pending 与模板 loading/error 单独展示；输入变化立即清空旧预检，迟到响应不得恢复旧提示 |
| G0.3 隐私 | DESIGN / Release 说明笼统宣称所有处理或数据都在本机 | 页面与文档明确本地 ASR、云模型接收转录、可选飞书接收发布内容；workflow 只改说明文字 |
| G0.4 浏览器发现 | 检查卡片伪元素挤占网格，标签与详情错位；窄屏任务条被多行顶栏覆盖 | 显式两行网格；任务条按顶栏实际高度定位并监听高度变化；加入真实 DOM 几何与遮挡断言 |

新增用例先在缺陷实现上失败，再修改实现。没有以增加跳过项处理安全验证失败。

## 自动化结果

环境：Windows，项目 `.venv` 的 Python `3.13.7`，Node `v24.2.0`，使用已安装依赖。

```text
.venv\Scripts\python.exe -m pytest -q -rs
796 passed, 3 skipped in 57.90s

node --check frontend/script.js
node --check scripts/capture_readme_screenshots.mjs
node --check scripts/verify_g0_browser.mjs
全部通过

.venv\Scripts\python.exe -m pip check
No broken requirements found.

git diff --check
通过
```

三个跳过仍为原有 Windows 符号链接创建权限限制，位于 `test_api.py`、`test_asr_process.py`、`test_media_retention.py`。本阶段没有新增跳过；结果打开的真实 junction 与硬链接用例已实际运行通过。不能把这理解为所有系统、所有文件系统链接类型均完成实机验收。

主要新增测试：

- `tests/test_result_access.py`：30 项结果路径、类型、身份与旧清单回归。
- `tests/test_progress_reliability.py`：37 项计算/状态边界及完整合成多 P 管线回归。
- `tests/test_frontend_hygiene.py`：补充 readiness、阶段 ETA、来源迟到响应、停止态与顶栏测量行为。

## 浏览器验收与复现

`scripts/verify_g0_browser.mjs` 复用已有截图脚本的 CDP 工具，无新依赖。在一个全新临时 workspace 服务上运行；真实后端请求仅允许 health、tasks、note-templates。Key 状态、模型缓存、登录与集成状态使用合成 fixture；结果打开也拦截为模拟失败，不启动任何系统应用。

矩阵：1440×900、1024×768、390×844，分别覆盖亮色、暗色、系统主题，共 **9 组通过**。系统主题这一轮模拟系统暗色。验证：

1. readiness 文案、字幕免 ASR、未验证 Key/目录说明。
2. 检查卡片标签与详情对齐且未被裁切。
3. 真实 Enter 打开设置、Escape 关闭并返回焦点。
4. 阶段进度和 ETA 可见，取消后隐藏；任务条没有被顶栏遮挡。
5. 结果按钮可达、Tab 顺序、可见焦点、打开失败时固定提示与路径保留。
6. 页面没有整体横向滚动；没有非白名单请求。

本地证据（被 `.gitignore` 排除）：`.test-tmp/g0-acceptance-20261022/` 下 27 张合成截图和 `browser-results.json`。已人工查看代表性的桌面进度、移动端 readiness、移动端结果及修复后任务条截图；没有用户媒体、真实凭据或用户任务标题。

复现命令，须先在独立 workspace 启动本机服务：

```powershell
node scripts/verify_g0_browser.mjs http://127.0.0.1:<隔离端口>/ <证据输出目录>
```

## 清理与残余限制

- 本次 Chrome 及其临时 profile 已由脚本关闭/清理；隔离后端在 8017，由本次会话终止。用户原有 8000 服务未操作。
- 删除临时 workspace 的命令被工具执行策略拦截，未改用其他删除手段绕过。`%TEMP%\Video2Knowledge-g0-20261022-233920` 保留空目录结构，检查时文件数为 0，不含媒体或凭据。此项环境清理尚未完成，不影响源码验收；截图证据按计划保留。
- 默认程序打开采用路径分发，最后一次检查到系统应用查找之间仍有竞争窗口；没有宣称提供沙箱。UNC、带链接/重解析点的祖先目录和硬链接保守拒绝；无安全内部文件时不会自动打开。
- 本轮没进行真实默认 Markdown 应用启动、Windows EXE 构建、打包态 ASR、真实模型性能或真实 LLM 验证。
- 现有中间件按回环客户端过滤，没有在本阶段改变 Host/Origin 策略。未来发布前应单独审查浏览器来源与本地访问安全，不应以文件路径测试代替整个本地服务安全审计。
- 浏览器中的进度和结果为合成 UI 状态；后端完整流的证据来自 fake ASR/合成字幕测试，不代表真实视频端到端已重验。

## 下一步

本轮止于 G0。下一产品阶段建议 G1“来源先行与轻量阅读器”，按现有路线图独立落实验收条件。G2 存储重构、G3 原文对照和发布需要后续明确范围，未在本次顺带实施。
