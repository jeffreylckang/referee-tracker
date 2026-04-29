import { useEffect, useState } from 'react'
import { fetchReferees, fetchPlayers, fetchTeams, fetchFilters, fetchReferee, fetchPlayer, fetchTeam } from '../api'
import styles from './CompareView.module.css'

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

async function fetchDetail(type, entity, opts) {
  if (type === 'referees') return fetchReferee(entity.official_id, opts)
  if (type === 'players')  return fetchPlayer(entity.player_id, opts)
  return fetchTeam(entity.team_tricode, opts)
}

function filterList(list, type, search) {
  if (!search) return list
  const q = search.toLowerCase()
  if (type === 'referees') return list.filter(r => r.official_name.toLowerCase().includes(q))
  if (type === 'players')  return list.filter(p =>
    p.player_name.toLowerCase().includes(q) ||
    (p.team_tricode || '').toLowerCase().includes(q) ||
    (TEAM_NAMES[p.team_tricode] || '').toLowerCase().includes(q)
  )
  return list.filter(t =>
    t.team_tricode.toLowerCase().includes(q) ||
    (TEAM_NAMES[t.team_tricode] || '').toLowerCase().includes(q)
  )
}

function getEntityName(type, entity) {
  if (!entity) return ''
  if (type === 'referees') return entity.official_name
  if (type === 'players')  return entity.player_name
  return TEAM_NAMES[entity.team_tricode] ?? entity.team_tricode
}

function getEntityId(type, entity) {
  if (type === 'referees') return entity.official_id
  if (type === 'players')  return entity.player_id
  return entity.team_tricode
}

export default function CompareView() {
  const [type,       setType]       = useState('referees')
  const [filters,    setFilters]    = useState({ seasons: [], foul_types: [] })
  const [season,     setSeason]     = useState('')
  const [gameType,   setGameType]   = useState('')
  const [foulDetail, setFoulDetail] = useState('')
  const [list,       setList]       = useState([])
  const [searchA,    setSearchA]    = useState('')
  const [searchB,    setSearchB]    = useState('')
  const [selectedA,  setSelectedA]  = useState(null)
  const [selectedB,  setSelectedB]  = useState(null)
  const [dataA,      setDataA]      = useState(null)
  const [dataB,      setDataB]      = useState(null)

  useEffect(() => {
    fetchFilters().then(f => setFilters(f))
  }, [])

  // Load list when type or filters change
  useEffect(() => {
    const opts = { season: season || undefined, game_type: gameType || undefined, foul_detail: foulDetail || undefined }
    setList([])
    if (type === 'referees')     fetchReferees(opts).then(setList)
    else if (type === 'players') fetchPlayers(opts).then(setList)
    else                         fetchTeams(opts).then(setList)
  }, [type, season, gameType, foulDetail])

  // Clear selections when type changes
  useEffect(() => {
    setSelectedA(null); setSelectedB(null); setDataA(null); setDataB(null)
  }, [type])

  // Re-fetch detail data when filters change (keep selections, update data)
  useEffect(() => {
    const opts = { season: season || undefined, game_type: gameType || undefined, foul_detail: foulDetail || undefined }
    if (selectedA) fetchDetail(type, selectedA, opts).then(setDataA)
    if (selectedB) fetchDetail(type, selectedB, opts).then(setDataB)
  }, [season, gameType, foulDetail]) // eslint-disable-line

  const opts = { season: season || undefined, game_type: gameType || undefined, foul_detail: foulDetail || undefined }

  async function selectA(entity) {
    setSelectedA(entity)
    setDataA(null)
    fetchDetail(type, entity, opts).then(setDataA)
  }

  async function selectB(entity) {
    setSelectedB(entity)
    setDataB(null)
    fetchDetail(type, entity, opts).then(setDataB)
  }

  const entityLabel = type === 'referees' ? 'a referee' : type === 'players' ? 'a player' : 'a team'

  return (
    <div className={styles.wrap}>
      <div className={styles.topBar}>
        <div className={styles.tabs}>
          <button className={type === 'referees' ? styles.tabActive : styles.tab} onClick={() => setType('referees')}>Referees</button>
          <button className={type === 'players'  ? styles.tabActive : styles.tab} onClick={() => setType('players')}>Players</button>
          <button className={type === 'teams'    ? styles.tabActive : styles.tab} onClick={() => setType('teams')}>Teams</button>
        </div>
        <div className={styles.filtersRow}>
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
        <div className={styles.pickersRow}>
          <Picker
            list={filterList(list, type, searchA)}
            type={type}
            search={searchA}
            setSearch={setSearchA}
            selected={selectedA}
            onSelect={selectA}
          />
          <div className={styles.vs}>vs</div>
          <Picker
            list={filterList(list, type, searchB)}
            type={type}
            search={searchB}
            setSearch={setSearchB}
            selected={selectedB}
            onSelect={selectB}
          />
        </div>
      </div>

      <div className={styles.compareArea}>
        <div className={styles.side}>
          {dataA
            ? <EntityCard type={type} data={dataA} />
            : <div className={styles.empty}>Select {entityLabel} to compare</div>
          }
        </div>
        <div className={styles.divider} />
        <div className={styles.side}>
          {dataB
            ? <EntityCard type={type} data={dataB} />
            : <div className={styles.empty}>Select {entityLabel} to compare</div>
          }
        </div>
      </div>
    </div>
  )
}

