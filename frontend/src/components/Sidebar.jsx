import { useLocation, useNavigate } from 'react-router-dom'
import Icon from '../Icon'

// ponytail: Sidebar 5 nav buttons + brand + user chip
// 传 5 个 handler 让 App 决定状态怎么变 (避免循环依赖)
// v2.2.4: 加"混剪项目"入口
export default function Sidebar({
  showTrash,
  showWatchFolders,
  onProjects,
  onTrash,
  onStyles,
  onWatchFolders,
  onMix,
}) {
  const navigate = useNavigate()
  const location = useLocation()

  const isProjectsActive = (location.pathname === '/' || location.pathname.startsWith('/project/')) && !showTrash && !showWatchFolders
  const isMixActive = location.pathname.startsWith('/mix') && !showTrash && !showWatchFolders
  const isTrashActive = showTrash
  const isStylesActive = location.pathname === '/styles' && !showTrash && !showWatchFolders
  const isWatchActive = showWatchFolders

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-mark">VC</div>
        <div className="sidebar-brand-name">视频切片工具</div>
      </div>

      <button
        className={`nav-item ${isProjectsActive ? 'active' : ''}`}
        onClick={onProjects}
      >
        <span className="nav-item-icon"><Icon name="scissors" /></span>
        切片项目
      </button>
      {/* v2.2.4: 混剪项目入口 (跟切片独立) */}
      <button
        className={`nav-item ${isMixActive ? 'active' : ''}`}
        onClick={onMix}
      >
        <span className="nav-item-icon"><Icon name="layers" /></span>
        混剪项目
      </button>
      <button
        className={`nav-item ${isTrashActive ? 'active' : ''}`}
        onClick={onTrash}
      >
        <span className="nav-item-icon"><Icon name="trash" /></span>
        回收站
      </button>
      <button
        className={`nav-item ${isStylesActive ? 'active' : ''}`}
        onClick={onStyles}
      >
        <span className="nav-item-icon"><Icon name="edit" /></span>
        风格管理
      </button>
      <button
        className={`nav-item ${isWatchActive ? 'active' : ''}`}
        onClick={onWatchFolders}
      >
        <span className="nav-item-icon"><Icon name="folder" /></span>
        监控文件夹
      </button>

      <div className="sidebar-bottom">
        <div className="user-chip">
          <div className="user-avatar">U</div>
          <div>
            <div className="user-name">工作台</div>
            <div className="user-status">● 在线</div>
          </div>
        </div>
      </div>
    </aside>
  )
}