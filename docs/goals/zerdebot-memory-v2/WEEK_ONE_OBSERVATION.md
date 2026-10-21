## Oct21：首周有限元数据观察完成，普通 ask 仍待完整修复

主40+独12次实际只读与全部52原响应的独立正确性/维护复核完成。四群CONTROL在两个时点均ACTIVE、learning=true且首发epoch保持，观察revision1；后续合法推进不强写回。Oct15–21共28个固定UTC日行中21存在、7缺席，中文3/4、其余三群各6/1（存在/缺席）。缺席或缺字段不当0，Oct21为部分日，不相减推积压、人数、事实或模型成功。28日行只有主读取，其余指定12项独立fresh。

第四群Oct21 News保存的4步骤均SENT并有回执；Quiz执行、题目记录和投票索引三份元数据按各角色自己的fresh执行记录关联一致。两项均有独立fresh，不代表完整News清单、原生Telegram、内容语义、故障恢复或周榜；这些缺口保持。自然0/50有据、0/20未知、起点null、production_ready=false保持，四群仍RELEASED_OBSERVING。

人类指出普通 `/ask RTX SPARK` 仍用群聊缺上下文代替有效主题回答。PR286已部署的selector提示修复与旧两条对照只提供有限证据，不能称普通问答完整修好；主/备用普通生成模板仍待修复，真实内部mode/模型原因没有捕获。本次元数据观察不关闭该问题。

本轮52操作器AWS只读、0云写/UI/模型/运行部署，自然增量0；CI既有OIDC/CDK只读另计。52份实际原响应同原起点2026-10-21T17:42:41.712325+00:00，期限2026-10-28T17:42:41.712325+00:00；首API前已登记Z10与原zerde。新增第十七项，原十六项保持。主/独/start入口均结束不可重跑；行政快照单独保留，不按private后缀扩大原文范围。

[完成与边界](WEEK_ONE_OBSERVATION.md)、[实际聚合](evidence/2026-10-21-week-one-observation/completion.safe.json)、[独立复核](evidence/2026-10-21-week-one-observation/completion-independent.safe.json)、[维护复核](evidence/2026-10-21-week-one-observation/completion-maintenance.safe.json)、[十七项副本](RETAINED_COPIES.md)。

## 以下为此前完整冻结阶段，不作当前状态或重跑指令

# 首周有限业务观察

状态：本地准备；真实云读取尚未执行。完整本地计划入口为2026-10-21-week-one-observation/PLAN.md；正式工具和双PRE绑定见本目录的准备证据。运行仍PR286，不部署新包。

## 最小范围

账号/区域和三表ARN/TableId沿已核安全来源，在新角色首轮重新读回身份。主依序STS1、三表Describe3、四CONTROL4、四群Oct15–21日计数28、第四群Oct21News1、QuizExec1；仅该角色读到完整有效DONE时增加QUIZ与POLL两个关联点读，共最多40。独角色自己读身份/四CONTROL/News/QuizExec及自己的两个关联，共最多12；不把28日计数称全部fresh独读，其原响应另作本地独审。

所有GetItem强一致，只取原owner元数据；不Query/Scan/GSI/读日志/正文/用户或积分，不调用模型或写业务。CONTROL合法revision推进允许，epoch只比较原hash，不强写历史值或自动重开。COVERAGE的六计数来自不同处理阶段、可能跨日或包含修订，缺行ABSENT、缺字段MISSING；不补0，不相减推积压。其90日TTL与本地副本7日保留不同。Oct14首发部分日未覆盖，Oct21尚未结束，不宣称完整七日自然验收。

News只看保存步骤的发送确认，repair_note若返回仅留受控原文，不入safe摘要；空步骤不当无新闻，revision0属于合法初值，不证明manifest完整。Quiz三侧generation/poll_id/message_id要精确一致，POLL还核群/request/每日标志；不读题目/选项/答案。DONE后的生成expires_at不是发送回执TTL；记录逻辑过期另列。顺序读不是事务，缺席/漂移如实保留，不补读追平。

周榜没有独立持久发送回执，本轮NOT_COVERED；Oct16周五13:00UTC为上次正常时点、Oct23为下一次，不能把Oct17周六无记录当漏发。原生Telegram、完整答案语义、恢复/并发/UNKNOWN及自然质量仍由原工单验收。

## 执行和保留

原定Oct21 17:35UTC有限观察，实际窗口17:35–23:55UTC，每角色总600秒、请求前保留30秒余量、5秒连接/15秒读、SDK不重试，并核墙钟与monotonic。异常立即保留PARTIAL_UNKNOWN；主/独正式label各一次。新工具只导入旧冻结工具的纯校验helper，绝不执行旧入口或读取旧raw/snapshot。

首API前建立真实anchor/空ledger并登记Z10和原zerde，原期限=实际anchor+604800秒；本次准备尚无anchor或新增期限。每API先INTENT再CAPTURED，原响应0600/目录0700，身份/hash/期限核验，错误只留固定code/类型。未知保全、不自动重跑。内置全局与批锁，不重复外锁；UI/发布/删除串行。正式状态只有实际回执可证明。

## 当前边界

四群已启用、RELEASED_OBSERVING保持；自然0/50有据、0/20未知、起点null、production_ready=false。无自然新增，不邀请人/造聊天/新群。已有十六项精确责任及全部失败/UNKNOWN保持；已结束ask/媒体/清理once不可重跑。当前准备发现并修订news revision0、时钟预算、登记语义和失败回执门，未执行旧草稿，不能宣称第一次就无问题。

[准备证据](evidence/2026-10-21-week-one-observation/preparation.safe.json)；[任务状态](task_manifest.json)；[原十六项副本](RETAINED_COPIES.md)。
