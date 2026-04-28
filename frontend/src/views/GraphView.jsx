import { useEffect, useRef, useState, useCallback } from 'react'
import ForceGraph from 'force-graph'
import { fetchGraph, fetchFilters, fetchReferee, fetchPlayer } from '../api'
import styles from './GraphView.module.css'

export default function GraphView() {
  const mountRef      = useRef(null)
  const graphRef      = useRef(null)
  const dataRef       = useRef({ nodes: [], links: [] })
  const hlNodes       = useRef(new Set())   // highlighted node objects
  const hlLinks       = useRef(new Set())   // highlighted link objects
  const hoverNodeRef  = useRef(null)

  const [filters,  setFilters]  = useState({ seasons: [], foul_types: [], teams: [] })
  const [season,   setSeason]   = useState('2025-26')   // default: current season
  const [foulType, setFoulType] = useState('')
  const [gameType, setGameType] = useState('')
  const [team,     setTeam]     = useState('')
  const [loading,  setLoading]  = useState(true)
  const [panel,    setPanel]    = useState(null)

  // Load filter options; update season to actual most recent from DB
  useEffect(() => {
    fetchFilters().then(f => {
      setFilters(f)
      if (f.seasons.length > 0) {
        const latest = f.seasons[f.seasons.length - 1]
        setSeason(prev => prev === latest ? prev : latest)
      }
    })
  }, [])

  const loadGraph = useCallback(async () => {
    setLoading(true)
    const data = await fetchGraph({ season, foul_detail: foulType, game_type: gameType, team, min_fouls: 3 })
    setLoading(false)
    dataRef.current = data

    const el = mountRef.current
    if (!el) return

    if (!graphRef.current) {
      graphRef.current = ForceGraph()(el)
        .backgroundColor('#0d1117')
        // Tooltip on hover (always)
        .nodeLabel(n => `${n.name} (${n.foul_count} fouls)`)
        // Custom node rendering: diamond = referee, circle = player
        .nodeCanvasObject((node, ctx, globalScale) => {
          const r = 5
          const isHl = hlNodes.current.size === 0 || hlNodes.current.has(node)
          const isHovered = hoverNodeRef.current === node

          ctx.globalAlpha = isHl ? 1 : 0.12

          if (node.type === 'referee') {
            // Diamond
            ctx.beginPath()
            ctx.moveTo(node.x,         node.y - r * 1.4)
            ctx.lineTo(node.x + r * 1.4, node.y)
            ctx.lineTo(node.x,         node.y + r * 1.4)
            ctx.lineTo(node.x - r * 1.4, node.y)
            ctx.closePath()
            ctx.fillStyle = '#f97316'
            ctx.fill()
            if (isHl && hlNodes.current.size > 0) {
              ctx.strokeStyle = 'rgba(251,146,60,0.6)'
              ctx.lineWidth = 1
              ctx.stroke()
            }
          } else {
            // Circle
            ctx.beginPath()
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
            ctx.fillStyle = '#38bdf8'
            ctx.fill()
            if (isHl && hlNodes.current.size > 0) {
              ctx.strokeStyle = 'rgba(56,189,248,0.5)'
              ctx.lineWidth = 1
              ctx.stroke()
            }
          }

          // Label: show when hovered, connected to hovered node, or zoomed in
          const showLabel = isHovered || globalScale > 3 || (isHovered && isHl)
          if (showLabel) {
            const fontSize = Math.min(4, 14 / globalScale)
            ctx.font = `500 ${fontSize}px -apple-system, sans-serif`
            ctx.fillStyle = '#e6edf3'
            ctx.textAlign = 'center'
            ctx.textBaseline = 'top'
            ctx.globalAlpha = 1
            ctx.fillText(node.name, node.x, node.y + r * 1.6)
          }

          ctx.globalAlpha = 1
        })
        // Hit area (generous, matches visible shape)
        .nodePointerAreaPaint((node, color, ctx) => {
          const r = 8
          ctx.beginPath()
          if (node.type === 'referee') {
            ctx.moveTo(node.x,     node.y - r)
            ctx.lineTo(node.x + r, node.y)
            ctx.lineTo(node.x,     node.y + r)
            ctx.lineTo(node.x - r, node.y)
            ctx.closePath()
          } else {
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
          }
          ctx.fillStyle = color
          ctx.fill()
        })
        // Custom link rendering for highlight control
        .linkCanvasObjectMode(() => 'replace')
        .linkCanvasObject((link, ctx) => {
          const isHl = hlLinks.current.size === 0 || hlLinks.current.has(link)
          const src = link.source
          const tgt = link.target
          if (!src.x || !tgt.x) return
          ctx.beginPath()
          ctx.moveTo(src.x, src.y)
          ctx.lineTo(tgt.x, tgt.y)
          ctx.strokeStyle = isHl
            ? 'rgba(255,255,255,0.55)'
            : 'rgba(255,255,255,0.05)'
          ctx.lineWidth = isHl && hlLinks.current.size > 0 ? 1 : 0.5
          ctx.stroke()
        })
        // Hover: highlight connected nodes + links, dim everything else
        .onNodeHover(node => {
          hoverNodeRef.current = node
          hlNodes.current.clear()
          hlLinks.current.clear()
          if (node) {
            hlNodes.current.add(node)
            dataRef.current.links.forEach(link => {
              const s = link.source
              const t = link.target
              if (s === node || t === node) {
                hlLinks.current.add(link)
                hlNodes.current.add(s)
                hlNodes.current.add(t)
              }
            })
          }
        })
        // Click opens detail panel
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
        // Simulation: referees repel each other strongly → act as hubs
        .cooldownTicks(180)
        .d3AlphaDecay(0.02)
        .d3VelocityDecay(0.35)
        .onEngineStop(() => {
          if (graphRef.current) {
            graphRef.current.cooldownTicks(0)
            graphRef.current.zoom(3, 1000)
          }
        })

      graphRef.current.width(el.clientWidth).height(el.clientHeight)

      // Referee nodes repel each other strongly so they spread as hubs
      // Player nodes have light repulsion so they cluster near their referees
      graphRef.current.d3Force('charge').strength(n => n.type === 'referee' ? -350 : -40)
      // Short link distance keeps players close to their referee hubs
      graphRef.current.d3Force('link').distance(40).strength(0.6)
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
      if (graphRef.current) graphRef.current.width(el.clientWidth).height(el.clientHeight)
    })
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  return (
    <div className={styles.wrap}>
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

      <div className={styles.legend}>
        <span><span className={styles.dotReferee} /> Referee</span>
        <span><span className={styles.dotPlayer}  /> Player</span>
        <span className={styles.hint}>Hover a node to see connections · Click for details · Scroll to zoom</span>
      </div>

      <div ref={mountRef} className={styles.canvas} />

      {panel && (
        <div className={styles.panel}>
          <button className={styles.close} onClick={() => setPanel(null)}>✕</button>
          {panel.type === 'referee' ? <RefereePanel data={panel.data} /> : <PlayerPanel data={panel.data} />}
        </div>
      )}
    </div>
  )
}

function periodLabel(p) {
  if (p <= 4) return `Q${p}`
  return `OT${p - 4 > 1 ? p - 4 : ''}`
}

function RefereePanel({ data }) {
  const { referee, top_players, foul_breakdown, period_breakdown } = data
  const total = period_breakdown?.reduce((s, p) => s + p.count, 0) || 0
  return (
    <>
      <div className={styles.panelHeader}>
        <span className={styles.dotReferee} />
        <h2>{referee.official_name}</h2>
      </div>
      <Section title="By quarter">
        {period_breakdown?.map(p => (
          <Row key={p.period} label={periodLabel(p.period)}
            value={`${p.count}${total ? '  (' + ((p.count / total) * 100).toFixed(0) + '%)' : ''}`} />
        ))}
      </Section>
      <Section title="Foul breakdown">
        {foul_breakdown.map(f => <Row key={f.foul_detail} label={f.foul_detail} value={f.count} />)}
      </Section>
      <Section title="Players called for the most fouls">
        {top_players.slice(0, 10).map(p => (
          <Row key={p.fouler_player_id} label={p.fouler_player_name} value={`${p.total_fouls} fouls`} />
        ))}
      </Section>
    </>
  )
}

function PlayerPanel({ data }) {
  const { player, top_referees, foul_breakdown, period_breakdown } = data
  const total = period_breakdown?.reduce((s, p) => s + p.count, 0) || 0
  return (
    <>
      <div className={styles.panelHeader}>
        <span className={styles.dotPlayer} />
        <h2>{player.player_name}</h2>
        {player.team_tricode && <span className={styles.team}>{player.team_tricode}</span>}
      </div>
      <Section title="By quarter">
        {period_breakdown?.map(p => (
          <Row key={p.period} label={periodLabel(p.period)}
            value={`${p.count}${total ? '  (' + ((p.count / total) * 100).toFixed(0) + '%)' : ''}`} />
        ))}
      </Section>
      <Section title="Foul breakdown">
        {foul_breakdown.map(f => <Row key={f.foul_detail} label={f.foul_detail} value={f.count} />)}
      </Section>
      <Section title="Referees who called the most fouls">
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
