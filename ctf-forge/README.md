# CTF-Forge

授权本地 ELF 逆向工作流。默认由当前 Codex、Hermes 或其他 Agent 决策，项目负责 Docker 内执行、观察、候选验证、记录和报告。也支持 DeepSeek API 经 LangGraph 无人值守运行。

**任意 Agent 先读 `AGENTS.md`。真实验收状态见 `IMPLEMENTATION_STATUS.md`。**

若未来公开，发布范围只允许可复用代码、自建样例、测试和脱敏方法文档。比赛附件、flag、平台回执、实例端点、会话凭据与现场工作目录均须排除。当前没有 GitHub remote，也未提交或推送。多 Agent 赛事实战的调度与交接方法见 [`docs/AGENT_COMPETITION_PLAYBOOK.md`](docs/AGENT_COMPETITION_PLAYBOOK.md)。

## 现在可以做什么

`solve → observe → step → submit_flag → report` 已通过真实容器闭环测试。提供 pyelftools ELF 解析、strings、objdump、Capstone、受限 GDB、Python 和题目程序运行。无答案时只保留候选，不把字符串格式匹配当成功。

BoxPwnr 的平台接口、Target 与执行结果对象已实际复用；第三方来源及哈希见 `THIRD_PARTY_NOTICES.md`、`third_party/boxpwnr-source.json`。采用 AGPL-3.0，LICENSE 已保留。

## 环境与启动

Python 3.12+、uv、Docker Linux 引擎。本机已有 Python 3.12.14，Docker 已装入 WSL Ubuntu-22.04；分析镜像基于 Ubuntu 24.04。项目独立虚拟环境不替换系统 Python，不依赖本地模型。

在项目目录执行：

```powershell
uv sync --locked
.\scripts\start-docker.ps1
uv run ctf-forge doctor
uv run ctf-forge self-test
```

WSL 空闲关机后 dockerd 会一并消失；每次开工先跑 `uv run ctf-forge doctor`，失败则 `.\scripts\start-docker.ps1`。

本机分析镜像已构建。重新构建：

```powershell
uv run ctf-forge build-image
```

如果 WSL 连 Docker Hub 超时，但 Windows 能访问，`scripts/fetch-ubuntu-image.py` 可在 Windows 下载并核对官方 Ubuntu manifest、压缩层及解压层哈希：

```powershell
uv run python scripts/fetch-ubuntu-image.py
wsl -d Ubuntu-22.04 -u root --exec docker load -i /mnt/<drive>/<project>/.data/ubuntu-docker.tar
uv run ctf-forge build-image
```

其他机器请按实际项目位置改最后的绝对路径；当前基镜像来源记录在 `third_party/ubuntu-image-source.json`。普通 native Docker 环境把 `configs/sandbox.yaml` 的 `wsl_distro` 改成 null 即可。

## 方式一：当前 Codex 或任意 Agent 驱动（默认）

不需要 API Key，也不另启动模型。可以直接对当前 Agent 说：“读项目 AGENTS.md，用这个项目分析这道题”。Agent 使用下列协议：

```text
uv run ctf-forge solve <ELF路径> --description <描述文件>
uv run ctf-forge observe <task_id>
uv run ctf-forge step <task_id> --action <动作JSON文件>
uv run ctf-forge report <task_id>
```

`solve` 默认 external 模式，输出 task_id、观察和工具 Schema，容器保持到验证成功、主动关闭或寿命上限。动作文件示例：

```json
{"tool":"strings","arguments":{}}
```

```json
{"tool":"python","arguments":{"code":"print('sandbox test')"}}
```

```json
{"tool":"submit_flag","arguments":{"value":"flag{candidate}"}}
```

有可信本地标准答案时，加 `--answer-file <文本文件>`。答案只由宿主验证器读取，不送入容器、提示词或 observe。外部 Agent 本身拥有宿主访问权限时，必须遵守“不读取答案/源码来替代解题”的评测约定；本项目不声称能限制宿主机所有者。

无验证依据时，submit_flag 返回未验证候选。结束任务保存部分报告并销毁容器：

```text
uv run ctf-forge close <task_id>
```

故障后在原预算内显式恢复为外部 Agent 模式：

```text
uv run ctf-forge resume <task_id>
```

恢复保留观察、候选和计数，核对已暂存输入哈希，并重新创建容器。不自动延长预算，不自动重放有副作用的旧命令。锁文件残留时先检查其中 PID 确认原进程已退出，再处理锁。

## 方式二：DeepSeek API 无人值守

复制 `.env.example` 到 `.env`，只在本地填写 API Key。示例使用当前官方 `deepseek-flash` 和 `https://api.deepseek.com`；模型名称可自行替换。

```text
CTF_FORGE_MODEL__PROVIDER=deepseek
CTF_FORGE_MODEL__NAME=deepseek-flash
CTF_FORGE_MODEL__BASE_URL=https://api.deepseek.com
CTF_FORGE_MODEL__API_KEY=在本机填写
CTF_FORGE_MODEL__THINKING=false
```

```text
uv run ctf-forge config-check
uv run ctf-forge model-check
uv run ctf-forge solve <ELF路径> --mode autonomous --description <描述文件> --answer-file <可信答案文件>
```

