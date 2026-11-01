# CTF-Forge 实施状态

版本：v7；2026-11-01。取消 GitHub 发布并完成全目录隐私复核。

## v7：取消公开发布与隐私复核

- 用户取消 GitHub 发布；项目没有 remote、没有 commit、没有 push。GitHub CLI 设备登录失败，`gh auth status` 确认未登录，没有取得 GitHub token；失败登录留下的本机 `device-id` 已删除。
- 对整个项目目录（排除第三方虚拟环境和生成缓存）做凭据与身份扫描：未发现非空 API key、平台 token、GitHub token、私钥、JWT、AWS/Google/Slack 凭据、URL 内嵌账号、本人姓名/学号或本机用户名路径。
- `.env` 与 `.env.example` 的 API key / auth token 字段均为空；`configs/models.yaml` 的 `api_key` 为 `null`。`.env` 仍含普通模型名称、基础 URL 和超时配置，不属于秘密。
- 审计曾发现旧修改备份含真实比赛 flag、队伍标识和本机路径；对应冗余备份已删除，复扫无命中。
- GitHub CLI 为机器级 MSI；非管理员卸载返回 Windows Installer 1730，程序本体仍待管理员卸载。这不影响项目目录隐私结论。

## v6：实战收口与公开版

- HI Cyber Con 2026 赛后成绩快照记录：**42 / 68 题、2461 / 5751 分、12 / 12 类覆盖**；峰值 2465，终场因动态计分回落 4 分。用户随后明确要求删除全部下载赛题与现场材料；原始逐题报告、平台回执和工作区已永久删除，因此公开版只把这些数字作为赛后快照，不再声称可由仓库逐题复算。
- 新增 `docs/AGENT_COMPETITION_PLAYBOOK.md`：固化平台闭环、主调度职责、单题唯一负责人、错误提交预算、实例池、HANDOFF 五要素、赛中节拍与公开发布闸门。
- 公开范围只含核心代码、测试、自建样例、配置示例、许可证和脱敏文档。`challenges/platform/`、`.data/`、`reports/`、`workspaces/`、现场脚本、flag、端点与凭据均未进入提交；本机对应现场材料也已删除约 11.75 GB。
- 移除 README 示例和隔离探针中的本机绝对路径；隔离探针改为通用挂载点检查。
- 2026-11-01 复验：Ruff、格式、mypy 全过；pytest **81 passed**；真实 Docker `self-test` **14 / 14** 通过。
- 未验证：DeepSeek 云端自主解题仍无用户 Key，不得把脚本 smoke 或这次外部 Agent 实战成绩写成模型 Pass@k。

## v5：HI Cyber Con 2026 CTF 实战（Agentic AI 分组，19:05 中间快照）

- 赛事窗口 2026-10-30 22:00 ~ 11-01 22:00（UTC+8），68 题 / 12 类，总分 5,751；奖金 USD 2,500 前 5 队（总榜）。
- 本工具链路（platform pull → solve external → step 动作 → submit_flag 平台判定）在真赛运行，
  截至 19:05 战绩 **13 题 / 718 分**：Cold Beacon 54、Signal Lock 57、The Inner Engine 57、Snapfile 59、
  Cold Beacon 之外另有 Cold Circuit 67、Broken Signals 53、Zanzibar Whisper 53、Memory Liar 54、
  The Foxglove Trace 54、Roof of Africa 53、Forgotten Secrets 54、Ghost in the Wire 53、Cipher Cascade 52。
- 全部作答的 flag 均由「程序/数据自证 + 平台 goodFlag」两条独立证据确认，错误提交共 2 次（均为适配器探针）。
- **合规备注（必须留档）**：Cipher Cascade、Forgotten Secrets、Ghost in the Wire、Roof of Africa 四题由执行方在宿主机上做纯静态分析
  （编码链/单字节 XOR/pcap 解析/steghide），未走容器沙箱；其余题均为容器内执行。规则允许（Agentic AI 组解法不受限），
  但这四题的「沙箱已覆盖」不能当作已验证结论。
