# Video2Knowledge Design — Knowledge Studio

- Status: Active
- Date: 2026-10-21
- Applies to: `frontend/` Web UI、`sources/icon.png` / `sources/icon.ico` 品牌资产

## Source of truth

本文件是 Video2Knowledge 界面与品牌资产的唯一设计基线。视觉 token 的实现位置是
`frontend/style.css` 的 `:root` / `html[data-theme=...]` 自定义属性；品牌图形的构造规则与
取色同时记录在 `scripts/make_brand_assets.py` 的 docstring 中。两者必须与本文件保持一致：
改 token 或标志构造时，先改本文件，再改实现，并在 PR/提交说明里指出三者同步。

参考但不作为基线的文档：`AGENTS.md`（仓库治理）、`PRD.md`（产品范围）、
`UPSTREAM.md`（上游归属）。上游 VideoToNo 的视觉与品牌规范对本项目**不**具有约束力。

## Brand

- 名称：Video2Knowledge（用户可见唯一产品名；`VideoToNo` 只出现在健康接口
  `service` 字段等协议兼容位置与归属说明中）。
- 气质：清晰、安静、本地可信的「知识工作台」（Knowledge Studio）——不是视频下载器，
  也不是通用 AI 控制台。
- 标志：原创几何图形「播放三角 + 知识节点」。圆角方形底为 Indigo `#4F46E5` → Cyan
  `#0891B2` 对角渐变（左上→右下，圆角半径 22%）；白色播放三角代表视频输入；三枚
  浅 Cyan `#A5F3FC`、白描边、逐级缩小的圆点从三角尖端向右上连出，代表视频被沉淀为
  互相连接的知识点。
- 资产来源（provenance）：`sources/icon.png`（1024×1024 RGBA）与 `sources/icon.ico`
  （16/24/32/48/64/128/256 多尺寸）由 `python scripts/make_brand_assets.py` 可重复生成，
  只依赖仓库已有的 Pillow；ICO 多尺寸构造复用 `scripts/make_icon.py`。全部几何与颜色
  是脚本常量，4 倍超采样 + LANCZOS 缩小，同一环境下输出逐字节确定（已验证）。
  不使用第三方图标包、图库或任何未确认许可证的素材；不描摹上游图标。
- 禁止用法：不拉伸/旋转标志，不改渐变方向与取色，不在低对比底色上直接放置，
  不把标志用作内容插图；历史 `sources/icon_3d*.png` 等上游衍生图不再用于应用、
  favicon、托盘或文档。

## Product goals

1. 把「选模板与保存位置 → 链接/文件 → 笔记或字幕稿」的高频路径放在首屏完成。
2. 低频配置（模型档案、识别参数、凭据、MCP、留存）完整保留但默认收纳，
   不与任务流抢注意力。
3. 所有处理在本机完成、可感知：服务状态、进度、失败原因与日志始终可查。
4. 结果可带走：复制、下载（Markdown/SRT/HTML/JSON/TXT/PNG）、自定义目的地、
   Obsidian 与飞书（可选）出口稳定在结果区顶部。

## Personas and jobs

- **本地知识工作者**：粘贴 B 站/抖音链接或上传本地媒体，一键得到结构化笔记，
  保存进 Obsidian Vault 或本地目录。Job：用最少的决策完成「看视频 → 有笔记」。
- **转录优先用户**：只想要带时间轴的字幕稿（可能交给外部 agent 再加工）。
  Job：明确选择「仅转录」，不需要配置任何 LLM。
- **Agent 使用者**：让 Cherry Studio / Codex 等客户端通过 MCP 直接驱动本机服务。
  Job：一眼找到接入地址并复制；不需要时它不占屏幕。

## Information architecture

桌面端（>680px）：

1. **顶部应用栏**：标志、产品名与版本、服务状态、主题切换、设置入口（右侧）。
2. **主阅读列**（单列、自上而下）：输出类型/处理方式（显式单选）→
   笔记模板卡片 → 本地 Markdown 目的地 + 飞书附加发布 →
   来源 composer（来源类型 + 链接/文件 + 主操作）→ 当前方案摘要（一行，随选择实时更新）→
   最近任务 → 处理进度（含失败面板与默认折叠的运行记录）→ 结果（操作区在预览上方）。
3. **设置面板**：从右侧滑出的可关闭面板，三组，顺序固定：
   `笔记生成`（总结模型、笔记风格、模板、推理强度、API Key）→
   `本地转录`（Whisper 模型、GPU、截图）→
   `存储与接入`（失败任务媒体保留、B 站凭据、MCP 接入、恢复默认）。
   模板 select 与编辑器保留在设置里作为高级管理入口；任务前选择仍在首屏。

