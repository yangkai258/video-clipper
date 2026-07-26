import { useEffect, useState } from 'react'
import Icon from './Icon'  // eslint-disable-line no-unused-vars

const STORAGE_KEY = 'video-clipper-theme'
const DARK = 'dark'
const LIGHT = 'light'

/**
 * 读取持久化主题（无 localStorage 时返回默认）
 */
function readSavedTheme() {
  if (typeof window === 'undefined') return DARK
  try {
    return localStorage.getItem(STORAGE_KEY) || DARK
  } catch {
    return DARK
  }
}

/**
 * 亮暗切换按钮
 *
 * - 默认 dark
 * - 写 document.documentElement.dataset.theme（CSS 变量自动切换）
 * - 持久化到 localStorage
 * - 顶栏右侧 SVG icon 切换
 */
export default function ThemeToggle() {
  const [theme, setTheme] = useState(readSavedTheme)

  // 每次 theme 变化都同步到 DOM + localStorage
  useEffect(() => {
    if (typeof document === 'undefined') return
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      // localStorage 不可用（隐私模式 / quota）— 静默忽略
    }
  }, [theme])

  const toggle = () => setTheme((t) => (t === DARK ? LIGHT : DARK))
  const isDark = theme === DARK
  const nextLabel = isDark ? '亮色' : '暗色'

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      aria-label={`切换到${nextLabel}主题`}
      title={`切换到${nextLabel}主题`}
    >
      <span className="theme-toggle-icon" aria-hidden="true">
        <Icon name={isDark ? 'sun' : 'moon'} size={14} />
      </span>
    </button>
  )
}