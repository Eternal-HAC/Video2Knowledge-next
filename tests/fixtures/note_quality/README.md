# 原创合成案例 schema 1

每个 JSON 均为公开、无隐私的手工案例，不是实际模型输出。
`segments` 是权威合成输入；`required_points` 用稳定 P 编号标注字面候选，
`required_literals` / `forbidden_literals` 是显式规则；`anchors` 记录半开区间对应段下标。
`reference_body` 是人工参考文本，经现有模板安全外壳渲染；不是唯一合法答案。
`available_attachments` 仅为相对路径声明，不表示存在图片文件。

使用、限制与人工评阅方法见 [离线质量工具](../../../docs/quality/README.md)。
新增案例需同时扩展工具的固定 ID 集合及覆盖测试，不能从用户工作区自动收集训练/评测素材。
