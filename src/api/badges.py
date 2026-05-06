"""
Badge computation for referee, player, and team detail pages.

Each compute_* function returns (badges, banner_stats).

badges is a list of dicts:
    { "id", "label", "stat", "description", "direction" }
    direction: "high" | "low" | "neutral"

banner_stats is a dict of key numbers for the overview banner.

Significance criteria (both must pass):
    t-test badges  : p < α_bonferroni  AND  Cohen's d ≥ 0.5
    z-test badges  : p < α_bonferroni  AND  Cohen's h ≥ 0.2

Bonferroni correction applied per entity type:
    referee : 8 tests  →  α = 0.05 / 8  ≈ 0.00625
    player  : 3 tests  →  α = 0.05 / 3  ≈ 0.01667
    team    : 2 tests  →  α = 0.05 / 2  = 0.025
"""

import math
from scipy import stats

ALPHA           = 0.05
N_REF_TESTS     = 8
N_PLAYER_TESTS  = 3
N_TEAM_TESTS    = 2

MIN_D = 0.5   # Cohen's d threshold for t-test badges
MIN_H = 0.2   # Cohen's h threshold for z-test proportion badges

# Matches the GAME_TYPE_CLAUSE in main.py
_GTC = """
    AND (%(game_type)s IS NULL
         OR (%(game_type)s = 'regular'  AND g.playoff_round IS NULL)
         OR (%(game_type)s = 'playoff'  AND g.playoff_round IS NOT NULL))
"""


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def _welch(n1, mean1, var1, n2, mean2, var2):
    """Welch's t-test from summary statistics. Returns (p_value, mean1, mean2)."""
    if n1 < 2 or n2 < 2 or not var1 or not var2:
        return 1.0, mean1, mean2
    se2 = var1 / n1 + var2 / n2
    if se2 <= 0:
        return 1.0, mean1, mean2
    t  = (mean1 - mean2) / math.sqrt(se2)
    df = se2 ** 2 / ((var1 / n1) ** 2 / (n1 - 1) + (var2 / n2) ** 2 / (n2 - 1))
    pv = float(2 * stats.t.sf(abs(t), df))
    return pv, mean1, mean2


def _z_prop(count1, n1, count2, n2, alternative="two-sided"):
    """
    One-sample z-test for proportions.
    count2/n2 is the reference (league) proportion treated as known.
    Returns p-value.
    """
    if n1 < 2 or n2 < 2 or count2 == 0:
        return 1.0
    p0 = count2 / n2
    p1 = count1 / n1
    if p0 <= 0 or p0 >= 1:
        return 1.0
    se = math.sqrt(p0 * (1 - p0) / n1)
    if se == 0:
        return 1.0
    z = (p1 - p0) / se
    if alternative == "two-sided":
        return float(2 * stats.norm.sf(abs(z)))
    if alternative == "greater":
        return float(stats.norm.sf(z))
    return float(stats.norm.cdf(z))   # "less"


def _cohens_d(mean1, mean2, n1, var1, n2, var2):
    """Cohen's d using pooled standard deviation."""
    if n1 < 2 or n2 < 2:
        return 0.0
    pooled_var = ((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2)
    return abs(mean1 - mean2) / math.sqrt(pooled_var) if pooled_var > 0 else 0.0


def _cohens_h(p1, p2):
    """Cohen's h effect size for two proportions."""
    if p1 <= 0 or p2 <= 0 or p1 >= 1 or p2 >= 1:
        return 0.0
    return abs(2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2)))


def _p_label(pv):
    if pv < 0.001: return "p < 0.001"
    if pv < 0.01:  return "p < 0.01"
    return "p < 0.05"


def _pct_diff(a, b):
    return round((a - b) / b * 100, 1) if b else 0


def _summary(cur, sql, params):
    """
    Wrap sql (which must produce a column named 'cnt') in a summary
    aggregation and return (n, mean, sample_variance).
    """
    cur.execute(f"""
        SELECT COUNT(*)                AS n,
               COALESCE(AVG(cnt),      0) AS mean,
               COALESCE(VARIANCE(cnt), 0) AS var
        FROM ({sql}) _sub
    """, params)
    row = cur.fetchone()
    return int(row["n"]), float(row["mean"]), float(row["var"])


