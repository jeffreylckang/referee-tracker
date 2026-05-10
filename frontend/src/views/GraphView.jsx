import { useEffect, useRef, useState, useCallback } from 'react'
import ForceGraph from 'force-graph'
import { fetchGraph, fetchFilters, fetchReferees, fetchReferee, fetchPlayer } from '../api'
import styles from './GraphView.module.css'

const FOUL_LABELS = {
  shooting:   'Shooting',
  personal:   'Personal',
  offensive:  'Offensive',
  loose_ball: 'Loose Ball',
  flagrant_1: 'Flagrant 1',
  flagrant_2: 'Flagrant 2',
  technical:  'Technical',
}

export default function GraphView() {
  const mountRef      = useRef(null)
  const graphRef      = useRef(null)
  const dataRef       = useRef({ nodes: [], links: [] })
  const hlNodes       = useRef(new Set())
  const hlLinks       = useRef(new Set())
  const panelAbortRef = useRef(null)

  const [filters,          setFilters]          = useState({ seasons: [], foul_types: [], teams: [] })
  const [refereeList,      setRefereeList]      = useState([])
  const [season,           setSeason]           = useState('')
  const [foulType,         setFoulType]         = useState('')
  const [gameType,         setGameType]         = useState('')
  const [team,             setTeam]             = useState('')
  const [selectedReferee,  setSelectedReferee]  = useState(null)  // official_id
  const [loading,          setLoading]          = useState(true)
  const [panel,            setPanel]            = useState(null)
  const selectedNodeRef = useRef(null)

  // Load filter options and referee list; default to top referee
  useEffect(() => {
    fetchFilters().then(f => setFilters(f))
    fetchReferees().then(refs => {
      setRefereeList(refs)
      if (refs.length > 0) setSelectedReferee(refs[0].official_id)
    })
  }, [])

  const loadGraph = useCallback(async () => {
    if (selectedReferee === null) return  // wait until default referee is set
    // Clear highlight state when graph reloads
    selectedNodeRef.current = null
    hlNodes.current.clear()
    hlLinks.current.clear()
    setPanel(null)
    setLoading(true)
    const minFouls = selectedReferee ? 10 : 3
    const data = await fetchGraph({ season, foul_detail: foulType, game_type: gameType, team, official_id: selectedReferee, min_fouls: minFouls })
    setLoading(false)
    dataRef.current = data

    const el = mountRef.current
    if (!el) return

    if (!graphRef.current) {
      graphRef.current = ForceGraph()(el)
        .backgroundColor('#07091a')
        .nodeLabel(n => `${n.name} (${n.foul_count} fouls)`)
        .nodeCanvasObject((node, ctx, globalScale) => {
          const r = 5
          const isHl = hlNodes.current.size === 0 || hlNodes.current.has(node)

          ctx.globalAlpha = isHl ? 1 : 0.12

          if (node.type === 'referee') {
            ctx.beginPath()
            ctx.moveTo(node.x,           node.y - r * 1.4)
            ctx.lineTo(node.x + r * 1.4, node.y)
            ctx.lineTo(node.x,           node.y + r * 1.4)
            ctx.lineTo(node.x - r * 1.4, node.y)
            ctx.closePath()
            ctx.fillStyle = '#f59e0b'
            ctx.fill()
            if (isHl && hlNodes.current.size > 0) {
              ctx.strokeStyle = 'rgba(245,158,11,0.6)'
              ctx.lineWidth = 1
              ctx.stroke()
            }
          } else {
            ctx.beginPath()
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
            ctx.fillStyle = '#93c5fd'
            ctx.fill()
            if (isHl && hlNodes.current.size > 0) {
              ctx.strokeStyle = 'rgba(147,197,253,0.5)'
              ctx.lineWidth = 1
              ctx.stroke()
            }
          }

          const isSelected = selectedNodeRef.current === node
          const showLabel = isSelected || (hlNodes.current.size > 0 && hlNodes.current.has(node)) || globalScale > 3
          if (showLabel) {
            const fontSize = Math.min(4, 14 / globalScale)
            ctx.font = `500 ${fontSize}px -apple-system, sans-serif`
            ctx.fillStyle = '#dce8fa'
            ctx.textAlign = 'center'
            ctx.textBaseline = 'top'
            ctx.globalAlpha = 1
            ctx.fillText(node.name, node.x, node.y + r * 1.6)
          }

          ctx.globalAlpha = 1
        })
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
        .linkCanvasObjectMode(() => 'replace')
        .linkCanvasObject((link, ctx) => {
          const src = link.source
          const tgt = link.target
          if (src.x == null || tgt.x == null) return

          const hlActive = hlLinks.current.size > 0
          const isHl = !hlActive || hlLinks.current.has(link)

          ctx.beginPath()
          ctx.moveTo(src.x, src.y)
          ctx.lineTo(tgt.x, tgt.y)

          if (!isHl) {
            ctx.strokeStyle = 'rgba(255,255,255,0.04)'
            ctx.lineWidth = 0.3
            ctx.stroke()
            return
          }

          const maxCount = hlActive
            ? Math.max(...[...hlLinks.current].map(l => l.count || 1))
            : (link.count || 1)
          const t = Math.min((link.count || 1) / maxCount, 1)
          const alpha = hlActive ? 0.2 + t * 0.65 : 0.15
          const lineWidth = hlActive ? 0.5 + t * 3.5 : 0.4

          ctx.strokeStyle = `rgba(255,255,255,${alpha})`
          ctx.lineWidth = lineWidth
          ctx.stroke()

          if (hlActive && link.count > 1) {
            const mx = (src.x + tgt.x) / 2
            const my = (src.y + tgt.y) / 2
            ctx.font = '500 3px sans-serif'
            ctx.fillStyle = `rgba(255,255,255,${alpha})`
            ctx.textAlign = 'center'
            ctx.textBaseline = 'middle'
            ctx.fillText(String(link.count), mx, my)
          }
        })
        .onEngineStop(() => {
          if (graphRef.current) graphRef.current.zoomToFit(800, 30)
        })
        .cooldownTicks(180)
        .d3AlphaDecay(0.02)
        .d3VelocityDecay(0.35)

      graphRef.current.width(el.clientWidth).height(el.clientHeight)
    }

    // Re-register click handler every load so it closes over current season/gameType
    graphRef.current.onNodeClick(node => {
      if (selectedNodeRef.current === node) {
        selectedNodeRef.current = null
        hlNodes.current.clear()
        hlLinks.current.clear()
        setPanel(null)
        graphRef.current.refresh()
        return
      }
      selectedNodeRef.current = node
      hlNodes.current.clear()
      hlLinks.current.clear()
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
      graphRef.current.refresh()

      // Abort any previous in-flight panel requests, then show loading immediately
      if (panelAbortRef.current) panelAbortRef.current.abort()
      const ctrl = new AbortController()
      panelAbortRef.current = ctrl
      const signal = ctrl.signal

      const clickedNode = node
      const id = node.id.slice(2)
      setPanel({ type: node.type, data: null })
      const opts = { season: season || undefined, game_type: gameType || undefined }
      if (node.type === 'referee') {
        fetchReferee(id, { ...opts, include_badges: false, signal })
          .then(data => { if (selectedNodeRef.current === clickedNode) setPanel({ type: 'referee', data }) })
          .catch(() => {})
        fetchReferee(id, { ...opts, signal })
          .then(data => { if (selectedNodeRef.current === clickedNode) setPanel({ type: 'referee', data }) })
          .catch(() => {})
      } else {
        fetchPlayer(id, { ...opts, include_badges: false, signal })
          .then(data => { if (selectedNodeRef.current === clickedNode) setPanel({ type: 'player', data }) })
          .catch(() => {})
        fetchPlayer(id, { ...opts, signal })
          .then(data => { if (selectedNodeRef.current === clickedNode) setPanel({ type: 'player', data }) })
          .catch(() => {})
      }
    })

    // Compute fixed radial positions — single referee at center, players by foul count
    const W = el.clientWidth || 800
    const H = el.clientHeight || 600
    const refNodes    = data.nodes.filter(n => n.type === 'referee')
    const playerNodes = data.nodes.filter(n => n.type === 'player')
      .sort((a, b) => b.foul_count - a.foul_count)

    if (refNodes.length === 1) {
      // Referee fixed at graph origin (0,0); force-graph centers view on mean node position
      refNodes[0].fx = 0; refNodes[0].fy = 0
      refNodes[0].x  = 0; refNodes[0].y  = 0

      const minR = 40
      const maxR = Math.min(W, H) * 0.44
      const n_   = playerNodes.length

      // Deterministic pseudo-random angle per player — organic look, consistent on reload
      function hashAngle(id) {
        let h = 0
        const s = String(id)
        for (let i = 0; i < s.length; i++) h = Math.imul(31, h) + s.charCodeAt(i) | 0
        return (Math.abs(h) % 10000) / 10000 * 2 * Math.PI
      }

      playerNodes.forEach((n, i) => {
        const angle  = hashAngle(n.id)                // random direction, consistent per player
        const t      = n_ > 1 ? i / (n_ - 1) : 0    // rank 0 (most fouls) → minR, last → maxR
        const radius = minR + t * (maxR - minR)
        const px = radius * Math.cos(angle)
        const py = radius * Math.sin(angle)
        n.fx = px; n.fy = py
        n.x  = px; n.y  = py
      })

      graphRef.current.d3Force('charge').strength(0)
      graphRef.current.d3Force('link').strength(0)
      graphRef.current.cooldownTicks(0)
    } else {
      // Multiple referees: light physics, moderate repulsion
      graphRef.current.d3Force('charge').strength(n => n.type === 'referee' ? -200 : -25)
      graphRef.current.d3Force('link').distance(link => 15 + 50 / Math.sqrt(link.count || 1)).strength(0.6)
      graphRef.current.cooldownTicks(180)
    }

    graphRef.current.graphData(data)
  }, [season, foulType, gameType, team, selectedReferee])

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
        <select value={selectedReferee ?? ''} onChange={e => setSelectedReferee(e.target.value ? Number(e.target.value) : null)}>
          <option value="">All referees</option>
          {refereeList.map(r => <option key={r.official_id} value={r.official_id}>{r.official_name}</option>)}
        </select>

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
        <span className={styles.hint}>Click a node to highlight connections · Click again to deselect · Scroll to zoom</span>
      </div>

      <div ref={mountRef} className={styles.canvas} />

      {panel && (
        <div className={styles.panel}>
          <button className={styles.close} onClick={() => setPanel(null)}>✕</button>
          {!panel.data
            ? <p className={styles.loading} style={{ padding: '8px 0' }}>Loading…</p>
            : panel.type === 'referee' ? <RefereePanel data={panel.data} /> : <PlayerPanel data={panel.data} />
          }
        </div>
      )}
    </div>
  )
}

