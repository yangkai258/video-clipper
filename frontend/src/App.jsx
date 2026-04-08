import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'

function App() {
  const [projects, setProjects] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const navigate = useNavigate()

  const API_BASE = '/api/v1'

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

  // 版本标识（用于区分正式版/测试版）
  const VERSION_LABEL = window.location.port === '3030' ? '🧪 测试版 v1.1-beta' : '✅ 正式版 v1.0'
  const VERSION_STYLE = window.location.port === '3030' ? { color: '#f59e0b' } : { color: '#10b981' }

  return (
    <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ ...VERSION_STYLE, marginBottom: '10px', fontWeight: 'bold' }}>{VERSION_LABEL}</div>
      <h1>🎬 Video Clipper - 智能视频切片</h1>
      
      {/* 上传区域 */}
      <div style={{ 
        border: '2px dashed #ccc', 
        padding: '40px', 
        textAlign: 'center',
        marginBottom: '20px',
        borderRadius: '8px'
      }}>
        <h3>上传视频</h3>
        <input 
          type="file" 
          accept="video/*" 
          onChange={handleUpload}
          disabled={uploading}
        />
        {uploading && (
          <div style={{ marginTop: '10px' }}>
            上传中：{uploadProgress}%
            <progress value={uploadProgress} max="100" style={{ width: '200px' }} />
          </div>
        )}
      </div>

      {/* 项目列表 */}
      <h2>项目列表 ({projects.length})</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '20px' }}>
        {projects.map(project => (
          <div 
            key={project.id} 
            style={{ 
              border: '1px solid #ddd', 
              padding: '15px', 
              borderRadius: '8px',
              backgroundColor: project.status === 'completed' ? '#f0fff0' : 
                               project.status === 'processing' ? '#fff8e1' : '#fff'
            }}
          >
            <h3>{project.name}</h3>
            <p><strong>状态:</strong> {
              project.status === 'completed' ? '✅ 完成' :
              project.status === 'processing' ? `⏳ ${project.current_step || '处理中'}` :
              project.status === 'failed' ? '❌ 失败' : '⏸️ 待处理'
            }</p>
            
            {project.status === 'processing' && (
              <div style={{ marginBottom: '10px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ fontSize: '12px', color: '#666' }}>进度</span>
                  <span style={{ fontSize: '12px', color: '#666' }}>{project.progress || 0}% - {project.estimated_remaining || '未知'}</span>
                </div>
                <progress value={project.progress || 0} max="100" style={{ width: '100%' }} />
              </div>
            )}
            
            <p><strong>切片:</strong> {project.clip_count} 个</p>
            <p><strong>合集:</strong> {project.collection_count} 个</p>
            <p><strong>创建时间:</strong> {new Date(project.created_at + 'Z').toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}</p>
            
            <div style={{ marginTop: '10px', display: 'flex', gap: '10px' }}>
              {project.status === 'pending' && (
                <button onClick={() => startProcessing(project.id)}>
                  ▶️ 开始处理
                </button>
              )}
              <button onClick={() => navigate(`/project/${project.id}`)}>
                📁 查看详情
              </button>
              <button 
                onClick={() => deleteProject(project.id, project.name)}
                style={{ backgroundColor: '#ff4444', color: 'white', border: 'none', padding: '5px 10px', borderRadius: '4px', cursor: 'pointer' }}
              >
                🗑️ 删除
              </button>
            </div>
          </div>
        ))}
      </div>

      {projects.length === 0 && (
        <p style={{ textAlign: 'center', color: '#999' }}>暂无项目，上传第一个视频开始吧！</p>
      )}
    </div>
  )
}

export default App
