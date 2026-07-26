import React from 'react'  // eslint-disable-line no-unused-vars
import ReactDOM from 'react-dom/client'
import {Route } from 'react-router-dom'  // eslint-disable-line no-unused-vars
import App from './App'  // eslint-disable-line no-unused-vars
import ProjectDetail from './pages/ProjectDetail'  // eslint-disable-line no-unused-vars
import StyleManager from './pages/StyleManager'  // eslint-disable-line no-unused-vars
import MixListPage from './pages/MixListPage'  // eslint-disable-line no-unused-vars
import MixWizardPage from './pages/MixWizardPage'  // eslint-disable-line no-unused-vars
import MixDetailPage from './pages/MixDetailPage'  // eslint-disable-line no-unused-vars
import MixBatchListPage from './pages/MixBatchListPage'  // eslint-disable-line no-unused-vars
import MixBatchWizardPage from './pages/MixBatchWizardPage'  // eslint-disable-line no-unused-vars
import MixBatchDetailPage from './pages/MixBatchDetailPage'  // eslint-disable-line no-unused-vars
import LibraryPage from './pages/LibraryPage'  // eslint-disable-line no-unused-vars
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
        {/* v2.2.6: 批量混剪路由 */}
        <Route path="/mix/batch" element={<App />} />
        <Route path="/mix/batch/new" element={<App />} />
        <Route path="/mix/batch/:id" element={<App />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)