移动端（≤680px）：顶部栏压缩（隐藏副标题、主题按钮只留图标）；模板卡片在组件内部
横向滑动，目的地纵向排列，不产生页面级横向滚动；设置面板变为全宽覆盖层；
结果操作区允许换行为两列。

## Design principles

1. **任务优先**：首屏回答「用什么结构、存到哪里、给我什么、要哪种产物、点开始」；
   模型与接入细节留在设置中。
2. **一屏一事**：设置、日志、凭据等次级信息默认折叠或收纳，展开不打断主阅读列。
3. **状态不只靠颜色**：进度/成功/失败同时用文字、徽标文案与图标语义表达。
4. **本地可信**：无第三方资源、无追踪；敏感信息（API Key、凭据）不进浏览器存储，
   界面文案明确说明数据去向。
5. **克制的动效**：仅用于面板开合、状态与进度反馈（150–220ms），尊重
   `prefers-reduced-motion`。

## Visual language

颜色 token（`style.css` 自定义属性为准）：

| Token | Light | Dark | 用途 |
| --- | --- | --- | --- |
| `--bg` | `#F7F7F2`（暖纸面） | `#0F1117`（深海军蓝黑） | 页面背景 |
| `--surface` | `#FFFFFF` | `#171B26` | 卡片、面板 |
| `--text` | `#23263B` | `#E9EBF4` | 主文字 |
| `--primary` / `--primary-strong` / `--primary-hover` | `#4F46E5` / `#4F46E5` / `#4338CA` | `#818CF8` / `#4F46E5` / `#6366F1` | 主操作、选中态、链接焦点 |
| `--accent` | `#0891B2` | `#22D3EE` | 辅助强调、进度渐变、信息提示 |
| `--success` | `#0C9C63` | `#34D399` | 完成、可用状态 |
| `--warning` | `#A97C14` | `#FBBF24` | 提醒、可继续的异常 |
| `--danger` | `#C93F3F` | `#F87171` | 失败、破坏性操作 |

- 字体：仅系统字体栈 `"Segoe UI Variable", "Segoe UI", "Microsoft YaHei", sans-serif`；
  等宽仅用于日志/编号（`ui-monospace, SFMono-Regular, Consolas, monospace`）。
  不引入网络字体。
- 圆角：卡片 `--radius-card: 16px`；控件 `--radius: 10px`；状态胶囊/芯片 999px 满圆角。
- 阴影：轻量层级阴影（亮色 `rgba(28,40,56,.10)`，暗色 `rgba(0,0,0,.24)`），
  设置面板用更强的反向投影表示浮层。
- 图标：仅品牌标志（PNG）与内联 SVG 线条图标（主题、设置、删除），无第三方图标库。

## Components

- **App bar**：粘性顶栏；左侧品牌（40px 标志 + 名称/版本 + 一句话定位），
  右侧服务状态胶囊、主题三段开关、设置按钮（`aria-expanded` + `aria-controls`）。
- **Source composer**：来源类型下拉 + 链接输入/文件选择 + 主按钮（≥44px）一行；
  输出类型（生成笔记/仅转录）与处理方式（从头/复用）为分段单选控件。
- **Template chooser**：六个内置模板与全部自定义模板共用一组卡片；内置模板桌面端
  三列，自定义模板顺序追加；卡片与设置中的 `#noteTemplate` 双向同步；加载失败时
  明确提示且继续阻止提交。「管理模板」打开设置并把焦点移到现有模板编辑区。
- **Destination chooser**：本地目的地为默认 Markdown、自定义绝对路径、Obsidian Vault
  三选一；飞书是独立的附加发布开关。本地 Markdown 始终保留。显式选择自定义目录或
  Obsidian 后，对应必填输入缺失时在提交前阻止任务。
- **Plan summary**：一行实时摘要（`#planSummary`，`aria-live="polite"`），
  跟随输出类型、模型档案/模型、模板、目的地与飞书开关更新。
- **Settings panel**：右侧抽屉（桌面 ≤400px，移动全宽），含关闭按钮与半透明遮罩；
  打开方式：设置按钮、MCP 芯片/提示、凭据引导；关闭方式：关闭按钮、遮罩点击、
  Escape。关闭后焦点回到设置按钮。
- **Progress card**：步骤条 + 进度条 + 用时 + 取消；失败面板常驻可见；
  运行记录为默认折叠的 `<details>`（任务失败时自动展开）。
- **Result card**：操作区（重新生成、复制、更多导出格式、格式感知的导出按钮、飞书重试）固定在预览上方，
  窄屏换行为两列网格；预览为 Markdown 渲染区。
