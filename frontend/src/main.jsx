import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import App from './App'
import ProjectDetail from './pages/ProjectDetail'
import StyleManager from './pages/StyleManager'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/project/:id" element={<ProjectDetail />} />
        <Route path="/styles" element={<StyleManager />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)
