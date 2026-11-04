# 实验一汇总（自动生成，来源 results/raw.csv）

## 表 A：模型×能力 质量表（准确率 %，仅计调用成功轮次）

| model_id | chat | tool_use | code | reasoning |
|---|---|---|---|---|
| `Qwen/Qwen3-8B` | 98.3 | 98.9 | 50.0 | 100.0 |
| `Qwen/Qwen3.5-4B` | 91.5 | 92.2 | 36.7 | — |
| `THUDM/GLM-4-9B-0414` | 85.8 | 0.0 | 98.3 | — |
| `XingChenAGI/Xing4.0-29B` | 95.8 | 72.2 | 71.7 | 100.0 |
| `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B` | 93.3 | — | 76.7 | 98.3 |
| `glm-4.7-flash` | 100.0 | 87.1 | 81.2 | 100.0 |
| `mimo9b:latest` | 91.4 | 30.2 | 67.2 | 100.0 |

## 表 B：模型×能力 性能表（s / %）

| model_id | 能力 | TTFT P50 | TTFT P95 | 耗时 P95 | 成功率 | 样本数 |
|---|---|---|---|---|---|---|
| `Qwen/Qwen3-8B` | chat | 22.34 | 53.65 | 83.04 | 100.0% | 60 |
| `Qwen/Qwen3-8B` | tool_use | 12.53 | 30.33 | 32.39 | 100.0% | 90 |
| `Qwen/Qwen3-8B` | code | 257.07 | 531.78 | 565.42 | 13.3% | 60 |
| `Qwen/Qwen3-8B` | reasoning | 58.69 | 217.80 | 228.41 | 98.3% | 60 |
| `Qwen/Qwen3.5-4B` | chat | 65.62 | 146.62 | 148.48 | 78.3% | 60 |
| `Qwen/Qwen3.5-4B` | tool_use | 3.39 | 7.82 | 11.29 | 100.0% | 90 |
| `Qwen/Qwen3.5-4B` | code | 4.82 | 18.45 | 49.71 | 100.0% | 60 |
| `THUDM/GLM-4-9B-0414` | chat | 0.51 | 1.50 | 11.30 | 100.0% | 60 |
| `THUDM/GLM-4-9B-0414` | tool_use | 0.80 | 1.61 | 3.43 | 100.0% | 90 |
| `THUDM/GLM-4-9B-0414` | code | 0.49 | 1.47 | 15.61 | 100.0% | 60 |
| `XingChenAGI/Xing4.0-29B` | chat | 13.71 | 26.21 | 39.26 | 100.0% | 60 |
| `XingChenAGI/Xing4.0-29B` | tool_use | 2.64 | 17.38 | 18.59 | 100.0% | 90 |
| `XingChenAGI/Xing4.0-29B` | code | 20.76 | 37.54 | 59.09 | 100.0% | 60 |
| `XingChenAGI/Xing4.0-29B` | reasoning | 8.34 | 17.99 | 24.42 | 100.0% | 60 |
| `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B` | chat | 12.70 | 39.82 | 51.63 | 100.0% | 60 |
| `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B` | code | 15.49 | 117.65 | 132.67 | 100.0% | 60 |
| `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B` | reasoning | 23.14 | 108.47 | 115.14 | 100.0% | 60 |
| `glm-4.7-flash` | chat | 3.61 | 5.89 | 7.43 | 10.0% | 60 |
| `glm-4.7-flash` | tool_use | 1.66 | 3.80 | 4.57 | 34.4% | 90 |
| `glm-4.7-flash` | code | 11.91 | 24.49 | 29.65 | 26.7% | 60 |
| `glm-4.7-flash` | reasoning | 8.28 | 12.26 | 14.62 | 16.7% | 60 |
| `mimo9b:latest` | chat | 0.70 | 3.37 | 9.87 | 96.7% | 60 |
| `mimo9b:latest` | tool_use | 1.08 | 4.48 | 66.90 | 95.6% | 90 |
| `mimo9b:latest` | code | 6.66 | 19.61 | 27.41 | 72.6% | 84 |
| `mimo9b:latest` | reasoning | 1.17 | 4.18 | 6.61 | 93.3% | 60 |

## 表 C：现行权重序 vs 实验质量序（H1 检验）

| 能力 | 现行权重序 | 实验质量序 | 秩差 | Spearman ρ | 结论 |
|---|---|---|---|---|---|
| chat | XingChenAGI/Xing4.0-29B > Qwen/Qwen3-8B > glm-4.7-flash > deepseek-ai/DeepSeek-R1-0528-Qwen3-8B > THUDM/GLM-4-9B-0414 > Qwen/Qwen3.5-4B > glm-4.6V-Flash > glm-4-flash-250414 > glm-4-flash > mimo9b:latest | glm-4.7-flash > Qwen/Qwen3-8B > XingChenAGI/Xing4.0-29B > deepseek-ai/DeepSeek-R1-0528-Qwen3-8B > Qwen/Qwen3.5-4B > mimo9b:latest > THUDM/GLM-4-9B-0414 | 1.57 | -0.750 | 需调整 |
| tool_use | XingChenAGI/Xing4.0-29B > THUDM/GLM-4-9B-0414 > glm-4.7-flash > Qwen/Qwen3-8B > Qwen/Qwen3.5-4B > mimo9b:latest | Qwen/Qwen3-8B > Qwen/Qwen3.5-4B > glm-4.7-flash > XingChenAGI/Xing4.0-29B > mimo9b:latest > THUDM/GLM-4-9B-0414 | 2.33 | 0.257 | 需调整 |
| code | deepseek-ai/DeepSeek-R1-0528-Qwen3-8B > THUDM/GLM-4-9B-0414 > XingChenAGI/Xing4.0-29B > Qwen/Qwen3-8B > glm-4.7-flash > Qwen/Qwen3.5-4B > mimo9b:latest | THUDM/GLM-4-9B-0414 > glm-4.7-flash > deepseek-ai/DeepSeek-R1-0528-Qwen3-8B > XingChenAGI/Xing4.0-29B > mimo9b:latest > Qwen/Qwen3-8B > Qwen/Qwen3.5-4B | 1.71 | -0.571 | 需调整 |
| reasoning | deepseek-ai/DeepSeek-R1-0528-Qwen3-8B > XingChenAGI/Xing4.0-29B > Qwen/Qwen3-8B > glm-4.7-flash > mimo9b:latest | mimo9b:latest > XingChenAGI/Xing4.0-29B > Qwen/Qwen3-8B > glm-4.7-flash > deepseek-ai/DeepSeek-R1-0528-Qwen3-8B | 1.60 | 0.707 | 需调整 |

> 秩差 = 同一模型在权重序与质量序中位次的平均差；≤1 视为 H1 成立（排序基本一致）。
> Spearman ρ = 权重名次与准确率名次的等级相关系数（−1~+1，越接近 1 越一致，并列名次取平均）；
> 一般 |ρ| ≥ 0.8 视为高度一致，与秩差口径互为印证。仅对已测模型计算，模型数 <2 时为“—”。