function Picker({ list, type, search, setSearch, selected, onSelect }) {
  const [open, setOpen] = useState(false)
  const shown = list.slice(0, 12)

  return (
    <div className={styles.picker}>
      <div className={styles.pickerInput}>
        <input
          value={selected && !open ? getEntityName(type, selected) : search}
          placeholder={`Search ${type}…`}
          onFocus={() => { setOpen(true); setSearch('') }}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onChange={e => setSearch(e.target.value)}
        />
        {open && shown.length > 0 && (
          <div className={styles.dropdown}>
            {shown.map(item => (
              <div
                key={getEntityId(type, item)}
                className={styles.dropdownItem}
                onMouseDown={() => { onSelect(item); setOpen(false); setSearch('') }}
              >
                {type === 'players' && item.team_tricode
                  ? <>{getEntityName(type, item)} <span className={styles.dropdownTeam}>{item.team_tricode}</span></>
                  : getEntityName(type, item)
                }
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function EntityCard({ type, data }) {
  if (type === 'referees') {
    const { referee, top_players, foul_breakdown, period_breakdown, games_worked, fouls_per_game } = data
    const total = foul_breakdown.reduce((s, f) => s + f.count, 0)
    return (
      <div>
        <div className={styles.cardHeader}>
          <span className={styles.dotReferee} />
          <div>
            <h2>{referee.official_name}</h2>
            <p className={styles.totalFouls}>
              {total.toLocaleString()} fouls
              {games_worked != null && <span className={styles.cardMeta}> · {games_worked} games worked</span>}
              {fouls_per_game != null && <span className={styles.cardMeta}> · {fouls_per_game} fouls per game</span>}
            </p>
          </div>
        </div>
        <Section title="Foul breakdown"><FoulTable rows={foul_breakdown} /></Section>
        {period_breakdown?.length > 0 && (
          <Section title="By quarter"><PeriodTable rows={period_breakdown} /></Section>
        )}
        <Section title="Players called for the most fouls by this referee">
          <RelList items={top_players.slice(0, 3)} nameKey="fouler_player_name" sub="fouler_team_tricode" />
        </Section>
      </div>
    )
  }

  if (type === 'players') {
    const { player, top_referees, foul_breakdown, period_breakdown, games_played, fouls_per_game } = data
    const total = foul_breakdown.reduce((s, f) => s + f.count, 0)
    return (
      <div>
        <div className={styles.cardHeader}>
          <span className={styles.dotPlayer} />
          <div>
            <h2>{player.player_name}</h2>
            <p className={styles.totalFouls}>
              {total.toLocaleString()} fouls
              {player.team_tricode && <span className={styles.teamBadge}>{player.team_tricode}</span>}
              {games_played != null && <span className={styles.cardMeta}> · {games_played} games</span>}
              {fouls_per_game != null && <span className={styles.cardMeta}> · {fouls_per_game} fouls per game</span>}
            </p>
          </div>
        </div>
        <Section title="Foul breakdown"><FoulTable rows={foul_breakdown} /></Section>
        {period_breakdown?.length > 0 && (
          <Section title="By quarter"><PeriodTable rows={period_breakdown} /></Section>
        )}
        <Section title="Referees who called the most fouls on this player">
          <RelList items={top_referees.slice(0, 3)} nameKey="official_name" />
        </Section>
      </div>
    )
  }

  // teams
  const { team_tricode, top_referees, foul_breakdown, games_played, fouls_per_game } = data
  const total = foul_breakdown.reduce((s, f) => s + f.count, 0)
  return (
    <div>
      <div className={styles.cardHeader}>
        <span className={styles.dotPlayer} />
        <div>
          <h2>{TEAM_NAMES[team_tricode] ?? team_tricode}</h2>
          <p className={styles.totalFouls}>
            {total.toLocaleString()} fouls <span className={styles.teamBadge}>{team_tricode}</span>
            {games_played != null && <span className={styles.cardMeta}> · {games_played} games</span>}
            {fouls_per_game != null && <span className={styles.cardMeta}> · {fouls_per_game} fouls per game</span>}
          </p>
        </div>
      </div>
      <Section title="Foul breakdown"><FoulTable rows={foul_breakdown} /></Section>
      <Section title="Referees who called the most fouls on this team">
        <RelList items={top_referees.slice(0, 3)} nameKey="official_name" />
      </Section>
    </div>
  )
}

function FoulTable({ rows }) {
  const total = rows.reduce((s, f) => s + f.count, 0)
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Type</th>
          <th className={styles.num}>Count</th>
          <th className={styles.num}>%</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(f => (
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

function PeriodTable({ rows }) {
  const total = rows.reduce((s, p) => s + p.count, 0)
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Quarter</th>
          <th className={styles.num}>Count</th>
          <th className={styles.num}>%</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(p => (
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

function RelList({ items, nameKey, sub }) {
  if (!items?.length) return <p className={styles.muted}>No data</p>
  return (
    <div className={styles.relList}>
      {items.map((item, i) => (
        <div key={i} className={styles.relItem}>
          <span>{item[nameKey]}{sub && item[sub] && <span className={styles.muted}> · {item[sub]}</span>}</span>
          <span className={styles.relCount}>{item.total_fouls} fouls</span>
        </div>
      ))}
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
