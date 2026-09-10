# Memory V2 离线评估

**产品状态：IMPLEMENTED_UNPROVEN；模型效果：NOT_VERIFIED。**

观测来源：`fake_provider`。本报告不能替代真实模型 trace、独立标签复核、dev canary 或七天真实群试运行。

语料：240 场景 / 516 唯一 gold 事实标注 / 256 未知问题。
语料 SHA256：`66a8e35625b3c64b1e107152a3a461f09be4cf225c01c8459695a6b3b56fc4b7`。全部文本、身份和业务快照均为合成、AI 编写。

| 切片 | TP / FP / FN | Precision | Recall | 来源支持（支持/断言） | Unknown abstention（正确/问题） |
| --- | --- | --- | --- | --- | --- |
| 总计 | 161 / 7 / 603 | 95.83% | 21.07% | 96.15% (250/260) | 95.31% (244/256) |
| kk | 41 / 1 / 150 | 97.62% | 21.47% | 98.46% (64/65) | 95.31% (61/64) |
| ru | 41 / 2 / 150 | 95.35% | 21.47% | 95.52% (64/67) | 95.31% (61/64) |
| en | 39 / 2 / 152 | 95.12% | 20.42% | 95.24% (60/63) | 95.31% (61/64) |
| mixed | 40 / 2 / 151 | 95.24% | 20.94% | 95.38% (62/65) | 95.31% (61/64) |

已知问题完整回答比例逐语言必须 ≥90%；不能用未知拒答率代表正常问答能力：

- kk: 10.71% (6/56)。
- ru: 10.71% (6/56)。
- en: 7.14% (4/56)。
- mixed: 8.93% (5/56)。

零容忍各自判定，缺 trace 是 UNVERIFIED，不能计作零错误：

- wrong_identity: PASS；错误 0，可检查 checkpoint 404。
- cross_chat: PASS；错误 0，可检查 checkpoint 404。
- sensitive_leak: PASS；错误 0，可检查 checkpoint 404。
- delete_resurrection: PASS；错误 0，可检查 checkpoint 404。
- business_damage: PASS；错误 0，可检查 checkpoint 404。
- automatic_social: PASS；错误 0，可检查 checkpoint 404。

数值门槛满足：False；观测完整：False。这只描述所提供文件，不认证其真实模型来源。

正常处理、恢复、暂停与过期分别报告；暂停/过期不会当作 DONE 或零延迟：

```json
{
  "coverage": {
    "states": {
      "done": 797,
      "pending": 4,
      "paused": 4,
      "expired": 8
    },
    "distinct_work": 813,
    "observed_checkpoints": 404,
    "expected_checkpoints": 404,
    "status": "SUPPLIED_TRACE_UNVERIFIED",
    "pending_max_age_seconds": 1
  },
  "latency": {
    "normal": {
      "samples": 793,
      "p95_seconds": 2,
      "limit_seconds": 300,
      "status": "PASS"
    },
    "recovery": {
      "samples": 4,
      "p95_seconds": 63,
      "limit_seconds": 600,
      "status": "PASS"
    },
    "ask_text": {
      "samples": 0,
      "p95_seconds": null,
      "limit_seconds": 15,
      "status": "UNVERIFIED"
    }
  },
  "cost": {
    "provided_trace_usd": 0.0,
    "trace_records": 0,
    "status": "NOT_PROVIDED"
  }
}
```

dev canary：NOT_RUN。真实群：0 天 / 0 有依据问答 / 0 未知问题；门槛为 7 天 / 50 / 20。
