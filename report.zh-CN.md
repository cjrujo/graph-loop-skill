# THE-30 交付报告：Graph & Loop 1.0.0-rc3

已在独立 recovery-revision/source 完成逐节点内部断点、主动暂停/明确取消、显式恢复与便携状态包候选。冻结 rc2 保留不变；没有发布授权，当前等待 Jensen 独立验收。

交付文件：

- `graph-loop.zip`：完整标准技能资源，包括 SKILL、状态模板、恢复合同、只读 inspector、可选保存/检查/导入导出脚本、chat fallback 与英文 resume prompt。
- `graph-loop-review-bundle.zip`：完整源码、原 20 项及新增 18 项检查、场景文件、日志、历史标记与逐文件 hash。
- [英文 resume prompt](resume-prompt.en.md)、[英文 install prompt](install-prompt.en.md)、[中文用户演示](user-demo.zh-CN.md)。
- [实际生成的暂停恢复包](examples/portable-demo-v1-r5.zip)：固定本地模拟工作，含原始状态、上下文/产物/验收证据、manifest、进度与英文提示词。
- [详细验证报告](validation/verification-report.zh-CN.md)、[变更与边界](review.zh-CN.md)、[发布候选清单](release-manifest.json)。

实测：原 20 项通过；新增 18 项检查通过（17 项文件/进程/工具执行，1 项 chat fallback 文档检查）。真实子进程 SIGKILL 后从最近提交点继续；暂停后没有新业务步骤；导出在隔离新目录/进程恢复，已完成分支不重复；模拟 provider 的已发生但未确认效果不重发；篡改/缺失产物、坏最新快照、旧包和预算回退不会通过恢复门。skill-creator 与归档/引用/hash 检查均有日志，不能把这些固定用例当成模型遵从或七宿主实测。

用户停止后保留最新的版本化恢复 ZIP，或完整可复制快照；下次附上该包并粘贴英文 resume prompt，给出当前范围和权威转移来源。首次执行前技能要求公布真实状态位置与取回方式；无宿主能力时明确限制。恢复包中的授权摘要只是证据；未知外部效果必须对账，取消不会偷偷转为重试。

主要不确定性：硬停止仍可能丢失上次 checkpoint 后的未落盘工作；宿主取消/持久化/导出/唤醒能力未集成测试；不承诺任何原因下无损无缝，也不声称 exactly-once。没有 GitHub 写入/发布、采购、全局安装、预算调整或再委派。

本地根目录：`deliverables/THE-28/recovery-revision/source/`。下载链接与文档保存回执将记录在当前 THE-30 任务 report；父任务报告和发布审批材料由 Jensen 负责。
