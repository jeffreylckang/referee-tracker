import { useEffect, useRef, useState, useCallback } from 'react'
import ForceGraph3D from '3d-force-graph'
import { fetchGraph, fetchFilters, fetchReferee, fetchPlayer } from '../api'
import styles from './GraphView.module.css'

export default function GraphView() {
  const mountRef  = useRef(null)
  const graphRef  = useRef(null)
  const [filters,  setFilters]  = useState({ seasons: [], foul_types: [], teams: [] })
  const [season,   setSeason]   = useState('')
  const [foulType, setFoulType] = useState('')
  const [gameType, setGameType] = useState('')
  const [team,     setTeam]     = useState('')
  const [loading,  setLoading]  = useState(true)
  const [panel,    setPanel]    = useState(null)

  // Load filter options once
  useEffect(() => {
    fetchFilters().then(setFilters)
  }, [])

  // Build / rebuild graph when filters change
  const loadGraph = useCallback(async () => {
    setLoading(true)
    const data = await fetchGraph({ season, foul_detail: foulType, game_type: gameType, team, min_fouls: 3 })
    setLoading(false)

    const el = mountRef.current
    if (!el) return

    if (!graphRef.current) {
      graphRef.current = ForceGraph3D()(el)
        .backgroundColor('#0d1117')
        .nodeLabel(n => `${n.type === 'referee' ? '🟠' : '🔵'} ${n.name} (${n.foul_count} fouls)`)
        .nodeColor(n => n.type === 'referee' ? '#f97316' : '#38bdf8')
        .nodeVal(n => Math.sqrt(n.foul_count) * 0.8)
        .linkColor(() => 'rgba(255,255,255,0.08)')
        .linkWidth(l => Math.log(l.count + 1) * 0.4)
        .cooldownTicks(100)
        .d3AlphaDecay(0.04)
        .d3VelocityDecay(0.4)
        .onEngineStop(() => {
          if (graphRef.current) graphRef.current.cooldownTicks(0)
        })
        .onNodeClick(async node => {
          const id = node.id.slice(2)
          if (node.type === 'referee') {
            const data = await fetchReferee(id, { season: season || undefined, game_type: gameType || undefined })
            setPanel({ type: 'referee', data })
          } else {
            const data = await fetchPlayer(id, { season: season || undefined, game_type: gameType || undefined })
            setPanel({ type: 'player', data })
          }
        })

      // size to container immediately
      graphRef.current.width(el.clientWidth).height(el.clientHeight)
    }

    graphRef.current.graphData(data)
  }, [season, foulType, gameType, team])

  useEffect(() => {
    loadGraph()
  }, [loadGraph])

  // Resize handler
  useEffect(() => {
    const el = mountRef.current
    if (!el) return
    const obs = new ResizeObserver(() => {
      if (graphRef.current) {
        graphRef.current.width(el.clientWidth).height(el.clientHeight)
      }
    })
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  return (
    <div className={styles.wrap}>
      {/* Filter bar */}
      <div className={styles.filters}>
        <select value={season} onChange={e => setSeason(e.target.value)}>
          <option value="">All seasons</option>
          {filters.seasons.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        <select value={gameType} onChange={e => setGameType(e.target.value)}>
          <option value="">All game types</option>
          <option value="regular">Regular season</option>
          <option value="playoff">Playoffs</option>
        </select>

        <select value={foulType} onChange={e => setFoulType(e.target.value)}>
          <option value="">All foul types</option>
          {filters.foul_types.map(f => <option key={f} value={f}>{f}</option>)}
        </select>

        <select value={team} onChange={e => setTeam(e.target.value)}>
          <option value="">All teams</option>
          {filters.teams.map(t => <option key={t} value={t}>{t}</option>)}
        </select>

        {loading && <span className={styles.loading}>Loading…</span>}
      </div>

      {/* Legend */}
      <div className={styles.legend}>
        <span><span className={styles.dotReferee} /> Referee</span>
        <span><span className={styles.dotPlayer}  /> Player</span>
        <span className={styles.hint}>Click a node for details · Drag to explore</span>
      </div>

      {/* Graph canvas */}
      <div ref={mountRef} className={styles.canvas} />

      {/* Detail panel */}
      {panel && (
        <div className={styles.panel}>
          <button className={styles.close} onClick={() => setPanel(null)}>✕</button>
          {panel.type === 'referee' ? (
            <RefereePanel data={panel.data} />
          ) : (
            <PlayerPanel data={panel.data} />
          )}
        </div>
      )}
    </div>
  )
}

function RefereePanel({ data }) {
  const { referee, top_players, foul_breakdown } = data
  return (
    <>
      <div className={styles.panelHeader}>
        <span className={styles.dotReferee} />
        <h2>{referee.official_name}</h2>
      </div>
      <Section title="Foul breakdown">
        {foul_breakdown.map(f => (
          <Row key={f.foul_detail} label={f.foul_detail} value={f.count} />
        ))}
      </Section>
      <Section title="Top players fouled">
        {top_players.slice(0, 10).map(p => (
          <Row key={p.fouler_player_id} label={p.fouler_player_name} value={`${p.total_fouls} fouls`} />
        ))}
      </Section>
    </>
  )
}

function PlayerPanel({ data }) {
  const { player, top_referees, foul_breakdown } = data
  return (
    <>
      <div className={styles.panelHeader}>
        <span className={styles.dotPlayer} />
        <h2>{player.player_name}</h2>
        {player.team_tricode && <span className={styles.team}>{player.team_tricode}</span>}
      </div>
      <Section title="Foul breakdown">
        {foul_breakdown.map(f => (
          <Row key={f.foul_detail} label={f.foul_detail} value={f.count} />
        ))}
      </Section>
      <Section title="Top referees">
        {top_referees.slice(0, 10).map(r => (
          <Row key={r.official_id} label={r.official_name} value={`${r.total_fouls} fouls`} />
        ))}
      </Section>
    </>
  )
}

function Section({ title, children }) {
  return (
    <div className={styles.section}>
      <h3>{title}</h3>
      <div className={styles.rows}>{children}</div>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className={styles.row}>
      <span>{label}</span>
      <span className={styles.rowVal}>{value}</span>
    </div>
  )
}
