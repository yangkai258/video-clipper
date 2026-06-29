import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'

const API_BASE = '/api/v1'

// ponytail: 2s for processing, 5s for steady state - single timer swaps on status change
const POLL_MS = { processing: 2000, default: 5000 }

export function useProjectData(projectId) {
  const [project, setProject] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    if (!projectId) return
    try {
      const res = await axios.get(`${API_BASE}/projects/${projectId}`)
      setProject(res.data.project)
    } catch (e) {
      console.error('加载项目失败:', e)
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!project) return
    const intervalMs = POLL_MS[project.status] || POLL_MS.default
    const interval = setInterval(load, intervalMs)
    return () => clearInterval(interval)
  }, [project?.status, load])

  return { project, loading, reload: load, setProject }
}
