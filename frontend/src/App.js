import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import Ideias from './pages/Ideias';
import Trends from './pages/Trends';
import Roteiros from './pages/Roteiros';
export default function App() {
    return (_jsx(BrowserRouter, { children: _jsxs("div", { className: "app", children: [_jsxs("nav", { className: "nav", children: [_jsx(NavLink, { to: "/ideias", className: ({ isActive }) => isActive ? 'nav-link active' : 'nav-link', children: "Ideias" }), _jsx(NavLink, { to: "/trends", className: ({ isActive }) => isActive ? 'nav-link active' : 'nav-link', children: "Trends" }), _jsx(NavLink, { to: "/roteiros", className: ({ isActive }) => isActive ? 'nav-link active' : 'nav-link', children: "Roteiros" })] }), _jsx("main", { className: "main", children: _jsxs(Routes, { children: [_jsx(Route, { path: "/", element: _jsx(Ideias, {}) }), _jsx(Route, { path: "/ideias", element: _jsx(Ideias, {}) }), _jsx(Route, { path: "/trends", element: _jsx(Trends, {}) }), _jsx(Route, { path: "/roteiros", element: _jsx(Roteiros, {}) })] }) })] }) }));
}
