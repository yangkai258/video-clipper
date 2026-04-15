import { useState, useEffect } from 'react'
import axios from 'axios'

const API_BASE = '/api/v1'

function Admin() {
  const [systemInfo, setSystemInfo] = useState(null)
  const [workerStatus, setWorkerStatus] = useState(null)
  const [databaseStats, setDatabaseStats] = useState(null)
  const [loading, setLoading] = useState(true)

  // 加载系统状态
  const loadSystemStatus = async () => {
    try {
      const res = await axios.get(`${API_BASE}/admin/system`)
      setSystemInfo(res.data)
    } catch (error) {
      console.error('加载系统信息失败:', error)
    }
  }

  // 加载 Worker 状态
  const loadWorkerStatus = async () => {
    try {
      const res = await axios.get(`${API_BASE}/admin/worker`)
      setWorkerStatus(res.data)
    } catch (error) {
      console.error('加载 Worker 状态失败:', error)
    }
  }

  // 加载数据库统计
  const loadDatabaseStats = async () => {
    try {
      const res = await axios.get(`${API_BASE}/admin/database`)
      setDatabaseStats(res.data)
    } catch (error) {
      console.error('加载数据库统计失败:', error)
    }
  }

  useEffect(() => {
    const loadAll = async () => {
      await Promise.all([loadSystemInfo(), loadWorkerStatus(), loadDatabaseStats()])
      setLoading(false)
    }
    loadAll()
  }, [])

  // 刷新状态
  const handleRefresh = () => {
    setLoading(true)
    Promise.all([loadSystemInfo(), loadWorkerStatus(), loadDatabaseStats()]).then(() => {
      setLoading(false)
    })
  }

  if (loading) {
    return (
      <div className="container fade-in">
        <div className="card" style={{ textAlign: 'center', padding: '48px' }}>
          <p>加载中...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="container fade-in">
      {/* 页面标题 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h1>⚙️ 系统管理后台</h1>
        <button className="btn btn-secondary" onClick={handleRefresh}>
          🔄 刷新状态
        </button>
      </div>

      {/* 系统信息卡片 */}
      <div className="project-grid">
        {/* 系统信息 */}
        <div className="card">
          <h2>💻 系统信息</h2>
          <div style={{ marginTop: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-color)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>应用版本</span>
              <span>{systemInfo?.version || '-'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-color)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>运行状态</span>
              <span style={{ color: systemInfo?.status === 'running' ? 'var(--color-success)' : 'var(--color-error)' }}>
                {systemInfo?.status === 'running' ? '✅ 运行中' : '❌ 异常'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-color)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>启动时间</span>
              <span>{systemInfo?.uptime || '-'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Python 版本</span>
              <span>{systemInfo?.python_version || '-'}</span>
            </div>
          </div>
        </div>

        {/* Worker 状态 */}
        <div className="card">
          <h2>👷 Worker 状态</h2>
          <div style={{ marginTop: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-color)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Worker 状态</span>
              <span style={{ color: workerStatus?.running ? 'var(--color-success)' : 'var(--color-error)' }}>
                {workerStatus?.running ? '✅ 运行中' : '❌ 未运行'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-color)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>进程数</span>
              <span>{workerStatus?.workers || 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-color)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>活跃任务</span>
              <span>{workerStatus?.active_tasks || 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-color)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>已完成任务</span>
              <span>{workerStatus?.completed_tasks || 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
              <span style={{ color: 'var(--text-secondary)' }}>失败任务</span>
              <span style={{ color: workerStatus?.failed_tasks > 0 ? 'var(--color-error)' : 'var(--text-primary)' }}>
                {workerStatus?.failed_tasks || 0}
              </span>
            </div>
          </div>
        </div>

        {/* 数据库统计 */}
        <div className="card">
          <h2>🗄️ 数据库统计</h2>
          <div style={{ marginTop: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-color)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>项目总数</span>
              <span>{databaseStats?.projects || 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-color)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>切片总数</span>
              <span>{databaseStats?.clips || 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-color)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>合集总数</span>
              <span>{databaseStats?.collections || 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
              <span style={{ color: 'var(--text-secondary)' }}>数据库大小</span>
              <span>{databaseStats?.db_size || '-'}</span>
            </div>
          </div>
        </div>

        {/* Redis 状态 */}
        <div className="card">
          <h2>📦 Redis 状态</h2>
          <div style={{ marginTop: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-color)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>连接状态</span>
              <span style={{ color: databaseStats?.redis_connected ? 'var(--color-success)' : 'var(--color-error)' }}>
                {databaseStats?.redis_connected ? '✅ 已连接' : '❌ 未连接'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border-color)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>队列任务数</span>
              <span>{databaseStats?.queue_size || 0}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
              <span style={{ color: 'var(--text-secondary)' }}>内存使用</span>
              <span>{databaseStats?.redis_memory || '-'}</span>
            </div>
          </div>
        </div>
      </div>

      {/* 任务列表 */}
      <h2 style={{ marginTop: '32px' }}>📋 最近任务</h2>
      <div className="card">
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'left', borderBottom: '2px solid var(--border-color)' }}>
              <th style={{ padding: '12px 8px' }}>任务 ID</th>
              <th style={{ padding: '12px 8px' }}>类型</th>
              <th style={{ padding: '12px 8px' }}>状态</th>
              <th style={{ padding: '12px 8px' }}>进度</th>
              <th style={{ padding: '12px 8px' }}>开始时间</th>
              <th style={{ padding: '12px 8px' }}>耗时</th>
            </tr>
          </thead>
          <tbody>
            {databaseStats?.recent_tasks?.length > 0 ? (
              databaseStats.recent_tasks.map(task => (
                <tr key={task.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '12px 8px', fontFamily: 'monospace', fontSize: 'var(--text-sm)' }}>
                    {task.id.slice(0, 8)}...
                  </td>
                  <td style={{ padding: '12px 8px' }}>{task.task_type}</td>
                  <td style={{ padding: '12px 8px' }}>
                    <span className={`status-badge status-${task.status === 'completed' ? 'completed' : task.status === 'processing' ? 'processing' : 'error'}`}>
                      {task.status}
                    </span>
                  </td>
                  <td style={{ padding: '12px 8px' }}>{task.progress}%</td>
                  <td style={{ padding: '12px 8px', fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                    {task.started_at ? new Date(task.started_at + 'Z').toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '-'}
                  </td>
                  <td style={{ padding: '12px 8px', fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                    {task.duration || '-'}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="6" style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                  暂无任务记录
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default Admin