# ---------------------------------------------------------------------------
# Referee badges  (8 tests)
# ---------------------------------------------------------------------------

def compute_referee_badges(cur, official_id, season, game_type):
    alpha = ALPHA / N_REF_TESTS
    badges = []
    p = {"official_id": official_id, "season": season, "game_type": game_type}

    # ------------------------------------------------------------------
    # 1. Volume — Welch's t-test on per-game foul counts
    # ------------------------------------------------------------------
    ref_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.official_id = %(official_id)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
        GROUP BY f.game_id
    """
    lg_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.official_id != %(official_id)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
        GROUP BY f.official_id, f.game_id
    """
    n1, m1, v1 = _summary(cur, ref_sql, p)
    n2, m2, v2 = _summary(cur, lg_sql,  p)
    pv, mean_ref, mean_lg = _welch(n1, m1, v1, n2, m2, v2)
    d = _cohens_d(mean_ref, mean_lg, n1, v1, n2, v2)
    pct = _pct_diff(mean_ref, mean_lg)

    banner_stats = {
        "fouls_per_game": round(mean_ref, 2),
        "league_avg":     round(mean_lg,  2),
        "pct_diff":       pct,
    }

    if pv < alpha and d >= MIN_D:
        if mean_ref > mean_lg:
            badges.append({
                "id": "high_whistler", "label": "High Whistler", "direction": "high",
                "stat": f"{mean_ref:.2f} vs {mean_lg:.2f} league avg ({pct:+.1f}%)",
                "description": (
                    f"Calls significantly more fouls per game than a typical referee. "
                    f"Welch's two-sample t-test, Bonferroni correction. "
                    f"{_p_label(pv)}, Cohen's d = {d:.2f}."
                ),
            })
        else:
            badges.append({
                "id": "quiet_whistle", "label": "Quiet Whistle", "direction": "low",
                "stat": f"{mean_ref:.2f} vs {mean_lg:.2f} league avg ({pct:+.1f}%)",
                "description": (
                    f"Calls significantly fewer fouls per game than a typical referee. "
                    f"Welch's two-sample t-test, Bonferroni correction. "
                    f"{_p_label(pv)}, Cohen's d = {d:.2f}."
                ),
            })

    # ------------------------------------------------------------------
    # 2. Tech Magnet — one-tailed z-test for proportions
    # ------------------------------------------------------------------
    cur.execute(f"""
        SELECT SUM(CASE WHEN f.foul_detail = 'technical' THEN 1 ELSE 0 END) AS tech,
               COUNT(*) AS total
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.official_id = %(official_id)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
    """, p)
    row = cur.fetchone()
    ref_tech, ref_tot = int(row["tech"] or 0), int(row["total"] or 0)

    cur.execute(f"""
        SELECT SUM(CASE WHEN f.foul_detail = 'technical' THEN 1 ELSE 0 END) AS tech,
               COUNT(*) AS total
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.official_id != %(official_id)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
    """, p)
    row = cur.fetchone()
    lg_tech, lg_tot = int(row["tech"] or 0), int(row["total"] or 0)

    pv = _z_prop(ref_tech, ref_tot, lg_tech, lg_tot, alternative="greater")
    r  = ref_tech / ref_tot if ref_tot else 0
    l  = lg_tech  / lg_tot  if lg_tot  else 0
    h  = _cohens_h(r, l)
    if pv < alpha and h >= MIN_H:
        badges.append({
            "id": "tech_magnet", "label": "Tech Magnet", "direction": "high",
            "stat": f"{r*100:.1f}% of calls vs {l*100:.1f}% league avg",
            "description": (
                f"Technical fouls make up a significantly higher share of their calls than the league average. "
                f"One-tailed z-test for proportions, Bonferroni correction. "
                f"{_p_label(pv)}, Cohen's h = {h:.2f}."
            ),
        })

    # ------------------------------------------------------------------
    # 3. Crunch Time Caller — Q4 proportion, one-tailed z-test
    # ------------------------------------------------------------------
    cur.execute(f"""
        SELECT SUM(CASE WHEN f.period = 4               THEN 1 ELSE 0 END) AS q4,
               SUM(CASE WHEN f.period BETWEEN 1 AND 4   THEN 1 ELSE 0 END) AS reg
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.official_id = %(official_id)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
    """, p)
    row = cur.fetchone()
    ref_q4, ref_reg = int(row["q4"] or 0), int(row["reg"] or 0)

    cur.execute(f"""
        SELECT SUM(CASE WHEN f.period = 4               THEN 1 ELSE 0 END) AS q4,
               SUM(CASE WHEN f.period BETWEEN 1 AND 4   THEN 1 ELSE 0 END) AS reg
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.official_id != %(official_id)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
    """, p)
    row = cur.fetchone()
    lg_q4, lg_reg = int(row["q4"] or 0), int(row["reg"] or 0)

    pv = _z_prop(ref_q4, ref_reg, lg_q4, lg_reg, alternative="greater")
    r  = ref_q4 / ref_reg if ref_reg else 0
    l  = lg_q4  / lg_reg  if lg_reg  else 0
    h  = _cohens_h(r, l)
    if pv < alpha and h >= MIN_H:
        badges.append({
            "id": "crunch_time", "label": "Crunch Time Caller", "direction": "high",
            "stat": f"{r*100:.1f}% in Q4 vs {l*100:.1f}% league avg",
            "description": (
                f"Calls a significantly higher share of fouls in Q4 than the league average. "
                f"One-tailed z-test for proportions, Bonferroni correction. "
                f"{_p_label(pv)}, Cohen's h = {h:.2f}."
            ),
        })

    # ------------------------------------------------------------------
    # 4. Home / Away Bias — game-level Welch's t-test on per-game home proportion
    # ------------------------------------------------------------------
    ref_home_sql = f"""
        SELECT SUM(CASE WHEN f.fouler_team_tricode = g.home_team_tricode THEN 1.0 ELSE 0.0 END)
               / NULLIF(COUNT(*), 0) AS cnt
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.official_id = %(official_id)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
        GROUP BY f.game_id
    """
    lg_home_sql = f"""
        SELECT SUM(CASE WHEN f.fouler_team_tricode = g.home_team_tricode THEN 1.0 ELSE 0.0 END)
               / NULLIF(COUNT(*), 0) AS cnt
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
        GROUP BY g.game_id
    """
    n1, m1, v1 = _summary(cur, ref_home_sql, p)
    n2, m2, v2 = _summary(cur, lg_home_sql,  p)
    pv, mean_ref_h, mean_lg_h = _welch(n1, m1, v1, n2, m2, v2)
    d = _cohens_d(mean_ref_h, mean_lg_h, n1, v1, n2, v2)
    if pv < alpha and d >= MIN_D:
        if mean_ref_h > mean_lg_h:
            badges.append({
                "id": "home_bias", "label": "Home Bias", "direction": "neutral",
                "stat": f"{mean_ref_h*100:.1f}% home fouls vs {mean_lg_h*100:.1f}% league avg",
                "description": (
                    f"Calls a significantly higher share of fouls on the home team than a typical referee. "
                    f"Game-level Welch's t-test (each game's home-foul proportion is one observation), "
                    f"Bonferroni correction. p = {pv:.4f} (α = {alpha:.4f}), Cohen's d = {d:.2f}."
                ),
            })
        else:
            badges.append({
                "id": "away_bias", "label": "Away Bias", "direction": "neutral",
                "stat": f"{mean_ref_h*100:.1f}% home fouls vs {mean_lg_h*100:.1f}% league avg",
                "description": (
                    f"Calls a significantly lower share of fouls on the home team than a typical referee — "
                    f"harder on away teams. Game-level Welch's t-test (each game's home-foul proportion "
                    f"is one observation), Bonferroni correction. p = {pv:.4f} (α = {alpha:.4f}), Cohen's d = {d:.2f}."
                ),
            })

    # ------------------------------------------------------------------
    # 5–8. Foul type outliers (shooting, personal, offensive, loose_ball)
    #       Two-tailed z-test for proportions; flagrant excluded
    # ------------------------------------------------------------------
    TYPES = {"shooting": "Shooting", "personal": "Personal",
             "offensive": "Offensive", "loose_ball": "Loose Ball"}
    type_list = list(TYPES.keys())

    cur.execute(f"""
        SELECT f.foul_detail, COUNT(*) AS cnt
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.official_id = %(official_id)s
          AND f.foul_detail = ANY(%(types)s)
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
        GROUP BY f.foul_detail
    """, {**p, "types": type_list})
    ref_t = {r["foul_detail"]: int(r["cnt"]) for r in cur.fetchall()}
    ref_tot = sum(ref_t.values())

    cur.execute(f"""
        SELECT f.foul_detail, COUNT(*) AS cnt
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.official_id != %(official_id)s
          AND f.foul_detail = ANY(%(types)s)
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
        GROUP BY f.foul_detail
    """, {**p, "types": type_list})
    lg_t = {r["foul_detail"]: int(r["cnt"]) for r in cur.fetchall()}
    lg_tot = sum(lg_t.values())

    for ft, ft_label in TYPES.items():
        rc = ref_t.get(ft, 0)
        lc = lg_t.get(ft, 0)
        pv = _z_prop(rc, ref_tot, lc, lg_tot, alternative="two-sided")
        rp = rc / ref_tot if ref_tot else 0
        lp = lc / lg_tot  if lg_tot  else 0
        h  = _cohens_h(rp, lp)
        if pv < alpha and h >= MIN_H:
            if rp > lp:
                direction, suffix = "high", "Heavy"
            else:
                direction, suffix = "low", "Light"
            label = f"{ft_label} {suffix}" if ft != "personal" or direction == "high" else "Let 'Em Play"
            badges.append({
                "id": f"{ft}_{direction}", "label": label, "direction": direction,
                "stat": f"{rp*100:.1f}% of calls vs {lp*100:.1f}% league avg",
                "description": (
                    f"{ft_label} fouls make up a significantly {'higher' if direction == 'high' else 'lower'} "
                    f"share of their calls than the league average. "
                    f"Two-tailed z-test for proportions, Bonferroni correction. "
                    f"{_p_label(pv)}, Cohen's h = {h:.2f}."
                ),
            })

    return badges, banner_stats


