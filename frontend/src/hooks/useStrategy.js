import { useState, useCallback } from 'react'
import axios from 'axios'

const API_BASE = '/api/v1'

// ponytail: pendingProject 改成由 App 持有 (因为它从 upload onDone 注入)
// 本 hook 只管: showStrategyModal, presets, customStyles, withSubtitle, outputFormat
// 以及 loadStrategies / selectStrategy(传入 pendingProject) / startProcessing
export function useStrategy({ onAfterProcess }) {
  const [showStrategyModal, setShowStrategyModal] = useState(false)
  const [presets, setPresets] = useState([])
  const [customStyles, setCustomStyles] = useState([])
  const [withSubtitle, setWithSubtitle] = useState(true)
  const [outputFormat, setOutputFormat] = useState('original')
  // v2.2.1: 保留 raw 视频供后续重切 (rerun API 用), 默认 false 省 disk
  const [keepRaw, setKeepRaw] = useState(false)

  const loadStrategies = useCallback(async () => {
    try {
      const [p, s] = await Promise.all([
        axios.get(`${API_BASE}/strategies/presets`),
        axios.get(`${API_BASE}/styles`),
      ])
      setPresets(p.data.strategies)
      setCustomStyles(s.data)
    } catch (e) { console.error(e) }
  }, [])

  const openStrategyModal = useCallback((project) => {
    setShowStrategyModal(true)
    return project
  }, [])

  const closeStrategyModal = useCallback(() => {
    setShowStrategyModal(false)
  }, [])

  // ponytail: pendingProject 由调用方传入 (与 hook 内部的 modal state 分离)
  const selectStrategy = useCallback(async (strategy, pendingProject) => {
    if (!pendingProject) return
    try {
      await axios.put(`${API_BASE}/projects/${pendingProject.id}/config`, {
        target_duration: strategy.target_duration,
        max_clips: strategy.max_clips,
        with_subtitle: withSubtitle,
        output_format: outputFormat,
        processing_mode: strategy.processing_mode || 'standard',
        style_id: strategy.id,
        style_name: strategy.name,
        style_positioning: strategy.style_positioning,
        subtitle_style: strategy.subtitle_config || null,
        keep_raw: keepRaw,  // v2.2.1: 保留 raw 供重切
      })
    } catch (e) { console.error('配置失败:', e) }
    try {
      await axios.post(`${API_BASE}/projects/${pendingProject.id}/process`)
      if (onAfterProcess) onAfterProcess()
    } catch (e) {
      alert(`处理失败：${e.response?.data?.detail || e.message}`)
    }
    closeStrategyModal()
  }, [withSubtitle, outputFormat, keepRaw, onAfterProcess, closeStrategyModal])

  // 直接处理已存在项目 (不通过 strategy modal)
  const startProcessing = useCallback(async (id) => {
    try {
      await axios.post(`${API_BASE}/projects/${id}/process`)
      if (onAfterProcess) onAfterProcess()
    } catch (e) {
      alert(`处理失败：${e.response?.data?.detail || e.message}`)
    }
  }, [onAfterProcess])

  return {
    showStrategyModal, setShowStrategyModal,
    presets, customStyles,
    withSubtitle, setWithSubtitle,
    outputFormat, setOutputFormat,
    keepRaw, setKeepRaw,  // v2.2.1
    loadStrategies,
    openStrategyModal, closeStrategyModal,
    selectStrategy, startProcessing,
  }
}
