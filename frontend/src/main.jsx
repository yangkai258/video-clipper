import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import App from './App'
import ProjectDetail from './pages/ProjectDetail'
import StyleManager from './pages/StyleManager'
import MixListPage from './pages/MixListPage'
import MixWizardPage from './pages/MixWizardPage'
import MixDetailPage from './pages/MixDetailPage'
// v2.2.5: 资源库独立路由
import LibraryPage from './pages/LibraryPage'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/project/:id" element={<App />} />
        <Route path="/styles" element={<App />} />
        {/* v2.2.4: 混剪独立路由 */}
        <Route path="/mix" element={<App />} />
        <Route path="/mix/new" element={<App />} />
        <Route path="/mix/:id" element={<App />} />
        {/* v2.2.5: 资源库路由 */}
        <Route path="/library" element={<App />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)