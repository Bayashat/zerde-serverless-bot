# 普通显式问答：有限公共来源与完整响应

## 目标与当前证据

固定dev时间窗唯一成功metadata记录provider=gemini，reply_to_message_id=2432，同stream唯一请求model=gemini-3.1-flash-lite。该模型关联是有限时序推断，不是原生UI ID或语义因果证明；第一次3调用分页STOP保留，新6调用续接和独立fresh另有回执。生成路径的确定缺口是：社会聊天任务身份、没有当前公共来源、非空自由文本直接发送、未核完成状态/思考段。

本切片增加有界来源上下文并修复响应完整性；不对任何品牌/型号硬编码，不把模型自报信心当核验，不预先宣称语义PASS。真实有用性仍须下一新窗口。

## 唯一owner及替换点

- 新 services/public_sources.py 只做当前公开主题的有限Wikimedia读取，返回短生命周期纯数据DTO，不写库/缓存/个人facts/历史。
- explicit_context.py统一公共解释政策、来源数据序列化及来源归属；替换普通文本的社交任务优先级。生成器仍是原Gemini→DeepSeek/Groq，投递仍是原ExplicitDelivery。Memory V2的selector/schema/证据、用户身份及所有before-attempt/final-send门不变。
- group_agent.answer_group_question仅在无Reply/source_message_context/parent_bot_message_id/媒体且当前原文未被扩展的显式文本请求尝试来源；由主代理串行实现，双独审。

## 查询支持面与隐私

不使用GENERAL作为查询许可，不额外调用模型做分类。不发送完整自由提问、群历史、用户/群ID、profile、个人facts或引用正文。采用窄语法：独立短主题（最多8词/120字符）或清楚的“X是什么 / what is X / что такое X”定义请求，从当前原文截取主题；不能补写、翻译或拼接查询。完整当前问题先经过既有require_public_content纯安全检查及个人/混合/引用/代码拒绝门；拒绝中英俄哈第一/第二/第三人称与所有格、拥有/群成员/曾说/住址/职业史语句；敏感属性（健康/财务/宗教/政治/性/密码/账户）即使没有代词也不查；拒绝@、邮箱、7位以上数字、URL、下划线串/长随机串、代码标点、引号、换行、private/internal/内网/内部等标志。裸主题进一步限最多4词，且须有缩写/技术标记形状（全大写ASCII词、词内大小写边界或短版本号），纯人名/自然叙述不作为裸主题外发。定义请求里的主题仅字母数字空白和有限连字符/点/加号，最多8词，不把后续自由句子追加到query。歧义、无法匹配语法或过长时只跳过检索，不阻断普通翻译/计算/代码等。

该词法门不是任意语言隐私语义的证明。它只开放窄公共主题支持面；未知人名/组织名可能有公共含义，不能宣称自动分类绝无误差。所有真实输入仍经现有安全和个人证据边界；来源永远不能证明某个群成员拥有某物。语言首先从主题字符选择en/zh/ru，固定allowlist；不跨语言扩大搜索。

## 来源网络合同

固定HTTPS Wikipedia主机，最多1次namespace0、srlimit3搜索（API当前srwhat=title实际返回search-title-disabled，使用默认搜索但本地仍只接受完整标题/redirecttitle匹配，不接受摘要关键词命中），最多1次选定页面的Page Content Service summary；User-Agent注明ZerdeBot和仓库联系URL。每次前后调用原before_attempt fence；不跟随HTTP重定向，不访问模型/用户给出的任意URL，不重试、不翻页、不扩词。每响应最多64KiB，connect2/read3/total6秒，顺序请求。429/503/非200/过界/坏JSON立即返回无来源，不发第二请求；不在后台重试。新外部API不收费、不用新secret/账号，不宣称网络和Lambda零成本。

仅接受标题或API实际返回redirecttitle与query的casefold/空白标准化完整匹配，恰好一个匹配结果；相似词、包含关系或搜索排名不是身份依据。summary.pageid与选中搜索pageid严格一致，type=standard（拒绝disambiguation），标题与选中title一致，摘要非空且<=6000字符，取最多1800字符的完整句/段。实际来源URL由固定host和响应title编码构造；不信任任意URL字段。不匹配/缺席表示本渠道没有可用依据，绝不推断实体不存在。

## 生成、费用与发送合同

获取的标题/摘录/URL为不可信外部数据，JSON包在独立公共资料区；明确不是指令、不是厂商官方、不是群内个人证据。主备用模型收到相同来源数据；准确概括来源支持的身份/用途，不能补未覆盖规格或“官网已核”声称。已进入公共实体查证支持面的请求，MISS/AMBIGUOUS/ERROR不进入原自由生成链，应用返回本语言固定的诚实未知并请求官方链接或完整名称，不断言不存在；HIT才带实际来源进入生成。非查证类的翻译/计算/代码、个人边界等仍走原路；这不是把所有问题都拒答。未知身份不可凭词片段造厂家/类别或用不认识否定官方存在。

