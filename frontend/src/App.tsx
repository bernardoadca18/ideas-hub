import {
  BrowserRouter,
  Routes,
  Route,
  NavLink,
  useLocation,
} from "react-router-dom";
import { Lightbulb, FileText, Film, TrendingUp, Gamepad2 } from "lucide-react";
import Ideias from "./pages/Ideias";
import Trends from "./pages/Trends";
import Roteiros from "./pages/Roteiros";
import GameAnalysis from "./pages/GameAnalysis";
import { MediaStudioPage } from "./components/MediaStudioPage";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 5000 } },
});

const areas = [
  { path: "/ideias", label: "Ideias", icon: Lightbulb },
  { path: "/roteiros", label: "Roteiros", icon: FileText },
  { path: "/studio", label: "Studio de mídia", icon: Film },
  { path: "/trends", label: "Tendências", icon: TrendingUp },
  { path: "/game-analysis", label: "Análise de jogos", icon: Gamepad2 },
];
function StudioShell() {
  const { pathname } = useLocation();
  const current = areas.find((a) => a.path === pathname)?.label || "Ideias";
  return (
    <div className="app">
      <a className="skip-link" href="#main-content">
        Pular para o conteúdo
      </a>
      <aside className="studio-sidebar">
        <NavLink to="/ideias" className="studio-brand">
          <b>N</b>
          <span>
            NeoVids<small>ESTÚDIO EDITORIAL</small>
          </span>
        </NavLink>
        <nav className="nav" aria-label="Navegação principal">
          {areas.map(({ path, label, icon: Icon }) => (
            <NavLink
              key={path}
              to={path}
              className={({ isActive }) =>
                "nav-link" +
                (isActive || (path === "/ideias" && pathname === "/")
                  ? " active"
                  : "")
              }
            >
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <footer>Bolas Industries</footer>
      </aside>
      <div className="studio-body">
        <header className="studio-topbar">
          NeoVids <span>/</span> <strong>{current}</strong>
        </header>
        <main className="main" id="main-content" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<Ideias />} />
            <Route path="/ideias" element={<Ideias />} />
            <Route path="/trends" element={<Trends />} />
            <Route path="/roteiros" element={<Roteiros />} />
            <Route path="/game-analysis" element={<GameAnalysis />} />
            <Route path="/studio" element={<MediaStudioPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <StudioShell />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
