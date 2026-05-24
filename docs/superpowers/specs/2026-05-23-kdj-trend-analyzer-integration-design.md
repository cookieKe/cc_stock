# KDJ V2 集成 TrendAnalyzer — 替换趋势回归评分

## 目标

用 TrendAnalyzer（之字转向 + 道氏趋势分类）替换 KDJ V2 中的 `_trend_regression_score`（OLS 低点回归），提供更准确的趋势结构判断。

## 改动范围

**仅修改一个文件：** `backend/strategy_engine/built_in/kdj_reversal_v2.py`

## 核心映射

| TrendAnalyzer 趋势 | 基础分 | 强度加成 | 谷底加成 | 最终区间 |
|---------------------|--------|----------|----------|----------|
| `strong_up` | 80 | + strength.score × 0.20 | +10 (如果最后转折点是谷底) | 80–100 |
| `slow_up` | 60 | + strength.score × 0.25 | +10 | 60–85 |
| `sideways` | 45 | + strength.score × 0.15 | +10 | 45–70 |
| `slow_down` | 25 | + strength.score × 0.20 | +10 | 25–55 |
| `strong_down` | 10 | + strength.score × 0.10 | — | 10–20 |

"最近转折点是谷底" 加分：确认价格刚从低点反弹，对反转策略是关键看涨信号。

## 具体改动

1. **新增 import:** `from backend.strategy_engine.trend_analyzer import TrendAnalyzer`
2. **新增方法:** `_trend_analyzer_score(self, df, p)` 
3. **修改 `score()` 第129行:** `self._trend_regression_score(lows, p)` → `self._trend_analyzer_score(df, p)`
4. **删除方法:** `_trend_regression_score`
5. **删除参数:** `trend_regression_days`
6. **保持不变:** `trend_weight` (15%) 及其他所有组件

## 设计原则

- 下降趋势**不给0分**：KDJ 反转策略的目标股都在下跌中，硬过滤会导致无结果
- **谷底加成**是核心信号：股价已触底反弹
- 原有 J 超卖门禁、背离检测、量能确认等组件**完全不动**
