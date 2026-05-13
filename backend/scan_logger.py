"""扫描日志：输出到控制台和根目录 log/ 文件夹"""
import logging
import os
import sys

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "log")

def _init():
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    root = logging.getLogger("scan")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    # file handler
    fh = logging.FileHandler(os.path.join(LOG_DIR, "scan.log"), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)
    # console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)
    return root

logger = _init()
