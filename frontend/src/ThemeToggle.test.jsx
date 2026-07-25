/**
 * v2.2.15 主题切换组件 test
 *
 * 覆盖 v2.1.43 关键 invariant:
 * - localStorage 持久化
 * - dataset.theme DOM 同步
 * - 默认亮色 (v2.2.1+ 运营团队偏好)
 * - 切换 dark <-> light
 * - aria-label 切换 (无障碍)
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import ThemeToggle from './ThemeToggle'

describe('ThemeToggle', () => {
  beforeEach(() => {
    // 每个 test 前清 localStorage + reset document.documentElement
    localStorage.clear()
    document.documentElement.dataset.theme = ''
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('默认渲染 light 主题按钮 (亮色 icon 月亮, aria-label 切换到暗色)', () => {
    render(<ThemeToggle />)
    const btn = screen.getByRole('button', { name: /切换到暗色主题/ })
    expect(btn).toBeInTheDocument()
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('点击切换到 dark 主题 (暗色 icon 太阳, aria-label 切换到亮色)', () => {
    render(<ThemeToggle />)
    const btn = screen.getByRole('button', { name: /切换到暗色主题/ })
    fireEvent.click(btn)
    expect(document.documentElement.dataset.theme).toBe('dark')
    // 切完 aria-label 翻转
    expect(screen.getByRole('button', { name: /切换到亮色主题/ })).toBeInTheDocument()
  })

  it('再次点击切回 light', () => {
    render(<ThemeToggle />)
    const btn = screen.getByRole('button', { name: /切换到暗色主题/ })
    fireEvent.click(btn)
    fireEvent.click(btn)
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('theme 变化持久化到 localStorage', () => {
    render(<ThemeToggle />)
    fireEvent.click(screen.getByRole('button', { name: /切换到暗色主题/ }))
    expect(localStorage.getItem('video-clipper-theme')).toBe('dark')
  })

  it('读 localStorage 还原上次的 theme (dark)', () => {
    localStorage.setItem('video-clipper-theme', 'dark')
    render(<ThemeToggle />)
    expect(document.documentElement.dataset.theme).toBe('dark')
    // aria-label 显示切到亮色
    expect(screen.getByRole('button', { name: /切换到亮色主题/ })).toBeInTheDocument()
  })

  it('读 localStorage 还原 (light, 跟默认一样)', () => {
    localStorage.setItem('video-clipper-theme', 'light')
    render(<ThemeToggle />)
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('无 localStorage 时 (v2.2.1 运营偏好) 默认 light', () => {
    render(<ThemeToggle />)
    expect(document.documentElement.dataset.theme).toBe('light')
  })
})
