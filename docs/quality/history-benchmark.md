# 历史记录规模基准

G5 只使用原创合成任务，不读取已有 workspace、Vault、Provider 配置、Cookie 或私人媒体。
完整方法和结果由 [G5 合同](../strategy/15-g5-task-contract.md) 与对应验收记录管理。

更新：G5.1-C 增加 `--cache` 六状态复测，报告 schema=2，见 [实际证据与退化](../strategy/20-history-cache-c-acceptance.md)
和 [原始报告](benchmarks/g51-c-20261023.json)。命令为 `python -m scripts.benchmark_history --cache --output-dir <新目录> --repeats 7`。
先检验 1,000 条方向；无收益时停止后续规模。C 当时的默认命令绕过列表缓存并标记 `bypassed_g5_reference`。
[D 默认回退](../strategy/21-history-cache-default-rollback.md) 后，默认命令直接测量产品读取入口，标记 `production_direct`；
只有 `--cache` 显式替换 list-only reader 测量实验缓存。不能把默认查询标成缓存命中。
TTL 不延长，统计各样本 hit/miss；方法计数、读取和分配与计时分开。
缓存尚不满足优化门禁；D 默认 1,000 条 p95 为 742.230ms，仍未达 300ms。下面的 G5 原始方法与结果保持为历史依据。

## 复现

仓库根目录运行，输出目录必须尚不存在，父目录需已存在：

```powershell
.venv\Scripts\python.exe -m scripts.benchmark_history --output-dir .test-tmp/g5-run --repeats 7
```

默认生成 100、1,000、10,000 个任务，约数万个文件，保留在该隔离目录用于复现。
`--sizes 1000` 可只测一档；重复次数可选 2–31。脚本不删除或覆盖既有目录，不支持扫描用户历史。
请勿在业务后端进程中 import 后运行，CLI 拒绝复用已经加载的 backend.main。

应用导入前禁用 dotenv，将新旧 WORKSPACE 和模型缓存路径指向新建 bootstrap，预加载上限固定 100。
拦截网络连接与外部进程启动；不启动 HTTP 服务或浏览器。当前历史 async 处理函数内无 await，
工具直接执行真实协程至返回，不创建 Windows 事件循环的 loopback 自管道；未来若增加异步悬挂，
工具明确失败，需先更新计量方法，不能静默省略实际等待。

## 输入与查询

- 每个任务保留 task.json 和三段合成转录。已完成笔记任务另有一份短合成 Markdown，
  模板快照包含相同的合成整理要求。实际内容字节数在报告中记录；不是磁盘占用量。
- 混合已完成/失败/取消、笔记/转录、web/agent 来源和收藏。部分为精简旧格式，
  runtime 未保存 result，包含历史回退路径；不声称与用户真实数据分布相同。
- 默认列表、关键词+状态+产物+平台组合筛选、收藏和第二页，共 4 个查询，分页 20 条。
- 相同生成规则产生相同 dataset_sha256，不包含当前日期、绝对路径、随机标题或真实视频。
  比较优化前后时输入摘要与查询结果 response_sha256 必须相同。

## 指标口径

| 指标 | 含义与限制 |
|---|---|
| empty_backend_import_ms | 空隔离目录中的一次源码模块导入，不包含 EXE/Launcher/服务启动 |
| startup.restore_ms | 已有合成任务目录的首次恢复，预加载至多 100 条；仍扫描并排序所有目录 |
| first_ms | 恢复后第一次执行该查询，文件刚生成，后续查询也可能已暖；不是冷磁盘 |
| raw_ms / p50 / p95 | 无 IO 包装器、无 tracemalloc 的重复处理函数耗时；不含 HTTP、JSON 传输或 DOM |
| reads | 另跑一次，统计成功返回的 Python Path.open 读句柄，不包括 stat、目录扫描、缺失打开尝试或物理磁盘 IO |
| python_traced_peak_bytes | 另跑一次的 Python 跟踪分配峰值，不是进程 RSS、原生库内存或整机内存 |

百分位使用 nearest-rank；7 个样本的 p95 等于最大值，只作本机描述，不代表稳定 SLO。
不要清理 OS 文件缓存、终止用户进程或改电源/安全软件设置来制造“好成绩”。
没有隔离后台负载，CPU、磁盘、防病毒检查、供电与文件缓存都会影响结果；跨设备需重新测量。
首次查询、计数与内存单独测量，不能直接把它们的耗时相减推算纯磁盘时间。

每次报告记录工具、backend/main.py 和 task_repository.py 的 SHA-256、环境版本、
输入字节摘要、实际样本和结果摘要。运行期间不要修改这些源码；未提交状态无法仅靠 HEAD 复现，
需要保留对应补丁。报告不含任务正文、标题、绝对路径或用户标识。

## 决策规则

参考目标为 1,000 条暖查询 p95 < 300ms。它不是 CI 的硬时间断言，CI 锁定读取次数和功能语义，
时间数据在本机单独记录。先消除同一请求的重复清单/路径处理，不引入数据库或全文搜索。
仍未达到目标时如实记录，不通过减少可查询历史、隐藏筛选结果或只扫描第一页来换取数字。
缓存/可重建索引需要独立设计失效、收藏即时可见、外部修改、删除与重建回退；不能跳过这些条件。

## 本轮结果

见 [G5 验收](../strategy/16-g5-acceptance.md) 和原始 [优化前](benchmarks/g5-before-20261023.json) /
[优化后](benchmarks/g5-after-20261023.json) 报告。每任务清单读取从两次降为一次，目录规范化从三次降为一次，
响应摘要保持相同。1,000 条默认暖态 p95 从 1755.670ms 降到 1011.433ms，仍未达到 300ms 参考目标。
启动恢复的单次数据没有一致改善。该任务只完成基准和请求内去重，没有加入缓存、数据库或索引。