function periodLabel(p) {
  if (p <= 4) return `Q${p}`
  return `OT${p - 4 > 1 ? p - 4 : ''}`
}

function BadgeCards({ badges }) {
  if (!badges?.length) return null
  return (
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
  )
}

function RefereePanel({ data }) {
  const { referee, top_players, top_players_drawn, foul_breakdown, period_breakdown, crew_chief_games, badges } = data
  const total = period_breakdown?.reduce((s, p) => s + p.count, 0) || 0
  return (
    <>
      <div className={styles.panelHeader}>
        <span className={styles.dotReferee} />
        <h2>{referee.official_name}</h2>
      </div>
      {(crew_chief_games != null || badges?.length > 0) && (
        <Section title="Overview">
          {crew_chief_games != null && <Row label="Games as crew chief" value={crew_chief_games} />}
          <BadgeCards badges={badges} />
        </Section>
      )}
      <Section title="By quarter">
        {period_breakdown?.map(p => (
          <Row key={p.period} label={periodLabel(p.period)}
            value={`${p.count}${total ? '  (' + ((p.count / total) * 100).toFixed(0) + '%)' : ''}`} />
        ))}
      </Section>
      <Section title="Foul breakdown">
        {foul_breakdown.map(f => <Row key={f.foul_detail} label={FOUL_LABELS[f.foul_detail] ?? f.foul_detail} value={f.count} />)}
      </Section>
      <Section title="Players called for the most fouls by this referee">
        {top_players.slice(0, 10).map(p => (
          <Row key={p.fouler_player_id} label={p.fouler_player_name} value={`${p.total_fouls} fouls`} />
        ))}
      </Section>
      {top_players_drawn?.length > 0 && (
        <Section title="Players who draw the most fouls called by this referee">
          {top_players_drawn.slice(0, 10).map(p => (
            <Row key={p.player_id} label={p.player_name} value={`${p.total_fouls_drawn} drawn`} />
          ))}
        </Section>
      )}
    </>
  )
}

