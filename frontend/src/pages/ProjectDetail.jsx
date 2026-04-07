import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import axios from 'axios'

function ProjectDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('clips') // 'clips' or 'collections'
  
  // 分页状态
  const [currentPage, setCurrentPage] = useState(1)
  const [itemsPerPage] = useState(8) // 每页显示 8 个切片

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
        <p><strong>创建时间:</strong> {new Date(project.created_at + 'Z').toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}</p>
        {project.completed_at && (
          <p><strong>完成时间:</strong> {new Date(project.completed_at + 'Z').toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}</p>
        )}
      </div>

      {/* 标签页切换 */}
      {project.clips?.length > 0 && (
        <div style={{ marginBottom: '20px' }}>
          <button 
            onClick={() => { setActiveTab('clips'); setCurrentPage(1); }}
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
            onClick={() => { setActiveTab('collections'); setCurrentPage(1); }}
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
        <div>
          {/* 分页信息 */}
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            marginBottom: '15px',
            padding: '10px',
            backgroundColor: '#f8f9fa',
            borderRadius: '4px'
          }}>
            <span style={{ fontSize: '14px', color: '#666' }}>
              显示 {((currentPage - 1) * itemsPerPage) + 1} - {Math.min(currentPage * itemsPerPage, project.clips.length)} / {project.clips.length} 个切片
            </span>
            <div style={{ display: 'flex', gap: '5px' }}>
              <button 
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                style={{ 
                  padding: '5px 12px', 
                  border: '1px solid #ddd', 
                  borderRadius: '4px',
                  backgroundColor: currentPage === 1 ? '#eee' : '#fff',
                  cursor: currentPage === 1 ? 'not-allowed' : 'pointer'
                }}
              >
                ← 上一页
              </button>
              <span style={{ padding: '5px 12px', fontSize: '14px' }}>
                第 {currentPage} / {Math.ceil(project.clips.length / itemsPerPage)} 页
              </span>
              <button 
                onClick={() => setCurrentPage(p => Math.min(Math.ceil(project.clips.length / itemsPerPage), p + 1))}
                disabled={currentPage >= Math.ceil(project.clips.length / itemsPerPage)}
                style={{ 
                  padding: '5px 12px', 
                  border: '1px solid #ddd', 
                  borderRadius: '4px',
                  backgroundColor: currentPage >= Math.ceil(project.clips.length / itemsPerPage) ? '#eee' : '#fff',
                  cursor: currentPage >= Math.ceil(project.clips.length / itemsPerPage) ? 'not-allowed' : 'pointer'
                }}
              >
                下一页 →
              </button>
            </div>
          </div>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '15px' }}>
            {project.clips
              .slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage)
              .map((clip, index) => (
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
                    src={`${API_BASE}/projects/${id}/files/${clip.video_path.split('/').map(encodeURIComponent).join('/')}`}
                  />
                </div>
              ))}
          </div>
          
          {/* 底部分页 */}
          <div style={{ 
            display: 'flex', 
            justifyContent: 'center', 
            marginTop: '20px',
            gap: '5px'
          }}>
            {Array.from({ length: Math.ceil(project.clips.length / itemsPerPage) }, (_, i) => i + 1).map(page => (
              <button
                key={page}
                onClick={() => setCurrentPage(page)}
                style={{
                  padding: '5px 12px',
                  border: '1px solid #007bff',
                  borderRadius: '4px',
                  backgroundColor: currentPage === page ? '#007bff' : '#fff',
                  color: currentPage === page ? '#fff' : '#007bff',
                  cursor: 'pointer'
                }}
              >
                {page}
              </button>
            ))}
          </div>
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
              {coll.video_path ? (
                <video 
                  controls 
                  style={{ width: '100%', marginTop: '10px', borderRadius: '4px' }}
                  src={`${API_BASE}/projects/${id}/files/${coll.video_path.split('/').map(encodeURIComponent).join('/')}`}
                  onError={(e) => {
                    e.target.style.display = 'none';
                    e.target.parentElement.innerHTML += `<p style="color: #ff4444; font-size: 12px; margin-top: 10px;">⚠️ 视频文件不存在（合集生成失败）</p>`;
                  }}
                />
              ) : (
                <p style={{ color: '#ff4444', fontSize: '14px', marginTop: '10px' }}>⚠️ 视频文件不存在（合集生成失败）</p>
              )}
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
