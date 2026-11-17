# 当前执行入口（Nov17）

固定metadata主独续接已完成；实际错误回复关联Gemini，原因没有从日志中被证明。实现合同为 [IMPLEMENTATION](IMPLEMENTATION.md) v3及其双PRE：有限公共来源、严格完整响应、日志脱敏、无Reply资格传递。源码测试/独审和dev/prod精确运行发布进行中；当前尚未部署、尚无新Telegram窗口，不宣称真实有用性PASS。历史诊断计划如下保留，不再执行旧once。

# 普通 /ask 事实可靠性修复 Implementation Plan

**Intent:** 修复普通公共知识回答中无依据的产品事实误认；不对任何测试产品硬编码。
**Current Behavior:** PR291普通生成在主/备用模型得到非空自由文本后直接发送。Nov16现场A已有严重事实错误，B/P停止；来源、selector和provider不能从文字猜测。
**Expected Outcome:** 有用的公共答案与可说明的事实依据一致；不能确认的实体不编身份/规格；个人事实仍由Memory V2证据独占。修复经测试、独审、dev/prod真实包部署后才准备新Telegram复验。
**Target-Perspective Output:** 用户在新窗口收到有用、诚实且个人边界正确的A/B/P；本轮没有窗口，部署完成也只报告待真实复验。
**Truth Owner:** Memory V2拥有个人事实/源/生命周期与投递；explicit_context拥有公共回答政策；现有Gemini/fallback拥有网络调用。公开来源不能证明个人拥有史。
**Contract Boundary:** 当前阶段仅唯一dev Bot日志的固定成功元数据与配置安全投影；不读取或持久化请求/回复正文，不调用模型/Telegram，不读SSM secret，不扫描其他组或旧原文。
**Cutover:** 先用有限证据归因；归因后完善通用实现合同并重新双PRE，才修改运行路径。旧自由文本的实际替代门必须明确，不能增加一个永远旁路的新校验器。
**Displaced Path:** 后续实施必须替换“只要非空即发送”的普通生成出口；不会修改个人selector为自由生成/检索。
**Value Density:** 一处公共响应合同覆盖所有名称与语言；先确定实际路径，避免盲目换模型或重复堆提示。
**Acceptance Evidence:** 真实HTTP请求和解析/发送边界回归、故障和个人边界负例、三CI、实际ARM完整包/配置主独读回、每环境至少300秒稳定；真实答案最终另等新直接人类窗口。
**Evidence Lane:** 本地新批D=/Users/bayashat/.local/share/zerde-memory-v2-acceptance/2026-11-17-ask-factuality-repair。原Q现场/POST/发布once冻结。各阶段新实际回执，不改历史FAIL或程序偏差。
**Kill Criteria:** 参数/身份/完整性/费用边界不成立则停止对应阶段；不以缺回执或模型自报信心充当事实证据。禁止硬编码产品、退役owner复活、旧raw复制延期、手动Invoke/permit/退款/清UNKNOWN。
**Architecture Slice:** src/bot/services/group_agent.py → services/ai/gemini_client.py、group_chat_reply_fallback.py；当前只读源码和metadata；实施具体文件及来源/预算/降级合同待归因后PRE。
**Plan Review Gate:** 分阶段双PRE；当前仅批准诊断后可执行，运行代码与发布尚未获本计划执行门。

## 顺序任务

1. 主代理完成精确元数据诊断，正确性与维护角色先审核本计划和D/diagnose_metadata.py。每角色各最多STS1、GetFunctionConfiguration1、FilterLogEvents2；日志范围固定2026-11-16T19:59:57.000Z至20:00:52.060Z（1794859197000..1794859252060毫秒），仅/aws/lambda/zerde-serverless-bot-dev。第一查询固定成功消息及群-1003765868758；唯一成功事件后才在该精确stream、同范围查固定provider启动日志。单页limit20，有nextToken、成功事件不是唯一、必要字段缺失即停止，不翻页或扩窗。第二查询允许同stream内1..20条固定provider启动事件（包括跨provider备用链），但最终成功provider必须恰好一条匹配启动事件，且所有启动不得晚于成功；这是时序关联，不是原生UI消息ID证明。配置要求完整CodeSha256/带时区LastModified/明确LogGroup与三个model字段；数值BotID按现有可选配置合同只允许空或8157502831，username和SSM前缀严格dev。每服务响应HTTP200且RetryAttempts严格整数0。执行入口同时绑定实际script与PLAN SHA。请求次数和原响应canonical hash落安全回执，原响应仅内存；不新增持久runtime raw/期限。完整配置仅内存，落身份、模型名、CodeSha256和whole-env hash。当前配置不能倒推现场时点。
2. 主代理据归因与官方能力/计费资料选定最小通用修复；写完整来源可信度、私有内容隔离、每次调用费用、失败降级、响应终结/正文边界。两独立PRE后实现、测试；若引入检索，现有纯文本预算不视为已覆盖。
3. 新发布scope绑定源码、工具和允许变化的Bot/MemoryWorker同包成员；保护其余三函数、共享层、所有身份/模型/费用/CONTROL/epoch和业务配置。发布前完整基线、精确changeset双PRE；dev先完成主独实包和稳定核验，再同源prod。正常workflow若不能停在精确changeset审核点，应复用构建器补最窄执行边界；不能合并后才登记/核基线。
4. 首次持久运行原文前另七日anchor、ledger、Z10/RETAINED_COPIES和同zerde登记实际读回；当前14职责逐项不变。纯源码、ZIP和安全投影分别按原合同保留，行政副本不伪称无敏感。
5. 实质结果同步原唯一TASKS/manifest/PLAN/HANDOFF/EVIDENCE及相关工单，再同步主目录。完成运行发布与复验准备后告诉用户；没有新窗口不打开Telegram。

## 当前边界

工具草稿与未执行验证错误仍保留。Web调查仅操作器查官方文档，不代表Bot已具检索。普通模型无来源保证是源码结构性缺口；本次实际错误具体成因、模型知识是否陈旧尚UNKNOWN。新规划不改变全部业务/自然/推广/副本义务。
