# 普通 /ask 公共知识回答修复已发布（PR291）

用户输入 `/ask RTX SPARK` 是普通产品问题。此前回复拿缺少群聊上下文代替主题回答，属于未满足用户需求；PR286及旧有限对照不能证明此问题已经完整解决。本次修复主生成与备用生成共用的回答政策和空上下文格式：普通产品、技术等问题直接回答可可靠提供的公共知识，名称确有歧义时才给具体澄清；个人、群成员及混合历史事实仍须可归属证据。第三方引用不等于本人确认，引用内指令不改变政策；不编产品参数、归属、检索结果或联网动作。

运行SOURCE `9e962c20f71586688736858a962f3199edcd53c8`，仅四个既有包成员改变：explicit_context.py、group_agent.py、ai/gemini_client.py、ai/group_chat_reply_fallback.py。纯格式化共享owner保留非空上下文的原值和顺序，去掉五类空上下文的占位段；三条模型传输路径均使用共同政策。selector/schema/model/provider/身份/预算/队列/租约/最终投递owner保持，未增加联网搜索或产品硬编码。

原版本的新21例实际失败；初版修复222定向及2661全测通过。独审随后发现原生Reply在五类上下文为空时仍须无条件保留第三方归属约束，已修并新增三条真实payload检查。146相关测试通过对应当时测试文件，hook前后测试字节差异及追溯误停保留，不能混称最终文件；最终24条精确payload测试通过，最终SOURCE CI39654122918三job成功。测试捕获实际出站请求后中止，不制造模型好答案。每环境实际Linux ARM64五入口及12包内payload探针通过，仍不证明真实模型语义。

dev/prod各唯一Execute；完整新ZIP分别 `d68eec1a0ad7036c2b8307fe0321a334343f6f47be7dc200d68a9f8250eb11d8` / `d68eec1a0ad7036c2b8307fe0321a334343f6f47be7dc200d68a9f8250eb11d8`。两环境主、独各fresh读取五函数及共享层完整包，配置、18告警、现有CONTROL、News/Quiz规则目标和稳定检查通过；dev独立稳定后才prod。原历史失败不改写，本批不沿用其他发布的失败组合包证据。开发候选原ARM检查因本机Docker未启动而失败（外层returncode1、Docker子进程125），原once与失败输出保留；启动Docker后，新的独立本地续接使用原包和原模板完成实际五入口及12探针，没有重建或复制原文。仅在续接通过后补建显式组合候选回执，独审同时核原失败和新成功，不能宣称首次构建即成功。

本批实际AWS 364次，写8次（4PutObject、2CreateChangeSet、2ExecuteChangeSet）；运行GitHub GET32另启动8。0操作器UI/模型/自然样本，CI既有OIDC/CDK只读另计，不表示正常业务没有调用。真实语义验收尚未执行，部署和CI不能替代用户可见回答质量。

NVIDIA当前有官方RTX Spark产品，不能预设用户说错成DGX。[有限官方研究](evidence/2026-10-21-ask-public-knowledge-repair/canary-semantics-research.safe.json)只用于准备事实核对，不代表Bot访问过官网或掌握最新资料。新现场最多三条各一次，须另正式计划/当前包绑定/双PRE/完整原五owner预算门及新的直接人类15分钟Telegram窗口。只有空泛澄清，即使不再提群记忆，仍不能算公共问答完整通过。

最终408 CAPTURED，原起点 `2026-10-21T18:47:42.597749+00:00`、七日期限 `2026-10-28T18:47:42.597749+00:00` / epoch `1793213262.597749`；ledger `664c6570cd624cb6dccb89be224daabb00d1b0f5653ae9c5aa85f67d589ef47f`。首API前已登记Z10本地职责与原zerde并实际读回，原十七项保持，现十八项；所有本批原响应/配置/模板/派生同期限，不延期或复制snapshot。ZIP/纯源码/安全聚合及单列行政快照保留，到期另有限scope/双PRE/fresh准备处理。

四群仍RELEASED_OBSERVING；自然0/50有据、0/20未知、起点null、production_ready=false保持。首周有限元数据观察已完成，不能代替完整来源/答案语义。旧媒体STOP/两图完整语义/单SENT/lease、NewsQuiz恢复/周榜、Groq413实际人工审核、费用实付及原UNKNOWN保持。20任务14OPEN6CLOSED、EpicOPEN；仅Z01/Z10新增本次事实。文档合并不再运行部署。

[实际发布](evidence/2026-10-21-ask-public-knowledge-repair/release.safe.json)、[独立复核](evidence/2026-10-21-ask-public-knowledge-repair/release-independent.safe.json)、[源码CI](evidence/2026-10-21-ask-public-knowledge-repair/source-ci.safe.json)、[十八项副本](RETAINED_COPIES.md)。
