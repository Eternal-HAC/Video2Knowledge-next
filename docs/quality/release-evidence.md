# 环境清单与发布资产对照

本轮只提供离线工具和操作合同，没有构建、联网下载、Git 操作或更新 Release。

## 环境观察

```powershell
.venv\Scripts\python.exe -m scripts.release_evidence environment
```

可加 `--output <新的报告文件>`。只读取运行解释器版本、OS 大版本和固定依赖的安装元数据，
不读 Provider 配置、环境变量、用户文件或执行外部进程。未安装或格式不符合白名单为 null。
清单是部分关键依赖观察值，不是全依赖 SBOM、锁文件、完整构建环境或重现性保证。
使用 PyYAML 解析的离线工具复用当前 `uvicorn[standard]` 已声明的依赖，没有安装新包。

2026-10-23 本机观察：Python 3.13.7、PyInstaller 6.22.3；当前 CI/Release workflow 使用 Python 3.11。
此轮不统一版本、不升级依赖，后续发布应在选定环境重新完整验证，不能互换两个环境的证据。

## 同一候选的四方对照

获得独立发布授权后，再按照以下步骤执行：

1. 记录源码 commit 和 dirty 状态、候选 EXE、构建环境、文件大小与 SHA-256。
   候选必须是从已记录源码构建并经过真实打包验收的那一份字节。
2. 上传同一候选及单条 `SHA256SUMS.txt`。重新构建产生新候选，不能沿用旧验收。
3. 经 GitHub API 回读标签目标、预发布标记以及资产 name / size / digest，
   将 EXE 资产对象保存到隔离 `asset.json`，不附带认证头或账号资料。
4. 把远端 EXE 另存为下载副本；保持本地候选不变，然后运行下面的离线比较。
5. 所有字节和 digest 一致后，仍需另做下载版的隔离离线 ASR/功能烟雾验收。
   比较器不会启动 EXE，也不证明运行成功。

```powershell
.venv\Scripts\python.exe -m scripts.release_evidence verify-assets --candidate .test-tmp/candidate.exe --downloaded .test-tmp/downloaded.exe --checksums .test-tmp/SHA256SUMS.txt --metadata .test-tmp/asset.json
```

预期资产名直接读取当前 `product_info.py`，本轮仍为
`Video2Knowledge-1.0.0-beta.3-portable.exe`。这不表示它已包含 G0–G4 修改。
检查：本地候选 hash、下载副本 hash、校验文件 hash、GitHub `sha256:` digest 必须全部一致，
名称精确一致，两个文件大小与 API size 一致且大于零。缺失 digest 直接失败，不自动降低门禁。
校验文件只接受当前 EXE 的单条标准 SHA-256 记录，拒绝重复条目和路径替换。

输出无绝对路径或原始异常；失败返回固定错误码。输入路径拒绝链接/重解析点和硬链接，
输出文件只新建。工具相信调用方提供的 `asset.json`，它不能验证文件确实来自 GitHub，
也不能证明 tag 指向哪个 commit；真实 API 回读和下载来源证据必须另外保留。

## 发布文字与故障恢复

- 分别写明：离线测试、浏览器、打包态缓存 ASR、有限真实 Provider 的输入/模型/时间范围。
  G4 规则报告不得当作真实 LLM 笔记质量结果，也不能把旧版 DeepSeek 证据变成本版全 Provider 保证。
- main 已推送、标签/Release/上传失败时，只补缺失步骤。禁止移动标签、重写历史或覆盖同名不同 hash 资产。
- 远端发生外部推进立即停，不自动 rebase/force push。所有外部写入按当次授权执行。
- 本轮资产比较只使用测试里的合成字节；没有把它们作为 EXE 发布或验收。
