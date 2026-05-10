const BASE = import.meta.env.VITE_API_URL

export async function fetchStats() {
  const r = await fetch(`${BASE}/api/stats`)
  return r.json()
}

export async function fetchSummary({ season, game_type, foul_detail } = {}) {
  const params = new URLSearchParams()
  if (season)      params.set('season',      season)
  if (game_type)   params.set('game_type',   game_type)
  if (foul_detail) params.set('foul_detail', foul_detail)
  const r = await fetch(`${BASE}/api/summary?${params}`)
  return r.json()
}

export async function fetchFilters() {
  const r = await fetch(`${BASE}/api/filters`)
  return r.json()
}

export async function fetchGraph({ season, foul_detail, game_type, team, official_id, min_fouls = 3 } = {}) {
  const params = new URLSearchParams()
  if (season)      params.set('season',      season)
  if (foul_detail) params.set('foul_detail', foul_detail)
  if (game_type)   params.set('game_type',   game_type)
  if (team)        params.set('team',        team)
  if (official_id) params.set('official_id', official_id)
  params.set('min_fouls', min_fouls)
  const r = await fetch(`${BASE}/api/graph?${params}`)
  return r.json()
}

export async function fetchReferees({ season, game_type, foul_detail } = {}) {
  const params = new URLSearchParams()
  if (season)      params.set('season',      season)
  if (game_type)   params.set('game_type',   game_type)
  if (foul_detail) params.set('foul_detail', foul_detail)
  const r = await fetch(`${BASE}/api/referees?${params}`)
  return r.json()
}

export async function fetchPlayers({ season, game_type, foul_detail } = {}) {
  const params = new URLSearchParams()
  if (season)      params.set('season',      season)
  if (game_type)   params.set('game_type',   game_type)
  if (foul_detail) params.set('foul_detail', foul_detail)
  const r = await fetch(`${BASE}/api/players?${params}`)
  return r.json()
}

export async function fetchReferee(id, { season, game_type, foul_detail, include_badges, signal } = {}) {
  const params = new URLSearchParams()
  if (season)               params.set('season',        season)
  if (game_type)            params.set('game_type',     game_type)
  if (foul_detail)          params.set('foul_detail',   foul_detail)
  if (include_badges === false) params.set('include_badges', 'false')
  const r = await fetch(`${BASE}/api/referee/${id}?${params}`, { signal })
  return r.json()
}

export async function fetchTeams({ season, game_type, foul_detail } = {}) {
  const params = new URLSearchParams()
  if (season)      params.set('season',      season)
  if (game_type)   params.set('game_type',   game_type)
  if (foul_detail) params.set('foul_detail', foul_detail)
  const r = await fetch(`${BASE}/api/teams?${params}`)
  return r.json()
}

export async function fetchTeam(tricode, { season, game_type, foul_detail, include_badges, signal } = {}) {
  const params = new URLSearchParams()
  if (season)               params.set('season',        season)
  if (game_type)            params.set('game_type',     game_type)
  if (foul_detail)          params.set('foul_detail',   foul_detail)
  if (include_badges === false) params.set('include_badges', 'false')
  const r = await fetch(`${BASE}/api/team/${tricode}?${params}`, { signal })
  return r.json()
}

export async function fetchPlayer(id, { season, game_type, foul_detail, include_badges, signal } = {}) {
  const params = new URLSearchParams()
  if (season)               params.set('season',        season)
  if (game_type)            params.set('game_type',     game_type)
  if (foul_detail)          params.set('foul_detail',   foul_detail)
  if (include_badges === false) params.set('include_badges', 'false')
  const r = await fetch(`${BASE}/api/player/${id}?${params}`, { signal })
  return r.json()
}
