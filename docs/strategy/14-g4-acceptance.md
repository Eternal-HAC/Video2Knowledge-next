# G4 离线质量与发布证据验收

日期：2026-10-23。范围：[G4 执行合同](13-g4-task-contract.md) 的离线轨。
分支 `codex/beta4-progress-result-loop`；HEAD `7ff61e7568a324b9d2e7a31161ff0b7927ca3f9b` 未变。
产品仍为 `1.0.0-beta.3`。保留 G0–G3 全部既有未提交修改，没有 stage/commit/push/build/release。

## 交付

- `tests/fixtures/note_quality/`：12 个原创合成案例，每例 3 个信息点，覆盖全部 6 个内置模板；
  保存分段、人工参考正文、字面规则及时间相交下标。
- `scripts/evaluate_notes.py`：确定性离线规则 CLI，默认渲染人工参考；可显式读取固定案例名的
  待测合成成稿目录。使用现有模板替换/Frontmatter、转录 hash、SRT 往返和定位函数。
- `scripts/quality_io.py`：有界读取、链接/重解析组件及硬链接检查、独占创建报告、固定错误码，
  参数错误不回显未知参数；没有工作区扫描或自动上传。
- `scripts/diagnostic_contract.py`：schema 1 白名单纯函数，丢弃未知字段，限制枚举、数值与版本；
  不导出正文、路径、Key、自由模型名。未接入产品 API/UI/日志。
- `scripts/release_evidence.py`：只观测当前解释器和关键依赖元数据；离线对照候选/下载副本/
  校验文件/GitHub digest 与大小，不下载或执行资产。
- [使用说明](../quality/README.md)、[人工表](../quality/manual-review.md)、
  [诊断合同](../quality/diagnostics.md)、[发布流程](../quality/release-evidence.md) 与
  [环境观察值](../quality/environment-20261023.json)。

本阶段不修改 backend/frontend/product_info 或 workflow。此前这些路径的 dirty 改动仍归 G0–G3。

## 新鲜验证

1. 先补测试，最初因工具不存在出现 ModuleNotFoundError；实现后加入负向破坏检查，验证遗漏信息点、
   漏尾、数字修改、坏 Frontmatter、时码/相交错误、危险/未声明附件确实失败。
2. 新工具针对性测试：`74 passed`。同时验证同义表达可通过、报告稳定、正文不回显、
   NaN/Infinity/超大整数和秘密哨兵被拒绝、已有输出不被覆盖、重复校验条目/错 digest 会失败。
3. 最终完整回归：`957 passed, 3 skipped in 60.90s`；G4 前基线为 `883 passed, 3 skipped`。
   既有三个跳过来自 Windows 符号链接权限，位于 test_api:2012、test_asr_process:597、
   test_media_retention:145。新增测试没有添加 skip；硬链接使用真实文件，重解析组件使用受控替身。
4. 实际运行离线 CLI，`reference-rules-final.json` 的 12 例全部通过，36 个字面信息点满足，
   `manual_review=not_scored`。报告记录案例/成稿/转录 hash；没有实际模型输出或人工评分。
5. `environment.json` 与已记录环境一致：Windows 11、Python 3.13.7、PyInstaller 6.22.3。
   CI/Release 仍为 Python 3.11，本轮没有验证该环境，也没有生成锁文件或新 EXE。
6. 前端、截图和 G0–G3 六项 Node 语法检查通过；pip check 无损坏依赖，git diff --check 干净。
   Python 工具可编译；staged diff 为空，既有 dirty 文件保留。

本地证据目录：`.test-tmp/g4-acceptance-20261023/`。保留最终规则报告及无隐私环境报告；
早期 `reference-rules.json` 是调试报告，已由 `reference-rules-final.json` 取代，不作最终基准。
本阶段没有启动服务器、浏览器或子进程服务，没有需要停止的测试服务。

## 证据边界与后续

- 全部字面规则通过不能证明事实正确、全部信息覆盖或没有幻觉；人工表保持未评。
- 两小时时间轴只有 3 段，用于尾部锚点/小时格式检查；没有用它宣称长文本/长视频性能通过。
  既有 summarizer 的尾部补齐、分块失败保留、半截流不重提等替身测试仍在完整回归中，
  本轮没有重新实现这些管线或对真实模型测量。
- 附件是路径声明检查，未验证实际文件或图片内容；有限 Markdown 识别器不能代替安全渲染。
- 诊断仅规格/参考投影，现有日志并未因此自动脱敏。还需稳定错误码来源和独立的 API/UI 集成。
- 资产对照测试使用合成字节，没有下载本版 EXE。传入 metadata 文件的真实来源、标签 commit、
  打包功能都要在未来授权的发布门禁核验。
- 真实模型评测须单独指定输入、Provider/模型、请求/重试/费用上限和停止规则。未授权、不执行。
- 下一候选为 G5 历史规模基准；先测量再决定是否需要索引。发布前 Host/Origin 审查仍未完成。
