# 普通 /ask 意图分流修复已发布（PR286）

截图中的 `/ask RTX SPARK` 被回复为个人记忆缺证据，用户看到的行为不正确。本次仅修改原 selector 的 SYSTEM 意图指令：先区分普通知识/产品/技术/人物主题与个人、群成员历史问题；礼貌第一人称和无关或同词 facts 不应把普通问题改成个人记忆。个人及混合问题仍受原公开证据约束。原截图实际模型输出未捕获，不能据提示词缺陷倒推出该次精确内部 mode。

运行构建 `23df3413d2a0668ac766b9fc736c494c557e3ce8`，仅 `services/memory_v2/answer_prompt.py` 一个包成员改变；原schema/model/provider/retry/budget/身份/投递owner保持。16个多语案例与34新测试覆盖真实selector/parser/adapter及owner入口的provider stub；最终196定向通过，源码CI39456220920最终2640测试及三个job成功。两环境各五ARM入口/12实包合成检查通过，均不冒充真实模型语义。

dev/prod各唯一Execute，运行完整ZIP分别为 `64ee7382ec32dae504d89aa51a38e4e6336e0f255544dd82ba3e3c5b6e3c4509` / `64ee7382ec32dae504d89aa51a38e4e6336e0f255544dd82ba3e3c5b6e3c4509`。主、独完整包及配置/18告警/现有CONTROL/News-Quiz目标保护、Execute后至少300秒稳定通过。dev原独立收集在14成功读、五完整ZIP后AssertionError停止；精确分支UNKNOWN。旧失败保全，新窄续接仅下载缺失层并用新metadata重核、沿用并校验五原完整ZIP，明确是组合证据。prod两次新post每包取得当前下载地址，无第二Execute。

操作器AWS 367调用，写8次（4 PutObject、2 Create、2 Execute），运行GitHub GET32另启动8；原失败14成功读计入总数。0操作器UI/模型/自然样本，CI既有OIDC/CDK读另计，不指正常业务无调用。真实普通ask和个人缺证据对照尚未本批执行；另新有限dev合同、完整原预算时点门及新的直接人类15分钟独占窗口后才能验收。不把包校验、CI或普通成功当完整Memory自然质量。

本批原文最终411 CAPTURED，原起点 `2026-10-20T16:31:53.365253+00:00`、七日期限 `2026-10-27T16:31:53.365253+00:00`（原epoch `1793118713.3652532`）固定；ledger `2f28b418cc207648b0ef46b5b1b4776afca9d86d28f99ea0f96fa28ecc61b2e6`。API/配置/含原文派生同一期限，源码/完整ZIP/安全聚合保留，另scope/PRE到期处理。今天告警341已履行，原十五项不合并延期，加本批共十六项。不是安全擦盘。

四群仍RELEASED_OBSERVING；自然0/50有据、0/20未知、起点null、production_ready=false。旧媒体2424–2427/STOP/版本差异/未发Q、完整双图语义/单SENT/lease缺口保持；旧Quiz、费用实付和其它业务UNKNOWN不关闭。20任务仍14OPEN/6CLOSED、EpicOPEN。文档提交和合并不再运行部署。

[实际发布聚合](evidence/2026-10-20-ask-intent-repair/release.safe.json)、[独立直接复核](evidence/2026-10-20-ask-intent-repair/release-independent.safe.json)、[源码CI](evidence/2026-10-20-ask-intent-repair/source-ci.safe.json)、[副本台账](RETAINED_COPIES.md)。