- 未解/放弃：Entitlement（三层壳 + SMC VM）、Last Execution（自定义容器格式，文档公式为陷阱）、
  Night Batch（GnuCOBOL）、Obfuscated Flow / Epsilon Drift（SHA-256 KDF 门控）、Rocinate Revenge / No Bit Sings Alone / The Coffee Shop（500 分题，0-1 解）。
- 工具侧经验：单工具 30 秒上限使枚举类分析必须分片；容器离线，纯 stdlib 做题（无 PIL/numpy/pycryptodome/steghide）。

新增比赛平台（rCTF）拉题与提交适配；其余结论沿用 v3。

## v4 增量（平台适配，仅宿主侧联网）

- 新增 `src/ctf_forge/platform/rctf.py`：`platform me` / `list` / `pull` / `submit` 四个命令，
  以及 `solve --platform-challenge <id>` 把平台作为独立验证器。容器配置未改（仍断网、非 root、只读根）。
- **已实测（真平台，2026-11-01）**：`platform me` 返回分组 `agentic`、`banned=false`；
  `platform list --category reverse` 返回 10 道 Reverse；`platform pull "Cold Beacon"` 下载
  `cold-beacon.zip` 17603 B，`sha256=a01791f8…10d8` 与题目声明一致（`all_verified=true`）。
- **提交路径已实测两个方向**：CLI `platform submit` 提交错误候选 → 平台 `badFlag`、`accepted=false`；
  会话内 `step submit_flag` 提交错误候选 → 候选记 `rejected`、任务保持 `running`、`verified_flag` 为空。
  **平台接受路径已实测（同日补齐）**：Cold Beacon 经约束求解得到候选，程序自身输出与平台 `goodFlag` 两条证据一致；`step submit_flag` 将候选记为 `platform_accepted`，任务转为 `succeeded`，账号分数 0→54。完整 flag、任务 ID 和报告只留本地忽略目录，不进入公开状态文件。
- 附件来源说明：本平台题目 JSON 的 `files` 字段为空，附件写在题目描述的 markdown 链接里（对象存储）；
  `pull` 按该链接下载并核对 `SHA-256:` 行，多文件时按出现顺序配对。
- 平台对库默认 UA 返回 Cloudflare `1010 browser_signature_banned`，`configs/platform.yaml` 的
  `user_agent` 因此是必需项；该文件不含凭据，凭据只在 `.env` 或 `.data/hi-session.secret.json`。
- 修复 `scripts/start-docker.ps1`：旧版 `$ErrorActionPreference='Stop'` 会把 wsl/docker 的 stderr
  当致命错误，dockerd 未启动时脚本直接抛错、无法拉起引擎。修复后实测可拉起并复跑 `self-test` 14/14。
- 本轮真实失败记录：会话 `0f19865d4aa74bb69018376400cc099e` 关闭时 WSL 里的 dockerd 已停止，
  清理失败 → 任务按设计记 `failed`（stop_reason 含 `cleanup_required`）。说明引擎随 WSL 空闲关机消失，
  开工前必须 `doctor`。
- 未做/未验证：除 Cold Beacon 外未解其它赛题；
  非 reverse 分类与 instancer 题未适配；`platform pull` 未处理需要认证头的对象存储链接（本次为公开链接）。
- 工具链复算：`uv run ruff check .` / `ruff format --check .` / `mypy src/` / `pytest -q` 全过
  （**81 passed**，v3 为 63；新增 `tests/unit/test_platform.py`）。
- 运行限制（实测）：单工具上限 30 秒 + 超时销毁容器，枚举类分析必须分片；第一次尝试因此触发 `tool_timeout`，任务记 `partial`，`resume` 后可继续（本次即靠 resume 完成）。

## v3 历史（以下为 v3 原文）