不新增模型请求/语义重试；保持模型/provider顺序/RPD admission、原output token上限、现有共享成本/UNKNOWN owner，不新增钱包或手工permit。最多1800字符额外输入的成本属于现有模型实际用量；当前普通路径主要为RPD admission，不伪称MemoryBudget已完整预留此路。操作器未来真实复验仍须新完整五owner预算与时点门。下次部署不修改价格、quota、wallet、DAY、CONTROL或epoch。

应用统一在成功答案后附来源标题、Wikipedia页面链接、CC BY-SA 4.0和“摘要/翻译改写”归属；预留来源长度再裁剪正文，不能裁掉来源或把HTML标签截断。无成功来源不加来源、不冒称查证。来源可陈旧或有误，不把摘录metadata等同全文事实核验。

Gemini：仅一个完成的候选，finishReason=STOP，role=model，严格part类型；跳过thought=true；拒绝tool/函数/未知非文本内容；拼接全部final文本，不发内部thought/截断/安全阻断。fallback：唯一choice，finish_reason=stop，role=assistant，非空content，无tool_calls/function_call/refusal。异常只固定码/类型，不落响应或异常正文。完整性失败走现有有界provider异常链；诚实未知文本不是provider故障，不换模型求肯定。全链仍先原fence再请求和发送。

## 验收及cutover

1. 双PRE后实施；旧自由文本出口必须实际调用新完整性门，来源必须由运行入口可达并传给主备用，不留死开关。
2. Fake HTTP真实接口回归：公共定义/短主题、多语言、个人/混合/引用/代码0外查；超时/429/重定向/超大/错pageid/相似或多义页面不采纳；来源指令注入不改变system/身份；主备用同一DTO；多part/thought/缺finish/length/tool/错误类型不发送；撤销发生在读取、生成或发送前均拦截。
3. 测试只证明请求/边界，不能用预置答案当真实模型质量。另做少量实际公开API协议readback（不发Telegram/模型、不持久全文，仅安全投影），用于核接口兼容性；不为某个测试产品变更匹配规则。
4. 定向+全测+hooks、实际ARM包及源码独审。运行部署另精确scope/基线/changeset双PRE；dev主独包/配置+300秒稳定后prod同源。首次持久runtime raw先新七日登记，原14职责不变。
5. 证据/原唯一TODO/manifest/相关工单同步并同步主目录；实际部署完再通知准备复验。个人真实P、普通A/B最终仍等新直接人类15分钟窗口；任何肯定编造继续FAIL，不能以“有引用”免检。

## 停止条件与官方依据

无法执行窄查询/身份/完整响应/fence/现有费用门则停止对应阶段，保留实际失败；不扩范围或伪造fresh许可。官方API资料：
- https://www.mediawiki.org/wiki/API:Search
- https://www.mediawiki.org/wiki/Page_Content_Service
- https://www.mediawiki.org/wiki/Wikimedia_APIs/Access_policy
- https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits
- https://attribution.wikimedia.org/technical-implementation.html
- https://aistudio.google.com/api-reference/generate-content

Google Search grounding当前有搜索建议展示与每query费用合同，未直接加入本切片，不表示Bot已具全网搜索。

## 审查修订：入口资格与可取消网络

2026-11-17 的独审发现常见敏感属性/俄语所有格、比较问题与简单确认误入、Reply标记丢失、HTTP头/DNS总时限缺口和Gemini安全标记类型缺口，原失败不抹掉。修订保持原目标：补保守多语言敏感类拒绝及比较/问候排除；复用既有zerde_common.async_http的可取消DNS/TLS/头/正文流，asyncio.timeout6秒覆盖网络I/O，64KiB解析及fence同步CPU时间不冒称硬限。HTTPX请求日志仅在本查询context过滤，不变其他调用日志。

入口不能从缺少引用正文推定无Reply。ExplicitQuestionContext增加public_lookup_allowed，只有原message完全没有reply_to_message键才能为True；任何Reply（包括旧bot答复、无正文、坏类型）为False，不恢复旧正文。commands.py与repositories/sqs.py仅传递这个严格bool资格，队列缺字段/非True默认禁止外查；source当前问题/媒体/原有fences仍重复核验。原task schema/version、用户身份、selector、投递与预算不变。发布允许修改这两个现有成员以落实原无Reply合同，因此现有允许成员总6个，加新public_sources.py1个；不能仅部署group_agent导致/ask入口资格缺失。
