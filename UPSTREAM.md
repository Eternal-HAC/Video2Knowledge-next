# Upstream

Video2Knowledge successor 派生自开源项目 **VideoToNo**。

- 上游仓库：<https://github.com/like-attract/video-to-note>
- 采用版本：`v1.4.2`
- 基线提交：`0b1df7fe6db3035f94603d58b6f6ab0028083c0f`
- 许可证：MIT License
- 原项目名称：VideoToNo

本仓库保留上游 Git 历史、`LICENSE` 中的版权声明和 MIT License 条款。后续修改应继续明确上游来源，不将上游已有工作描述为本项目的原创实现。

## 计划中的定制方向

以下内容是后续开发方向，当前基线提交不表示已经完成：

- 支持输出到指定普通目录或 Obsidian Vault；
- 支持个人 Markdown 模板；
- 调整默认媒体与中间文件保留策略；
- 避免同名输出文件被静默覆盖；
- LLM 处理失败时保留可获取的 transcript；
- 加强 API Key 等凭据在 Git、日志和生成内容中的安全边界。

功能实现和验收状态以仓库后续提交及测试结果为准。
