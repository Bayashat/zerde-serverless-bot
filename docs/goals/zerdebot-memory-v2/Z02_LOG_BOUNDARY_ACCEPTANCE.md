# Webhook授权边界与日志出口组合验收

2026-10-01，范围为 PR235 发布时已独立下载的实际 Bot ZIP 和共享层，在本地 Linux ARM64 / Python 3.13 下运行。产品代码未改，运行源码仍 `7d3f42827662cae428bc3276319a165add9c417a`。两环境下载包字节相同；本轮只计16个本地场景，不计作两个线上环境各16次。

## 已执行的矩阵

以下8类各运行INFO、DEBUG两个独立进程，16/16通过；独立逐项核对全部32条原始输出流、实际路由及模块/隔离证据通过。

| 输入 | 所需证据 |
|---|---|
| 私聊正常 | 真实Telegram adapter仅构造固定帮助回复，日志没有输入正文 |
| 未配置群 | 原白名单判断拒绝，无发送、Memory或Dispatcher调用 |
| 缺少Webhook凭据 | 畸形正文尚未解析，先返回Unauthorized并记录固定拒绝日志 |
| 错误Webhook凭据 | 同上，错误凭据不入日志 |
| 配置群普通消息 | 唯一Update日志只含类型、update_id及长度/数量，下游调用顺序正确 |
| 凭据正确但JSON无效 | 原解析器返回Invalid request，只留安全错误信息 |
| 私聊HTTP错误 | 本地HTTP替身返回500，真实adapter/异常链保留状态与响应长度，排除响应正文 |
| 私聊transport错误 | 本地HTTP边缘抛真实urllib3异常对象链，真实adapter/webhook/formatter脱敏 |

69条实际日志逐行均为JSON；同时要求初始化、校验、错误与元数据正证据，不能以空输出通过。内容与凭据测试值相互独立，原始stdout/stderr未经二次清洗。42个评分器负控与135项工具独审检查分别记录，不加到16个产品组合场景中。

## 运行与安全边界

实际Webhook、config、凭据比较、JSON解析、Telegram `_post/send_message`、日志adapter/formatter与脱敏器均从完整发布包导入。只替换HTTP边缘、Memory摄取取得入口、spam.run和group-agent下游，并显式传入无IO的Dispatcher；逐项核调用计数与顺序。普通消息之外的Update形状不在本矩阵。

Docker固定原AWS ARM镜像digest，禁止拉取和外网，根文件系统只读，去掉capabilities且禁止提权；只挂载已核包、工具、全假fixture和独立输出目录。进程清空宿主环境，socket/DNS/botocore保护计数均为0。导入文件与原包清单哈希一致。已结束的容器和脚本不重跑；没有AWS、Telegram或模型调用。

固定45分钟准备/执行期限内完成，本轮实际549.190495秒。工具PRE最初发现截止时间及FAIL分类两项问题，修正后再执行；原报告保留。没有把工具问题写成生产故障或产品泄漏。

## 证据与未覆盖

[安全聚合](evidence/2026-10-01-z02-webhook-log-boundary/result.safe.json)绑定原运行、独立复核、包、镜像、fixture及raw日志哈希。私有入口为验收根下`2026-10-01-z02-webhook-log-boundary/CURRENT.md`；原始文件保持0600。

本轮不覆盖Lambda root handler、API Gateway/CloudWatch收集、生产历史日志、urllib3自身真实重试警告、其它业务/媒体/模型路径或reserved-extra字段新对抗输入。HTTP响应与transport失败均为本地合成边缘，不是Telegram线上错误。Z02及Epic仍OPEN，自然样本无新增、production_ready=false；旧Quiz精确UI链接缺口保持。

下一步沿原logger/urllib3所有者补真实库重试日志证据：先把只读研究收紧为独立的本地loopback契约、工具和评审，不改产品logger或原16场景预期。已完成运行冻结，不能改日志/评分器使旧结果变为其它结论。若后续发现泄漏，保留FAIL并单独修复和发布。

实际容器删除命令的成功码由运行器断言，原运行器没有单独保存删除回执；独审另作一次只读Docker列表，确认16个精确ID/名字现均无残留，不补写删除时刻。模块回执覆盖73或75个一方模块；完整依赖包已核hash，但没有逐个记录所有第三方模块的运行导入路径。