function PlayerPanel({ data }) {
  const { player, top_referees, top_referees_drawn, foul_breakdown, period_breakdown, badges } = data
  const total = period_breakdown?.reduce((s, p) => s + p.count, 0) || 0
  return (
    <>
      <div className={styles.panelHeader}>
        <span className={styles.dotPlayer} />
        <h2>{player.player_name}</h2>
        {player.team_tricode && <span className={styles.team}>{player.team_tricode}</span>}
      </div>
      {badges?.length > 0 && (
        <Section title="Overview">
          <BadgeCards badges={badges} />
        </Section>
      )}
      <Section title="By quarter">
        {period_breakdown?.map(p => (
          <Row key={p.period} label={periodLabel(p.period)}
            value={`${p.count}${total ? '  (' + ((p.count / total) * 100).toFixed(0) + '%)' : ''}`} />
        ))}
      </Section>
      <Section title="Foul breakdown">
        {foul_breakdown.map(f => <Row key={f.foul_detail} label={FOUL_LABELS[f.foul_detail] ?? f.foul_detail} value={f.count} />)}
      </Section>
      <Section title="Referees who called the most fouls on this player">
        {top_referees.slice(0, 10).map(r => (
          <Row key={r.official_id} label={r.official_name} value={`${r.total_fouls} fouls`} />
        ))}
      </Section>
      {top_referees_drawn?.length > 0 && (
        <Section title="Referees who call the most fouls in favor of this player">
          {top_referees_drawn.slice(0, 10).map(r => (
            <Row key={r.official_id} label={r.official_name} value={`${r.total_fouls_drawn} drawn`} />
          ))}
        </Section>
      )}
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
