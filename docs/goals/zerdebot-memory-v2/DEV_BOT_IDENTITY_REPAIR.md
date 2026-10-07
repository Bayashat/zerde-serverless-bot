# Dev bot身份配置有限修复

状态：PLAN_V4独立PRE、本地源码正确性和维护审查通过；38项infra测试、2390全测与hooks通过。唯一development用户名已单次创建并精确读回；PR/CI和实际配置发布尚待。

实际公开提及已认证接收而未回答；当前dev用户名误继承repo生产用户名，dev数字ID正确。修复唯一配置owner为现有GitHub development AGENT_BOT_USERNAME与CDK Bot环境。已增加development用户名覆盖，保留repo/prod和全部ID；Worker原本不含这两个身份字段，应保持不变。预览只从development身份job传两字段，不整体改变preview的其它配置/凭据上下文。

源码独审后、最终PR CI前，先对唯一development用户名操作器做PRE，再单次create及精确读回；其余身份保持。随后测试、三job CI、skip-directive受控合并后，以新精确config-only changeset仅改dev Bot用户名，所有Code/层字节保持PR248，prod不执行空变更。实际主独读回及预算reader重绑后才称配置交付；重新真实mention/Reply另批有限合同，不重发已经失败的输入。当前计划私有入口2026-10-08-dev-bot-identity-fix/PLAN_V4.md，发布操作PRE另审。

本批原文及真实失败见[安全结果](evidence/2026-10-08-z01-public-text/result.safe.json)和[副本台账](RETAINED_COPIES.md)。Z01仍OPEN，自然样本不增加。

本地首次全测有一例既有异步DNS/HTTP超时（1F/2389P）；未修改该测试或产品代码，同定向两参数复查2P，随后完整2390P。原失败报告保留。GitHub变量操作为14GET+1POST，唯一development用户名从缺席变为@zerde_dev_bot，其余五项身份值/缺席及原环境保护保持；不是Lambda已更新。
