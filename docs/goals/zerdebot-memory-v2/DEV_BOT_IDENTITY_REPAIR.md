## 2026-10-08：dev 提及身份配置已修复并完成实际读回

实际公开验收发现 dev 用户名误继承生产值。PR251 已将 development 身份与目标默认值分开，并修正 PR 预览的身份来源；15项新回归、38项infra测试、2390全测及三项CI通过。配置源码 `59674f58cfa7e5f92170b88fa5e0bad5bdf81dff`、合并 `ec72bea66c955782a94b87d10d6d5a7ba1287261`。唯一 development 用户名变量已创建并精确读回；dev 数字ID原本正确，生产身份和其他配置来源保持。

实际配置发布只改 dev Bot 的 AGENT_BOT_USERNAME 为 @zerde_dev_bot；全部两环境五函数及共享层的完整ZIP字节均保持PR248构建源 `8f1ba52960d8fe1b551dcdfe3e104b9d06ef04a0`。主检、独立读回和十函数300秒后稳定检查通过；业务资源、控制与预算保护保持，prod没有执行变更集。原五费用owner和104文件闭包不变，新的预算reader已绑定本轮实际配置并通过7次只读时点核验，不是持续模型许可或账单。

一次 ExecuteChangeSet 已获HTTP200；其后堆栈显示更新中、变更集暂为AVAILABLE，原轮询工具因此INCOMPLETE并完整保留。新独审合同只用6次AWS读取确认原次更新完成和精确模板，没有再次部署。独立首次查询默认视图时见三条记录而停止：另外两条是引用原Lambda ARN的动态依赖。新精确合同保全96文件并仅迁移95项ledger路径，直接读回API集成/调用权限符合原模板；随后独立前后同时核默认三行及属性一行，完整配置与包保护保持。此处只证明当前符合原模板及资源身份保持，不声称CloudFormation没有调用依赖服务。dev独立artifact阶段API上限只增加两次属性视图读取到26，原Lambda检查全部保留。首次全测的既有异步DNS超时失败也保留，未改旧测试，后续原用例和完整全测通过。

本次完成的是配置修复；新公开mention/清晰Reply验收仍待另批计划、现场和独审，不能把旧失败输入补成PASS。此前普通文本静默及ask仅有限通过，提及真实FAIL、Reply未发及UI_STOP保持。Z01/Z10/Epic仍OPEN，20工单14OPEN/6CLOSED；自然0/50有据、0/20未知、production_ready=false，不开新群或prod记忆。

当前入口为验收根 `2026-10-08-dev-bot-identity-fix` 的 final-release、最终独审和 budget-DevIdentityFinal20261008A；唯一当前时点reader为该目录 read_budget_published.py，原J reader不得冒充当前配置。新配置证据原文采用第十项期限2026-10-14 21:48:46.021161UTC，第九项公开文本原文仍为同日20:45:55.665021UTC，原八项期限不变。最近到期责任仍为Oct8九份CloudWatch原文，是否已履行以精确清理回执为准；此配置修复没有执行删除。见[配置交付证据](evidence/2026-10-08-dev-bot-identity-fix/release.safe.json)、[有限修复契约](DEV_BOT_IDENTITY_REPAIR.md)和[副本台账](RETAINED_COPIES.md)。

## 以下为此前阶段与原失败证据，不作当前待做或重跑指令

## 原计划与发布前状态（历史）

# Dev bot身份配置有限修复

状态：PLAN_V4独立PRE、本地源码正确性和维护审查通过；38项infra测试、2390全测与hooks通过。唯一development用户名已单次创建并精确读回；PR/CI和实际配置发布尚待。

实际公开提及已认证接收而未回答；当前dev用户名误继承repo生产用户名，dev数字ID正确。修复唯一配置owner为现有GitHub development AGENT_BOT_USERNAME与CDK Bot环境。已增加development用户名覆盖，保留repo/prod和全部ID；Worker原本不含这两个身份字段，应保持不变。预览只从development身份job传两字段，不整体改变preview的其它配置/凭据上下文。

源码独审后、最终PR CI前，先对唯一development用户名操作器做PRE，再单次create及精确读回；其余身份保持。随后测试、三job CI、skip-directive受控合并后，以新精确config-only changeset仅改dev Bot用户名，所有Code/层字节保持PR248，prod不执行空变更。实际主独读回及预算reader重绑后才称配置交付；重新真实mention/Reply另批有限合同，不重发已经失败的输入。当前计划私有入口2026-10-08-dev-bot-identity-fix/PLAN_V4.md，发布操作PRE另审。

本批原文及真实失败见[安全结果](evidence/2026-10-08-z01-public-text/result.safe.json)和[副本台账](RETAINED_COPIES.md)。Z01仍OPEN，自然样本不增加。

本地首次全测有一例既有异步DNS/HTTP超时（1F/2389P）；未修改该测试或产品代码，同定向两参数复查2P，随后完整2390P。原失败报告保留。GitHub变量操作为14GET+1POST，唯一development用户名从缺席变为@zerde_dev_bot，其余五项身份值/缺席及原环境保护保持；不是Lambda已更新。
