# TrendAnalyzer — 统一趋势分析模块

## 目标

提供一个共享的趋势分析工具模块，供所有策略导入使用。基于之字转向（ZigZag）算法识别显著的局部高点和低点，忽略小波动，并据此判断趋势方向和强度。

## 集成方式

共享工具模块，位于 `backend/strategy_engine/trend_analyzer.py`。各策略按需导入使用，不作为独立策略注册。

## 核心算法

### 之字转向（从新到旧扫描）

标准 ZigZag 指标，但从最新数据向最早数据扫描，消除起点敏感性：

1. 若指定 `lookback`，仅保留最近 N 个数据点
2. 将收盘价序列反转，从最新日期向最旧日期遍历
3. 起点 = 最新收盘价，初始方向未知
4. 向历史方向扫描：
   - 当前方向上升：跟踪走过的最高价，当价格从最高点回落超过 `threshold%` → 记录峰值，方向转为下降
   - 当前方向下降：跟踪走过的最低价，当价格从最低点反弹超过 `threshold%` → 记录谷底，方向转为上升
5. 将找到的转折点按时间升序输出

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `threshold` | float | 0.05 | 反转认定阈值（5%），价格反向波动超过此比例才认定转折 |
| `lookback` | int | None | 分析最近 N 个交易日，None 表示全部 |

## 输出结构

```python
{
    # 所有识别出的转折点（按时间升序）
    'turning_points': [
        {'type': 'peak'|'trough', 'date': datetime, 'price': float, 'index': int}
    ],

    # 趋势方向（五态）
    'trend': 'strong_up' | 'slow_up' | 'sideways' | 'slow_down' | 'strong_down',

    # 趋势强度
    'strength': {
        'slope': float,        # 归一化斜率（连接关键转折点）
        'persistence': int,    # 当前趋势持续的转折点数量
        'score': float         # 综合强度 0-100
    },

    # 关键价位
    'last_high': float,        # 最近一个相对高点
    'last_low': float,         # 最近一个相对低点
}
```

## 趋势判断规则（五态分类）

基于最后 2-3 组转折点的高低点比较（道氏理论）：

| 高点比较 | 低点比较 | 趋势 |
|---------|---------|------|
| 更高高点 | 更高低点 | `strong_up` |
| 更高高点 | 低点未明显抬升 | `slow_up` |
| 更低高点 | 更低低点 | `strong_down` |
| 更低低点 | 高点未明显下降 | `slow_down` |
| 其他组合 | — | `sideways` |

**阈值放宽：** 比较时使用 `threshold * 0.5` 作为"明显"的标准（即默认 ±2.5%），避免噪声导致误判。

**退避规则：**
- 转折点 < 2 个 → `sideways`
- 转折点仅 2 个（一峰一谷）→ 仅基于最后一个转折点类型判断方向，无法确认持续性 → `slow_up` / `slow_down`

## 趋势强度计算

### 斜率（归一化 → 0-100）

取最后一个谷底到最后一个峰顶（上升趋势）或最后一个峰顶到最后一个谷底（下降趋势）的连线，计算对数收益率后年化归一化。震荡趋势斜率为 0。

### 持续性

当前趋势方向上连续的转折点数量。例如最近是"上升-上升-上升"则持续性 = 3。

### 综合分数

```
score = min(slope_normalized * 0.6 + persistence_normalized * 0.4 * 100, 100)
persistence_normalized = min(persistence / 4, 1.0)  # 4个连续转折点=满分
```

## 边界情况处理

| 情况 | 处理 |
|------|------|
| 数据量 < 5 | 返回 `sideways`，无转折点 |
| 全部数据未触发任何反转 | 根据首尾价格变化判断单一方向，无转折点 |
| lookback > 数据长度 | 退回全部数据 |
| 数据中有 NaN | 向前填充后处理 |

## 文件结构

```
backend/strategy_engine/trend_analyzer.py    # 核心类 TrendAnalyzer
backend/tests/test_trend_analyzer.py          # 单元测试
```

## 策略集成

各策略在 `score()` 方法中按需使用：

```python
from strategy_engine.trend_analyzer import TrendAnalyzer

ta = TrendAnalyzer(threshold=0.05)
result = ta.analyze(df, lookback=60)

# 用法1: 方向过滤
if result['trend'] in ('strong_down', 'slow_down'):
    return 0

# 用法2: 强度作为因子
trend_bonus = result['strength']['score'] * 0.15
```

## 测试计划

1. **转折点检测** — 构造已知峰谷的模拟数据，验证识别准确性
2. **阈值灵敏度** — 验证 5% 阈值过滤掉小幅波动，10% 阈值更迟钝
3. **趋势分类** — 模拟 5 种趋势状态，验证分类正确
4. **边界数据** — 单边上涨/下跌/横盘/极短数据
5. **从新到旧扫描** — 验证数据起点不同但结果一致
