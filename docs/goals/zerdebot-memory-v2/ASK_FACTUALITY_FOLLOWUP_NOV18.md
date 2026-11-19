## Nov18 后续修复：通用别名来源与只读恢复已实际部署，等待新的现场复验

SOURCE b9be511 已实际部署 dev/prod。公共来源使用来源明确的别名映射并拒绝已见身份冲突，仍最多两次 HTTP；getMe/getChatMember 冻结只读请求，在20秒总限内最多两次，sendMessage 每次调用仍单次。没有产品硬编码，个人证据、模型/预算、投递门与生产权限不变。最终2842项全量测试、源CI三job、每环境5个ARM handler及23项禁网包内检查通过；两环境主独各完整6ZIP及配置/CONTROL、间隔至少300秒的稳定核验通过。

N此前真实复验仍为PARTIAL：A诚实未知但无用，B实际166.135秒观察内未见完整回复，P未发；窗口已释放，不推断之后无回复。新U复验工具及独立POST双PRE、离线验证完成，尚无新窗口/anchor/raw。下一必须新的直接人类15分钟窗口执行A/B/P，工程发布不能替代真实有用性。原15副本责任、20任务14OPEN6CLOSED＋EpicOPEN、四群RELEASED_OBSERVING及其他业务/自然/费用UNKNOWN保持。

完整Bot/Memory ZIP `fa00a9786b8e7124d15b392b9112a3a146be6bedb18e4480327bd42dc9021b7d`；Execute完成至stable观测的记录时点间隔：dev 357.531秒，prod 28410.737秒。该间隔不是连续服务健康证明，时间或环境跳变原因不推断。实际资源数量dev 2 /prod 3；prod第三个资源是IAM Policy，前后完整权限语义核验相等、权限增量0；出现该变更的具体原因仍UNKNOWN。

成功发布阶段AWS 490逻辑调用，8确认写=4Put+2Create+2Execute，未知写0，发布source guard GH GET 90。先前失败基线6AWS只读/10GH、prod两失败段各33只读尝试（各32服务响应/1失败）、第二段10GH GET、失败prod主POST7AWS只读另计，有限诊断2AWS只读另计，公共来源本地证明/PR及CI读取/CI已有OIDC和正常业务另计。0操作器UI/model/持久runtime raw/新期限/自然增量。

原baseline-dev下载News时TimeoutException，0云写；原once/失败/完整Bot与部分News保全，原因UNKNOWN。唯一新baseline-recovery-dev重新完整fresh闭合，未放宽超时或重试门。prod原候选及首次保护续接均在第33只读CF调用ConnectionClosedError，各32成功服务响应/1失败；两段中间CONTROL revision未投影的UNKNOWN保留。独立受审新入口按每个CF逻辑调用建立新连接，仍单次无重试，fresh全保护闭合后发布，未重建ZIP或重跑ARM，具体连接故障原因仍UNKNOWN。prod首次主POST又在Operations下载中TimeoutException，7个只读元数据响应且0写；新post-main-prod-recovery重新全量fresh六包，不复用旧部分ZIP，不重Execute。dev候选正确性旧报告metadata数量写14，原实际META为12，独立更正sidecar保留而不改原报告。工具草稿、合成夹具错误及旧T/N结果均保留，不称首次无问题。顺序读回非全局事务，B根因仍UNKNOWN。

新U入口 `/Users/bayashat/.local/share/zerde-memory-v2-acceptance/2026-11-18-ask-factuality-followup-retest`。离线工具准备不是现场许可；没有新窗口/采集期限，首次新采集前必须登记当时实际第16责任（如旧15未变）。[最终运行回执](evidence/2026-11-18-ask-factuality-followup/final.safe.json) SHA `9929f7b7e3bd69a62a9542d190b38d59163808f3fc6780a35ae934776f98b0dd`；[准备回执](evidence/2026-11-18-ask-factuality-followup/retest/preparation.safe.json)；[唯一TODO](TASKS.md)。

以下完整此前阶段保留。

# Nov18 普通 /ask 复验与通用修复

## 实际复验

N原入口：`/Users/bayashat/.local/share/zerde-memory-v2-acceptance/2026-11-18-ask-factuality-retest-next`。正确账户Баяшат/Test bots，12操作器只读AWS，A/B各一次；A完整诚实未知但无用，B观察166.135秒未见完整回复，P未发，窗口释放无草稿。没有生产全量或内部SENT/lease证明，不等于之后无回复。主独全文POST闭合的是证据与原合同，语义仍PARTIAL；自然样本增量0。17原件唯一原期限1795626160.299967，当前总15副本职责。

## 通用修复与验证

