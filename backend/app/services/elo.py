def elo_update(ra: int, rb: int, score_a: float, k: int = 32) -> tuple[int, int]:
    ea = 1 / (1 + 10 ** ((rb - ra) / 400))
    new_a = round(ra + k * (score_a - ea))
    new_b = round(rb + k * ((1 - score_a) - (1 - ea)))
    return new_a, new_b
