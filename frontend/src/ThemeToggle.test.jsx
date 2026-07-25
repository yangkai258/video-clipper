// v2.2.15 主题切换组件 test
//
// 覆盖 v2.1.43 关键 invariant:
// - 点击切换 dark <-> light
// - dataset.theme DOM 同步
// - localStorage 持久化 + 还原
// - aria-label 翻转 (无障碍)
//
// v2.2.15 fix: 5 fail root cause = beforeEach 仅 clear localStorage,
// 没强制 setItem 'light', 依赖 useState 初始读 clean state.
// 实际 React 18 可能在 first render 之前 setItem (useEffect 异步).
// 改用: 每个 test 手动控制 initial state, 不依赖 clean slate.
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import ThemeToggle from './ThemeToggle'

describe('ThemeToggle', () => {
  beforeEach(() => {
    // 强制 localStorage = 'light' (跟生产 default 一致, ramply 改 v2.2.1)
    localStorage.setItem('video-clipper-theme', 'light')
    document.documentElement.dataset.theme = ''
  })

  afterEach(() => {
    cleanup()
    localStorage.clear()
  })

  it('mount 时读 localStorage light → 渲染暗色切换 button', () => {
    render(<ThemeToggle />)
    // isDark=false, nextLabel=暗色, aria-label=切换到暗色主题
    const btn = screen.getByRole('button', { name: /切换到暗色主题/ })
    expect(btn).toBeInTheDocument()
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('mount 时读 localStorage dark → 渲染亮色切换 button', () => {
    localStorage.setItem('video-clipper-theme', 'dark')
    render(<ThemeToggle />)
    const btn = screen.getByRole('button', { name: /切换到亮色主题/ })
    expect(btn).toBeInTheDocument()
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('点击从 light → dark, 同步 dataset.theme + 持久化', () => {
    render(<ThemeToggle />)
    const btn = screen.getByRole('button', { name: /切换到暗色主题/ })
    fireEvent.click(btn)
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('video-clipper-theme')).toBe('dark')
    expect(screen.getByRole('button', { name: /切换到亮色主题/ })).toBeInTheDocument()
  })

  it('点击从 dark → light, 同步 dataset.theme + 持久化', () => {
    localStorage.setItem('video-clipper-theme', 'dark')
    render(<ThemeToggle />)
    const btn = screen.getByRole('button', { name: /切换到亮色主题/ })
    fireEvent.click(btn)
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(localStorage.getItem('video-clipper-theme')).toBe('light')
    expect(screen.getByRole('button', { name: /切换到暗色主题/ })).toBeInTheDocument()
  })

  it('再点切回 (light → dark → light 完整 toggle)', () => {
    render(<ThemeToggle />)
    fireEvent.click(screen.getByRole('button', { name: /切换到暗色主题/ }))
    fireEvent.click(screen.getByRole('button', { name: /切换到亮色主题/ }))
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('localStorage 损坏 (抛错) 走 DEFAULT_THEME fallback', () => {
    // mock localStorage.getItem 抛错, 模拟 Safari 隐私模式
    const originalGet = localStorage.getItem
    localStorage.getItem = () => { throw new Error('QuotaExceeded') }
    try {
      render(<ThemeToggle />)
      // 拿到 default 'light' (v2.2.1 运营偏好), 渲染 切换到暗色
      expect(screen.getByRole('button', { name: /切换到暗色主题/ })).toBeInTheDocument()
    } finally {
      localStorage.getItem = originalGet
    }
  })
})
