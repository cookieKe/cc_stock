from abc import ABC, abstractmethod
from typing import Optional


class NotificationChannel(ABC):
    """推送渠道抽象基类"""

    name: str = "base"

    @abstractmethod
    def send(self, title: str, content: str, recipient: str = "") -> bool:
        """发送通知。返回是否成功。"""

    @staticmethod
    def format_scan_report(scan_result: dict) -> str:
        """格式化扫描结果为推送文本。"""
        lines = [
            f"【A股扫描日报】{scan_result.get('scan_date', '')}",
            f"执行策略：{', '.join(scan_result.get('strategies_used', []))}",
            f"扫描股票：{scan_result.get('total_scanned', 0)}只 | 上榜：{scan_result.get('total_ranked', 0)}只",
            "",
            "🏆 Top 10 推荐：",
        ]
        for r in scan_result.get("top_20", [])[:10]:
            lines.append(f"  {r['rank']}. {r['name']}({r['code']})  综合评分 {r['score']}")
        return "\n".join(lines)

    @staticmethod
    def format_tracker_report(tracker_stats: dict) -> str:
        """格式化追踪统计为推送文本。"""
        lines = [
            "📊 追踪组合日报",
            f"追踪股票：{tracker_stats.get('count', 0)}只",
            f"平均累计收益：{tracker_stats.get('avg_return', 0)}%",
            f"盈利占比：{tracker_stats.get('positive_ratio', 0)}%",
            f"今日平均涨跌：{tracker_stats.get('today_avg_change', 0)}%",
        ]
        best = tracker_stats.get("best", {})
        worst = tracker_stats.get("worst", {})
        if best:
            lines.append(f"🏆 最佳：{best.get('name', '')} 累计+{best.get('return', 0)}%")
        if worst:
            lines.append(f"📉 最差：{worst.get('name', '')} 累计{worst.get('return', 0)}%")
        return "\n".join(lines)
