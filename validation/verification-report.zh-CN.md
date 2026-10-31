# rc3 验证报告

结论：原 20 项确定性用例复跑通过；新增 18 项检查通过，其中 17 项执行本地文件/进程/辅助工具行为，1 项仅检查 chat fallback 文档。样本是固定的本地模拟工作负载，provider ledger 也是模拟。没有模型能力成功率或七宿主实测结论。

## 实际执行与证据

| 检查 | 实际方法与观察 | 证据 |
|---|---|---|
| 原 20 项 | 文件任务、并行工具、branch/join、retry、版本失效、状态格式等原用例 20/20 | [results.json](results.json)、[test-output.log](test-output.log)、[runs](runs) |
| 节点中途硬中断 | 子进程提交 step 1 后在节点内纯计算等待处由父进程发 SIGKILL，returncode=-9；新进程读取最近提交点，恢复得 `[1,4,9]`，attempt=1、累计 work=3 | [process-observation.json](recovery-runs/sigkill/process-observation.json) |
| 主动暂停/便携恢复 | 固定 worker 收到 stdin pause 后未生成 step-2；保存 r5、导出 ZIP；新目录/进程导入，旧目录移走后仍恢复，small 分支字节/mtime 与 attempt 不变，large attempt=0 | [pause-observation.json](recovery-runs/pause-portable/pause-observation.json)、[示例 ZIP](../examples/portable-demo-v1-r5.zip) |
| 确认丢失的外部效果 | **模拟 provider** 记录 applied/calls=1，ack 未写回时 prepared 操作使 resume 阻塞；按 ID 对账记录证据后解除歧义，calls 始终 1 | [ledger.json](recovery-runs/simulated-provider/ledger.json)、[对账证据](recovery-runs/simulated-provider/task/evidence/provider-reconcile.json) |
| 缺失/篡改产物和输入 | 删除/改写 small.txt、改写输入，preflight 阻塞；依赖不因已有 succeeded 标记而放行 | [recovery-test-output.log](recovery-test-output.log) 的 04、11 |
| 最新快照损坏/缺失 | 非 JSON、合法 JSON 内篡改 checksum、删除 state.json 均拒绝自动加载；previous 仅只读查看，不自动执行旧步骤 | 同日志 05、13、14；[损坏快照场景](recovery-runs/corrupt-latest) |
| 旧包/来源/完整性 | 已更新源拒绝旧包；拒绝错 graph/lineage、已有目标覆盖、manifest 篡改、unsafe paths、symlink | 同日志 06、10、15、17 |
| 累计预算与生命周期 | attempt、work、非零 elapsed 不得清零；重启后耗尽预算仍阻塞；暂停要显式 resume，cancel 不复活；verifying 保留 phase/attempt，ready 暂停不虚增 attempt | 同日志 07、08、09、16、18 |
| chat fallback | **文档检查**完整状态/文件/缺项/英文提示词格式与提示词一致性；未执行聊天宿主/用户保存行为 | 同日志 12 |
| 标准技能包独立性 | 仅解压标准 ZIP，在临时目录运行其自身 inspector/import/show/check/resume/pause/export 共 8 条命令，二次导出 manifest、提示词和证据链接验证通过 | [isolated-package-check.json](isolated-package-check.json) |
| 结构/引用/归档/hash | 实际 skill-creator quick_validate；package_and_check 检查本地引用、安全路径、CRC、逐成员字节及逐文件 SHA-256、有限敏感值匹配、冻结基线一致性 | [结构日志](skill-creator-check.log)、[package-check.json](package-check.json)、[source-manifest.json](source-manifest.json)、[archive-manifest.json](archive-manifest.json)、[基线一致性](baseline-unchanged.json) |

全部新增结果：[recovery-results.json](recovery-results.json)。初次执行曾有一项断言匹配到了更早的 schema 拒绝原因，已修正为接受这两种明确拒绝；检查过程中还补齐了 ready 节点暂停恢复、paused 节点取消、保留路径和有限敏感值导出拒绝。最终日志对应当前代码；未掩盖未通过的业务场景。

## 可复现命令

在源码根目录执行，Python 3.10+，测试与保存/导出/包装工具均只用标准库：

```bash
python3 graph-loop/scripts/inspect_state.py graph-loop/assets/state-template.json --check
PYTHONDONTWRITEBYTECODE=1 python3 validation/run_validation.py
PYTHONDONTWRITEBYTECODE=1 python3 validation/run_recovery_validation.py
python3 validation/package_and_check.py
PYTHONDONTWRITEBYTECODE=1 python3 validation/check_isolated_skill_package.py
python3 validation/package_and_check.py
```

实际执行的 skill-creator 命令使用当前环境已安装校验器（依赖已存在的 PyYAML，没有新安装）：

```bash
python3 /tmp/paperclip-ai-801e4e0b-ca6b-4059-855d-1de14531c348-76346642-4d68-4d7a-8472-259e9625521e-wbavGz/provider/skills/.system/skill-creator/scripts/quick_validate.py graph-loop
```

新环境将路径换成其已安装 skill-creator 的路径；若没有此技能，不能声称重新跑过该校验。独立的 package_and_check 可在没有 PyYAML 时运行。

格式升级适配：原 20 项测试的逻辑与断言保留，仅 new_state/node 的输入模板路径改到 `validation/fixtures/legacy-state-template.json`（冻结 rc2 模板）；新 schema v2 由新增用例和当前模板只读检查覆盖。历史证据放在 [history/README.md](history/README.md)，不能当 rc3 CEO 验收。复跑会重写当前日志/快照，须重新打包刷新清单。

## 未测与限制

- 没有运行任何模型/学习策略、七宿主安装/激活、真实 provider、真实宿主 stop 按钮、跨设备用户下载或聊天留存测试。
- 真实进程中断仅测一个已握手的 checkpoint 后位置；未穷举写入每个指令偏移，未测断电、网络文件系统或硬件 fsync 语义。
- 固定 worker 的顺从不证明 AI 会遵循合同；18 项也不是通用能力成功率。累计耗时防回退用非零值测试；微型演示的 elapsed=0 不代表真实工作没有耗时。
- 没有持久化/可读取导出/唤醒工具就不能保证自动恢复。上次提交后的工作可能丢失；旧快照不能证明未发出请求，未知效果必须对账。
- 工具只机械保存/检查，不能证明语义验收、当前权限或来源真实性。SHA-256 不是签名；环境敏感值匹配不是完整 DLP。
- 只有本地候选与任务内交付；未 GitHub 写入、发布、采购、全局安装、调整预算或再委派。