# ---------------------------------------------------------------------------
# Player badges  (3 tests)
# ---------------------------------------------------------------------------

def compute_player_badges(cur, player_id, season, game_type):
    alpha = ALPHA / N_PLAYER_TESTS
    badges = []
    p = {"player_id": player_id, "season": season, "game_type": game_type}

    # ------------------------------------------------------------------
    # 1. Foul Magnet — per-game fouls DRAWN, Welch's t-test
    # ------------------------------------------------------------------
    ref_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.fouled_player_id = %(player_id)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
        GROUP BY f.game_id
    """
    lg_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.fouled_player_id != %(player_id)s
          AND f.fouled_player_id IS NOT NULL
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
        GROUP BY f.fouled_player_id, f.game_id
    """
    n1, m1, v1 = _summary(cur, ref_sql, p)
    n2, m2, v2 = _summary(cur, lg_sql,  p)
    pv, mean_drawn, mean_lg_drawn = _welch(n1, m1, v1, n2, m2, v2)
    d = _cohens_d(mean_drawn, mean_lg_drawn, n1, v1, n2, v2)
    pct_drawn = _pct_diff(mean_drawn, mean_lg_drawn)

    banner_stats = {
        "drawn_per_game":   round(mean_drawn,    2),
        "league_avg_drawn": round(mean_lg_drawn,  2),
        "drawn_pct_diff":   pct_drawn,
    }

    if pv < alpha and d >= MIN_D and mean_drawn > mean_lg_drawn:
        badges.append({
            "id": "foul_magnet", "label": "Foul Magnet", "direction": "high",
            "stat": f"{mean_drawn:.2f} vs {mean_lg_drawn:.2f} drawn/game ({pct_drawn:+.1f}%)",
            "description": (
                f"Draws significantly more fouls per game than the average player. "
                f"Welch's two-sample t-test, Bonferroni correction. "
                f"{_p_label(pv)}, Cohen's d = {d:.2f}."
            ),
        })

    # ------------------------------------------------------------------
    # 2. Foul Trouble — per-game fouls COMMITTED, Welch's t-test
    # ------------------------------------------------------------------
    ref_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.fouler_player_id = %(player_id)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
        GROUP BY f.game_id
    """
    lg_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.fouler_player_id != %(player_id)s
          AND f.fouler_player_id IS NOT NULL
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
        GROUP BY f.fouler_player_id, f.game_id
    """
    n1, m1, v1 = _summary(cur, ref_sql, p)
    n2, m2, v2 = _summary(cur, lg_sql,  p)
    pv, mean_comm, mean_lg_comm = _welch(n1, m1, v1, n2, m2, v2)
    d = _cohens_d(mean_comm, mean_lg_comm, n1, v1, n2, v2)
    pct_comm = _pct_diff(mean_comm, mean_lg_comm)

    banner_stats["committed_per_game"]   = round(mean_comm,    2)
    banner_stats["league_avg_committed"] = round(mean_lg_comm, 2)
    banner_stats["committed_pct_diff"]   = pct_comm

    if pv < alpha and d >= MIN_D and mean_comm > mean_lg_comm:
        badges.append({
            "id": "foul_trouble", "label": "Foul Trouble", "direction": "high",
            "stat": f"{mean_comm:.2f} vs {mean_lg_comm:.2f} committed/game ({pct_comm:+.1f}%)",
            "description": (
                f"Commits significantly more fouls per game than the average player. "
                f"Welch's two-sample t-test, Bonferroni correction. "
                f"{_p_label(pv)}, Cohen's d = {d:.2f}."
            ),
        })

    # ------------------------------------------------------------------
    # 3. Crunch Time Target — Q4 fouls DRAWN proportion, one-tailed
    # ------------------------------------------------------------------
    cur.execute(f"""
        SELECT SUM(CASE WHEN f.period = 4               THEN 1 ELSE 0 END) AS q4,
               SUM(CASE WHEN f.period BETWEEN 1 AND 4   THEN 1 ELSE 0 END) AS reg
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.fouled_player_id = %(player_id)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
    """, p)
    row = cur.fetchone()
    ref_q4, ref_reg = int(row["q4"] or 0), int(row["reg"] or 0)

    cur.execute(f"""
        SELECT SUM(CASE WHEN f.period = 4               THEN 1 ELSE 0 END) AS q4,
               SUM(CASE WHEN f.period BETWEEN 1 AND 4   THEN 1 ELSE 0 END) AS reg
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.fouled_player_id != %(player_id)s
          AND f.fouled_player_id IS NOT NULL
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
    """, p)
    row = cur.fetchone()
    lg_q4, lg_reg = int(row["q4"] or 0), int(row["reg"] or 0)

    pv = _z_prop(ref_q4, ref_reg, lg_q4, lg_reg, alternative="greater")
    r  = ref_q4 / ref_reg if ref_reg else 0
    l  = lg_q4  / lg_reg  if lg_reg  else 0
    h  = _cohens_h(r, l)
    if pv < alpha and h >= MIN_H:
        badges.append({
            "id": "crunch_time_target", "label": "Crunch Time Target", "direction": "high",
            "stat": f"{r*100:.1f}% drawn in Q4 vs {l*100:.1f}% league avg",
            "description": (
                f"Draws a significantly higher share of fouls in Q4 than the average player. "
                f"One-tailed z-test for proportions, Bonferroni correction. "
                f"{_p_label(pv)}, Cohen's h = {h:.2f}."
            ),
        })

    return badges, banner_stats


