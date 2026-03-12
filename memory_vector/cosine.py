import math
from typing import Iterable


def cosine(a: Iterable[float], b: Iterable[float]) -> float:
    """余弦相似度。输入为等长向量。"""
    aa = list(a)
    bb = list(b)
    if not aa or not bb or len(aa) != len(bb):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(aa, bb):
        dot += float(x) * float(y)
        na += float(x) * float(x)
        nb += float(y) * float(y)
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))

