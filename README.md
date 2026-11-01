# CTF-Forge

自主式 CTF 解题 Agent，第一阶段聚焦 ELF 逆向分析。由当前 Agent（Codex / 任意 LLM 助手）决策，项目负责 Docker 内执行、观察、候选验证、记录与报告；也支持 DeepSeek API 经 LangGraph 无人值守运行。

> **任意 Agent 先读 [`ctf-forge/AGENTS.md`](ctf-forge/AGENTS.md)。** 真实验收状态见 [`ctf-forge/IMPLEMENTATION_STATUS.md`](ctf-forge/IMPLEMENTATION_STATUS.md)。

## 功能

- **沙箱隔离**：每题一个独立容器，默认断网、非 root、只读根、`cap-drop ALL`、`no-new-privileges`，输入只读、工作目录独立挂载。
- **工具链**：pyelftools ELF 解析、strings、objdump、Capstone 反汇编、受限 GDB、Python、题目程序执行。
- **三种驱动模式**：
  1. 外部 Agent 驱动（默认，无需 API Key）——`solve → observe → step → submit_flag → report`
  2. DeepSeek API 无人值守（LangGraph + SQLite checkpoint）
  3. rCTF 平台拉题与提交（宿主侧联网，容器仍断网）
- **候选与验证分离**：无答案时只保留候选，不把字符串格式匹配当成功；平台模式下以 `good*` 应答记 `platform_accepted`。
- **预算控制**：默认每题 600 秒、30 次工具调用、15 次模型请求、100000 Token，连续无进展自动停止。

## 仓库结构

```
.
├── ctf-forge/                  # 主项目（Python 包，uv 管理）
│   ├── src/ctf_forge/          # 包源码：cli / core / llm / platform / sandbox / storage / workflow
│   ├── challenges/samples/     # 10 道自建 ELF 样例（key 检查 + XOR）
│   ├── configs/                # agent / models / sandbox / platform 配置
│   ├── docker/                 # Dockerfile（Ubuntu 24.04 分析镜像）
│   ├── docs/                   # Agent 竞赛手册等
│   ├── scripts/                # 辅助脚本
│   ├── tests/                  # 单元 + 集成测试
│   └── third_party/            # BoxPwnr 来源记录与哈希
├── 开发说明.txt                 # 项目开发规格（Milestone 0–7）
├── 使用说明.txt                 # 简明使用指南
├── CTF实战经验总结_v1.md        # 十二条可复用经验 + 错误复盘 + 开赛 SOP
└── 00_共享产出索引.md           # 版本变更与隐私复核记录
```

## 快速开始

要求：Python 3.12+、uv、Docker Linux 引擎（WSL2 亦可）。

```powershell
cd ctf-forge
uv sync --locked
.\scripts\start-docker.ps1        # WSL 环境下 dockerd 未启动时
uv run ctf-forge doctor           # 环境自检
uv run ctf-forge self-test        # 14 项容器隔离探测
```

外部 Agent 驱动（日常用法，不需要 API Key）：

```powershell
uv run ctf-forge solve <ELF路径> --description <描述文件>
uv run ctf-forge observe <task_id>
uv run ctf-forge step <task_id> --action <动作JSON文件>
uv run ctf-forge report <task_id>
```

完整命令、平台模式、DeepSeek 配置、重建镜像、Benchmark 等详见 [`ctf-forge/README.md`](ctf-forge/README.md)。

## 测试

```powershell
cd ctf-forge
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run pytest -q
uv run ctf-forge self-test
uv run python scripts/verify-external-smoke.py
```

当前状态：81 项测试通过，14/14 容器隔离探测通过，10/10 自建合成 ELF 集成通过。

## 隐私与发布范围

本仓库只包含可复用代码、自建样例、测试与脱敏方法文档。比赛附件、flag、平台回执、实例端点、会话凭据、`.data/`、`workspaces/`、`reports/` 现场目录均已排除（见 `.gitignore` 与 [`00_共享产出索引.md`](00_共享产出索引.md) 的隐私复核记录）。`.env` 不入库，模板见 `.env.example`。

## 许可证

AGPL-3.0。项目复用了 [BoxPwnr](https://github.com/boxpwnr/boxpwnr) 的平台接口、Target 与执行结果对象，来源与哈希见 [`ctf-forge/THIRD_PARTY_NOTICES.md`](ctf-forge/THIRD_PARTY_NOTICES.md) 与 [`ctf-forge/third_party/`](ctf-forge/third_party/)。