# ---------------------------------------------------------------------------
# Team badges  (2 tests)
# ---------------------------------------------------------------------------

def compute_team_badges(cur, team_tricode, season, game_type):
    alpha = ALPHA / N_TEAM_TESTS
    badges = []
    p = {"team_tricode": team_tricode, "season": season, "game_type": game_type}

    # ------------------------------------------------------------------
    # 1. Most / Least Penalized — Welch's t-test on per-game foul counts
    # ------------------------------------------------------------------
    team_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.fouler_team_tricode = %(team_tricode)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
        GROUP BY f.game_id
    """
    lg_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.fouler_team_tricode != %(team_tricode)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
        GROUP BY f.fouler_team_tricode, f.game_id
    """
    n1, m1, v1 = _summary(cur, team_sql, p)
    n2, m2, v2 = _summary(cur, lg_sql,   p)
    pv, mean_team, mean_lg = _welch(n1, m1, v1, n2, m2, v2)
    d = _cohens_d(mean_team, mean_lg, n1, v1, n2, v2)
    pct = _pct_diff(mean_team, mean_lg)

    banner_stats = {
        "fouls_per_game": round(mean_team, 2),
        "league_avg":     round(mean_lg,   2),
        "pct_diff":       pct,
    }

    if pv < alpha and d >= MIN_D:
        if mean_team > mean_lg:
            badges.append({
                "id": "most_penalized", "label": "Most Penalized", "direction": "high",
                "stat": f"{mean_team:.2f} vs {mean_lg:.2f} league avg ({pct:+.1f}%)",
                "description": (
                    f"Called for significantly more fouls per game than the average team. "
                    f"Welch's two-sample t-test, Bonferroni correction. "
                    f"{_p_label(pv)}, Cohen's d = {d:.2f}."
                ),
            })
        else:
            badges.append({
                "id": "least_penalized", "label": "Least Penalized", "direction": "low",
                "stat": f"{mean_team:.2f} vs {mean_lg:.2f} league avg ({pct:+.1f}%)",
                "description": (
                    f"Called for significantly fewer fouls per game than the average team. "
                    f"Welch's two-sample t-test, Bonferroni correction. "
                    f"{_p_label(pv)}, Cohen's d = {d:.2f}."
                ),
            })

    # ------------------------------------------------------------------
    # 2. Home / Away Disparity — home vs away per-game fouls, Welch's t-test
    # ------------------------------------------------------------------
    home_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.fouler_team_tricode = %(team_tricode)s
          AND g.home_team_tricode   = %(team_tricode)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
        GROUP BY f.game_id
    """
    away_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM foul_events f JOIN games g ON g.game_id = f.game_id
        WHERE f.fouler_team_tricode = %(team_tricode)s
          AND g.away_team_tricode   = %(team_tricode)s
          AND (%(season)s IS NULL OR g.season = %(season)s)
          {_GTC}
        GROUP BY f.game_id
    """
    n1, m1, v1 = _summary(cur, home_sql, p)
    n2, m2, v2 = _summary(cur, away_sql, p)
    pv, mean_home, mean_away = _welch(n1, m1, v1, n2, m2, v2)
    d = _cohens_d(mean_home, mean_away, n1, v1, n2, v2)
    if pv < alpha and d >= MIN_D:
        if mean_home > mean_away:
            badges.append({
                "id": "home_disadvantage", "label": "Home Disadvantage", "direction": "high",
                "stat": f"{mean_home:.2f} at home vs {mean_away:.2f} away",
                "description": (
                    f"Gets whistled significantly more at home than on the road. "
                    f"Welch's two-sample t-test, Bonferroni correction. "
                    f"{_p_label(pv)}, Cohen's d = {d:.2f}."
                ),
            })
        else:
            badges.append({
                "id": "away_disadvantage", "label": "Away Disadvantage", "direction": "high",
                "stat": f"{mean_away:.2f} away vs {mean_home:.2f} at home",
                "description": (
                    f"Gets whistled significantly more on the road than at home. "
                    f"Welch's two-sample t-test, Bonferroni correction. "
                    f"{_p_label(pv)}, Cohen's d = {d:.2f}."
                ),
            })

    return badges, banner_stats
