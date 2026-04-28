import { Routes, Route, NavLink } from 'react-router-dom'
import GraphView from './views/GraphView'
import DashboardView from './views/DashboardView'
import CompareView from './views/CompareView'
import DetailsView from './views/DetailsView'
import styles from './App.module.css'

export default function App() {
  return (
    <div className={styles.shell}>
      <nav className={styles.nav}>
        <span className={styles.logo}>Referee Tracker</span>
        <div className={styles.links}>
          <NavLink to="/"          className={({ isActive }) => isActive ? styles.active : ''}>Graph</NavLink>
          <NavLink to="/dashboard" className={({ isActive }) => isActive ? styles.active : ''}>Dashboard</NavLink>
          <NavLink to="/compare"   className={({ isActive }) => isActive ? styles.active : ''}>Compare</NavLink>
          <NavLink to="/details"   className={({ isActive }) => isActive ? styles.active : ''}>Details</NavLink>
        </div>
      </nav>
      <main className={styles.main}>
        <Routes>
          <Route path="/"          element={<GraphView />} />
          <Route path="/dashboard" element={<DashboardView />} />
          <Route path="/compare"   element={<CompareView />} />
          <Route path="/details"   element={<DetailsView />} />
        </Routes>
      </main>
    </div>
  )
}
