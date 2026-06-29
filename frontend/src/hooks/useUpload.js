import { useState, useRef, useCallback } from 'react'
import { ChunkedUploader } from '../ChunkedUploader'

// ponytail: 简单文件名清洗 + 扩展名抽取
function filenameSafe(s) {
  return s.replace(/[\\/:*?"<>|]/g, '_').slice(0, 80) || 'untitled'
}
function extOf(name) {
  const i = name.lastIndexOf('.')
  return i > 0 ? name.slice(i) : ''
}

// ponytail: 上传相关的 4 个 state + uploaderRef 全部封在 hook 里
// onDone 回调让 App 决定下一步 (弹策略选择 modal)
export function useUpload({ onDone }) {
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState({ received: 0, total: 0, speed: 0 })
  const [uploadState, setUploadState] = useState('idle')  // idle | uploading | pausing | paused | resuming | done | error
  const [uploadError, setUploadError] = useState('')
  const uploaderRef = useRef(null)

  const handleUpload = useCallback(async (e) => {
    const file = e.target.files[0]
    if (!file) return
    // 清空 input, 允许下次选同一文件触发 change
    e.target.value = ''
    const name = prompt('项目名称：', file.name.replace(/\.[^/.]+$/, ''))
    if (!name) return
    setUploading(true)
    setUploadError('')
    setUploadProgress({ received: 0, total: file.size, speed: 0 })
    setUploadState('uploading')

    const uploader = new ChunkedUploader({
      file: new File([file], filenameSafe(name) + extOf(file.name), { type: file.type }),
      onProgress: (p) => setUploadProgress(p),
      onState: (s, extra) => {
        setUploadState(s)
        if (s === 'error') setUploadError(extra?.error || '未知错误')
      },
      onDone: (data) => {
        setUploading(false)
        setUploadState('done')
        if (onDone) onDone({ projectId: data.project_id, name })
      },
      onError: (err) => {
        setUploadState('error')
        setUploadError(err.message)
      },
    })
    uploaderRef.current = uploader
    uploader.start()
  }, [onDone])

  const handlePause = useCallback(() => {
    if (uploaderRef.current && uploadState === 'uploading') {
      uploaderRef.current.pause()
      setUploadState('paused')
    }
  }, [uploadState])

  const handleResume = useCallback(() => {
    if (uploaderRef.current && uploadState === 'paused') {
      setUploadState('resuming')
      uploaderRef.current.resume()
    }
  }, [uploadState])

  const handleCancel = useCallback(() => {
    if (!uploaderRef.current) return
    if (!confirm('确定取消上传吗？已传的分片会丢失。')) return
    uploaderRef.current.cancel()
    setUploading(false)
    setUploadState('idle')
    setUploadProgress({ received: 0, total: 0, speed: 0 })
  }, [])

  return {
    uploading, uploadProgress, uploadState, uploadError,
    handleUpload, handlePause, handleResume, handleCancel,
  }
}