- **Toast**：右下角短提示，4.2s 自动消失。

## Accessibility

- 对比度按 WCAG AA：正文/控件文字 ≥4.5:1（主色文字在暗色底使用 `#818CF8` 而非
  `#4F46E5` 即为此）；状态除颜色外均有文字标签。
- 键盘焦点可见：`:focus-visible` 统一 2px `--primary` 描边 + 2px 偏移，不被
  `outline: none` 吞掉（输入框用 border + 柔光环表达）。
- 主要点击目标约 44px（主按钮、提交、设置开关）；紧凑辅助按钮不低于 32px。
- 最低宽度 320px；交互元素均有可访问名称（`aria-label`/`sr-only` 文本）。
- 设置面板：打开后焦点移到「关闭」按钮，Escape 或关闭后焦点回到触发按钮，
  `aria-expanded` 同步；运行记录用语义化 `<details>/<summary>`。
- `prefers-reduced-motion: reduce` 时禁用面板滑入、进度流动等全部动效。

## Responsive behavior

- **>1024px**：单列阅读轴居中（最大约 880px），设置面板右侧浮层。
- **681–1024px**：同桌面结构，列宽与间距随 `clamp()` 收缩；面板保持浮层。
- **≤680px**：顶栏紧凑（副标题隐藏、主题按钮只留图标）；composer 控件纵向堆叠、
  主按钮全宽；模板卡片在自身容器横向滑动，目的地卡片单列；设置面板全宽覆盖；
  进度步骤 2 列；结果操作区 2 列网格；
  `overflow-x: clip` 兜底，任何内容不产生页面级横向滚动（日志/代码块内部滚动除外）。

## Interaction states

- 按钮：default / hover（底色或边框加深）/ disabled（55% 透明度）/ loading
  （spinner + 文案，禁用重复提交）/ focus-visible。
- 任务状态徽标：`processing`（indigo）、`completed`（绿）、`failed`（红）、
  `cancelled`（灰），均有文字。
- 设置面板：closed（隐藏、`aria-expanded=false`）/ open（滑入 180ms、遮罩可见、
  焦点进入面板）。
- 模板：loading / ready / error；ready 时卡片以 `role=radio` 和 `aria-checked` 表达选中态，
  原生 button 保证 Tab 与 Enter/Space 可用。
- 目的地：default / custom / obsidian；切换只展开对应输入，不清空旧自定义路径。
- 飞书：默认关闭；开启后才展示文件夹和 lark-cli 状态，本地笔记完成状态独立。
- 运行记录：默认折叠；任务失败自动展开；新任务开始时回到折叠。
- 提示条（B 站凭据、MCP）：可忽略，忽略状态记入浏览器偏好（不含敏感信息）。

## Content voice

- 中文优先、短句、动词开头（「开始生成」「从断点继续」）；先给动作再给解释。
- 状态文案说人话并给出下一步（如「模板列表加载失败，点击『开始生成』会自动重试」）。
- 安全相关的说明必须显式（Key/凭据只留本机、不绕过平台限制、飞书上传需勾选确认）。
- 术语固定：产物叫「笔记」或「字幕稿」，处理叫「转写」，配置入口叫「设置」。

## Implementation constraints

- 不改后端 API、任务清单格式与业务语义；DOM 重排必须保留 `script.js` 绑定的全部
  元素 ID（由 `tests/test_frontend_hygiene.py` 守护）。
- CSP 保持 self-only，不新增内联脚本、外部资源或依赖；`script.js` 只新增布局交互
  和现有字段的偏好映射，不重写提交、轮询、凭据、留存或飞书业务逻辑。
- 前端资源改动必须 bump `index.html` 中 `script.js?v=YYYYMMDD-N` 缓存版本。
- 图标等二进制资产只能由仓库脚本（`scripts/make_brand_assets.py` +
  `scripts/make_icon.py`）生成，不提交手工编辑的图片。

## Open questions

1. 设置面板打开状态是否需要跨会话记住（当前不记住，每次回到任务首屏）？
2. 方案摘要是否需要展示 Whisper 模型的本机缓存状态（需要额外的状态接口轮询）？
3. 设置面板在小屏上是否应支持底部抽屉手势（当前为全宽覆盖层，无手势）？

## Interaction research provenance

模板卡片、任务前目的地选择和导出可发现性的产品结构参考了 Fabric、
video-fetcher-to-markdown、course2md 与 YouTube Transcript Notes 的公开交互思路。
本项目没有复制这些项目的代码、提示词、图标或其他资产；实现继续建立在本仓库原有的
模板存储、单篇 Markdown、Obsidian、飞书和导出管线上。
