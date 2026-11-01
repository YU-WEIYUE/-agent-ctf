# 第三方来源与复用范围

BoxPwnr: https://github.com/0ca/BoxPwnr

固定提交：`6e2778ce6741b2f1755b4cfbc5ea37b663b1399c`；许可证：AGPL-3.0。
项目根 `LICENSE` 保留上游许可证全文。CTF-Forge 本次衍生代码按 AGPL-3.0 提供，未发布。

实际复制并纳入包的四个模块位于 `src/ctf_forge/_vendor/boxpwnr/`：

- `platforms/base_platform.py`：平台抽象。仅将绝对导入调整为本地相对导入。
- `platforms/target.py`：题目/目标模型，原样保留。
- `executors/base_executor.py`：执行器协议与 RawExecutionResult，原样保留。
- `core/deadline.py`：截止时间基础设施，原样保留；当前未接入解题循环。

逐文件上游/本地 SHA256 见 `third_party/boxpwnr-source.json`；本地包初始化文件为新增，
未使用上游会自动导入多平台和 Linux PTY 的初始化逻辑。未复制整套大依赖、平台账户接口、
提示词、默认 Docker 执行策略和缺少答案时判成功的分支。

实际接入点：`adapters/local.py` 继承 BasePlatform、返回上游 Target；
`sandbox/docker_runtime.py` 直接返回上游 RawExecutionResult。DockerRuntime 提供受限 argv
接口，未声称实现上游全部 Shell/PTY BaseExecutor 协议。LangGraph 自动模式与外部 Agent 模式已接入同一套执行和验证引擎。

NYU Agents、EnIGMA、Clank the Flag 本轮只做过结构评估，未复制其源代码，不混拼多个框架。
`_vendor` 保留上游风格，Ruff 不改写这些文件；mypy 对上游未标注代码单独排除，
本地适配器与执行器仍接受检查。
