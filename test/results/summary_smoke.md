# 实验一汇总（自动生成，来源 results/raw.csv）

## 表 A：模型×能力 质量表（准确率 %，仅计调用成功轮次）

| model_id | chat | tool_use | code | reasoning |
|---|---|---|---|---|
| `glm-4-flash` | 100.0 | — | — | — |
| `glm-4.7-flash` | — | 100.0 | — | — |

## 表 B：模型×能力 性能表（s / %）

| model_id | 能力 | TTFT P50 | TTFT P95 | 耗时 P95 | 成功率 | 样本数 |
|---|---|---|---|---|---|---|
| `glm-4-flash` | chat | 1.06 | 1.06 | 1.77 | 100.0% | 1 |
| `glm-4.7-flash` | tool_use | 1.45 | 1.45 | 1.48 | 50.0% | 2 |

## 表 C：现行权重序 vs 实验质量序（H1 检验）

| 能力 | 现行权重序 | 实验质量序 | 秩差 | 结论 |
|---|---|---|---|---|
| chat | XingChenAGI/Xing4.0-29B > Qwen/Qwen3-8B > glm-4.7-flash > deepseek-ai/DeepSeek-R1-0528-Qwen3-8B > THUDM/GLM-4-9B-0414 > Qwen/Qwen3.5-4B > glm-4.6V-Flash > glm-4-flash-250414 > glm-4-flash > mimo9b:latest | glm-4-flash | 8.00 | 需调整 |
| tool_use | XingChenAGI/Xing4.0-29B > THUDM/GLM-4-9B-0414 > glm-4.7-flash > Qwen/Qwen3-8B > Qwen/Qwen3.5-4B > mimo9b:latest | glm-4.7-flash | 2.00 | 需调整 |
| code | deepseek-ai/DeepSeek-R1-0528-Qwen3-8B > THUDM/GLM-4-9B-0414 > XingChenAGI/Xing4.0-29B > Qwen/Qwen3-8B > glm-4.7-flash > Qwen/Qwen3.5-4B > mimo9b:latest | 无数据 | — | 待评测 |
| reasoning | deepseek-ai/DeepSeek-R1-0528-Qwen3-8B > XingChenAGI/Xing4.0-29B > Qwen/Qwen3-8B > glm-4.7-flash > mimo9b:latest | 无数据 | — | 待评测 |

> 秩差 = 同一模型在权重序与质量序中位次的平均差；≤1 视为 H1 成立（排序基本一致）。
