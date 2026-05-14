import os
import numpy as np
from PIL import Image
from typing import Dict, List
import logging

_log = logging.getLogger(__name__)


class PatternLoader:
    """从图片目录加载K线形态模板，提取曲线并缓存。"""

    def __init__(self, patterns_dir: str, target_length: int = 60):
        self.patterns_dir = patterns_dir
        self.target_length = target_length
        self._templates: Dict[str, np.ndarray] = {}
        self._loaded = False

    def load_templates(self) -> Dict[str, np.ndarray]:
        """加载所有模板，返回 {名称: 归一化曲线数组}。已在内存中则直接返回缓存。"""
        if self._loaded and self._templates:
            return self._templates

        self._templates = {}
        if not os.path.isdir(self.patterns_dir):
            _log.warning(f"形态目录不存在: {self.patterns_dir}")
            self._loaded = True
            return self._templates

        for fname in sorted(os.listdir(self.patterns_dir)):
            if fname.startswith("."):
                continue
            fpath = os.path.join(self.patterns_dir, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                curve = self._extract_curve(fpath)
                if curve is not None and len(curve) >= 5:
                    name = os.path.splitext(fname)[0]
                    self._templates[name] = curve
                    _log.info(f"已加载形态模板: {name} ({len(curve)} 点)")
                else:
                    _log.warning(f"未能从图片提取有效曲线: {fname}")
            except Exception as e:
                _log.error(f"加载图片失败 {fname}: {e}")

        self._loaded = True
        _log.info(f"共加载 {len(self._templates)} 个形态模板")
        return self._templates

    def reload(self) -> Dict[str, np.ndarray]:
        """强制重新从磁盘加载模板。"""
        self._loaded = False
        self._templates = {}
        return self.load_templates()

    def match(self, closes: List[float], min_correlation: float = 0.5) -> float:
        """将收盘价序列与所有模板匹配，返回最高相似度得分 (0-100)。"""
        result = self.match_with_info(closes, min_correlation)
        return result["score"]

    def match_with_info(self, closes: List[float], min_correlation: float = 0.5) -> dict:
        """匹配并返回 {'score': float, 'name': str|None}。"""
        if not closes or len(closes) < 10:
            return {"score": 0.0, "name": None}

        templates = self.load_templates()
        if not templates:
            return {"score": 0.0, "name": None}

        prices = np.array(closes, dtype=float)
        price_norm = self._normalize(prices)
        if price_norm is None:
            return {"score": 0.0, "name": None}

        best_score = 0.0
        best_name = None
        for name, template in templates.items():
            corr = self._pearson_correlation(price_norm, template)
            score = max(0.0, corr) * 100
            if score > best_score:
                best_score = score
                best_name = name

        if best_score / 100 < min_correlation:
            return {"score": 0.0, "name": None}
        return {"score": round(best_score, 2), "name": best_name}

    # ── image processing ────────────────────────────────────────

    def _extract_curve(self, fpath: str) -> np.ndarray | None:
        """从图片中提取曲线，返回归一化后的数组。"""
        img = Image.open(fpath).convert("L")
        w, h = img.size
        if w < 20 or h < 20:
            return None

        arr = np.array(img, dtype=float)

        # Determine background: light or dark
        edge_pixels = np.concatenate([
            arr[0, :], arr[-1, :], arr[:, 0], arr[:, -1]
        ])
        bg_bright = np.median(edge_pixels)
        is_light_bg = bg_bright > 128

        # Crop chart region: find non-background content boundaries
        if is_light_bg:
            mask = arr < (bg_bright - 30)
        else:
            mask = arr > (bg_bright + 30)

        rows_with_content = np.any(mask, axis=1)
        cols_with_content = np.any(mask, axis=0)
        row_idx = np.where(rows_with_content)[0]
        col_idx = np.where(cols_with_content)[0]

        if len(row_idx) < 5 or len(col_idx) < 5:
            return None

        r0, r1 = row_idx[0], row_idx[-1]
        c0, c1 = col_idx[0], col_idx[-1]
        crop = arr[r0:r1 + 1, c0:c1 + 1]
        ch, cw = crop.shape

        # Extract curve: for each column, find the "main" line pixel
        # In a chart, the curve is usually the darkest (light bg) or brightest (dark bg)
        curve_y = []
        cols_to_sample = max(self.target_length, 10)
        step = max(1, cw / cols_to_sample)

        x = 0.0
        while x < cw and len(curve_y) < cols_to_sample:
            xi = int(x)
            col = crop[:, min(xi, cw - 1)]

            if is_light_bg:
                # Dark pixels are the curve
                candidates = np.where(col < bg_bright - 40)[0]
            else:
                # Bright pixels are the curve
                candidates = np.where(col > bg_bright + 40)[0]

            if len(candidates) > 0:
                # Invert y: image y=0 is top, but chart top = high price
                curve_y.append(1.0 - float(np.median(candidates)) / ch)
            x += step

        if len(curve_y) < 5:
            return None

        curve = np.array(curve_y, dtype=float)
        return self._normalize(curve)

    # ── helpers ─────────────────────────────────────────────────

    @staticmethod
    def _normalize(arr: np.ndarray) -> np.ndarray | None:
        """Min-Max normalize to [0, 1]."""
        a_min, a_max = arr.min(), arr.max()
        if a_max - a_min < 1e-9:
            return None
        return (arr - a_min) / (a_max - a_min)

    def _pearson_correlation(self, a: np.ndarray, b: np.ndarray) -> float:
        """计算两条曲线的 Pearson 相关系数。将 b 插值到与 a 等长。"""
        if len(b) != len(a):
            xp = np.linspace(0, 1, len(b))
            xi = np.linspace(0, 1, len(a))
            b = np.interp(xi, xp, b)

        a_mean, b_mean = a.mean(), b.mean()
        a_std, b_std = a.std(), b.std()
        if a_std < 1e-9 or b_std < 1e-9:
            return 0.0
        return float(np.corrcoef(a, b)[0, 1])


# Global singleton, initialized by the strategy
pattern_loader: PatternLoader | None = None


def get_pattern_loader(patterns_dir: str = None) -> PatternLoader:
    """获取全局 PatternLoader 单例。"""
    global pattern_loader
    if pattern_loader is None:
        if patterns_dir is None:
            patterns_dir = os.path.join(
                os.path.dirname(__file__), "patterns"
            )
        pattern_loader = PatternLoader(patterns_dir)
    return pattern_loader
