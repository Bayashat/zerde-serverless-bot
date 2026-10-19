# Oct21 首发527原文到期清理准备

Goal/Intent：履行 Z10 原七日副本责任；Oct19 本轮只完成本地准备与文档交付，不改变四群已启用功能。
Truth owner：R=/Users/bayashat/.local/share/zerde-memory-v2-acceptance/2026-10-14-memory-v2-launch/raw-retention.safe.json，SHA788460e51d786c91122bcedc516559dc4fb57913b31af44d84f2649ee1d1aa37，最终527 CAPTURED/0 NOT_CREATED。anchor.first_capture_at=1791983450.198516（Oct14 13:10:50.198516UTC），原deadline=1792588250.198516（Oct21 13:10:50.198516UTC），604800秒保持。completion/final的465是当时阶段，不替代最终ledger；以completion/docs-release-independent最终账本绑定闭合。
Contract：按原files数组相对R完整路径原顺序527项，逐项sha256/size/dev/ino/mode0o600核验。元数据研究库存910常规文件、383保留、7目录（3个0700、4个0755）、0链接、0ZIP。全部目标祖先0700；原目录模式保持、不chmod。无前一批链接例外，不引入旧scope/basename/previous_path或后缀规则。
Cutover：另建本目录2026-10-21-launch-raw-expiry新有限工具；只拷贝审查后的纯源码逻辑，不导入或运行旧once。原R的业务/发布/评分/UI窗口及失败记录均冻结，不重跑或改写。完整旧历史是事实证据，不是执行指令。
Evidence：O_NOFOLLOW/lstat/fstat流式hash及前后完整库存，目标原账本身份与所有保护文件/目录保持。保护项历史hash只采明确相对路径来源映射；其他仅fresh基线。两非目标private行政快照需创建来源回执证实，不能按后缀猜测，也不声称内容无敏感。仅流式hash实际目标字节，不解析、输出或复制原文。
Kill criteria：schema/原期限/类型/链接/硬链接/祖先/身份/hash/全库存或来源不符立即停，保全失败；已执行once不能重跑，必要时另窄续接并独审。
Forbidden：今天0删除、0公告/实际apply/verify_absence、0云运行API/UI/模型/预算/运行部署/新原文/新期限。不使用旧S已删除snapshot；不改当前CONTROL、epoch、owner、UNKNOWN，不动用户导出/现役PITR/必要恢复/其他五期限。

## Ordered board

1. Explorer只读安全账本/聚合/源码和路径元数据，输出explorer及protected-provenance，核两行政快照来源及历史hash范围；不得读目标正文/hash或运行旧工具。
2. 主代理实现本PLAN与make_scope；正确性与维护分别审计划及生成器，绑定PLAN/make_scope/protected-provenance，ALIGNED双PRE后唯一scope构建。内置全局/批锁，source R零写、目标原身份和前后库存保持。
3. 主实现新expire_raw/verify_absence，原527/383/7与原期限/ledger/scope固定；正确性和维护双PRE，有限合成负控验证路径/时间/身份/notice/严格bool/一次性/失败保全。禁止实际目标上测试删除。
4. 主唯一inspect Prep20261019A；seal工具先双审后聚合实际回执。独立fresh工具另先双审，再独立重新核527/383/7/hash及前后库存。完成态PREPARED_NOT_DELETED，独立结果由实际独立回执闭合，不改根历史PENDING。
5. 从实际main25275bc4cb8bb0f5af4f21715a1607766deefcf5的新feat/zerde-launch-raw-expiry-preparation分支同步计划/证据/保留职责/下一动作/Z10及Epic。task_manifest仅Z10新增准备，其余19对象及20任务14OPEN6CLOSED/EpicOPEN保持。保留旧完整正文和Epic冻结尾，必要时有据压缩顶部并独审；canonical不超过65536bytes。正确性/维护、hooks/CI、唯一merge/工单正文与独立fresh读回完成后更新原zerde heartbeat。
6. Oct21到期当轮重新核占用，新唯一inspect（不复用Prep20261019A），按scope原序精确公告527目标/383保护/7目录及待核和届时其他未履行期限。notice真实announced_targets/deadline_epoch/scope_sha256/announced_at，每intent距公告0..3600秒。到期原hash/身份/全库存保持才唯一apply，预期1054条journal，apply与journal unlink_returned/absent双侧严格True；再独立fresh逐路径不存在及保留核验。未到期不用apply试探；早到每次<=60秒等，真实延误UNKNOWN如实记。中止保全partial另窄续接，不重apply/重建原文。普通unlink非安全擦盘或所有云副本消失。

## 保持的责任与业务状态

六个原UTC期限：Oct20 14:32:29.705948告警341已另批准备未删；Oct21 13:10:50.198516本527；Oct24 16:20:38.287378 H10；Oct24 16:29:48.470834 O51（两批不合并）；Nov1 11:46:02.425旧memory SYSTEM；Nov2 08:45:11.254旧stats SYSTEM。SYSTEM按原身份到期只读，不预判消失。原heartbeat每日阿拉木图19:05覆盖Oct20，Oct20完成后立即改到Oct21到期前60分钟内；今日不提前改变而漏掉Oct20。

四群RELEASED_OBSERVING，Oct17有限元数据观察已交付；自然0/50有据0/20未知、起点null/production_ready=false不表示功能未启用。下一Oct21首周观察另有限合同及新真实七日登记，本轮不云轮询空群、不造聊天/样本、不借旧UI窗口。原dev有限PASS/所有失败UNKNOWN/控制台阶段和原账本保持。原45ZIP和39ZIP属其他批次明确保留范围，本批没有ZIP，不扩展删除授权。全部业务/自然/推广/副本义务完成才删除automation。


## 实际准备回执

PREPARED_NOT_DELETED。scope SHA `16c76bcdb3a75fa2bbee73bef22b1f21ea52e10a061e945953214df865c79f5d`，主准备 `72e3f6fa15d578cbd994d6defb3fb368fee7c79db60d855de4b475395ea753f7`，独立fresh `504d2fee582fae0c64e268feea29f569f5f3e47baeb05fe6e815e05220bd1fc0`。910常规文件分为527目标/383保留，7原目录，0ZIP/0链接；41保留有精确历史hash、342仅fresh。源码/安全聚合/原ledger/两行政快照保留。原期限不变，普通unlink非安全擦盘，37在线退役数不增。

独立检查发现builder初稿缺少每块截止门禁，已在正式执行前增加每文件/每1MiB读前后检查、dev/ino提前严格校验与最终527绑定。最初未执行源码未另存快照，这一留证缺口据实记录；后续v2未执行源码保全。研究原rollout JSON形状误读、作者控制报告构建时缺合同文件、独立工具未执行v1报告误写link=1及修为0、维护合成harness与最终修订记录均保留，不宣称首次无问题或已观察线上故障。主inspect准备阶段也逐块截止检查；Due只读复核可在实际晚到后执行，唯一apply仍严格原deadline。

[主准备](evidence/2026-10-21-launch-raw-expiry/preparation.safe.json)；[独立准备](evidence/2026-10-21-launch-raw-expiry/independent.safe.json)；[台账](RETAINED_COPIES.md)。全部准备once结束不可重跑；下一到期执行必须新label、精确公告和原hash/身份/全库存复核。
