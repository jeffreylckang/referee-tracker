import { useEffect, useState } from 'react'
import { fetchReferees, fetchPlayers, fetchTeams, fetchFilters, fetchReferee, fetchPlayer, fetchTeam } from '../api'
import styles from './DashboardView.module.css'

const FOUL_LABELS = {
  shooting:   'Shooting',
  personal:   'Personal',
  offensive:  'Offensive',
  loose_ball: 'Loose Ball',
  flagrant_1: 'Flagrant 1',
  flagrant_2: 'Flagrant 2',
  technical:  'Technical',
}

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

  // Load filter options once
  useEffect(() => {
    fetchFilters().then(f => setFilters(f))
  }, [])

  // Reload list whenever list-level filters change
  useEffect(() => {
    setLoading(true)
    setDetail(null)
    const opts = { season: season || undefined, game_type: gameType || undefined, foul_detail: foulDetail || undefined }
    Promise.all([fetchReferees(opts), fetchPlayers(opts), fetchTeams(opts)]).then(([r, p, t]) => {
      setReferees(r)
      setPlayers(p)
      setTeams(t)
      setLoading(false)
    })
  }, [season, gameType, foulDetail])

  const query = search.toLowerCase()

  const filteredReferees = referees.filter(r =>
    r.official_name.toLowerCase().includes(query)
  )

  const filteredPlayers = players.filter(p =>
    p.player_name.toLowerCase().includes(query)
  )

  const filterOpts = { season: season || undefined, game_type: gameType || undefined, foul_detail: foulDetail || undefined }

  async function selectReferee(r) {
    const data = await fetchReferee(r.official_id, filterOpts)
    setDetail({ type: 'referee', data })
  }

  async function selectPlayer(p) {
    const data = await fetchPlayer(p.player_id, filterOpts)
    setDetail({ type: 'player', data })
  }

  async function selectTeam(t) {
    const data = await fetchTeam(t.team_tricode, filterOpts)
    setDetail({ type: 'team', data })
  }

  return (
    <div className={styles.wrap}>
      {/* Left: list */}
      <div className={styles.list}>
        <div className={styles.listHeader}>
          <div className={styles.tabs}>
            <button className={tab === 'referees' ? styles.tabActive : styles.tab} onClick={() => { setTab('referees'); setDetail(null) }}>Referees</button>
            <button className={tab === 'players'  ? styles.tabActive : styles.tab} onClick={() => { setTab('players');  setDetail(null) }}>Players</button>
            <button className={tab === 'teams'    ? styles.tabActive : styles.tab} onClick={() => { setTab('teams');    setDetail(null) }}>Teams</button>
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

        {loading ? (
          <div className={styles.empty}>Loading…</div>
        ) : tab === 'referees' ? (
          <table className={styles.table}>
            <thead>
              <tr><th>Referee</th><th className={styles.num}>Total fouls</th></tr>
            </thead>
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
              <tr><th>Player</th><th>Team</th><th className={styles.num}>Total fouls</th></tr>
            </thead>
            <tbody>
              {filteredPlayers.map(p => (
                <tr key={p.player_id} onClick={() => selectPlayer(p)}
                  className={detail?.data?.player?.player_id === p.player_id ? styles.selectedRow : styles.row}>
                  <td>{p.player_name}</td>
                  <td className={styles.muted}>{p.team_tricode || '—'}</td>
                  <td className={styles.num}>{p.total_fouls.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr><th>Team</th><th className={styles.num}>Total fouls</th></tr>
            </thead>
            <tbody>
              {teams.filter(t => t.team_tricode.toLowerCase().includes(query)).map(t => (
                <tr key={t.team_tricode} onClick={() => selectTeam(t)}
                  className={detail?.data?.team_tricode === t.team_tricode ? styles.selectedRow : styles.row}>
                  <td>{t.team_tricode}</td>
                  <td className={styles.num}>{t.total_fouls.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Right: detail */}
      <div className={styles.detail}>
        {!detail ? (
          <div className={styles.empty}>Select a {tab === 'referees' ? 'referee' : tab === 'players' ? 'player' : 'team'} to see details</div>
        ) : detail.type === 'referee' ? (
          <RefereeDetail data={detail.data} season={season} />
        ) : detail.type === 'player' ? (
          <PlayerDetail data={detail.data} season={season} />
        ) : (
          <TeamDetail data={detail.data} season={season} />
        )}
      </div>
    </div>
  )
}

function RefereeDetail({ data, season }) {
  const { referee, top_players, foul_breakdown } = data
  const total = foul_breakdown.reduce((s, f) => s + f.count, 0)

  return (
    <div className={styles.detailInner}>
      <div className={styles.detailHeader}>
        <span className={styles.dotReferee} />
        <div>
          <h2>{referee.official_name}</h2>
          {season && <p className={styles.sub}>{season}</p>}
        </div>
      </div>

      <Section title="Foul breakdown">
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
      </Section>

      <Section title="Players called for the most fouls by this referee">
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
      </Section>
    </div>
  )
}

function PlayerDetail({ data, season }) {
  const { player, top_referees, foul_breakdown } = data
  const total = foul_breakdown.reduce((s, f) => s + f.count, 0)

  return (
    <div className={styles.detailInner}>
      <div className={styles.detailHeader}>
        <span className={styles.dotPlayer} />
        <div>
          <h2>{player.player_name}</h2>
          <p className={styles.sub}>{[player.team_tricode, season].filter(Boolean).join(' · ')}</p>
        </div>
      </div>

      <Section title="Foul breakdown">
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
      </Section>

      <Section title="Referees who called the most fouls on this player">
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
    </div>
  )
}

function TeamDetail({ data, season }) {
  const { team_tricode, top_referees, foul_breakdown } = data
  const total = foul_breakdown.reduce((s, f) => s + f.count, 0)

  return (
    <div className={styles.detailInner}>
      <div className={styles.detailHeader}>
        <span className={styles.dotPlayer} />
        <div>
          <h2>{team_tricode}</h2>
          {season && <p className={styles.sub}>{season}</p>}
        </div>
      </div>

      <Section title="Foul breakdown">
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
      </Section>

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