版本：v3；2026-11-01。用户目标：完整工作流，任意 Agent 接手即可使用；未来可选 DeepSeek API 或直接 Codex。

## 当前交付

- 默认 external 模式：当前 Codex/任意 Agent 直接决策 → JSON 动作 → Docker 注册工具 → 观察反馈 → 宿主独立答案验证 → JSON/Markdown 完整或部分报告。**真实闭环已通过。**
- 可选 autonomous 模式：DeepSeek/OpenAI 兼容接口 → LangGraph 多轮工具循环 → 同一执行/验证/报告引擎；SQLite checkpoint 保存完整状态。
- DeepSeek 专用分支保留 thinking 工具续轮的 reasoning_content。HTTP 协议与多轮字段测试通过；**没有用户 API Key，DeepSeek 云端解题未实测，LLM Pass@1/Pass@3 没有成绩。**
- 本地 Ollama 不作为依赖。早期临时 Qwen3 试验有两次失败，报告保留；Qwen3 临时模型与中断的 Qwen2.5 下载缓存已清理，未继续本地模型试验。

## 已核验证据

- `uv sync --locked` 成功；Python 3.12.14，uv.lock 已生成；Git 仓库已建，无 remote、未发布。
- `uv run ruff check .`、`uv run ruff format --check .`、`uv run mypy src/` 通过；`uv run pytest -q` **63 passed**。
  原始输出：`.data/verification-20261101.txt`；一键复算：`uv run python scripts/check.py`。
- WSL Ubuntu-22.04 已安装并启动 Docker 29.1.3。Ubuntu 24.04 分析镜像已构建，基镜像从官方 registry 的 manifest/层摘要核对后由 Windows 下载导入，来源 `third_party/ubuntu-image-source.json`。
- `uv run ctf-forge self-test` **14/14 通过**：非 root、根/输入只读、工作可写、指定宿主路径不可见、容器不含凭据、断网、资源/权限配置、超时销毁。
  `.data/environment-check.json` 保存实际镜像 ID 和配置；这组探测不声称证明容器绝对无法逃逸。
- 真实工具：pyelftools 结构化 ELF、file/readelf/strings、objdump、Capstone、GDB batch 与 Python 均已实际运行。
  `.data/tool-integration-test.json` 指向 `reports/4d52663c413b4198afc3490d8b6c2308.json`。
- Windows→WSL 曾误经 Shell，Python 单行代码因此失败；已改成 `--exec` 直接传 argv。
  保留失败报告 `reports/3af52f8d8e864206b6643e49bc51b3d5.json`；修复后 Python 等全部通过。
  带分号的输入保持二进制参数，不执行宿主命令；证据 `.data/wsl-argv-test.json`。
- 10 道自建简单 ELF 已编译；修复后脚本控制器经公开 CLI 全流程再次 **10/10 验证成功**：
  `reports/external-smoke-1793519835263525400.json`，每题映射 task_id/原始报告。
  复算：`uv run python scripts/verify-external-smoke.py`。
  **这是同一家族合成题的脚本集成测试，不是模型自主成绩，不证明真实比赛水平。**
- 真正的外部 Agent 风格单题闭环含 strings/GDB/run_binary/宿主验证已通过，任务 `58a785ee5bb8423abac82c7fa03e6aaa`。
- 无答案不成功的真实负例：`dc07c9caa6e04c48b56ccb93ff66f7b0`，最终 partial；候选/已验证/拒绝分开。
- API 错误、输入变更、答案变更、并发锁、预算停止、最后一次允许调用的候选验证、清理失败不算成功等有测试覆盖。

## 状态与使用入口

