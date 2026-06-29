import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

// ponytail: 'clips' 不写进 URL,避免污染默认状态
const DEFAULT_TAB = 'clips'

// ponytail: setter 同时接受值和 updater 函数,沿用 React setState 语义
// (e.g. setPage(p => p + 1))
function applySetter(searchParams, setSearchParams, key, value) {
  const next = new URLSearchParams(searchParams)
  const newVal = typeof value === 'function' ? value(parseInt(searchParams.get(key) || '1', 10)) : value
  next.set(key, String(newVal))
  setSearchParams(next, { replace: true })
}

export function useUrlTabs() {
  const [searchParams, setSearchParams] = useSearchParams()

  const activeTab = searchParams.get('tab') || DEFAULT_TAB

  const setActiveTab = useCallback((t) => {
    const next = new URLSearchParams(searchParams)
    if (t === DEFAULT_TAB) next.delete('tab')
    else next.set('tab', t)
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams])

  // 切片/合集各持一份分页 (cp / kp),切 tab 互不重置
  const clipsPage = parseInt(searchParams.get('cp') || '1', 10)
  const collectionsPage = parseInt(searchParams.get('kp') || '1', 10)

  const setClipsPage = useCallback((p) => {
    applySetter(searchParams, setSearchParams, 'cp', p)
  }, [searchParams, setSearchParams])

  const setCollectionsPage = useCallback((p) => {
    applySetter(searchParams, setSearchParams, 'kp', p)
  }, [searchParams, setSearchParams])

  return {
    activeTab,
    setActiveTab,
    clipsPage,
    setClipsPage,
    collectionsPage,
    setCollectionsPage,
  }
}
