# G5.1-A 独立历史缓存验收

日期：2026-10-23。范围：按 [G5.1 合同](17-history-cache-design.md) 完成步骤 A。
**独立缓存模块已实现，尚未接入历史列表、repository 写入口或前端；没有产品性能提升的验收结论。**

## 交付与边界

- 新增 `backend/history_cache.py` 和 `tests/test_history_cache.py`，未修改原 main、repository 或前端。
- 只实例化显式创建的 `HistorySummaryCache`，没有默认单例、启动扫描、磁盘缓存或后台线程。
- 默认最多 12,000 条、16 MiB 编码负载、单项 64 KiB，LRU 淘汰；不截断标题或查询数据。
- 固定 30 秒复核期限，命中不续期。计时保守地从 loader 开始读取前起算；慢读取超过期限不装入缓存。
- 每次命中仍校验工作区、目录和清单身份；可靠指纹变化后重读。不可靠身份走只读 loader，但不缓存。
- 工作区路径/根身份变化清空；单个缺失或不安全任务只失效该项，不影响其他任务。
- 缺失/损坏/空值不做负缓存，不返回上次成功值；持续变化最多读取两次，不无限重试。
- 精确失效与 clear 不读写文件；RLock 使失效等待正在装入的条目结束，再移除该条目。
- 只缓存白名单标量投影的 UTF-8 JSON 字节；命中解码成新对象。模板、正文、URL、配置、日志及未知字段不入缓存。
- `CacheInfo` 只含数量/负载/hit/miss/eviction，没有路径、标题或内容。miss 计数仅包含进入合法可读候选路径的读取；缺失/不安全路径不计入。

模块不读取完整清单，也不自行提取业务字段。调用者必须提供只读、已投影的 loader；
超限或不支持的字典原样返回但不保留，业务兼容回退由 B 阶段接线处理。
不得直接将通用 manifest reader 变成缓存 reader，也不能让收藏资格或文件访问依赖本模块。

## 实际测试过程

先新增测试时模块尚不存在，实际得到 `ModuleNotFoundError`，没有虚构旧模块功能。
核心初版的 65 项测试通过后，审阅补测发现一个实质缺口：缺失任务会清空全缓存。
失败结果为 `1 failed, 48 passed`。随后区分根失效与单项失效，补齐其他边界。

最终专项命令：

```text
pytest tests/test_history_cache.py tests/test_history_performance.py tests/test_task_repository.py -q
114 passed in 3.80s
```

其中新增缓存规则 78 项，原历史/存储规则 36 项；没有修改旧测试来迎合缓存。
覆盖合同的缓存层 C01–C10，包括所有指纹分量、固定 TTL、UTF-8 负载上限、LRU、
单项超限、返回对象污染、文件替换/删除/修复、根替换、损坏缓存回退、不可靠身份、
路径别名和无特权链接替身、有限重读、清空/精确失效及 event 协调的并发读/失效。
C10 验证的是核心锁与显式 invalidate，并非真实 repository 的写后接线；I/U 集成用例仍待 B/C。

最终隔离完整回归：`1056 passed, 3 skipped in 63.64s`。
三项跳过仍为 `test_api.py:2012`、`test_asr_process.py:597` 和 `test_media_retention.py:145`
的既有 Windows 符号链接权限限制，没有新增 skip。较早的 1055 项完整结果不作为最终数字，
因为之后补加了“无关目录 mtime 变化不应失效”测试，最终完整套件已包含该项。

检查还包括 Python 编译、前端/截图脚本 Node 语法、pip check、tracked/new-file whitespace。
缓存未进入产品执行路径，本步未启动浏览器/测试服务，也未执行基准重新计时或便携版验收。

## 当前接口与后续接线

内部调用约定：

```python
cache = HistorySummaryCache()  # B 阶段决定产品中唯一实例的持有位置
projection = cache.read(canonical_workspace, safe_task_id, read_only_projection_loader)
cache.invalidate(canonical_manifest_path)  # 写成功后、writer 返回前；不做 I/O
cache.clear()                             # C 阶段显式刷新
counts = cache.info()                     # 仅开发计量，不是公开 API
```

实际实现每次 read 都做路径身份检查，冷项在 loader 前后各检查一次。
这一步尚未优化重复的工作区检查；B/C 测量前不能因“没有 JSON 文件 open”就宣称达到 300ms。
计量中的 payload_bytes 不包含 Python 对象、路径键与 LRU 额外内存，不能宣称是进程 RSS 上限。
身份探测与打开仍有既有路径竞争窗口，不提供跨进程事务或恶意文件系统沙箱。

下一步为 G5.1-B：先锁定摘要归并的 live/disk 优先级和隐藏规则，再接列表专用 loader，
最后在 repository.update 成功替换后接精确失效。收藏资格、恢复/复用、导出和文件打开
继续走新鲜读取；现有 API 及前端本步均未变化。

## 权限与保留物

完整回归导入隔离目录为 `.test-tmp/g51-a-regression-20261023/workspace/`，
设定独立 `VIDEO2KNOWLEDGE_WORKSPACE`/`WHISPER_CACHE_DIR` 且禁用 dotenv，未扫描用户工作区。
合成 pytest 文件使用临时测试目录；没有删除用户或前轮基准文件。
原 main、repository、基准脚本和前端 script 的 hash 在本步保持不变；staged diff 为空。
没有依赖安装、外网调用、真实凭据、模型/媒体下载、平台登录、飞书写入、构建或 Git 提交/发布。
