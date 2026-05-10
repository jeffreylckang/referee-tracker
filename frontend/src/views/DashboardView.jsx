import { useEffect, useRef, useState, useMemo } from 'react'
import { fetchReferees, fetchPlayers, fetchTeams, fetchFilters, fetchReferee, fetchPlayer, fetchTeam, fetchSummary } from '../api'
import styles from './DashboardView.module.css'

const TEAM_NAMES = {
  ATL: 'Atlanta Hawks',         BOS: 'Boston Celtics',        BKN: 'Brooklyn Nets',
  CHA: 'Charlotte Hornets',     CHI: 'Chicago Bulls',         CLE: 'Cleveland Cavaliers',
  DAL: 'Dallas Mavericks',      DEN: 'Denver Nuggets',        DET: 'Detroit Pistons',
  GSW: 'Golden State Warriors', HOU: 'Houston Rockets',       IND: 'Indiana Pacers',
  LAC: 'LA Clippers',           LAL: 'Los Angeles Lakers',    MEM: 'Memphis Grizzlies',
  MIA: 'Miami Heat',            MIL: 'Milwaukee Bucks',       MIN: 'Minnesota Timberwolves',
  NOP: 'New Orleans Pelicans',  NYK: 'New York Knicks',       OKC: 'Oklahoma City Thunder',
  ORL: 'Orlando Magic',         PHI: 'Philadelphia 76ers',    PHX: 'Phoenix Suns',
  POR: 'Portland Trail Blazers',SAC: 'Sacramento Kings',      SAS: 'San Antonio Spurs',
  TOR: 'Toronto Raptors',       UTA: 'Utah Jazz',             WAS: 'Washington Wizards',
}

const FOUL_LABELS = {
  shooting:   'Shooting',
  personal:   'Personal',
  offensive:  'Offensive',
  loose_ball: 'Loose Ball',
  flagrant_1: 'Flagrant 1',
  flagrant_2: 'Flagrant 2',
  technical:  'Technical',
}

const PERIOD_LABEL = p => p <= 4 ? `Q${p}` : `OT${p - 4 > 1 ? p - 4 : ''}`