- 任意 Agent 入口：`AGENTS.md`；用户操作/配置：`README.md`。
- 工具接口：`uv run ctf-forge tools`；能力发现：`capabilities`，默认 solve=external。
- Docker 下次未运行时执行 `scripts/start-docker.ps1`；不用新建计划任务。
- `.env` 现在是 DeepSeek 示例配置，API Key 空白；直接 Codex 模式不需要填写。
- 每次会话的报告在 reports/，旧报告修改时进入 reports/history/；输入/状态在 workspaces/，数据库和 checkpoint 在 .data/。
- 所有当前测试容器已销毁；容器自动寿命 900 秒兜底外部 Agent 失联。无平台提交或外部联系。

## 实际边界

- 未实测用户 DeepSeek 云端调用，也未跑真实模型的 10 题 Benchmark；相关命令已实现，等用户配置 Key 后运行，不能把脚本 10/10 填成模型 Pass@k。
- 恢复命令在原预算内以 external 模式重建容器，保留观察/计数；不会自动回放旧命令或扩预算。Graph checkpoint 不是跨所有异常无损恢复的承诺。
- 独立验证器当前支持用户指定的可信标准答案文件精确比对，不支持任意平台自动验证或提交。无标准答案就只能交候选。
- GDB 提供受限 batch 动作；不是无限制交互调试器。Capstone 当前基础工具支持 x86/x86-64。
- external Agent 自己的模型 Token/费用不在项目观测范围；0 次模型调用表示程序未发起额外请求，不代表外部 Agent 没有消耗。
- 答案不送入工具容器/模型提示词，但外部 Agent 本来具有宿主权限，须遵守不读答案/样例源码的评测约定。

## v1–v2 历史快照（以下已被 v3 替代）

# CTF-Forge 实施状态

版本：v2；2026-11-01。当前采用 BoxPwnr 精简复用；用户要求任意 Agent 可发现并直接调用。

## 当前结论

- M0–M1：安装与基础工程已验收。`uv sync --locked` 成功；独立 Python 3.12.14 环境。
- BoxPwnr 固定提交 6e2778ce6741b2f1755b4cfbc5ea37b663b1399c，四模块实际纳入包。
  LocalReversePlatform 继承上游 BasePlatform/Target，DockerRuntime 返回上游 RawExecutionResult。
  BaseExecutor/Deadline 原件保留供后续接入，目前没有接入 Solver。来源和哈希可核。
- M2–M3 部分：已提供非 root、断网、只读根、cap-drop ALL 的 Docker 配置，输入只读/工作独立挂载；
  有界输出、命令超时后销毁容器、固定 file/readelf/strings argv 和 JSON 静态报告已实现。
  **本机缺 Docker，真实镜像构建、容器隔离及 ELF 集成未验收，M2/M3 不算完成。**
- 缺答案绝不判成功；答案只存在适配器私有字段，不进入 Target 或提示词。
  尚无用户可调用的完整本地验证器 CLI，不把模型状态校验当独立验证器。
- `AGENTS.md` 已成为任意 Agent 的自包含入口，`capabilities` 提供 schema_version=1 的 JSON 能力发现。
  不读取 AGENTS.md 的 Agent 需用户明确让其先读；无需依赖此聊天。
- 已跑 `ruff check .`、`ruff format --check .`、`mypy src/` 全通过；`pytest -q` 47 passed。
  vendor 不改上游格式/不做严格类型扫描；其来源哈希和本地集成另有测试。
- 手动真实 CLI 已跑：init、capabilities、config-check、示例 task add/list 成功；
  doctor 真实返回 1，原因 Docker CLI missing。示例任务是登记用文本，不是已解 Reverse。
- M4–M7 未完成：无模型 API 实测、自动多轮 Solver、LangGraph checkpoint、GDB 或 Benchmark。
- 未发布、无远程、无自动提交 Flag。采用上游 AGPL-3.0，LICENSE 与第三方声明在项目内。

## 下一位 Agent

先读 AGENTS.md；先解决 Docker Linux 引擎，构建 docker/Dockerfile，验证断网/只读输入/资源限制/
超时销毁/主机文件隔离，再用授权 ELF 跑 inspect。不要在宿主机执行题目。
静态链路实际通过后接模型工具循环与独立验证。无需重写已复用的平台和结果对象。

