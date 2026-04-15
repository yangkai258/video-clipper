import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import './index.css'

function App() {
  const [projects, setProjects] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [showStrategyModal, setShowStrategyModal] = useState(false)
  const [pendingProject, setPendingProject] = useState(null)
  const [presets, setPresets] = useState([])
  const [customStyles, setCustomStyles] = useState([])
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

  // 加载预设策略和自定义风格
  const loadStrategies = async () => {
    try {
      const [presetsRes, stylesRes] = await Promise.all([
        axios.get(`${API_BASE}/strategies/presets`),
        axios.get(`${API_BASE}/styles`)
      ])
      setPresets(presetsRes.data.strategies)
      setCustomStyles(stylesRes.data)
    } catch (error) {
      console.error('加载策略失败:', error)
    }
  }

  useEffect(() => {
    loadProjects()
    loadStrategies()
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
      setPendingProject({ id: projectId, name })
      setShowStrategyModal(true)  // 上传成功后显示策略选择
      
      setUploading(false)
      loadProjects()
    } catch (error) {
      alert(`上传失败：${error.response?.data?.detail || error.message}`)
      setUploading(false)
    }
  }

  // 选择策略并开始处理
  const selectStrategy = async (strategy) => {
    if (!pendingProject) return

    setShowStrategyModal(false)
    
    // 如果是自定义风格，先更新项目配置
    if (strategy.id.startsWith('style_')) {
      try {
        await axios.put(`${API_BASE}/projects/${pendingProject.id}/config`, {
          style_id: strategy.id,
          strategy_name: strategy.name,
          target_duration: strategy.target_duration,
          max_clips: strategy.max_clips,
          content_types: strategy.content_types,
          rules: strategy.rules,
          content_guidelines: strategy.content_guidelines,
          keep_rules: strategy.keep_rules,
          remove_rules: strategy.remove_rules,
          style_positioning: strategy.style_positioning
        })
      } catch (error) {
        console.error('更新配置失败:', error)
      }
    }

    // 开始处理
    try {
      const processRes = await axios.post(`${API_BASE}/projects/${pendingProject.id}/process`)
      alert(`✅ 处理已开始！\n策略：${strategy.name}\n任务 ID: ${processRes.data.task_id}`)
    } catch (error) {
      alert(`⚠️ 处理启动失败：${error.response?.data?.detail || error.message}`)
    }
    
    setPendingProject(null)
  }

  // 开始处理（项目列表）
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>🎬 Video Clipper - 智能视频切片</h1>
        <button className="btn btn-secondary" onClick={() => navigate('/styles')} style={{ fontSize: 'var(--text-sm)', padding: '8px 16px' }}>
          ✂️ 风格管理
        </button>
      </div>
      
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

      {/* 策略选择弹窗 */}
      {showStrategyModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          overflow: 'auto'
        }}>
          <div className="card" style={{
            maxWidth: '1000px',
            width: '90%',
            maxHeight: '90vh',
            overflow: 'auto',
            margin: '20px'
          }}>
            <h2 style={{ marginBottom: '8px' }}>📦 选择切片策略</h2>
            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginBottom: '24px' }}>
              选择一个适合你内容的切片方式，处理开始后将根据此策略自动生成切片
            </p>

            {/* 预设策略 */}
            <h3 style={{ marginBottom: '16px' }}>🎯 预设策略</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '32px' }}>
              {presets.map(preset => (
                <button
                  key={preset.id}
                  onClick={() => selectStrategy(preset)}
                  style={{
                    textAlign: 'left',
                    padding: '16px',
                    border: '1px solid var(--border-color)',
                    borderRadius: '8px',
                    backgroundColor: 'var(--bg-primary)',
                    cursor: 'pointer',
                    transition: 'all 0.2s'
                  }}
                  onMouseEnter={(e) => {
                    e.target.style.borderColor = 'var(--color-primary)'
                    e.target.style.transform = 'translateY(-2px)'
                  }}
                  onMouseLeave={(e) => {
                    e.target.style.borderColor = 'var(--border-color)'
                    e.target.style.transform = 'translateY(0)'
                  }}
                >
                  <div style={{ fontSize: '28px', marginBottom: '8px' }}>{preset.name.split(' ')[0]}</div>
                  <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>{preset.name.split(' ').slice(1).join(' ')}</div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                    {preset.description}
                  </div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
                    ⏱️ {preset.target_duration}秒/切片 · 📹 最多{preset.max_clips}个
                  </div>
                </button>
              ))}
            </div>

            {/* 自定义风格 */}
            {customStyles.length > 0 && (
              <>
                <h3 style={{ marginBottom: '16px' }}>📋 我的风格 ({customStyles.length})</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
                  {customStyles.map(style => (
                    <button
                      key={style.id}
                      onClick={() => selectStrategy(style)}
                      style={{
                        textAlign: 'left',
                        padding: '16px',
                        border: '1px solid var(--border-color)',
                        borderRadius: '8px',
                        backgroundColor: 'var(--bg-primary)',
                        cursor: 'pointer',
                        transition: 'all 0.2s'
                      }}
                      onMouseEnter={(e) => {
                        e.target.style.borderColor = 'var(--color-primary)'
                        e.target.style.transform = 'translateY(-2px)'
                      }}
                      onMouseLeave={(e) => {
                        e.target.style.borderColor = 'var(--border-color)'
                        e.target.style.transform = 'translateY(0)'
                      }}
                    >
                      <div style={{ fontWeight: 'bold', marginBottom: '8px', fontSize: 'var(--text-lg)' }}>
                        {style.name}
                      </div>
                      {style.description && (
                        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                          {style.description}
                        </div>
                      )}
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', marginBottom: '8px' }}>
                        ⏱️ {style.target_duration}秒/切片 · 📹 最多{style.max_clips}个
                      </div>
                      {style.content_guidelines && (
                        <div style={{ 
                          fontSize: 'var(--text-xs)', 
                          color: 'var(--text-secondary)', 
                          padding: '6px', 
                          backgroundColor: 'rgba(59, 130, 246, 0.05)', 
                          borderRadius: '4px',
                          marginTop: '8px'
                        }}>
                          📌 {style.content_guidelines.substring(0, 50)}{style.content_guidelines.length > 50 ? '...' : ''}
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              </>
            )}

            {/* 取消按钮 */}
            <div style={{ marginTop: '24px', textAlign: 'center' }}>
              <button 
                className="btn btn-secondary"
                onClick={() => {
                  setShowStrategyModal(false)
                  setPendingProject(null)
                }}
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
