"""
Badge computation for referee, player, and team detail pages.

Each compute_* function returns (badges, banner_stats).

badges is a list of dicts:
    { "id", "label", "description", "direction" }
    direction: "high" | "low" | "neutral"

banner_stats is a dict of key numbers for the overview banner.

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
    """
    Welch's t-test from summary statistics (mean, sample variance).
    Returns (p_value, mean1, mean2).
    """
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


def _pct_diff(a, b):
    return round((a - b) / b * 100, 1) if b else 0


def _summary(cur, sql, params):
    """
    Wrap sql (which must produce a column named 'cnt') in a summary
    aggregation and return (n, mean, sample_variance).
    """
    cur.execute(f"""
        SELECT COUNT(*)           AS n,
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
    pct = _pct_diff(mean_ref, mean_lg)

    banner_stats = {
        "fouls_per_game": round(mean_ref, 2),
        "league_avg":     round(mean_lg,  2),
        "pct_diff":       pct,
    }

    if pv < alpha:
        if mean_ref > mean_lg:
            badges.append({
                "id": "high_whistler", "label": "High Whistler", "direction": "high",
                "description": (
                    f"Calls {mean_ref:.1f} fouls/game vs the league average of {mean_lg:.1f} "
                    f"({pct:+.1f}%). Welch's t-test with Bonferroni correction (α = {alpha:.4f})."
                ),
            })
        else:
            badges.append({
                "id": "quiet_whistle", "label": "Quiet Whistle", "direction": "low",
                "description": (
                    f"Calls {mean_ref:.1f} fouls/game vs the league average of {mean_lg:.1f} "
                    f"({pct:+.1f}%). Welch's t-test with Bonferroni correction (α = {alpha:.4f})."
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
    if pv < alpha:
        r = ref_tech / ref_tot * 100 if ref_tot else 0
        l = lg_tech  / lg_tot  * 100 if lg_tot  else 0
        badges.append({
            "id": "tech_magnet", "label": "Tech Magnet", "direction": "high",
            "description": (
                f"Technical fouls make up {r:.1f}% of their calls vs the league average of {l:.1f}%. "
                f"One-tailed z-test for proportions, Bonferroni correction (α = {alpha:.4f})."
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
    if pv < alpha:
        r = ref_q4 / ref_reg * 100 if ref_reg else 0
        l = lg_q4  / lg_reg  * 100 if lg_reg  else 0
        badges.append({
            "id": "crunch_time", "label": "Crunch Time Caller", "direction": "high",
            "description": (
                f"{r:.1f}% of regulation fouls called in Q4 vs league average of {l:.1f}%. "
                f"One-tailed z-test for proportions, Bonferroni correction (α = {alpha:.4f})."
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
    if pv < alpha:
        if mean_ref_h > mean_lg_h:
            badges.append({
                "id": "home_bias", "label": "Home Bias", "direction": "neutral",
                "description": (
                    f"Calls {mean_ref_h*100:.1f}% of fouls on the home team per game vs the league "
                    f"average of {mean_lg_h*100:.1f}%. Harder on home teams than a typical referee. "
                    f"Game-level Welch's t-test, Bonferroni correction (α = {alpha:.4f})."
                ),
            })
        else:
            badges.append({
                "id": "away_bias", "label": "Away Bias", "direction": "neutral",
                "description": (
                    f"Calls {mean_ref_h*100:.1f}% of fouls on the home team per game vs the league "
                    f"average of {mean_lg_h*100:.1f}%. Harder on away teams than a typical referee. "
                    f"Game-level Welch's t-test, Bonferroni correction (α = {alpha:.4f})."
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
        if pv < alpha:
            rp = rc / ref_tot * 100 if ref_tot else 0
            lp = lc / lg_tot  * 100 if lg_tot  else 0
            if rc / ref_tot > lc / lg_tot:
                direction, suffix = "high", "Heavy"
            else:
                direction, suffix = "low", "Light"
            badges.append({
                "id": f"{ft}_{direction}", "label": f"{ft_label} {suffix}", "direction": direction,
                "description": (
                    f"{ft_label} fouls are {rp:.1f}% of their calls vs league average of {lp:.1f}%. "
                    f"Two-tailed z-test for proportions, Bonferroni correction (α = {alpha:.4f})."
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
    pct_drawn = _pct_diff(mean_drawn, mean_lg_drawn)

    banner_stats = {
        "drawn_per_game":   round(mean_drawn,    2),
        "league_avg_drawn": round(mean_lg_drawn,  2),
        "drawn_pct_diff":   pct_drawn,
    }

    if pv < alpha and mean_drawn > mean_lg_drawn:
        badges.append({
            "id": "foul_magnet", "label": "Foul Magnet", "direction": "high",
            "description": (
                f"Draws {mean_drawn:.1f} fouls/game vs the league average of {mean_lg_drawn:.1f} "
                f"({pct_drawn:+.1f}%). Welch's t-test, Bonferroni correction (α = {alpha:.4f})."
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
    pct_comm = _pct_diff(mean_comm, mean_lg_comm)

    banner_stats["committed_per_game"]   = round(mean_comm,    2)
    banner_stats["league_avg_committed"] = round(mean_lg_comm, 2)
    banner_stats["committed_pct_diff"]   = pct_comm

    if pv < alpha and mean_comm > mean_lg_comm:
        badges.append({
            "id": "foul_trouble", "label": "Foul Trouble", "direction": "high",
            "description": (
                f"Commits {mean_comm:.1f} fouls/game vs the league average of {mean_lg_comm:.1f} "
                f"({pct_comm:+.1f}%). Welch's t-test, Bonferroni correction (α = {alpha:.4f})."
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
    if pv < alpha:
        r = ref_q4 / ref_reg * 100 if ref_reg else 0
        l = lg_q4  / lg_reg  * 100 if lg_reg  else 0
        badges.append({
            "id": "crunch_time_target", "label": "Crunch Time Target", "direction": "high",
            "description": (
                f"{r:.1f}% of fouls drawn occur in Q4 vs the league average of {l:.1f}%. "
                f"One-tailed z-test for proportions, Bonferroni correction (α = {alpha:.4f})."
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
    pct = _pct_diff(mean_team, mean_lg)

    banner_stats = {
        "fouls_per_game": round(mean_team, 2),
        "league_avg":     round(mean_lg,   2),
        "pct_diff":       pct,
    }

    if pv < alpha:
        if mean_team > mean_lg:
            badges.append({
                "id": "most_penalized", "label": "Most Penalized", "direction": "high",
                "description": (
                    f"Called for {mean_team:.1f} fouls/game vs the league average of {mean_lg:.1f} "
                    f"({pct:+.1f}%). Welch's t-test, Bonferroni correction (α = {alpha:.4f})."
                ),
            })
        else:
            badges.append({
                "id": "least_penalized", "label": "Least Penalized", "direction": "low",
                "description": (
                    f"Called for {mean_team:.1f} fouls/game vs the league average of {mean_lg:.1f} "
                    f"({pct:+.1f}%). Welch's t-test, Bonferroni correction (α = {alpha:.4f})."
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
    if pv < alpha:
        if mean_home > mean_away:
            badges.append({
                "id": "home_disadvantage", "label": "Home Disadvantage", "direction": "high",
                "description": (
                    f"Called for {mean_home:.1f} fouls/game at home vs {mean_away:.1f} on the road. "
                    f"Gets whistled more at home than away. "
                    f"Welch's t-test, Bonferroni correction (α = {alpha:.4f})."
                ),
            })
        else:
            badges.append({
                "id": "away_disadvantage", "label": "Away Disadvantage", "direction": "high",
                "description": (
                    f"Called for {mean_away:.1f} fouls/game on the road vs {mean_home:.1f} at home. "
                    f"Gets whistled more away than at home. "
                    f"Welch's t-test, Bonferroni correction (α = {alpha:.4f})."
                ),
            })

    return badges, banner_stats
