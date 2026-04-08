import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import './index.css'

function App() {
  const [projects, setProjects] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const navigate = useNavigate()

  const API_BASE = '/api/v1'

  // 版本标识
  const isBeta = window.location.port === '3030'
  const VERSION_LABEL = isBeta ? '🧪 测试版 v1.1-beta' : '✅ 正式版 v1.0'
  const VERSION_CLASS = isBeta ? 'version-beta' : 'version-release'

  // 加载项目列表
  const loadProjects = async () => {
    try {
      const res = await axios.get(`${API_BASE}/projects/`)
      setProjects(res.data.projects)
    } catch (error) {
      console.error('加载项目失败:', error)
    }
  }

  useEffect(() => {
    loadProjects()
  }, [])

  // 处理文件上传
  const handleUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return

    const name = prompt('请输入项目名称:', file.name.split('.')[0])
    if (!name) return

    setUploading(true)
    setUploadProgress(0)

    const formData = new FormData()
    formData.append('name', name)
    formData.append('video', file)

    try {
      const res = await axios.post(`${API_BASE}/projects/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          setUploadProgress(percent)
        },
      })

      const projectId = res.data.project_id
      alert(`项目创建成功！\n项目 ID: ${projectId}\n\n即将自动开始处理...`)
      
      // 自动开始处理
      try {
        const processRes = await axios.post(`${API_BASE}/projects/${projectId}/process`)
        alert(`✅ 处理已开始！\n任务 ID: ${processRes.data.task_id}`)
      } catch (error) {
        alert(`⚠️ 项目已创建，但处理启动失败：${error.response?.data?.detail || error.message}\n\n请稍后在项目列表中手动点击"开始处理"`)
      }
      
      setUploading(false)
      loadProjects()
    } catch (error) {
      alert(`上传失败：${error.response?.data?.detail || error.message}`)
      setUploading(false)
    }
  }

  // 开始处理
  const startProcessing = async (projectId) => {
    if (!confirm('确定要开始处理这个项目吗？')) return

    try {
      const res = await axios.post(`${API_BASE}/projects/${projectId}/process`)
      alert(`处理已开始！\n任务 ID: ${res.data.task_id}`)
      loadProjects()
    } catch (error) {
      alert(`处理失败：${error.response?.data?.detail || error.message}`)
    }
  }

  // 删除项目
  const deleteProject = async (projectId, projectName) => {
    if (!confirm(`确定要删除项目 "${projectName}" 吗？此操作不可恢复。`)) return

    try {
      await axios.delete(`${API_BASE}/projects/${projectId}`)
      alert('项目已删除')
      loadProjects()
    } catch (error) {
      alert(`删除失败：${error.message}`)
    }
  }

  // 获取状态标签样式
  const getStatusClass = (status) => {
    switch (status) {
      case 'completed': return 'status-completed'
      case 'processing': return 'status-processing'
      case 'failed': return 'status-error'
      default: return 'status-pending'
    }
  }

  // 获取状态文案
  const getStatusText = (status, currentStep) => {
    switch (status) {
      case 'completed': return '✅ 已完成'
      case 'processing': return `⏳ ${currentStep || '处理中'}`
      case 'failed': return '❌ 失败'
      default: return '⏸️ 待处理'
    }
  }

  return (
    <div className="container fade-in">
      {/* 版本标识 */}
      <div className={`version-badge ${VERSION_CLASS}`}>{VERSION_LABEL}</div>
      
      {/* 页面标题 */}
      <h1>🎬 Video Clipper - 智能视频切片</h1>
      
      {/* 上传区域 */}
      <div className="upload-zone">
        <h3>上传视频</h3>
        <p style={{ color: 'var(--text-secondary)', marginTop: '8px' }}>
          支持 MP4、MOV、AVI、MKV 等格式
        </p>
        <input 
          type="file" 
          accept="video/*" 
          onChange={handleUpload}
          disabled={uploading}
          style={{ marginTop: '16px' }}
        />
        {uploading && (
          <div className="progress-container">
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${uploadProgress}%` }}></div>
            </div>
            <div className="progress-text">上传中：{uploadProgress}%</div>
          </div>
        )}
      </div>

      {/* 项目列表 */}
      <h2>项目列表 ({projects.length})</h2>
      
      {projects.length > 0 ? (
        <div className="project-grid">
          {projects.map(project => (
            <div key={project.id} className="card fade-in">
              {/* 卡片头部 */}
              <div className="project-card-header">
                <h3 className="project-title">{project.name}</h3>
                <span className={`status-badge ${getStatusClass(project.status)}`}>
                  {getStatusText(project.status, project.current_step)}
                </span>
              </div>
              
              {/* 进度条 */}
              {project.status === 'processing' && (
                <div className="progress-container">
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${project.progress || 0}%` }}></div>
                  </div>
                  <div className="progress-text">
                    {project.progress || 0}% · {project.estimated_remaining || '剩余时间未知'}
                  </div>
                </div>
              )}
              
              {/* 项目信息 */}
              <div className="project-info">
                <span>📹 {project.clip_count || 0} 个切片</span>
                <span>📁 {project.collection_count || 0} 个合集</span>
              </div>
              
              <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                创建时间：{new Date(project.created_at + 'Z').toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}
              </div>
              
              {/* 操作按钮 */}
              <div className="project-actions">
                {project.status === 'pending' && (
                  <button className="btn btn-primary btn-sm" onClick={() => startProcessing(project.id)}>
                    ▶️ 开始处理
                  </button>
                )}
                <button className="btn btn-secondary btn-sm" onClick={() => navigate(`/project/${project.id}`)}>
                  📁 查看详情
                </button>
                <button className="btn btn-danger btn-sm" onClick={() => deleteProject(project.id, project.name)}>
                  🗑️ 删除
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="card" style={{ textAlign: 'center', padding: '48px' }}>
          <p style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-lg)' }}>
            暂无项目，上传第一个视频开始吧！
          </p>
        </div>
      )}
    </div>
  )
}

export default App
