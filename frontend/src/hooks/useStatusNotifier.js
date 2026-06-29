import { useEffect, useRef } from 'react'

function notify(title, body) {
  if (!('Notification' in window)) return
  if (Notification.permission === 'granted') new Notification(title, { body })
}

export function useStatusNotifier(project) {
  const notifiedRef = useRef(new Set())
  const status = project?.status

  useEffect(() => {
    if (!status || !project) return
    const prev = notifiedRef.current.get(project.id)
    if (prev === 'processing' && status === 'completed' && !notifiedRef.current.has(project.id + ':done')) {
      notifiedRef.current.add(project.id + ':done')
      notify('切片完成', `「${project.name}」处理完成`)
    }
    if (prev === 'processing' && status === 'failed' && !notifiedRef.current.has(project.id + ':fail')) {
      notifiedRef.current.add(project.id + ':fail')
      notify('切片失败', `「${project.name}」处理失败`)
    }
    notifiedRef.current.set(project.id, status)
  }, [status, project?.id, project?.name])
}
