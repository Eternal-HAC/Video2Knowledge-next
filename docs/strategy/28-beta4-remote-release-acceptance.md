# Beta.4 远端发布验收

日期：2026-10-24。状态：**已公开为 GitHub Pre-release，实际下载资产验收通过**。

发布页面：[Video2Knowledge v1.0.0-beta.4](https://github.com/Eternal-HAC/Video2Knowledge-next/releases/tag/v1.0.0-beta.4)。

## 远端身份

| 项目 | 回读结果 |
|---|---|
| 推送 main | `7ff61e7` 快进到 `d8135b60270dbed8885fe11bd5af89c483cb5ac0` |
| 注释标签 | `v1.0.0-beta.4`，对象 `68fc5b9e2f591072c6e229dbe5a600a45c3720aa` |
| 标签目标 | `d8135b60270dbed8885fe11bd5af89c483cb5ac0`；与发布证据文档后续提交分开 |
| 构建源码 | `7df3d51f04f140ec11624abd6c43fb06167c9076`，其后本地证据提交不改变 60 个构建输入 |
| Release ID | `422600838` |
| 状态与发布时间 | `draft=false`、`prerelease=true`；2026-10-24 08:23:48 UTC，即北京时间 16:23:48 |
| EXE asset ID / 大小 | `671667866` / `133248935` 字节 |
| EXE SHA-256 | `f78ed36f707ff8d302f6e721b7b4f18067b0dcd3d64e63ed1f6afa190968dc5b` |
| 校验文件 asset ID / 大小 | `671667863` / `109` 字节 |
| 校验文件 SHA-256 | `c7113d291de4d2a7ef4c33f7f1ea7a13244907be4f5a4093c10929ba8707d668` |

Release 的 `target_commitish` 返回 `main`；真实标签提交通过注释标签对象另行解引用确认，不把分支名当作不可变提交证据。

## Draft、下载与公开顺序

用户明确授权后才快进 main、推送并创建注释标签。Release 工作流状态 active，仓库 Actions enabled，但标签推送超过两分钟仍无运行记录，后续列表也为空。按[已授权备用合同](26-beta4-release-closeout-plan.md)手工创建 Draft Pre-release，上传同一份本地已验收 EXE 与校验文件；没有改工作流开关或删除/移动标签。

本次发布资产来自现有 Python 3.13.7 / PyInstaller 6.22.3 本地构建。没有实际 CI 构建或 CI 测试通过证据，也没有把它写成 Python 3.11 CI 资产。

上传完成后，从 Draft 重新下载两项资产，才执行以下验收。通过后，先核对标签与资产身份，再公开同一个 Release。期间出现 GitHub API TLS 握手超时：只读门禁失败时未执行公开；CLI 的标签查询阶段也曾失败。退避后确认仍为 Draft，按已知 Release ID 完成精确 PATCH，并回读公开状态。未重传资产或重复创建 Release。

公开后的 asset ID、大小和 GitHub digest 与验收时的 Draft 相同；公开只改变状态及下载 URL，没有更换二进制。

## 下载资产验收

- EXE 四方摘要对照：本地候选、实际下载 EXE、下载的 SHA256SUMS.txt 和 GitHub asset digest 完全一致。校验文件本身也与 GitHub digest、本地原文件一致。
- 下载资产的只设置新 workspace 变量、只设置旧变量两套隔离客户端均通过：健康返回 Beta.4/portable/product/service/api_compat，六模板及静态资源正常。
- 每套客户端都验证 Host/Origin/Fetch Metadata 拒绝、同源字幕上传、原生 BackendClient HTTP，以及无 Origin/同源 Origin 两次 MCP SDK SSE 会话。原转录区间、显式恢复信息和未知提交查询通过，不进行付费重新生成。
- 历史 smoke 在明确 ExpectedVersion=Beta.4 下验证两条合成历史分页、收藏重启持久化、按需读取与离线来源/复用提示。
- 下载 EXE 的真实 HTTP ASR 使用 SAPI 合成中文 WAV 和现有缓存 small。任务完成，3 个中文片段，转录 Markdown 100 字符、SRT 157 字符，JSON、Markdown、清单及中央归档正常。
- 直接下载版 worker 协议另用合成 WAV 确认 requested_model=model=small、device=cpu、非空片段和退出码 0。没有从公开任务结果缺失的 device 字段推断设备。
- 两个客户端工作区及 worker 工作区经过有限文件白名单清理；本次 EXE 进程为 0，合成 WAV 已删除，凭据产物审计通过。原生 smoke 各自清理其临时目录。

结构化证据：[远端验收 JSON](../quality/beta4-remote-release-acceptance-20261024.json)。下载资产、日志和测试脚本保留在忽略目录 `.test-tmp/beta4-release-20261024/`；EXE 与校验文件位于其中 `download/`。

## 验证范围与后续

本轮不改变运行源码或依赖。60 个构建输入仍与冻结源码一致，完整源码回归继续引用[本地验收](27-beta4-local-release-acceptance.md)的 1382 passed、3 个原有权限跳过；本轮没有再运行整套 pytest。文档链接、JSON、Node 语法、pip 与差异检查另行执行。

没有真实 LLM、已有 Key 读取、平台登录、飞书写入、模型或公开视频下载。未做清洁新机认证，不宣称全部 Provider/平台/网络兼容，未把默认缓存或 300ms 性能目标写成已达成。

发布后以单独文档提交更新 main，标签仍指向上述 `d8135b6`。这一阶段到发布证据推送结束；新功能、数据库与性能实验需后续独立计划。
