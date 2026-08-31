import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Ideias from './pages/Ideias';
import Trends from './pages/Trends';
import Roteiros from './pages/Roteiros';
import GameAnalysis from './pages/GameAnalysis';

export default function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <nav className="nav">
          <NavLink to="/ideias" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            Ideias
          </NavLink>
          <NavLink to="/trends" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            Trends
          </NavLink>
          <NavLink to="/roteiros" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            Roteiros
          </NavLink>
          <NavLink to="/game-analysis" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            Game Analysis
          </NavLink>
        </nav>
        <main className="main">
          <Routes>
            <Route path="/" element={<Ideias />} />
            <Route path="/ideias" element={<Ideias />} />
            <Route path="/trends" element={<Trends />} />
            <Route path="/roteiros" element={<Roteiros />} />
            <Route path="/game-analysis" element={<GameAnalysis />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
