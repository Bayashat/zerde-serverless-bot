# 同步 Lambda 调用日志修复

`/quizreconcile`管理员校验后可以进入同步`LambdaInvoker.invoke`。原异常诊断带`exc_info=True`，凭据脱敏不等于任意普通正文移除。本地反例确认该路径能记录普通内容；没有据此声称线上同步调用已经泄漏或boto3必然回显poll。

唯一修改点为原同步异常日志：固定消息、配置的函数名、异常类型；去掉异常正文及cause/context输出。保留一次`RequestResponse`、原完整编码payload；不特判`FunctionError`，合法JSON包括列表/标量/null原样返回，空响应或捕获invoke/read/decode错误返回{}，logger自身失败仍可传播。async、formatter、权限、Quiz发布/计分/恢复与Memory费用owner均不改。

## 当前本地证据

- 新增17例，修复前8失败/9通过；修复后54个定向测试通过。
- 完整2357测试通过，保留一个原SDK DeprecationWarning；pre-commit通过。
- 真实adapter与JSONFormatter接入，仅替换外部client/response；验证完整请求、次数、返回与最终JSON。

## 发布与有限收口门槛

独立正确性/维护/POST审核后，固定候选commit与CI；新精确操作器PRE、五入口ARM、dev/prod实际五函数ZIP/共享层/配置保护主检及独审、300秒稳定窗口。预计仅Bot/MemoryWorker共同包更新，其余三包与层保持；实际差异以发布证据为准，不能从源码数目推断字节数。

实际发布后用新下载包做同步出口本地隔离探针及独立原始POST，并重新绑定原104文件预算reader。原五费用owner、UNKNOWN责任和费用起点不变。随后结合原16Webhook组合、2个真实urllib3重试、有限CloudWatch真实请求证据与PR240修复，按Z02原有限契约评审是否结项。

Z02当前OPEN。原CloudWatch FAIL不覆盖；9原文文件仍在2026-10-08 17:13:39.091570UTC精确清理。原Z10四期限见[副本台账](RETAINED_COPIES.md)。不把历史全量永不泄漏、无限媒体排列变成新门槛；也不以本次日志证据完成Quiz精确UI链接、其它业务恢复、真实账单或自然使用门槛。production_ready=false，不启用新群/prod记忆。
