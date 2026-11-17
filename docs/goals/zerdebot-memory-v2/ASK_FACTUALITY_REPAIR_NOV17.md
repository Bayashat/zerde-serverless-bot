## Nov17：普通 /ask 通用事实修复已部署，等待新窗口复验

普通实体问答已加入有限公共来源核对、无匹配时诚实未知、主/备用模型完整响应检查及无Reply资格传递；没有产品专用答案。SOURCE174a849已实际部署dev/prod，两环境主独各完整6ZIP、配置/CONTROL/原保护及至少300秒稳定通过。prod额外IAM Policy更新经新双审续接确认完整14条权限严格不变；旧STOP、解析错误和UNKNOWN保留。全量2797项测试通过（等价lint后151项定向及最终源码CI三job通过）；实际每环境5ARM handler及16项禁网包内检查通过。

新复验T离线21项与计划/主工具/独立POST双PRE完成，当前没有窗口/anchor/新原文；等新的直接人类15分钟回复再进行A/B/P。有限Wikipedia检索可能MISS，诚实未知仍属PARTIAL，真实有用性与个人边界未验收，旧A事实错误FAIL不改。原14副本职责、全部20任务14OPEN6CLOSED＋EpicOPEN、四群RELEASED_OBSERVING和其他业务/自然/费用UNKNOWN保持。

运行源码 `174a84998563e3e1bfeb3f9dc60370252b173503`，PR302。两环境Bot/Memory ZIP `e036010af142e57a98fbca18e05dee8c8df7cfbece67e06c96601068e94df066`。dev稳定 313.485 秒，prod稳定 322.703 秒。dev changeset两个Lambda，prod两个Lambda＋一个权限内容不变的IAMPolicy；不称纯两资源更新。

发布阶段AWS逻辑调用 526，已确认写8（4Put/2Create/2Execute），未知写0；更早有限生成元数据诊断15只读另计。发布source guard GH GET 90；PR/CI读取、平台既有CI OIDC/CDK与AWS服务内部动作另计。0操作器UI/model/持久runtime raw/新期限/自然增量，不代表机器人正常业务没有调用。

失败和限界：dev首次Docker未启动使ARM STOP，原ZIP不重建，以已审唯一续接完成；prod原prepare额外IAM导致STOP，新完整权限等价门续接原唯一CS，原截断签名解析harness错误保留。其cause UNKNOWN，失败阶段未封存的中间CONTROL revision连续性UNKNOWN。所有检查为顺序读回而非全局事务。

新T入口为 `/Users/bayashat/.local/share/zerde-memory-v2-acceptance/2026-11-17-ask-factuality-retest`，主工具、独立POST、计划双PRE与实际21项离线控制见[准备回执](evidence/2026-11-17-ask-factuality-repair/retest/preparation.safe.json)。没有当前新窗口，不能执行start、私有现场读、API/Telegram或模型；新首次采集前登记第15项且保留原14，当前没有新增。

[运行最终回执](evidence/2026-11-17-ask-factuality-repair/final.safe.json) SHA `cce3a66d62d01036371ec256c345f05c9b7808a44766b033c27bf49b76f34e62`；[唯一TODO](TASKS.md)仍按普通ask优先推进，媒体/验证码/spam/投票/News/Quiz/周榜/费用/自然质量及副本义务保持开放。