export default function DashboardView() {
  const [tab,        setTab]        = useState('referees')
  const [referees,   setReferees]   = useState([])
  const [players,    setPlayers]    = useState([])
  const [teams,      setTeams]      = useState([])
  const [filters,    setFilters]    = useState({ seasons: [], foul_types: [] })
  const [season,     setSeason]     = useState('')
  const [gameType,   setGameType]   = useState('')
  const [foulDetail, setFoulDetail] = useState('')
  const [search,     setSearch]     = useState('')
  const [detail,     setDetail]     = useState(null)
  const [loading,    setLoading]    = useState(true)
  const [summary,    setSummary]    = useState(null)
  const [playerSort, setPlayerSort] = useState('called')

  useEffect(() => {
    fetchFilters().then(f => setFilters(f))
  }, [])

  useEffect(() => {
    setLoading(true)
    setDetail(null)
    const opts = { season: season || undefined, game_type: gameType || undefined, foul_detail: foulDetail || undefined }
    fetchSummary(opts).then(setSummary)
    // Load each list independently — referees clear the spinner as soon as they arrive
    fetchReferees(opts).then(r => { setReferees(r); setLoading(false) })
    fetchPlayers(opts).then(p => setPlayers(p))
    fetchTeams(opts).then(t => setTeams(t))
  }, [season, gameType, foulDetail])

  const query = search.toLowerCase()
  const filterOpts = { season: season || undefined, game_type: gameType || undefined, foul_detail: foulDetail || undefined }

  const pendingRef = useRef(null)
  const abortRef   = useRef(null)

  function _newRequest() {
    if (abortRef.current) abortRef.current.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    return ctrl.signal
  }

  function selectReferee(r) {
    const id     = r.official_id
    const key    = `referee:${id}`
    const signal = _newRequest()
    pendingRef.current = key
    setDetail({ type: 'referee', data: null, _id: id })
    fetchReferee(id, { ...filterOpts, include_badges: false, signal })
      .then(data => { if (pendingRef.current === key) setDetail({ type: 'referee', data, _id: id }) })
      .catch(() => {})
    fetchReferee(id, { ...filterOpts, signal })
      .then(data => { if (pendingRef.current === key) setDetail({ type: 'referee', data, _id: id }) })
      .catch(() => {})
  }

  function selectPlayer(p) {
    const id     = p.player_id
    const key    = `player:${id}`
    const signal = _newRequest()
    pendingRef.current = key
    setDetail({ type: 'player', data: null, _id: id })
    fetchPlayer(id, { ...filterOpts, include_badges: false, signal })
      .then(data => { if (pendingRef.current === key) setDetail({ type: 'player', data, _id: id }) })
      .catch(() => {})
    fetchPlayer(id, { ...filterOpts, signal })
      .then(data => { if (pendingRef.current === key) setDetail({ type: 'player', data, _id: id }) })
      .catch(() => {})
  }

  function selectTeam(t) {
    const id     = t.team_tricode
    const key    = `team:${id}`
    const signal = _newRequest()
    pendingRef.current = key
    setDetail({ type: 'team', data: null, _id: id })
    fetchTeam(id, { ...filterOpts, include_badges: false, signal })
      .then(data => { if (pendingRef.current === key) setDetail({ type: 'team', data, _id: id }) })
      .catch(() => {})
    fetchTeam(id, { ...filterOpts, signal })
      .then(data => { if (pendingRef.current === key) setDetail({ type: 'team', data, _id: id }) })
      .catch(() => {})
  }

  const filteredReferees = referees.filter(r => r.official_name.toLowerCase().includes(query))
  const filteredPlayers  = players.filter(p => p.player_name.toLowerCase().includes(query))
  const filteredTeams    = teams.filter(t =>
    t.team_tricode.toLowerCase().includes(query) ||
    (TEAM_NAMES[t.team_tricode] || '').toLowerCase().includes(query)
  )

  return (
    <div className={styles.wrap}>
      {/* Left: list */}
      <div className={styles.list}>
        <div className={styles.listHeader}>
          <div className={styles.tabs}>
            <button className={tab === 'referees' ? styles.tabActive : styles.tab} style={tab === 'referees' ? { background: 'var(--referee)', color: '#fff' } : {}} onClick={() => { setTab('referees'); setDetail(null) }}>Referees</button>
            <button className={tab === 'players'  ? styles.tabActive : styles.tab} style={tab === 'players'  ? { background: 'var(--player)',  color: '#fff' } : {}} onClick={() => { setTab('players');  setDetail(null) }}>Players</button>
            <button className={tab === 'teams'    ? styles.tabActive : styles.tab} style={tab === 'teams'    ? { background: 'rgba(100,116,139,0.85)', color: '#fff' } : {}} onClick={() => { setTab('teams');    setDetail(null) }}>Teams</button>
          </div>
          <input
            placeholder={`Search ${tab}…`}
            value={search}
            onChange={e => setSearch(e.target.value)}
            className={styles.search}
          />
          <select value={season} onChange={e => setSeason(e.target.value)}>
            <option value="">All seasons</option>
            {filters.seasons.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={gameType} onChange={e => setGameType(e.target.value)}>
            <option value="">All game types</option>
            <option value="regular">Regular season</option>
            <option value="playoff">Playoffs</option>
          </select>
          <select value={foulDetail} onChange={e => setFoulDetail(e.target.value)}>
            <option value="">All foul types</option>
            {filters.foul_types.map(f => <option key={f} value={f}>{FOUL_LABELS[f] ?? f}</option>)}
          </select>
        </div>

        <div className={styles.listScroll}>
          {loading ? (
            <div className={styles.empty}>Loading…</div>
          ) : tab === 'referees' ? (
            <table className={styles.table}>
              <thead><tr><th>Referee</th><th className={styles.num}>Total Fouls Called</th></tr></thead>
              <tbody>
                {filteredReferees.map(r => (
                  <tr key={r.official_id} onClick={() => selectReferee(r)}
                    className={detail?.data?.referee?.official_id === r.official_id ? styles.selectedRow : styles.row}>
                    <td>{r.official_name}</td>
                    <td className={styles.num}>{r.total_fouls.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : tab === 'players' ? (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Player</th>
                  <th>Team</th>
                  <th className={`${styles.num} ${playerSort === 'called' ? styles.sortActive : styles.sortable}`}
                      onClick={() => setPlayerSort('called')} title="Sort by fouls called">
                    Called ↕
                  </th>
                  <th className={`${styles.num} ${playerSort === 'drawn' ? styles.sortActive : styles.sortable}`}
                      onClick={() => setPlayerSort('drawn')} title="Sort by fouls drawn">
                    Drawn ↕
                  </th>
                </tr>
              </thead>
              <tbody>
                {[...filteredPlayers]
                  .sort((a, b) => playerSort === 'drawn'
                    ? (b.total_fouls_drawn || 0) - (a.total_fouls_drawn || 0)
                    : (b.total_fouls || 0) - (a.total_fouls || 0))
                  .map(p => (
                  <tr key={p.player_id} onClick={() => selectPlayer(p)}
                    className={detail?.data?.player?.player_id === p.player_id ? styles.selectedRow : styles.row}>
                    <td>{p.player_name}</td>
                    <td className={styles.muted}>{p.team_tricode || '—'}</td>
                    <td className={styles.num}>{p.total_fouls.toLocaleString()}</td>
                    <td className={styles.num}>{(p.total_fouls_drawn || 0).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <table className={styles.table}>
              <thead><tr><th>Team</th><th className={styles.num}>Total fouls</th></tr></thead>
              <tbody>
                {filteredTeams.map(t => (
                  <tr key={t.team_tricode} onClick={() => selectTeam(t)}
                    className={detail?.data?.team_tricode === t.team_tricode ? styles.selectedRow : styles.row}>
                    <td>{TEAM_NAMES[t.team_tricode] ?? t.team_tricode} <span className={styles.muted}>({t.team_tricode})</span></td>
                    <td className={styles.num}>{t.total_fouls.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Right: banner + detail */}
      <div className={styles.detail}>
        <LeagueBanner summary={summary} collapsed={!!detail} onExpand={() => setDetail(null)} />
        <div className={styles.detailScroll}>
          {!detail ? (
            <div className={styles.empty}>Select a {tab === 'referees' ? 'referee' : tab === 'players' ? 'player' : 'team'} to see details</div>
          ) : !detail.data ? (
            <div className={styles.empty}>Loading…</div>
          ) : detail.type === 'referee' ? (
            <RefereeDetail data={detail.data} season={season} summary={summary} />
          ) : detail.type === 'player' ? (
            <PlayerDetail data={detail.data} season={season} summary={summary} />
          ) : (
            <TeamDetail data={detail.data} season={season} summary={summary} />
          )}
        </div>
      </div>
    </div>
  )
}

function LeagueBanner({ summary, collapsed, onExpand }) {
  if (!summary) return null
  const { total_fouls, total_games, total_refs, avg_fouls_per_game, median_fouls_per_game,
          most_active_ref, most_fouled_player, most_drawn_player, most_penalized_team } = summary

  if (collapsed) {
    return (
      <div className={styles.bannerCollapsed} onClick={onExpand} title="Click to expand league stats">
        <span className={styles.bannerChip}>League</span>
        <span>Avg {avg_fouls_per_game} fouls/game</span>
        <span className={styles.bannerSep}>·</span>
        <span>Median {median_fouls_per_game} fouls/game</span>
        <span className={styles.bannerExpandHint}>↑ expand</span>
      </div>
    )
  }

  return (
    <div className={styles.banner}>
      <div className={styles.bannerStatRow}>
        <BannerStat label="Total fouls"       value={total_fouls?.toLocaleString()} />
        <BannerStat label="Games"             value={total_games?.toLocaleString()} />
        <BannerStat label="Active refs"       value={total_refs?.toLocaleString()} />
        <BannerStat label="Avg fouls/game"    value={avg_fouls_per_game} />
        <BannerStat label="Median fouls/game" value={median_fouls_per_game} />
      </div>
      <div className={styles.bannerLeaderRow}>
        {most_active_ref && (
          <LeaderCard accent="var(--referee)" label="Most active ref"
            name={most_active_ref.official_name}
            sub={`${most_active_ref.total_fouls?.toLocaleString()} fouls · ${most_active_ref.games_worked} games`} />
        )}
        {most_fouled_player && (
          <LeaderCard accent="var(--player)" label="Most fouls committed"
            name={most_fouled_player.player_name}
            sub={`${most_fouled_player.total_fouls?.toLocaleString()} fouls`} />
        )}
        {most_drawn_player && (
          <LeaderCard accent="var(--player)" label="Most fouls drawn"
            name={most_drawn_player.player_name}
            sub={`${most_drawn_player.total_fouls_drawn?.toLocaleString()} fouls drawn`} />
        )}
        {most_penalized_team && (
          <LeaderCard accent="rgba(100,116,139,0.7)" label="Most penalized team"
            name={TEAM_NAMES[most_penalized_team.team_tricode] ?? most_penalized_team.team_tricode}
            sub={`${most_penalized_team.total_fouls?.toLocaleString()} fouls`} />
        )}
      </div>
    </div>
  )
}

function BannerStat({ label, value }) {
  return (
    <div className={styles.bannerStat}>
      <div className={styles.bannerStatVal}>{value ?? '—'}</div>
      <div className={styles.bannerStatLabel}>{label}</div>
    </div>
  )
}

function LeaderCard({ accent, label, name, sub }) {
  return (
    <div className={styles.leaderCard} style={{ borderLeftColor: accent }}>
      <span className={styles.leaderLabel} style={{ color: accent }}>{label}</span>
      <span className={styles.leaderName}>{name}</span>
      <span className={styles.leaderSub}>{sub}</span>
    </div>
  )
}

function OverviewBanner({ meta, badges }) {
  if (!meta && !badges?.length) return null
  return (
    <div className={styles.overviewBanner}>
      {meta && <p className={styles.bannerMeta}>{meta}</p>}
      {badges?.length > 0 && (
        <div className={styles.badges}>
          {badges.map(b => (
            <div key={b.id} className={styles.badge}>
              <div className={styles.badgeNameRow}>
                <span className={styles.badgeName}>{b.label}</span>
                {b.description && (
                  <span className={styles.badgeTooltipWrap}>
                    <span className={styles.badgeTooltipIcon}>?</span>
                    <span className={styles.badgeTooltipText}>{b.description}</span>
                  </span>
                )}
              </div>
              {b.stat && <span className={styles.badgeStat}>{b.stat}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function DeviationControl({ fpg, season_trend, leagueAvg, totalFoulsKey = 'total_fouls', label = 'fouls/game' }) {
  const [mode, setMode] = useState('league')

  const careerFpg = useMemo(() => {
    if (!season_trend?.length) return null
    const totalFouls = season_trend.reduce((s, r) => s + (r[totalFoulsKey] || 0), 0)
    const totalGames = season_trend.reduce((s, r) => s + (r.games_worked || r.games_played || 0), 0)
    return totalGames > 0 ? totalFouls / totalGames : null
  }, [season_trend, totalFoulsKey])

  const comp  = mode === 'league' ? leagueAvg : careerFpg
  const pct   = comp && fpg != null ? (fpg - comp) / comp * 100 : null
  const sign  = pct >= 0 ? '+' : ''
  const color = pct > 2 ? 'var(--referee)' : pct < -2 ? 'var(--player)' : 'var(--text-muted)'

  return (
    <div className={styles.deviationRow}>
      <span className={styles.deviationFpg}>{fpg != null ? `${fpg} ${label}` : '—'}</span>
      <span className={styles.deviationVs}>vs</span>
      <span className={styles.deviationFpg}>{comp != null ? `${comp.toFixed(2)} ${label}` : '—'}</span>
      <select className={styles.deviationSelect} value={mode} onChange={e => setMode(e.target.value)}>
        <option value="league">league avg</option>
        <option value="career">own career avg</option>
      </select>
      <span className={styles.deviationBadge} style={{ color }}>
        {pct != null ? `${sign}${pct.toFixed(1)}%` : '—'}
      </span>
    </div>
  )
}

function WeightedTable({ items, nameKey, idKey }) {
  if (!items?.length) return null
  const MIN_SHARED = 3
  const sorted = [...items]
    .filter(r => (r.games_shared || 0) >= MIN_SHARED)
    .map(r => ({ ...r, rate: r.games_shared > 0 ? r.total_fouls / r.games_shared : 0 }))
    .sort((a, b) => b.rate - a.rate)
    .slice(0, 10)
  if (!sorted.length) return null
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Name</th>
          <th className={styles.num}>Fouls</th>
          <th className={styles.num}>Shared games</th>
          <th className={styles.num}>Per game</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map(r => (
          <tr key={r[idKey]}>
            <td>{r[nameKey]}</td>
            <td className={styles.num}>{r.total_fouls}</td>
            <td className={styles.num}>{r.games_shared}</td>
            <td className={styles.num}>{r.rate.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function SeasonChart({ season_trend, note, fpgKey = 'fouls_per_game' }) {
  if (!season_trend?.length) return null
  const max = Math.max(...season_trend.map(s => parseFloat(s[fpgKey]) || 0))
  if (!max) return null
  return (
    <>
      {note && <p className={styles.chartNote}>{note}</p>}
      <div className={styles.chartWrap}>
        {season_trend.map(s => {
          const val = parseFloat(s[fpgKey]) || 0
          const pct = max > 0 ? (val / max) * 100 : 0
          const lbl = s.season?.slice(2).replace('-', '–') ?? s.season
          const games = s.games_worked ?? s.games_played
          return (
            <div key={s.season} className={styles.chartCol} title={`${s.season}: ${val} fouls/game (${games} games)`}>
              <div className={styles.chartBarWrap}>
                <div className={styles.chartBarVal}>{val.toFixed(1)}</div>
                <div className={styles.chartBar} style={{ height: `${pct}%` }} />
              </div>
              <div className={styles.chartLabel}>{lbl}</div>
            </div>
          )
        })}
      </div>
    </>
  )
}

function PeriodTable({ period_breakdown }) {
  if (!period_breakdown?.length) return null
  const total = period_breakdown.reduce((s, p) => s + p.count, 0)
  return (
    <table className={styles.table}>
      <thead><tr><th>Quarter</th><th className={styles.num}>Count</th><th className={styles.num}>%</th></tr></thead>
      <tbody>
        {period_breakdown.map(p => (
          <tr key={p.period}>
            <td>{PERIOD_LABEL(p.period)}</td>
            <td className={styles.num}>{p.count.toLocaleString()}</td>
            <td className={styles.num}>{total ? ((p.count / total) * 100).toFixed(1) + '%' : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function FoulTable({ foul_breakdown }) {
  const total = foul_breakdown.reduce((s, f) => s + f.count, 0)
  return (
    <table className={styles.table}>
      <thead><tr><th>Type</th><th className={styles.num}>Count</th><th className={styles.num}>%</th></tr></thead>
      <tbody>
        {foul_breakdown.map(f => (
          <tr key={f.foul_detail}>
            <td>{FOUL_LABELS[f.foul_detail] ?? f.foul_detail}</td>
            <td className={styles.num}>{f.count.toLocaleString()}</td>
            <td className={styles.num}>{total ? ((f.count / total) * 100).toFixed(1) + '%' : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function RefereeDetail({ data, season, summary }) {
  const { referee, top_players, top_players_drawn, foul_breakdown, period_breakdown, season_trend, crew_chief_games, badges, banner_stats } = data

  return (
    <div className={styles.detailInner}>
      <div className={styles.detailHeader}>
        <span className={styles.dotReferee} />
        <div>
          <h2>{referee.official_name}</h2>
          {season && <p className={styles.sub}>{season}</p>}
        </div>
      </div>
      <OverviewBanner
        meta={crew_chief_games != null ? `Games as Crew Chief: ${crew_chief_games.toLocaleString()}` : null}
        badges={badges}
      />

      <div className={styles.sectionRow}>
        <Section title="Foul breakdown"><FoulTable foul_breakdown={foul_breakdown} /></Section>
        {period_breakdown?.length > 0 && (
          <Section title="By quarter"><PeriodTable period_breakdown={period_breakdown} /></Section>
        )}
      </div>

      {season_trend?.length > 1 && (
        <Section title="Fouls called per game officiated, by season">
          <SeasonChart season_trend={season_trend} note="Fouls this referee called divided by the number of games they officiated that season." />
        </Section>
      )}

      <Section title="Players called for the most fouls by this referee">
        <div className={styles.scrollTableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Player</th><th>Team</th>
                <th className={styles.num}>Fouls</th>
                <th className={styles.num}>Shooting</th>
                <th className={styles.num}>Personal</th>
                <th className={styles.num}>Offensive</th>
                <th className={styles.num}>Loose Ball</th>
                <th className={styles.num}>Flagrant 1</th>
                <th className={styles.num}>Flagrant 2</th>
                <th className={styles.num}>Technical</th>
              </tr>
            </thead>
            <tbody>
              {top_players.map(p => (
                <tr key={p.fouler_player_id}>
                  <td>{p.fouler_player_name}</td>
                  <td className={styles.muted}>{p.fouler_team_tricode || '—'}</td>
                  <td className={styles.num}>{p.total_fouls}</td>
                  <td className={styles.num}>{p.shooting || 0}</td>
                  <td className={styles.num}>{p.personal || 0}</td>
                  <td className={styles.num}>{p.offensive || 0}</td>
                  <td className={styles.num}>{p.loose_ball || 0}</td>
                  <td className={styles.num}>{p.flagrant_1 || 0}</td>
                  <td className={styles.num}>{p.flagrant_2 || 0}</td>
                  <td className={styles.num}>{p.technical || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {top_players_drawn?.length > 0 && (
        <Section title="Players who draw the most fouls called by this referee">
          <div className={styles.scrollTableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Player</th><th>Team</th>
                  <th className={styles.num}>Total</th>
                  <th className={styles.num}>Shooting</th>
                  <th className={styles.num}>Personal</th>
                  <th className={styles.num}>Offensive</th>
                  <th className={styles.num}>Loose Ball</th>
                  <th className={styles.num}>Flagrant 1</th>
                  <th className={styles.num}>Flagrant 2</th>
                  <th className={styles.num}>Technical</th>
                </tr>
              </thead>
              <tbody>
                {top_players_drawn.map(p => (
                  <tr key={p.player_id}>
                    <td>{p.player_name}</td>
                    <td className={styles.muted}>{p.team_tricode || '—'}</td>
                    <td className={styles.num}>{p.total_fouls_drawn}</td>
                    <td className={styles.num}>{p.shooting || 0}</td>
                    <td className={styles.num}>{p.personal || 0}</td>
                    <td className={styles.num}>{p.offensive || 0}</td>
                    <td className={styles.num}>{p.loose_ball || 0}</td>
                    <td className={styles.num}>{p.flagrant_1 || 0}</td>
                    <td className={styles.num}>{p.flagrant_2 || 0}</td>
                    <td className={styles.num}>{p.technical || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
    </div>
  )
}

function PlayerDetail({ data, season, summary }) {
  const { player, top_referees, top_referees_drawn, drawn_breakdown,
          drawn_season_trend, fouls_drawn, drawn_per_game,
          foul_breakdown, period_breakdown, season_trend, fouls_per_game,
          badges, banner_stats } = data

  return (
    <div className={styles.detailInner}>
      <div className={styles.detailHeader}>
        <span className={styles.dotPlayer} />
        <div>
          <h2>{player.player_name}</h2>
          <p className={styles.sub}>{[player.team_tricode, season].filter(Boolean).join(' · ')}</p>
        </div>
      </div>

      <OverviewBanner badges={badges} />

      <div className={styles.sectionRow}>
        <Section title="Foul breakdown"><FoulTable foul_breakdown={foul_breakdown} /></Section>
        {period_breakdown?.length > 0 && (
          <Section title="By quarter"><PeriodTable period_breakdown={period_breakdown} /></Section>
        )}
      </div>

      {(season_trend?.length > 1 || drawn_season_trend?.length > 1) && (
        <div className={styles.twoColCharts}>
          {season_trend?.length > 1 && (
            <Section title="Fouls called per game, by season">
              <SeasonChart season_trend={season_trend} />
            </Section>
          )}
          {drawn_season_trend?.length > 1 && (
            <Section title="Fouls drawn per game, by season">
              <SeasonChart season_trend={drawn_season_trend} fpgKey="drawn_per_game" />
            </Section>
          )}
        </div>
      )}

      <Section title="Referees who called the most fouls on this player">
        <div className={styles.scrollTableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Referee</th>
                <th className={styles.num}>Fouls</th>
                <th className={styles.num}>Shooting</th>
                <th className={styles.num}>Personal</th>
                <th className={styles.num}>Offensive</th>
                <th className={styles.num}>Loose Ball</th>
                <th className={styles.num}>Flagrant 1</th>
                <th className={styles.num}>Flagrant 2</th>
                <th className={styles.num}>Technical</th>
              </tr>
            </thead>
            <tbody>
              {top_referees.map(r => (
                <tr key={r.official_id}>
                  <td>{r.official_name}</td>
                  <td className={styles.num}>{r.total_fouls}</td>
                  <td className={styles.num}>{r.shooting || 0}</td>
                  <td className={styles.num}>{r.personal || 0}</td>
                  <td className={styles.num}>{r.offensive || 0}</td>
                  <td className={styles.num}>{r.loose_ball || 0}</td>
                  <td className={styles.num}>{r.flagrant_1 || 0}</td>
                  <td className={styles.num}>{r.flagrant_2 || 0}</td>
                  <td className={styles.num}>{r.technical || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {top_referees_drawn?.length > 0 && (
        <Section title="Referees who call the most fouls in favor of this player">
          <div className={styles.scrollTableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Referee</th>
                  <th className={styles.num}>Total</th>
                  <th className={styles.num}>Shooting</th>
                  <th className={styles.num}>Personal</th>
                  <th className={styles.num}>Offensive</th>
                  <th className={styles.num}>Loose Ball</th>
                  <th className={styles.num}>Flagrant 1</th>
                  <th className={styles.num}>Flagrant 2</th>
                  <th className={styles.num}>Technical</th>
                </tr>
              </thead>
              <tbody>
                {top_referees_drawn.map(r => (
                  <tr key={r.official_id}>
                    <td>{r.official_name}</td>
                    <td className={styles.num}>{r.total_fouls_drawn}</td>
                    <td className={styles.num}>{r.shooting || 0}</td>
                    <td className={styles.num}>{r.personal || 0}</td>
                    <td className={styles.num}>{r.offensive || 0}</td>
                    <td className={styles.num}>{r.loose_ball || 0}</td>
                    <td className={styles.num}>{r.flagrant_1 || 0}</td>
                    <td className={styles.num}>{r.flagrant_2 || 0}</td>
                    <td className={styles.num}>{r.technical || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

    </div>
  )
}

function TeamDetail({ data, season, summary }) {
  const { team_tricode, top_referees, foul_breakdown, period_breakdown, season_trend, fouls_per_game, referee_win_loss, badges, banner_stats } = data

  return (
    <div className={styles.detailInner}>
      <div className={styles.detailHeader}>
        <span className={styles.dotPlayer} />
        <div>
          <h2>{TEAM_NAMES[team_tricode] ?? team_tricode}</h2>
          <p className={styles.sub}>{[team_tricode, season].filter(Boolean).join(' · ')}</p>
        </div>
      </div>
      <OverviewBanner badges={badges} />

      <div className={styles.sectionRow}>
        <Section title="Foul breakdown"><FoulTable foul_breakdown={foul_breakdown} /></Section>
        {period_breakdown?.length > 0 && (
          <Section title="By quarter"><PeriodTable period_breakdown={period_breakdown} /></Section>
        )}
      </div>

      {season_trend?.length > 1 && (
        <Section title="Fouls called per game, by season">
          <SeasonChart season_trend={season_trend} note="Fouls called on this team divided by games they appeared in foul data that season." />
        </Section>
      )}

      <Section title="Referees who called the most fouls on this team">
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Referee</th>
              <th className={styles.num}>Fouls</th>
              <th className={styles.num}>Shooting</th>
              <th className={styles.num}>Personal</th>
              <th className={styles.num}>Offensive</th>
              <th className={styles.num}>Loose Ball</th>
              <th className={styles.num}>Flagrant 1</th>
              <th className={styles.num}>Flagrant 2</th>
              <th className={styles.num}>Technical</th>
            </tr>
          </thead>
          <tbody>
            {top_referees.map(r => (
              <tr key={r.official_id}>
                <td>{r.official_name}</td>
                <td className={styles.num}>{r.total_fouls}</td>
                <td className={styles.num}>{r.shooting || 0}</td>
                <td className={styles.num}>{r.personal || 0}</td>
                <td className={styles.num}>{r.offensive || 0}</td>
                <td className={styles.num}>{r.loose_ball || 0}</td>
                <td className={styles.num}>{r.flagrant_1 || 0}</td>
                <td className={styles.num}>{r.flagrant_2 || 0}</td>
                <td className={styles.num}>{r.technical || 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      {referee_win_loss?.length > 0 && (
        <Section title="Team record when officiated by… (all-time)">
          <div className={styles.scrollTableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Referee</th>
                  <th className={styles.num}>W</th>
                  <th className={styles.num}>L</th>
                  <th className={styles.num}>Games</th>
                  <th className={styles.num}>Crew Chief</th>
                  <th className={styles.num}>Win%</th>
                </tr>
              </thead>
              <tbody>
                {referee_win_loss.map(r => (
                  <tr key={r.official_id}>
                    <td>{r.official_name}</td>
                    <td className={styles.num}>{r.wins}</td>
                    <td className={styles.num}>{r.losses}</td>
                    <td className={styles.num}>{r.games_reffed}</td>
                    <td className={styles.num}>{r.crew_chief_games || 0}</td>
                    <td className={styles.num}>{r.win_pct != null ? (r.win_pct * 100).toFixed(1) + '%' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className={styles.section}>
      <h3 className={styles.sectionTitle}>{title}</h3>
      {children}
    </div>
  )
}
