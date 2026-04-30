import { useEffect, useState } from 'react'
import { fetchStats } from '../api'
import styles from './DetailsView.module.css'

export default function DetailsView() {
  const [stats, setStats] = useState(null)

  useEffect(() => {
    fetchStats().then(setStats)
  }, [])

  return (
    <div className={styles.wrap}>
      <div className={styles.inner}>

        <section className={styles.section}>
          <h1 className={styles.pageTitle}>About the Data</h1>
          <p className={styles.lead}>
            This project collects every individual foul call made in NBA games and maps each one
            to the referee who called it, the player who committed it, and the game it occurred in.
            The goal is to surface patterns — which referees call the most fouls, which players get
            called on the most, and whether those patterns hold across seasons, game types, or
            specific foul categories.
          </p>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Data Source</h2>
          <div className={styles.card}>
            <div className={styles.cardRow}>
              <span className={styles.label}>Source</span>
              <span>NBA CDN — <code>cdn.nba.com</code></span>
            </div>
            <div className={styles.cardRow}>
              <span className={styles.label}>Files per game</span>
              <span>Play-by-play + Boxscore</span>
            </div>
            <div className={styles.cardRow}>
              <span className={styles.label}>Coverage</span>
              <span>2019–20 through 2025–26 (7 seasons, regular season + playoffs)</span>
            </div>
            <div className={styles.cardRow}>
              <span className={styles.label}>Update frequency</span>
              <span>Daily at 11am ET during the season — previous night's games are added automatically</span>
            </div>
            <div className={styles.cardRow}>
              <span className={styles.label}>Foul types tracked</span>
              <span>Shooting · Personal · Offensive · Loose Ball · Flagrant 1 · Flagrant 2 · Technical</span>
            </div>
          </div>
        </section>

        {stats && (
          <section className={styles.section}>
            <h2 className={styles.sectionTitle}>Database Snapshot</h2>
            <div className={styles.statGrid}>
              <Stat label="Foul events" value={stats.foul_events.toLocaleString()} />
              <Stat label="Games" value={stats.games.toLocaleString()} />
              <Stat label="Referees" value={stats.referees.toLocaleString()} />
              <Stat label="Players" value={stats.players.toLocaleString()} />
            </div>

            <h3 className={styles.subTitle}>By season</h3>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Season</th>
                  <th className={styles.num}>Total games</th>
                  <th className={styles.num}>Playoff games</th>
                  <th className={styles.num}>Regular season</th>
                </tr>
              </thead>
              <tbody>
                {stats.by_season.map(s => (
                  <tr key={s.season}>
                    <td>{s.season}</td>
                    <td className={styles.num}>{s.games.toLocaleString()}</td>
                    <td className={styles.num}>{s.playoff_games.toLocaleString()}</td>
                    <td className={styles.num}>{(s.games - s.playoff_games).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Limitations</h2>
          <p className={styles.lead}>
            Foul calls are three-sided. A player who commits many fouls could be there because they genuinely
            play aggressively, because certain referees have a pattern of calling fouls on them, or because
            the player they're guarding has a favorable whistle — drawing a lot of fouls from that referee.
            Similarly, a player who draws many fouls might be a skilled foul-drawer, or might just be guarded
            by players who foul a lot. High counts show patterns in the data; they don't explain the cause.
          </p>
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>What a Foul Event Looks Like</h2>
          <p className={styles.lead}>Each row in the database represents a single foul call and contains:</p>
          <table className={styles.table}>
            <thead><tr><th>Field</th><th>Example</th><th>Description</th></tr></thead>
            <tbody>
              {[
                ['game_id',            '0042400164',       'Unique NBA game identifier'],
                ['period',             '4',                'Quarter (1–4) or overtime (5+)'],
                ['clock',              'PT02M14.00S',      'Time remaining in the period'],
                ['foul_detail',        'shooting',         'Category of foul called'],
                ['official_name',      'Tyler Ford',       'Referee who made the call'],
                ['fouler_player_name', 'D. Brooks',        'Player called for the foul'],
                ['fouler_team_tricode','HOU',              'Team of the player fouled'],
                ['season',             '2024-25',          'NBA season'],
                ['playoff_round',      'First Round',      'Null for regular season games'],
              ].map(([field, example, desc]) => (
                <tr key={field}>
                  <td><code>{field}</code></td>
                  <td className={styles.muted}>{example}</td>
                  <td className={styles.muted}>{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

      </div>
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className={styles.statCard}>
      <div className={styles.statValue}>{value}</div>
      <div className={styles.statLabel}>{label}</div>
    </div>
  )
}
