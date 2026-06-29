import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'

const API_BASE = '/api/v1'

// ponytail: projects + trash + tabs + search 一个 hook 抽完
// 5s 轮询 projects, 仅在首页加载时才走 trash
export function useProjects() {
  const [projects, setProjects] = useState([])
  const [trashProjects, setTrashProjects] = useState([])
  const [showTrash, setShowTrash] = useState(false)
  const [activeTab, setActiveTab] = useState('all')
  const [search, setSearch] = useState('')

  const loadProjects = useCallback(async () => {
    try {
      const res = await axios.get(`${API_BASE}/projects/`)
      setProjects(res.data.projects)
    } catch (e) {
      console.error('加载项目失败:', e)
    }
  }, [])

  const loadTrash = useCallback(async () => {
    try {
      const res = await axios.get(`${API_BASE}/projects/?include_deleted=true`)
      setTrashProjects((res.data.projects || []).filter(p => p.deleted_at))
    } catch (e) {
      console.error('加载回收站失败:', e)
    }
  }, [])

  useEffect(() => { loadProjects() }, [loadProjects])
  useEffect(() => {
    if (showTrash) loadTrash()
  }, [showTrash, loadTrash])
  useEffect(() => {
    const id = setInterval(loadProjects, 5000)
    return () => clearInterval(id)
  }, [loadProjects])

  const deleteProject = useCallback(async (id, name, permanent = false) => {
    const msg = permanent
      ? `确认永久删除「${name}」？此操作不可恢复。`
      : `确认删除「${name}」？将移动到回收站，30 天内可恢复。`
    if (!confirm(msg)) return
    try {
      await axios.delete(`${API_BASE}/projects/${id}${permanent ? '?permanent=true' : ''}`)
      loadProjects()
    } catch (e) {
      const detail = e.response?.data?.detail || e.message
      if (e.response?.status === 409) {
        if (confirm(`${detail}

是否强制永久删除（会撤销 celery task）？`)) {
          return deleteProject(id, name, true)
        }
      } else {
        alert(`删除失败：${detail}`)
      }
    }
  }, [loadProjects])

  const restoreProject = useCallback(async (id) => {
    try {
      await axios.post(`${API_BASE}/projects/${id}/restore`)
      loadProjects()
    } catch (e) { alert(`恢复失败：${e.response?.data?.detail || e.message}`) }
  }, [loadProjects])

  const purgeTrash = useCallback(async () => {
    if (!confirm('永久删除 30 天前的回收站项目？此操作不可恢复。')) return
    try {
      const res = await axios.post(`${API_BASE}/projects/trash/cleanup?older_than_days=30`)
      alert(`已清理 ${res.data.cleaned_count} 个项目`)
      loadProjects()
    } catch (e) { alert(`清理失败：${e.message}`) }
  }, [loadProjects])

  const purgeAllTrash = useCallback(async () => {
    if (!confirm(`永久删除回收站里全部 ${trashProjects.length} 个项目？此操作不可恢复！`)) return
    try {
      const res = await axios.post(`${API_BASE}/projects/trash/purge-all`)
      alert(`已清理 ${res.data.cleaned_count} 个项目`)
      loadTrash()
    } catch (e) { alert(`清理失败：${e.message}`) }
  }, [loadTrash, trashProjects.length])

  // 派生: 按 tab + 搜索过滤
  const filteredProjects = projects.filter(p => {
    if (activeTab === 'all') return true
    if (activeTab === 'processing') return p.status === 'processing'
    if (activeTab === 'completed') return p.status === 'completed'
    if (activeTab === 'failed') return p.status === 'failed'
    if (activeTab === 'pending') return p.status === 'pending'
    return true
  }).filter(p => !search || p.name.toLowerCase().includes(search.toLowerCase()))

  const counts = {
    all: projects.length,
    processing: projects.filter(p => p.status === 'processing').length,
    completed: projects.filter(p => p.status === 'completed').length,
    failed: projects.filter(p => p.status === 'failed').length,
    pending: projects.filter(p => p.status === 'pending').length,
  }

  return {
    projects, setProjects,
    trashProjects, setTrashProjects,
    showTrash, setShowTrash,
    activeTab, setActiveTab,
    search, setSearch,
    filteredProjects,
    counts,
    loadProjects, loadTrash,
    deleteProject, restoreProject, purgeTrash, purgeAllTrash,
  }
}
