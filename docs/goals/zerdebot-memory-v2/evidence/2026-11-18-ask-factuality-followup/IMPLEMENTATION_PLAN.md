# 普通 ask 第二轮通用修复

依据：N真实A安全未知但无用，B166.135秒未见完整回复/P未发，N主独POST已经闭合且窗口释放；E唯一2AWS错误单页PARTIAL，发生过成员授权查询包装失败，但B归属/底层异常UNKNOWN，不能叫已证明B根因。新公开两次API元数据探测证明存在短名redirect，不能当Lambda现场效果。沿用户已授权实现、测试和dev/prod实际部署，不硬编码产品，不再用本N窗口。

## 范围与唯一owner
1. services/public_sources.py 原owner：第一HTTP改generator=search+prop=redirects，仍原topic/language、namespace0、候选最多3，rdlimit50/rdprop pageid|title|fragment/rdshow=!fragment/rdnamespace0；最多第二summary HTTP，6秒/64KiB/不重试不跟页不生成query不缓存不写Memory。完整校验每个page/alias对象与namespace/非bool正pageid/长度/控制字符，拒绝fragment别名，拒绝重复pageid和已返回的跨pageid身份冲突。唯一canonical title按旧大小写/空白/下划线规范化全等优先；无canonical时要求batchcomplete严格true且无属性分页，然后以明确alias全等选唯一pageid。canonical优先可容忍无关alias属性分页，但不声称所有未返回别名无冲突或全百科唯一；任何已见冲突都STOP。继续summary页身份/标准类型/完整抽取门；没有明确来源仍诚实未知，不回退凭空生成。新增固定失败原因码/阶段耗时/调用数日志，不记query/title/URL/source/model文本或异常原文。
2. services/memory_v2/telegram_api.py 原owner：仅getChatMember/getMe只读call总20秒上限不可重置、最多2次HTTP同payload；每次网络段上限8秒，首次TransportError/TimeoutError或HTTP500/502/503/504可一次重试，间隔0.25秒。现役async_http会合并网络/协议错误为httpx.TransportError，因此明确对该已知折叠family做有限只读恢复，不声称可区分永久/瞬态根因，不改共享层映射。429/400/401/403/其它状态/坏响应/身份不符不做局部重试；原SQS重投保留。sendMessage仍严格1次，不包worker/guard/model整段。固定原因码/attempts/耗时日志，无token/URL/响应/异常链。CancelledError继续传播。授权和源/CONTROL/request/budget/lease/send前全部原门保留；网络成功后仍使用原精确身份核对。

## 验证与发布
主代理顺序实现；正确性与维护独立计划/代码审。沿现有PUBLIC/Telegram/explicit delivery实际transport seam加入多实体alias、canonical分页/已知冲突、结构/fragment/pageid坏值、请求数/取消、隐私0查、不可篡改source数据测试。身份read恢复测试经真实shared适配层模拟首个HTTPcore网络故障，第二成功、第二失败、权限/429/坏响应/身份拒绝不重试、无token日志/异常、总deadline/取消、getMe、send单次UNKNOWN、SQS旧恢复和所有门。只合成禁网，不造真实好答案。

uv sync --frozen，针对性及全量tests，precommit全部适用，源CI三job，主独代码审。实际部署新工具/双PRE/精确变更集/完整6ZIP与配置保护/ARM/包内验证、dev主独稳定后prod；只更改两个owner成员，不改层/依赖/provider/model/budget/runtimeconfig。基线是实际当前发布174a849，main d7f4fcf只是文档；完整运行读回不能用main替代。旧D所有入口冻结，若复用工具源码只能新路径/新scope新hash新once，不能读旧过期private或复制raw。未知失败保全，不默认重试发布。

## TODO
- [x] N实际复验和主独POST，17CAPTURED/原deadline1795626160.299967/15职责保持。
- [x] E精确单页诊断与公开alias元数据；诊断PARTIAL，非B因果证明。
- [ ] 本计划双审及最小实现。
- [ ] 实际transport合成与全量回归、代码双审/CI。
- [ ] 两环境真实发布/包/配置/ARM/主独稳定证据。
- [ ] 同步TODO/PLAN/manifest/HANDOFF/EVIDENCE/工单/同一automation真实状态，不改冻结历史。
- [ ] 另备新A/B/P，准备好才请用户新窗口；目前真实有用性未验收。

Z10等其他待办完整保留，当前P0是普通ask。无本地删除/新runtime raw/新期限/手动Invoke/队列读取/付款secret/伪造许可；15原责任不变。
