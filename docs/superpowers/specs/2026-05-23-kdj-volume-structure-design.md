# KDJ V2 量能结构分析 — 基于 TrendAnalyzer 转折点

## 目标

用 TrendAnalyzer 识别出的峰-谷结构，分析下跌段的量价关系是否符合"抛压衰竭"模式，
替换现有的 `_volume_score`（均量比）和 `_pass_peak_volume_gate`（单点扫描）。

## 改动文件

`backend/strategy_engine/built_in/kdj_reversal_v2.py`

## 核心逻辑

取 TrendAnalyzer 识别出的**最近一个峰→谷下跌段**，分析两个条件：

### 条件一：峰值放量（60%）

峰值成交量 > 下跌段平均成交量。高点充分换手，恐慌盘/出货压力释放。

```
vol_ratio = 峰值量 / 下跌段均量
vol_ratio ≥ 1.2 → 60分
vol_ratio ≥ 1.0 → 45分
vol_ratio < 1.0 → max(0, 45 - (1.0 - ratio) * 90)
```

### 条件二：下跌缩量（40%）

下跌段内收盘价下跌的交易日中，量也同步萎缩的比例。

```
contraction% = 缩量下跌天数 / 总下跌天数
contraction% ≥ 70% → 40分
contraction% ≥ 50% → 28分
contraction% < 50%  → contraction% * 56
```

### 总分 = 条件一 + 条件二（0-100）

## 边界处理

| 情况 | 处理 |
|------|------|
| 转折点 < 2 个 | 50 分 |
| 最近转折点是谷底（已反弹） | 取倒数第二个峰，向后找谷底 |
| 峰谷之间 < 2 个交易日 | 50 分 |
| 无成交量列 | 50 分 |

## 具体改动

1. **删除** `_pass_peak_volume_gate` 方法及其在 `score()` 中的调用
2. **替换** `_volume_score` 为新实现
3. **删除** 参数: `volume_short`, `volume_long`, `volume_boost`, `volume_penalty`
4. **保留** `volume_weight` (0.20)
