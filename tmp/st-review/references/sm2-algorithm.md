# SM-2 间隔复习算法

> `/st-review` 使用的简化版 SM-2 (SuperMemo 2) 算法。

## 核心参数

每个概念维护两个参数（存储在 `learning/learner/model.json`）：

| 参数 | 初始值 | 范围 | 含义 |
|------|--------|------|------|
| `easiness` | 2.5 | [1.3, 3.0] | 易度因子，越高表示越容易记住 |
| `interval_days` | 1 | ≥ 1 | 复习间隔天数 |

## 算法流程

### 1. 复习评估

每次复习后，对学习者的回答质量打分 q (0-5)：

| q | 含义 |
|---|------|
| 5 | 完美回答，毫无迟疑 |
| 4 | 通过，有小瑕疵 |
| 3 | 勉强通过，有迟疑但不完整 |
| 2 | 不通过，有明显遗漏 |
| 1 | 不通过，几乎忘记 |
| 0 | 完全不记得 |

### 2. 更新 easiness

```
easiness_new = easiness + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
```

边界约束：
- easiness 下限 1.3（即使完全忘记，也不会低于这个值）
- easiness 上限 3.0

### 3. 更新 interval

**如果 q ≥ 3（通过）**：
```
if interval_days <= 1 or review_count == 0:
    interval_new = 6
else:
    interval_new = round(interval_days * easiness_new)
```

**如果 q < 3（不通过）**：
```
interval_new = 1
lapse_count += 1
```

### 4. 计算 next_review

```
next_review = today + interval_new (天)
review_count += 1
last_quality = q
last_review = today
```

## 示例

### 正常路径（每次通过）

| 复习次数 | q | easiness | interval | next_review |
|----------|---|----------|----------|-------------|
| 首次学习 | - | 2.5 | - | - |
| 1 | 4 | 2.5 | 6 | +6天 |
| 2 | 4 | 2.5 | 15 | +15天 |
| 3 | 5 | 2.6 | 39 | +39天 |
| 4 | 5 | 2.7 | 105 | +105天 |

### 遗忘路径

| 复习次数 | q | easiness | interval | next_review |
|----------|---|----------|----------|-------------|
| 1 | 4 | 2.5 | 6 | +6天 |
| 2 | 1 | 2.18 | 1 | +1天 |
| 3 | 3 | 2.18 | 6 | +6天 |
| 4 | 4 | 2.24 | 13 | +13天 |

## 成熟概念判定

概念满足以下条件时视为"成熟"，在复习排序中降优先级：
- mastery = 4
- review_count ≥ 6
- easiness ≥ 2.5
- last_quality ≥ 4

成熟概念仍然会出现在复习列表中，但排在非成熟概念之后。
