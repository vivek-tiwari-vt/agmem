import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Timeline from './pages/Timeline'
import Graph from './pages/Graph'
import Agents from './pages/Agents'
import './App.css'

function App() {
    return (
        <BrowserRouter>
            <div className="app">
                <nav className="sidebar">
                    <div className="logo">
                        <h1>agmem</h1>
                        <span>Memory VCS</span>
                    </div>
                    <ul className="nav-links">
                        <li><NavLink to="/">Dashboard</NavLink></li>
                        <li><NavLink to="/timeline">Timeline</NavLink></li>
                        <li><NavLink to="/graph">Graph</NavLink></li>
                        <li><NavLink to="/agents">Agents</NavLink></li>
                    </ul>
                </nav>
                <main className="content">
                    <Routes>
                        <Route path="/" element={<Dashboard />} />
                        <Route path="/timeline" element={<Timeline />} />
                        <Route path="/graph" element={<Graph />} />
                        <Route path="/agents" element={<Agents />} />
                    </Routes>
                </main>
            </div>
        </BrowserRouter>
    )
}

export default App
