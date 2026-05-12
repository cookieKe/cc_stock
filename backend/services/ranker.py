from typing import List, Dict


class RankingEngine:
    """多策略加权排名引擎。"""

    @staticmethod
    def weighted_rank(results: List[dict], strategies: List[dict]) -> List[dict]:
        """加权汇总：各策略评分 × 权重 → 综合得分 → 降序排名。"""
        if not results or not strategies:
            return []
        total_weight = sum(s["weight"] for s in strategies)
        for r in results:
            weighted = sum(
                r["scores"].get(s["name"], 0) * s["weight"]
                for s in strategies
            )
            r["weighted_score"] = round(weighted / total_weight, 2) if total_weight > 0 else 0
        results.sort(key=lambda x: x["weighted_score"], reverse=True)
        for i, r in enumerate(results):
            r["rank"] = i + 1
        return results

    @staticmethod
    def sector_rank(results: List[dict], sector_map: Dict[str, str]) -> Dict[str, List[dict]]:
        """按行业分组排名。"""
        sectors: Dict[str, List[dict]] = {}
        for r in results:
            sector = sector_map.get(r["code"], "未知")
            if sector not in sectors:
                sectors[sector] = []
            sectors[sector].append(r)
        for sector, stocks in sectors.items():
            stocks.sort(key=lambda x: x["weighted_score"], reverse=True)
            for i, s in enumerate(stocks):
                s["sector_rank"] = i + 1
        return sectors

    @staticmethod
    def composite_score(results: List[dict], strategies: List[dict]) -> List[dict]:
        """综合评分：先归一化各策略评分，再加权汇总。"""
        if not results:
            return []
        strat_names = [s["name"] for s in strategies]
        for name in strat_names:
            values = [r["scores"].get(name, 0) for r in results]
            vmin, vmax = min(values), max(values)
            if vmax > vmin:
                for r in results:
                    r["scores"][name] = round((r["scores"].get(name, 0) - vmin) / (vmax - vmin) * 100, 2)
        return RankingEngine.weighted_rank(results, strategies)
