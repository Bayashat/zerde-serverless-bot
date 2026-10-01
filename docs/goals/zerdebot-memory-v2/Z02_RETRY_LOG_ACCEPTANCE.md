# 真实urllib3重试日志验收

2026-10-01，PR235发布时独立下载的实际Bot ZIP/共享层，本地Linux ARM64/Python3.13，INFO与DEBUG各一个场景通过，独立原始证据复核通过。没有产品改动、新部署、AWS、Telegram或模型调用；运行构建仍为`7d3f42827662cae428bc3276319a165add9c417a`。

## 实际结果

| 场景 | JSON日志 | 真实连接拒绝 | 库产生的重试WARNING | 保护违规 |
|---|---:|---:|---:|---:|
| INFO | 7 | 4 | 3 | 0 |
| DEBUG | 10 | 4 | 3 | 0 |

真实urllib3 2.7.0默认Retry(total=3)产生2→1→0警告序列；初次连接加三次重试均由操作系统返回ECONNREFUSED。完整ConnectionRefusedError→NewConnectionError→MaxRetryError与Webhook异常出口存在，bot路径中的测试token已被隐藏。stdout为空，stderr每条非空记录均为JSON，初始化/认证/错误等正证据齐全；10种固定内容/凭据变体在原始流及解码字段中均未命中。没有二次清洗原始输出。

8次连接是容器内部loopback失败，不是8次Telegram API调用。没有捕获未脱敏的中间异常对象；测试token经过URL异常路径的判断来自实际API base、未改URI构造代码及已脱敏警告的交叉证据，不冒称直接读取过中间原始token异常。

## 实包与隔离

Bot与层来自PR235两环境先前独立下载的同字节包，完整文件清单、每例77个实际导入模块及关键urllib3路径/哈希一致。本轮没有新查询AWS运行状态。固定原AWS ARM镜像digest，禁外网、只读根目录、非root、去capabilities/禁止提权；完整包未删依赖。

进程在调用前真实bind并持续持有一个未listen的127.0.0.1临时端口。精确数值地址解析和connect均委托原socket实现；仅此endpoint可达，其他connect/DNS/send/listen/accept及botocore调用被保护拒绝。任何意外连接成功或错误errno均立即FAIL；实际每例4次errno111、0次成功，最后socket关闭。产品TelegramClient、PoolManager、request、Retry、logger、formatter没有替换；仅无IO下游依赖被隔离。

每例实际Docker配置、退出、remove返回与按精确ID/name的不存在回执齐全，独立另只读确认两容器缺席。准备和两例执行合计961.535905秒，低于冻结45分钟期限。所有once及原raw冻结，不能重跑来改结论。

## 独审与工具证据

独审直接重读4份原始流、两份运行结果及包/模块/隔离/清理回执，未导入主评分器。主工具PRE曾发现中止情况下的FAIL分类不够严格，已在运行前修正并保留原NEEDS_REVISION。71个人工评分负控和2个正控只是工具检查，不能加到2个产品场景；工具独审的额外检查也不作为线上测试数。

[安全聚合](evidence/2026-10-01-z02-urllib3-retry/result.safe.json)绑定原报告、独审和artifact/fixture/raw哈希。私有入口为验收根`2026-10-01-z02-urllib3-retry/CURRENT.md`，原文仅本机私有文件。

## Z02有限收口

原工单要求是最终出口的message/嵌套extra/异常链脱敏、授权后元数据日志和Telegram错误展示最小化。按该契约复用证据，不因每轮“未覆盖”无限扩大任务。

| 原要求 | 已有证据 | 有限剩余 |
|---|---|---|
| 最终formatter/嵌套字段/异常链及reserved message/level | 原定向测试、PR235冻结全测；16场景实际包出口 | 原契约逐项映射与独审，不重跑已冻结测试 |
| 私聊/未授权群/错误凭据/授权群只记元数据 | 同日16场景、69条JSON，独审PASS | 一个既有dev正常Webhook请求从真实Lambda入口到CloudWatch的完整采集证据 |
| adapter保留业务分类，不展示完整body/token | 原真实formatter/adapter定向断言与16场景HTTP/边缘异常 | 同一契约映射，未声称在线触发Telegram失败 |
| urllib3网络重试耗尽与traceback | 本轮2场景17条JSON、真实默认连接拒绝重试独审PASS | 此有限生产者路径已补齐；不声称所有TLS/DNS/代理/读超时类别已测 |

下一步先冻结单独只读采集契约与工具PRE：仅既有授权dev Bot日志组，时间来自已完成请求证据，限定API/分页/窗口，绑定当前code/layer/config。完整读取选定invocation的START至END/REPORT、全部应用日志和采集边界，平台日志单列；不可只筛安全关键词。缺页、关联歧义、边界不完整或运行漂移即INCOMPLETE，不猜request ID，不以“没找到正文”当PASS。私有原文0600，公开只元数据/哈希与范围。该方案仍是下一步，尚无本轮线上采集执行或工具PRE。

不重发2404/2406或任何已结束UI动作，不新造消息、不读secret值、不Invoke/接收或purge队列。若既有记录无法唯一关联，先保留具体缺口，不能由本研究自动发新消息。最终按已有定向测试、16场景、本轮及有限采集证据逐条复核后，才决定Z02限定范围是否结项。

“不保证全部历史生产日志从未泄漏”及“没有穷举所有业务/媒体/模型/重试排列”是保证边界，不是无限追加的关闭门槛。若发现具体旁路或疑似真实泄漏，保全证据并单独处理。Z02与Epic仍OPEN；Z16反馈精确UI链接仍PARTIAL，自然0/50与0/20、production_ready=false、原预算UNKNOWN及四项副本职责保持。