流程为：准备沙箱/ELF 解析 → Coordinator 计划 → Solver 模型选工具 → 执行/记录 → 独立验证 → 完整或部分报告。LangGraph SQLite checkpoint 保存任务、消息、观察和计数。

DeepSeek 可打开 thinking；实现保留跨轮 `reasoning_content`，避免工具调用续轮缺字段；默认非 strict Beta schema，由本地 Pydantic 验证参数。接口依据：[官方入门](https://api-docs.deepseek.com/)、[工具调用](https://api-docs.deepseek.com/guides/tool_calls/)、[思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)。

**当前没有用户 DeepSeek Key：已通过本地 HTTP 协议测试，尚未实测 DeepSeek 云端解题。** 项目不会使用 Codex 登录文件或其他助手的密钥。通用 OpenAI 兼容端点可使用 provider=openai。

## 方式三：比赛平台（rCTF）拉题与提交

平台适配只在宿主侧联网，题目容器仍断网。凭据放 `.env` 的 `CTF_FORGE_PLATFORM__AUTH_TOKEN`，或用 `configs/platform.yaml` 指向的会话文件（默认 `.data/hi-session.secret.json`，已被 `.gitignore` 排除）。

```text
uv run ctf-forge platform me
uv run ctf-forge platform list --category reverse
uv run ctf-forge platform pull "<challenge-name>"
uv run ctf-forge solve <challenge-file> --description <description-file> --platform-challenge <challenge-id>
uv run ctf-forge platform submit "<challenge-name>" --flag "<candidate>"
```

- `pull` 从题目描述的 markdown 链接取附件（本平台附件在对象存储，不在题目 JSON 的 `files` 字段），并核对题目声明的 SHA-256；不一致退出码 1。
- `solve --platform-challenge` 让平台充当独立验证器：`submit_flag` 直接提交平台，只有返回 `good*` 才记 `platform_accepted` 并结束任务；`bad*` 记 `rejected`、任务继续。此时不需要也不使用标准答案文件。
- 平台对库默认 UA 返回 Cloudflare 1010，`configs/platform.yaml` 的 `user_agent` 是必需的浏览器签名；该文件不含凭据。
- 适用范围：有下载文件的题目（当前赛题中的 10 道 Reverse）。instancer/远程实例题与非 reverse 分类不在本工具范围内。

## 发现接口、状态与证据

```text
uv run ctf-forge capabilities
uv run ctf-forge tools
uv run ctf-forge inspect <ELF路径>
uv run ctf-forge task list
uv run ctf-forge task show <task_id>
```

`--project <目录>` 可从其他目录指定配置/状态根；单纯 `uv run` 仍应在本项目或使用 `uv --directory <项目>`。

- `.data/tasks.sqlite3`：任务与候选状态。
- `.data/checkpoints.sqlite3`：自动模式的 LangGraph 节点状态。
- `workspaces/<task_id>/session.json`：恢复所需信息；input 为题目副本，work 为容器可写区域。
- `reports/<task_id>.json`：完整观察、消息、验证证据、预算、输入哈希和停止原因。
- `reports/<task_id>.md`：可阅读报告，含候选验证和实际工具证据。
- `reports/history/`：报告被再次保存时保留的原件。
- `.data/events.jsonl`、各工作目录 events.jsonl：结构化日志。

退出码：0 表示命令完成，1 为运行错误，2 为参数错误，3 为自动模式停在部分/未验证。external 的 solve 返回 0 仅说明会话建立，是否解决看 status。没有平台自动提交功能。

## 预算与隔离

默认每题 600 秒、30 工具调用、15 模型请求、100000 Token、3 次连续无进展；单工具 30 秒；每输出流只保留最多 64 KiB。配置在 configs/，优先级：环境变量 > .env > YAML > 默认值；solve 的显式预算参数另行覆盖并随任务保存。

API 模式在调用边界按真实 usage 累计 Token，调用前用保守输入预留约束输出，缺 usage 时明确按保守字节估算；供应商分词/上下文开销不能视作精准计费。模型重试受剩余时间限制。external 模式的模型请求/Token 由外部 Agent 管理，项目记录 0 表示未观测到，不代表实际没有消耗。

容器默认断网、非 root、只读根、cap-drop ALL、no-new-privileges，输入只读、工作目录独立挂载，限制 CPU/内存/PID。额外 900 秒容器寿命上限处理外部 Agent 失联；超时销毁。WSL 使用 --exec 直接传递参数，不经宿主 Shell；模型凭据不进入容器。

## 测试与样例

```text
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run pytest -q
uv run ctf-forge self-test
uv run ctf-forge build-samples
uv run python scripts/verify-external-smoke.py
```

已有 10 道自行生成的简单 ELF：输入 key 检查 + XOR 解码。源码/答案仅供维护者与验证器，Solver 只接收 ELF。脚本 smoke 会从工具输出读取 fixture key、运行二进制取得候选，再交宿主验证；这是脚本集成测试，不是模型能力 Benchmark。

DeepSeek Key 配置后可运行真实模型 Benchmark：

```text
uv run ctf-forge benchmark --attempts 1 --limit 10
uv run ctf-forge benchmark --attempts 3 --limit 10
```

统计实际 Pass@1/Pass@3、用时、Token、工具执行成功率及被拒候选数；未测指标保持空值，不混用外部脚本结果。当前样例同属简单合成家族，不能推断比赛水平。API 计费未提供时成本为空。
