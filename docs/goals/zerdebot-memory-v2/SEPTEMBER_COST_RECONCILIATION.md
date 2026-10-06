> 10月6日补充：AWS九月账号发票摘要已核，USD38.65＋税6.18＝44.83；付款、历史Free Tier与产品完整归属仍未知。Groq/DeepSeek实际控制台均需用户登录。详见[后续有限核对](PROVIDER_COST_GAPS.md)。以下带日期数据保留原口径。

# 九月费用核对（2026-10-04）

本次是完成账期的一次有限核对，结论为 **PARTIAL：已取得可直接归属的费用，完整产品实付未知**。Z17保持OPEN。金额均USD；不将应用预算、Quiz次数、充值或目录价估算加进账单。

## AWS：UTC 2026-09-01至2026-10-01（结束日不含）

固定当前账号与Project=ZerdeBot，1 STS、1标签状态、4 CE查询，共6次只读；每组一页完整终止，四组Estimated=false。环境与服务按record type独立复算一致。没有资源、标签、控制、账务或付款修改。顺序查询不是跨接口事务，未来账单调整仍可能改变数字。

| 可直接归属范围 | 使用费USD |
|---|---:|
| dev | 0.5206115692 |
| prod | 0.9771578815 |
| 合计 | **1.4977694507** |

| 标签归属服务 | 使用费USD |
|---|---:|
| SQS | 0.6837816 |
| DynamoDB | 0.3913532149 |
| S3 | 0.272993 |
| Lambda | 0.1262593141 |
| CloudWatch | 0.0157347217 |
| API Gateway | 0.0076476 |
| SNS | 0 |

Project/Environment为Active，最后更新9月11日17:33:55UTC；Component为Inactive。本次没有证据证明整月标签完整或历史回填，故不能称上表覆盖Zerde整个九月。

整个账号Usage为38.6574992985、Tax6.18，总44.8374992985；未标Project池Usage32.5516953201、Tax6.18，总38.7316953201。它们不是Zerde费用，税费不得按比例猜分。四个结果集合没有Credit行，不能据此推导充值余额/银行扣款或所有可能优惠为零。原10月4日尚无AWS发票证据；10月6日已补摘要，已付款和九月逐项Free Tier额度仍未核验；10月当前免费额度不能代替九月。

[固定账期API语义](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_GetCostAndUsage.html)；[本次结果](evidence/2026-10-04-september-costs/result.safe.json)；[直接原始独立复算](evidence/2026-10-04-september-costs/independent-post.safe.json)。

## Google：九月使用日期，太平洋时间

在用户已指明的dev/prod账号中读取账单，未改支付、额度、凭据或发起模型请求。两个账号各自按Sep1–30的Charge period读取，排除了默认28天和另一个KZ Community Bot项目。

| 报表范围 | 未舍入小计USD | 页面显示USD |
|---|---:|---:|
| dev，Zerde Bot对应Gemini服务行 | 0.605498 | 0.61 |
| prod，精确Zerde项目行 | 0.438845 | 0.44 |

dev CSV的“总计”未舍入列本身为0.610000，不能把服务小计0.605498改叫其总计。prod CSV的Filtered total为0.438845。CSV独立核算和主UI账号/日期/筛选观察分别留证；dev CSV本身无项目/日期字段，prod有精确项目行但无账期字段。运行key与项目的独占使用关系本轮没有再次验证，因此这些是供应商项目报表，不是逐调用独占归因。

Google的日期按美国太平洋午夜（随夏令时变化），税和发票级调整不包含于Charge period；[官方口径](https://docs.cloud.google.com/billing/docs/how-to/reports)。因此不把Google PT与AWS UTC数据合成一个精确同窗总额。dev九月Billing period另显示服务0.61、调整8.01、税1.38、账单月总额10.00；单张发票/付款尚未对账，不能将这10美元当作模型消费，也不将使用报表税列0理解为账号无税。历史充值不是本月消费。

[供应商安全摘要](evidence/2026-10-04-september-costs/provider-result.safe.json)；[直接CSV独审](evidence/2026-10-04-september-costs/provider-independent-post.safe.json)；[阶段聚合](evidence/2026-10-04-september-costs/final.safe.json)。原provider-result中的pending为独审前时点，后续以独审回执为准。下载dev CSV的工具等待曾超时，文件实际完成；按精确名称/时间找到后移动至私有目录，未重复下载。原始CSV和UI观察仅在私有期限目录，仓库不包含账号、结算ID、项目ID或银行信息。

## 未完成项与停止边界

| 项目 | 当前证据及下一有限动作 |
|---|---|
| AWS未标/共享及税归属 | 缺历史资源级分摊，保持UNKNOWN；不新增基础设施或虚构历史回填 |
| AWS发票、付款、Free Tier | 10月6日账号发票摘要USD44.83已独审；付款与历史Free Tier仍UNKNOWN，不重跑已完成摘要查询 |
| Google | 使用报表已取得；运行key的非秘密项目映射、独占使用及发票/税/付款仍待，不能用项目名证明独占 |
| Groq/DeepSeek | 10月6日两官方控制台均需登录，未读取账号账单，UNKNOWN；等待用户登录，不凭SDK配置或无日志称零 |
| Z17其余业务 | dev空轮询同窗比较、故障/恢复/预算通知及Quiz恢复保护按原工单，费用查询不代替业务验收 |

本次CE已Estimated=false，不需为了等Estimated转正机械重跑Oct7；只有新增账单问题或实质修订才补查。下一到期责任是Oct8日志原文精确清理；Oct5旧stats USER备份已按原身份删除并独审，不可重跑。费用待登录项不阻止独立业务推进，不能用当前免费额度冒充九月历史。

## 原文保留及运行边界

实际6份AWS回执、2份CSV及1份主UI观察均0600，目录0700；共同期限2026-10-11 17:01:48.147210UTC，新精确清理/独审，安全hash与聚合保留。原五期限照旧，见[副本台账](RETAINED_COPIES.md)。本轮不部署，PR242仍为运行版本；原预算owner/UNKNOWN、dev控制/epoch、prod无CONTROL保持原义务，本轮没有重新读回它们，不能把“没有修改”称新的线上验收。自然样本仍0/50与0/20，production_ready=false。
