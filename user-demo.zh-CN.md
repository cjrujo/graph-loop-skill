# 用户演示：暂停后拿什么，下次贴什么

当前交付是 rc3 候选；以下真实运行使用固定本地模拟工作负载，没有调用模型或真实外部 provider。

开始前，AI 应先告诉你：「权威状态在 task-store/state.json；通过当前宿主文件查看器取得。便携包是带版本的 recovery-v1-rN.zip，通过实际附件链接下载。每个安全步骤或最多 30 秒提交一次；宿主工具无法中断时另列风险。」如果没有真实文件/附件能力，应直接给完整可复制快照，不能只报一个你打不开的路径。

你说「暂停」后，AI 必须立即停止启动新业务步骤，尽力停止/核对在途工具，仅保存状态与导出；不能为了收尾继续做下一业务步骤。已经发出的外部请求可能无法撤回。硬停止发生在它保存之前时，只能恢复最近已提交版本。

**本演示保存的文件：[portable-demo-v1-r5.zip](examples/portable-demo-v1-r5.zip)**。其中 `state.json` 是可读机器状态，`PROGRESS.md` 是进度，`RESUME_PROMPT.en.md` 是下次提示词，`files/` 带走必要上下文、已完成产物和验收证据，`MANIFEST.json` 校验所有其他成员，`ORIGIN.json` 写明来源、版本与缺项。此例没有缺失外部文件；实际任务必须列明无法带走的文件、账号权限或服务依赖。

实测暂停状态：graph=`portable-demo`，lineage=`the30-fixed-local-fixture`，graph v1 / revision 5；select 与 small 已成功，large 是有证据的排除分支；work 在第 1 个安全步骤暂停，attempt=1，累计工作单位=1，第 2 步文件不存在。恢复在新目录和新进程进行，原目录移走后仍得到 `[1,4,9]`；完成分支未重跑，work attempt 仍为 1，累计工作单位增至 3。证据见 [pause-observation.json](validation/recovery-runs/pause-portable/pause-observation.json)。elapsed=0 是此微型 fixture 未作耗时计费的值，不是实际长任务无时间成本；独立测试验证了非零累计耗时不能清零。

下次打开新会话，上传这个 ZIP，复制 [完整英文 resume prompt](resume-prompt.en.md)，填入 graph、lineage、版本和你的当前范围/授权来源。例如 prompt 开头填：

```text
I explicitly request that you resume my Graph & Loop task portable-demo from portable-demo-v1-r5.zip, graph version 1, revision 5, expected lineage the30-fixed-local-fixture. This is the fixed local demonstration only. The original writer has stopped; use the current user request as the authority transfer record after checking the package. Existing external-action gates remain in force.
```

再附上提示词剩余全文。AI 应先查来源、SHA-256、新旧版本、输入变化、产物/验收证据、预算/attempt 与权限，核对 running/verifying 和未确认操作。已完成且证据仍有效的节点复用；当前节点从最后提交步骤继续。取消状态不恢复；未知副作用不能用 timeout 当作失败重发。

可复现本例的本地导入（在源码根目录运行；这是 staging，不会自动业务执行）：

```bash
python3 graph-loop/scripts/recovery_store.py import examples/portable-demo-v1-r5.zip demo-staging --expected-graph portable-demo --expected-lineage the30-fixed-local-fixture
python3 graph-loop/scripts/recovery_store.py show demo-staging
python3 graph-loop/scripts/recovery_store.py check demo-staging
```

没有提供原权威状态时，导入显示 freshness unverified，并保留 interrupted。`check` 只查机械条件；即使退出码 0，也需要当前明确 resume 与 authority transfer、权限和语义验收检查，才能继续。详细恢复验证由 `validation/run_recovery_validation.py` 实际执行；不能把用户复制一次 prompt 当作模型一定遵从的证明。

若新 AI 读不了 ZIP，请提供其中 state、progress、manifest、必要文件完整文本及英文提示词。纯聊天场景使用 [完整快照模板](graph-loop/assets/chat-snapshot-template.md)，保留整个消息；不能只复制「下一步继续」一句。没有持久化或唤醒能力时，不承诺后台自动恢复。

先别宣布「永不中断」，先把第一个安全步骤带到下一场会话。
