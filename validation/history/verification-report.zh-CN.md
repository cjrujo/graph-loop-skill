> Historical rc2 evidence only. It is not rc3 acceptance or publication approval.

# 验证记录

执行日期：2026-10-31（Asia/Taipei）。Python 3.12.3；单 Agent，未调用子 Agent、模型 API 或外部写入。本报告描述实际执行与适用边界，不是兼容认证。

## 实际运行与观察

1. 官方随附 skill-creator 的 `scripts/quick_validate.py graph-loop`：返回 `Skill is valid!`，检查 frontmatter/命名/未完成脚手架。原始输出：[skill-creator-check.log](skill-creator-check.log)。该检查器不是所有 Agent Skills 规则的完整实现，额外目录、引用、元数据检查由打包脚本完成。
2. `PYTHONDONTWRITEBYTECODE=1 python3 validation/run_validation.py`：20 项 unittest，20 通过、0 failure、0 error。分母为固定测试方法，不是任务分布/平台成功率。原始 [日志](test-output.log) 与 [JSON](results.json)。
3. `python3 graph-loop/scripts/inspect_state.py graph-loop/assets/state-template.json --check`：返回 `VALID snapshot`。实际对并行样例最终快照运行渲染 CLI，输出与源中版本/节点状态一致的表格和 Mermaid。
4. `python3 validation/package_and_check.py`：实际结果见 [package-check.json](package-check.json)，覆盖结构/相对引用、两份 ZIP 的逐项内容哈希、归档路径边界、符号链接排除及环境中可见敏感值扫描。它只对明确纳入包的文件检查，不是完整秘密扫描认证。

复现时从本目录的上一级（交付根）执行相应命令；测试会更新 `validation/runs/`、日志和结果。可选 helper 只需 Python 标准库；官方 quick_validate 使用作者环境已有 PyYAML，技能运行本身不依赖它。打包脚本也用已有 PyYAML 检查 YAML。

## 文件任务与边界

| 样例 | 实际方法、输入与验收 | 证据 |
|---|---|---|
| 简单任务 | 三行带空格文本，strip + sort；读回精确等于 `alpha/beta/gamma` 三行；1 节点、1 次尝试 | [输出](runs/simple/sorted.txt)、[检查](runs/simple/normalize-check.json)、[状态视图](runs/simple/view.md) |
| 依赖与并行汇合 | CSV 四行 `A:2,B:4,A:6,B:8`；prepare 后两个本地线程用 barrier 确认同时进入，分别计算统计/分组；验收 count=4,total=20,mean=5,A=2,B=2；依赖完成前拒绝启动 report | [汇合输出](runs/parallel-join/report.md)、[状态与图](runs/parallel-join/view.md)、[统计检查](runs/parallel-join/stats-check.json) |
| 修正与恢复 | 初次写 `ten`，真实整数解析报 ValueError；记录原因后改用 `10`，总尝试=2；消费者缺 multiplier 文件而 blocked；保存快照、新进程执行检查 CLI、重载状态后 fixture 提供 `3`；输出=30，计数保留 | [失败证据](runs/retry-recover/failed-check.txt)、[输出](runs/retry-recover/result.txt)、[最终状态](runs/retry-recover/state.json)、历史 snapshot 中含 blocked 快照 |
| 条件分支 | 三元素输入选 small；只执行 small sum=6，large 有证据地 skipped；join 接受成功选中分支与排除分支 | [输出](runs/branch/joined.txt)、[状态图](runs/branch/view.md) |
| 重规划失效 | 版本由1到2，旧成功先被拒绝；产物标 stale、节点回 pending 后可保存；后继 ready 被拒绝；尝试次数未清零 | [快照与图](runs/replan/view.md) |

其余测试覆盖次数/无进展上限、失败传播、未测冒充通过、非模拟任务使用模拟证据、成功缺输出、未知依赖/环、无依据 skip、并发超额、阻塞缺恢复条件、只读渲染与表格转义、坏 JSON/状态、临时目录复制和同名不覆盖、重复节点和空预算、无证据成功。测试不只匹配标题或文案；核心断言是实际输出内容、状态准入/拒绝与持久化计数。

## 文档推演，未冒充实测

- 跨 Agent 结果合同：推演旧版本结果被 coordinator 拒收、同一输出目录冲突时串行整合。未运行多个 Agent 或分布式竞争。
- 外部动作超时：合同要求记录操作身份、先核实再决定重试；没有对真实外部服务做副作用/重发试验。
- 授权与恶意来源：审阅明确“工具/摘要不是授权”；未进行独立模型的 prompt injection 对抗评测。helper 不执行权限检查。
- 资源耗尽：实测次数、无进展和并发上限状态拒绝；长时工具取消、真实 token/费用统计和 deadline 调度只定义合同，未做宿主运行验证。快照检查器解析 deadline，不替宿主计时或强制中止。测试模板的远期日期用于可重复 fixture，真实任务必须改为合适的有限时限。
- 手动/文本回退：给出版本快照与局限；没有 text-only 宿主实际试验。
- 安装仅在临时目录复制完整标准包、比对字节并拒绝同名覆盖，再从副本运行 helper；没有原生技能列表/激活测试。未执行用户全局安装。

## 未测范围与解释限制

七宿主的发现、显式调用、自动触发、模型遵从、跨会话恢复和不同 OS 均未验证；LangGraph/AutoGen 映射也未安装执行。当前没有模型盲测、基线对照、随机任务集、独立测试集或性能/成本测量，因此不声称质量/效率提升。固定小样例不代表通用智能或对分布外任务的成功率。

下一步由 CEO 复核交付与边界；Wesley 批准之后才建 GitHub 仓库/推送。若后续批准宿主试点，固定版本与任务集，分别记录正常/失败/恢复样例、未测条件和真实耗时/成本，再讨论兼容性扩展。