E原入口：`/Users/bayashat/.local/share/zerde-memory-v2-acceptance/2026-11-18-ask-factuality-followup`。有限诊断2AWS/0写，精确dev四分钟错误单页，nextToken存在故PARTIAL。发现授权查询包装失败栈，底层原因与B关联UNKNOWN，未追页。完整响应仅内存解析；固定安全投影不新增持久runtime raw/期限。

公共来源第一请求读取明确redirect关系，完整校验返回对象、pageid、namespace、fragment和跨页身份冲突。canonical全等优先允许无关别名分页；仅alias命中必须batchcomplete严格true。最多3候选/50别名，仍至多2请求、每次6秒/64KiB，无自动跟页或产品答案。

原Telegram只读owner冻结payload，getMe/getChatMember总20秒内最多2HTTP、每段8秒、一次0.25秒间隔。仅折叠transport/timeouts或500/502/503/504恢复；429/权限/坏响应不局部重试。发送仍单次，原SQS和全部身份/预算/投递门不变。固定原因码/耗时/次数日志不包含URL/token/正文/异常链。

最终四源码测试文件哈希前后保持，全量2842 passed/223.90秒；独立正确性173定向＋19独立控制，维护137定向通过。主先前2838全量发生在最后修订前，不混称最终字节覆盖；初期lint/测试夹具/代码审问题保留。全部为合成测试，不是真实好答案。新源CI、ARM包、dev/prod实际发布仍待；目前运行仍PR302 SOURCE174a849…，文档main不能代替运行包。

## 下一步

- [x] N现场与主独POST、17原件原期限登记、释放窗口。
- [x] 有限诊断、通用代码修复、完整测试和代码双审。
- [ ] 新源CI、发布工具双PRE、实际5ARM/23包内检查。
- [ ] dev完整包/配置主独稳定，再prod同等验证。
- [ ] 同步最终证据/工单/同一automation；另备新A/B/P，新直接人类窗口才复验。

保留原13清理责任及36/22/2/5四批身份阻断、Q/N两新期限、媒体/NewsQuiz恢复/周榜/Groq权限/费用实付与自然质量各责任。无新清理，不改20任务14OPEN6CLOSED＋EpicOPEN。

## 安全证据镜像

- [result.safe.json](evidence/2026-11-18-ask-factuality-retest-next/result.safe.json) SHA256 `52d2d06a17b6dbbd3d99230a49d56c39ed5327e0e8ee71047d6b4a4443a27ddd`。
- [independent-post.safe.json](evidence/2026-11-18-ask-factuality-retest-next/independent-post.safe.json) SHA256 `42d5f4a5a584f0fadc11eff26d7fa4a99fc075d4d08e8ef74121122c0016f8c8`。
- [maintenance-post.safe.json](evidence/2026-11-18-ask-factuality-retest-next/maintenance-post.safe.json) SHA256 `ec73732b16f701534c04dad057ff727a41063fb9a41f6daf5dc4fdc2493d7aff`。
- [onsite-release.safe.json](evidence/2026-11-18-ask-factuality-retest-next/onsite-release.safe.json) SHA256 `6cc71e56f7b899229f3879d9e52ec629beee24893ba83087a92f0d09e2a831d7`。
- [diagnostic.safe.json](evidence/2026-11-18-ask-factuality-followup/diagnostic.safe.json) SHA256 `f4ad912e04b5b998367986de598567434b9e786c484192b38fae69d0ba76b511`。
- [diagnostic-independent.safe.json](evidence/2026-11-18-ask-factuality-followup/diagnostic-independent.safe.json) SHA256 `c3433adcfb3e5a7ebd4cf67d724b3c9ba9d26eec2c72354816c1d706e0d8fcba`。
- [diagnostic-maintenance-post.safe.json](evidence/2026-11-18-ask-factuality-followup/diagnostic-maintenance-post.safe.json) SHA256 `833dee95a90c32e0727929f6b5c000d3d6e55daa6397d24019f20075277f663e`。
- [IMPLEMENTATION_PLAN.md](evidence/2026-11-18-ask-factuality-followup/IMPLEMENTATION_PLAN.md) SHA256 `31eab380c003a2f83323828b72a74d6217c2037f121e1a11c4108904541adab1`。
- [source-correctness-review.safe.json](evidence/2026-11-18-ask-factuality-followup/source-correctness-review.safe.json) SHA256 `30b8ca0269902d0e71bee12e9dd7f6da52802f9d6a38790ff381ba3199ef77d4`。
- [source-maintenance-review.safe.json](evidence/2026-11-18-ask-factuality-followup/source-maintenance-review.safe.json) SHA256 `26b8e452887447ec5eae1ec08f30ef83cb2aa277a749bf127039b7c62ce868bd`。
- [full-tests.safe.json](evidence/2026-11-18-ask-factuality-followup/full-tests.safe.json) SHA256 `16d18a61f9d16a0a83a964cdc1b83b8d1a49b2af49bdc5bba71ebb4864d0d828`。
