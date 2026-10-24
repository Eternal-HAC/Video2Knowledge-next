# 诊断导出合同 v1

交付为 `scripts/diagnostic_contract.py` 的纯函数 `build_snapshot(runtime, environment)`。
当前没有诊断 API、UI 保存按钮、自动日志读取或远端上传。不能宣传为已经上线的诊断功能。

## 白名单

| 字段 | 允许值 |
|---|---|
| schema_version / product / version | 1；统一产品元数据，忽略调用方自报值 |
| runtime.mode | portable / source / unknown |
| runtime.stage | queued / downloading / transcribing / summarizing / exporting / completed / failed / cancelled / unknown |
| runtime.error_code | none / llm_unavailable / transcript_unavailable / output_unavailable / cancelled / internal_error / unknown |
| runtime.model_kind | remote / local / none / unknown |
| runtime.duration_seconds | 有限数值 0–604800，拒绝布尔值；含义必须由未来调用方限定为阶段耗时 |
| runtime.segment_count | 整数 0–1000000，拒绝布尔值 |
| environment.os / os_major | Windows / Linux / Darwin / unknown；大版本整数 0–999 |
| environment.python | 严格版本字串或 null |
| environment.packages | 固定 12 个依赖名，严格版本或 null |

未知字段全部丢弃；未知枚举为 unknown，非法数字/版本为 null。
版本仅允许有界数字版本、a/b/rc/post 或产品 beta/rc 后缀，拒绝 `+local`、路径、换行、任意后缀。
它不试图接受完整 PEP 440 的所有形式；拒绝的版本写 null，不能捏造一个可用值。

禁止自由模型名、标题、URL、正文、路径、Key、Cookie、Authorization、原始异常、日志、
命令行、环境变量、主机名、账号和未知嵌套对象。自由模型名可包含私人标识，本阶段仅保留模型类别。
只把可信代码产生的枚举交给此函数；不能把用户字符串塞进合法依赖版本等字段后宣称全面脱敏。

## 后续接入条件

1. 现有业务错误尚有自由异常字符串，稳定 error_code 必须在对应错误边界建立，不能用通用正则
   从日志“猜”代码。此参考函数不重分类当前错误，也不自动收集事件。
2. 将真实运行数据投影到此合同，预览和保存必须使用同一份投影，用户主动选择本地新文件。
3. 默认关闭，禁止后台上传和全文日志附带；重试也不得扩大字段集合。
4. 集成前补 API/UI、计时含义、取消、预览等端到端测试；未来扩字段提高 schema_version 并审查隐私。

当前测试用路径/凭据哨兵、异常大整数、非有限数值和未知字段证明本投影的边界；
这不能代替现有全部业务日志的凭据安全审查。