## 下方为 v1 历史快照（已被上述当前状态替代）

# CTF-Forge 实施状态

版本：v1；2026-11-01。

用户中途要求「等下，先到 GitHub 看有没有现成的」。自建开发已暂停，先评估复用方案。

## 本地实际状态

- 已创建独立 Git 仓库，无远程、无提交，无发布。
- 已写 M0–M1 的依赖声明、配置、数据模型、日志、SQLite、CLI 和测试代码。
- 使用本机已有 Python 3.12.14 创建 `.venv`；执行过 `uv sync`，生成 `uv.lock`。
- 安装会话结束后的最终退出状态未取得；不能宣称依赖安装验收通过。
- 尚未运行 Ruff、mypy、pytest 或 CLI 验收，M0/M1 均不能标为完成。
- Windows PATH、Docker Desktop 常用位置、WSL Ubuntu-22.04 中未发现 Docker。
- M2–M7 尚未实现，无 ELF 执行、模型 API 调用或自动解题成绩。
- 原开发说明未修改。README 中已提供的命令仍需实测，不是测试记录。

## GitHub 初筛（2026-11-01，源码/文档检查，未在本机运行）

1. BoxPwnr：https://github.com/0ca/BoxPwnr
   有本地题目平台、Docker 执行器、工具反馈循环、预算/尝试次数和轨迹报告；AGPL-3.0。
   检查到两项与本说明直接冲突：
   - `src/boxpwnr/platforms/local/local_platform.py` 的 `validate_flag` 在无标准答案时，
     将任意非空候选返回为有效且题目完成，虽反馈文本承认无法验证。
   - `src/boxpwnr/executors/docker/docker_executor.py` 默认 bridge 网络、NET_ADMIN、
     /dev/net/tun；不能将默认配置当成断网、最小权限的 ELF 沙箱。
   适合作复用候选，需先修上述判定并收紧隔离，不能称原样满足开发说明。

2. NYU CTF Agents：https://github.com/NYU-LLM-CTF/nyuctf_agents
   有单 Agent baseline 和 D-CIPHER 多 Agent、Docker 与配套 NYU CTF Bench。
   本项目第一阶段不需要多 Agent，优先看 baseline。README 提到历史版本、旧仓库路径和
   安装脚本，需核对实际当前文件；本轮未安装、未验证维护兼容性。仓库首页标 MIT，
   pyproject 分类器却写 Apache，后续复用应以具体 LICENSE 文件核对。

3. SWE-agent EnIGMA：https://github.com/SWE-agent/SWE-agent/tree/v0.7
   有 CTF 流程、交互 GDB 和运行轨迹。主分支 README 明确要求 EnIGMA 使用 0.7。
   文档：https://raw.githubusercontent.com/SWE-agent/SWE-agent/v0.7/docs/usage/enigma.md
   适合参考逆向工具交互，不应直接假定新主分支兼容 EnIGMA。

4. Clank the Flag：https://github.com/zeyu2001/clank-the-flag
   CTFd 下载与每题 Docker 容器，调用已有 Claude Code/Codex；README 中 Flag 仅正则提取。
   文档明确将模型凭据/认证放入题目容器，与说明的凭据隔离要求冲突，不能直接照搬。

5. CAI：https://github.com/aliasrobotics/cai
   当前仓库已归档，README 表明不再维护，许可证也不是全树统一 MIT。
   不选作新项目首选底座。

## 建议与下一步

先评估 BoxPwnr 的本地 Reverse 路径，在独立目录保留上游身份；补 Docker 后，
用一道人为已知答案的授权题检查真实工具链、答案隔离和验证判定，再决定复用范围。
不为了保留刚写的骨架继续投入。当前仅建议，未安装、克隆或修改这些第三方项目。
