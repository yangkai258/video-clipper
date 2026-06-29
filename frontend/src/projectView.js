export const API_BASE = '/api/v1'

export const statusLabel = {
  pending: '待处理',
  processing: '处理中',
  completed: '已完成',
  failed: '失败',
  deleted: '已删除',
}

export function formatTime(seconds) {
  if (!seconds) return '00:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export function formatTC(seconds) {
  if (!seconds) return '00:00'
  const m = Math.floor(seconds / 60)
  const sec = Math.floor(seconds % 60)
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

export function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z')
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

// v2.1.26: 按宽高判断视频 orientation
export function getOrientation(width, height) {
  if (!width || !height) return 'landscape'
  const ratio = width / height
  if (ratio < 0.83) return 'portrait'
  if (ratio >= 2.0) return 'cinemascope'
  if (ratio > 1.2) return 'landscape'
  return 'square'
}

export const orientationLabel = {
  portrait: '竖屏',
  landscape: '横屏',
  cinemascope: '宽银幕',
  square: '方形',
}

export function friendlyError(taskError) {
  if (!taskError) return { title: '处理失败', hint: '请查看日志或重新处理' }
  const err = String(taskError).toLowerCase()
  if (err.includes('ffmpeg') || err.includes('invalid data')) {
    return { title: '视频格式不支持', hint: 'ffmpeg 解析失败，请确认视频文件完整且格式标准' }
  }
  if (err.includes('memory') || err.includes('out of memory')) {
    return { title: '内存不足', hint: '视频可能过大，建议分段或降低分辨率' }
  }
  if (err.includes('timeout')) {
    return { title: '处理超时', hint: '请尝试较小的视频或重新处理' }
  }
  if (err.includes('whisper')) {
    return { title: '语音识别失败', hint: 'Whisper 加载或转录失败，请检查模型' }
  }
  return { title: '处理失败', hint: '请查看原始错误或重试' }
}

export function formatDuration(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds || 0))
  const hh = Math.floor(s / 3600)
  const mm = Math.floor((s % 3600) / 60)
  const ss = s % 60
  const pad = (n) => String(n).padStart(2, '0')
  if (hh > 0) return `${hh}:${pad(mm)}:${pad(ss)}`
  return `${pad(mm)}:${pad(ss)}`
}
