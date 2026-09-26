# Z20 源码退役执行契约（2026-09-27）

目标：在保留V2及现役显式/业务行为的前提下，从当前源码和运行包删除已退役旧知识算法。遵循[FINISH_EXECUTION](FINISH_EXECUTION.md)及已告知[删除前清单](RETIREMENT_INVENTORY.md)。源码基底main b232df6、线上build c9a4219，PR223独立读回完成。

唯一owner：V2事实writer/来源/控制/预算保持原样；纯Telegram文本与style格式统一迁到`services/explicit_context.py`；临时媒体facade只委托V2 EphemeralMediaRepository，不继承旧库，不建新的settings存储。现役plain请求完整内容与旧版合成基线等价；保留primary/fallback的发送围栏。

| 顺序/主代理负责 | 输入/允许范围 | 输出与验收 | 禁止/依赖 |
|---|---|---|---|
| S1调用闭包 | src/bot旧13模块、当前wiring/helper/provider/spam/SQS，dev历史导入拒绝 | 删除13模块及旧主动/频道/提取方法和生产者；现役import闭合、旧task先拒绝 | 不改V2事实/费用/生命周期owner，不改infra资源 |
| S2现役回归 | 混合tests与当前public eval owner imports | 18组旧请求完整等价；媒体/身份/删除/费用围栏保留；focused+full+ARM实包 | 不改gold/scorer/冻结run；不整删混合测试 |
| S3交付 | 本目录/指导文档、CI/PR/部署及实包检查 | POST/正确性/维护性审阅、CI；停读前freshSETTINGS；dev后prod实际包缺13模块与缓存 | 0/3精确键/AV类型/hash/newwriter任一变化即停，不恢复旧writer |
| S4后续资源 | 单独精确CDK及操作清单 | 消费者/权限解除后实际删表、vector资源并不存在读回 | 本源码阶段不宣称S4完成；6张现役表和控制/UNKNOWN保全 |

PRE独审、explorer、mixed-test清单（另有两项补充）和18组c9请求基线在私有`2026-09-27-legacy-source-retirement`。基线覆盖四语言默认/短/详细、文本/caption、真人/旧bot引用、单媒体/四项相册。只证明序列化与界面，不代替模型或生命周期验收。

字段兼容的style normalizer保留纯数据字段；plain serializer空旧context标签是冻结请求接口，无法读取或存储旧知识。router的旧schema拒绝与vector discard薄壳保留至对应资源真正退役，不是可启用旧算法。shared assets、git历史和副本义务不等于现役知识路径；PITR/保留期限继续单列Z10。

源码合并、部署、旧数据与云资源删除分别登记。出现旧引用依赖、请求漂移、媒体/发送围栏回退、未知settings或保护数据变化即停止对应步骤；回退仅无长期记忆显式问答。每次实质进展同步manifest/TASKS/HANDOFF/EVIDENCE与#221/#161/Epic157。当前IMPLEMENTING，未上线本源码清理，未删云资源。

本地实现门禁：2264全测PASS，pre-commit PASS，正确性/维护性POST ALIGNED。13模块物理缺失的打包反例65项通过；158混合现役case有明确对应。下一步冻结源码比较18请求、PR/CI及真实ARM构建。发布前首次fresh SETTINGS门禁尚未执行，云资源未删。
