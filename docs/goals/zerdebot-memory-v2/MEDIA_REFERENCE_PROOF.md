## Oct20：媒体引用摘要已部署两环境，真实多图问答另行验收

PR284运行SOURCE `89f4aaeff25a8c666c679fbdd4f961647a1aa56a`；dev/prod Bot/Memory共同完整ZIP `4ecda06e8cacc244243c99b5b21d5931e9d0cc362a8314019baaba24120f98c3`。每环境唯一Execute、主独五函数与共享层完整ZIP/配置保护及至少300秒稳定已完成（dev 429.225724秒，prod 424.238718秒）。只改 `services/telegram_media.py` 和 `services/handlers/commands.py`；News/Quiz/Operations/共享层原包、身份、18告警、实际规则/目标及CONTROL的原epoch和合法revision保持。文档HEAD与merge不当运行构建，不额外部署。

存储、检测和实际成功准备三个原日志边界增加版本1引用摘要。原日志脱敏不改，不输出原媒体标识或正文；转换前严格身份sidecar不入SQS/持久行/模型。摘要是可关联元数据，不能证明图片字节或Gemini理解。预算五owner、下载/模型请求/lease/发送策略不变。181相关/2606全测、源码CI三job及两环境各5个ARM入口与12项包内合成检查通过，这些不是自然或媒体业务验收。

原dev基线第10次DescribeAlarms发生ProxyConnectionError，原9成功和6完整ZIP保留；新6次只读补未完成保护，独立复核17份原文和6ZIP后确认组合基线。原失败仍失败，不是同一时点快照；后续prepare另fresh全保护。prod原prepare的37次AWS响应成功（含3写），但变更单额外包含两QuizRule描述表示差异而停于Execute前。原失败和未执行变更单保持；新V2仅把模板两Description恢复fresh实际规则en-dash，原ZIP不变，新变更单严格仅两Code后才唯一Execute。问号/en-dash表示差异原因UNKNOWN，其它配置和直接规则比较不放宽。操作器本批AWS 382次尝试=381成功+1原失败，其中10写=5PutObject+3CreateChangeSet+2Execute；运行GitHub40GET，启动8GET及CI/文档发布另计。0操作器UI/模型/自然样本；正常业务不计入该操作器数。原失败、工具草稿及审查harness修订均保全，不宣称首次无问题。

原T2424/2425、提问前STOP及旧评分结果永久冻结，不用新摘要回填。后续新媒体工具须绑定本次实际包、主独snapshot与原期限，再经独审、原完整7API五owner时点检查和新的直接人类15分钟Telegram独占窗口；仍须同两图完整Gemini链、语义43、单SENT、lease及原生Reply精确父目标。四群仍RELEASED_OBSERVING，自然0/50有据、0/20未知、起点null；production_ready=false仅指自然质量未验收。

[运行回执](evidence/2026-10-20-media-reference-proof/release.safe.json)、[独立回执](evidence/2026-10-20-media-reference-proof/release-independent.safe.json)。顺序读取非跨服务事务，不当模型许可；具体后续见本契约及保留职责。

## 以下为此前冻结阶段；其未部署、旧绑定或待核描述仅属当时，不作重跑指令

# 媒体引用摘要：本地源码阶段

现有日志隐藏相册与文件标识，旧现场无法证明同两张图跨环节一致。本次为存储、检测和实际成功准备三个既有日志边界增加版本1引用摘要。当前只有源码/离线证据，尚未发布运行包；原T现场2424/2425及提问前STOP保持，不能用新摘要回填旧结果。[源码回执](evidence/2026-10-20-media-reference-proof/source.safe.json)。

摘要固定为 SHA256(`zerde.media-reference.v1` 加一个NUL字节，再加UTF8规范JSON)。JSON六项按chat/message/user/type/group/unique顺序，前三项规范十进制字符串、后两项原字符串；ensure_ascii=true、紧凑分隔符。所有身份严格类型/范围检查，bool、前导零、空白、缺失、控制字符等不可证明；版本字段是整数1。原业务转换前的校验结果只在MediaReference内部sidecar，和实际转换后的引用再比较；截断或歧义不靠后续转换恢复证明。to_dict显式排除该字段，不入SQS、持久行或模型。

集合保持顺序、digest/null及requested/proven计数；空、超4、重复或缺失使集合UNAVAILABLE。实际prepared_refs只取原成功列表，最终下载总量门后才计入；原requested数量另明确记录。摘要是可关联元数据，不是匿名数据、图片字节校验或Gemini理解结果。原日志脱敏、用户正文、可下载file_id隐藏规则保持；预算/lease/下载/模型参数/发送策略不变。

181相关测试、2606全套回归通过；正确性与维护独立源码审通过。实际源码CI、ARM完整包/两环境发布与主独保护、后续新证据工具及人类新独占窗口仍待。原两图语义、43答案、单SENT/lease、原生Reply父目标仍分别验收；不降低旧门槛或造自然样本。四群继续已发布观察，自然0/50有据、0/20未知，全部工单状态保持。此源码阶段0新云/UI/原文/期限，原十四项职责不改。
