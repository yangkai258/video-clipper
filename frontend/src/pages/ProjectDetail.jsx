import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import axios from 'axios'

function ProjectDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('clips') // 'clips' or 'collections'

  const API_BASE = '/api/v1'

  useEffect(() => {
    loadProject()
  }, [id])

  const loadProject = async () => {
    try {
      const res = await axios.get(`${API_BASE}/projects/${id}`)
      setProject(res.data.project)
    } catch (error) {
      console.error('加载项目失败:', error)
      alert('加载项目失败：' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div style={{ padding: '20px' }}>加载中...</div>
  }

  if (!project) {
    return <div style={{ padding: '20px' }}>项目不存在</div>
  }

  return (
    <div style={{ padding: '20px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* 返回按钮 */}
      <button onClick={() => navigate('/')} style={{ marginBottom: '20px' }}>
        ← 返回列表
      </button>

      {/* 项目信息 */}
      <div style={{ 
        backgroundColor: project.status === 'completed' ? '#f0fff0' : 
                         project.status === 'processing' ? '#fff8e1' : '#fff',
        padding: '20px', 
        borderRadius: '8px',
        marginBottom: '20px',
        border: '1px solid #ddd'
      }}>
        <h1>{project.name}</h1>
        <p><strong>状态:</strong> {
          project.status === 'completed' ? '✅ 完成' :
          project.status === 'processing' ? '⏳ 处理中' :
          project.status === 'failed' ? '❌ 失败' : '⏸️ 待处理'
        }</p>
        <p><strong>视频时长:</strong> {project.video_duration ? `${Math.round(project.video_duration)}秒` : '未知'}</p>
        <p><strong>视频大小:</strong> {(project.video_size / 1024 / 1024).toFixed(1)} MB</p>
        <p><strong>切片数量:</strong> {project.clips?.length || 0} 个</p>
        <p><strong>合集数量:</strong> {project.collections?.length || 0} 个</p>
        <p><strong>创建时间:</strong> {new Date(project.created_at).toLocaleString('zh-CN')}</p>
        {project.completed_at && (
          <p><strong>完成时间:</strong> {new Date(project.completed_at).toLocaleString('zh-CN')}</p>
        )}
      </div>

      {/* 标签页切换 */}
      {project.clips?.length > 0 && (
        <div style={{ marginBottom: '20px' }}>
          <button 
            onClick={() => setActiveTab('clips')}
            style={{ 
              padding: '10px 20px', 
              marginRight: '10px',
              backgroundColor: activeTab === 'clips' ? '#007bff' : '#fff',
              color: activeTab === 'clips' ? '#fff' : '#333',
              border: '1px solid #007bff',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            🎬 切片视频 ({project.clips.length})
          </button>
          <button 
            onClick={() => setActiveTab('collections')}
            style={{ 
              padding: '10px 20px',
              backgroundColor: activeTab === 'collections' ? '#007bff' : '#fff',
              color: activeTab === 'collections' ? '#fff' : '#333',
              border: '1px solid #007bff',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            📦 合集视频 ({project.collections?.length || 0})
          </button>
        </div>
      )}

      {/* 切片列表 */}
      {activeTab === 'clips' && project.clips?.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '15px' }}>
          {project.clips.map((clip, index) => (
            <div 
              key={clip.id || index}
              style={{ 
                border: '1px solid #ddd', 
                padding: '15px', 
                borderRadius: '8px',
                backgroundColor: '#fff'
              }}
            >
              <h4 style={{ margin: '0 0 10px 0', fontSize: '14px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {clip.title}
              </h4>
              <p style={{ margin: '5px 0', fontSize: '12px', color: '#666' }}>
                ⏱️ {formatTime(clip.start_time)} - {formatTime(clip.end_time)} ({clip.duration.toFixed(1)}秒)
              </p>
              <p style={{ margin: '5px 0', fontSize: '12px', color: '#666' }}>
                📊 评分：{clip.score}
              </p>
              <video 
                controls 
                style={{ width: '100%', marginTop: '10px', borderRadius: '4px' }}
                src={`${API_BASE}/projects/${id}/files/${encodeURIComponent(clip.video_path)}`}
              />
            </div>
          ))}
        </div>
      )}

      {/* 合集列表 */}
      {activeTab === 'collections' && project.collections?.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '20px' }}>
          {project.collections.map((coll, index) => (
            <div 
              key={coll.id || index}
              style={{ 
                border: '1px solid #ddd', 
                padding: '15px', 
                borderRadius: '8px',
                backgroundColor: '#fff'
              }}
            >
              <h3 style={{ margin: '0 0 10px 0' }}>{coll.title}</h3>
              <p style={{ margin: '5px 0', fontSize: '14px', color: '#666' }}>
                📦 包含 {coll.clip_count} 个切片
              </p>
              <video 
                controls 
                style={{ width: '100%', marginTop: '10px', borderRadius: '4px' }}
                src={`${API_BASE}/projects/${id}/files/${encodeURIComponent(coll.video_path)}`}
              />
            </div>
          ))}
        </div>
      )}

      {/* 空状态 */}
      {project.clips?.length === 0 && project.collections?.length === 0 && (
        <div style={{ textAlign: 'center', color: '#999', padding: '40px' }}>
          <p>暂无视频数据</p>
          {project.status === 'pending' && (
            <p>点击"开始处理"生成切片视频</p>
          )}
          {project.status === 'processing' && (
            <p>处理中，请稍候...</p>
          )}
        </div>
      )}
    </div>
  )
}

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

export default ProjectDetail
