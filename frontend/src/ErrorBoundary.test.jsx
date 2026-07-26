/**
 * ErrorBoundary test (v2.2.30)
 * 测 React error boundary 兜底 — 子组件崩了显示"刷新重试" UI, 不让 Topbar 全挂.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import React from 'react'
import { ErrorBoundary } from './ErrorBoundary'

// 模拟崩的组件
function BoomChild({ shouldThrow = true }) {
  if (shouldThrow) {
    throw new Error('Test boom: 组件故意崩')
  }
  return <div>正常内容</div>
}

describe('ErrorBoundary', () => {
  let consoleSpy

  beforeEach(() => {
    // 静默 console.error (React 18 dev mode 故意打红, 防 test output 炸)
    consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    consoleSpy.mockRestore()
    cleanup()
  })

  it('子组件正常时透传 children', () => {
    render(
      <ErrorBoundary>
        <div>hello</div>
      </ErrorBoundary>,
    )
    expect(screen.getByText('hello')).toBeInTheDocument()
  })

  it('子组件崩了显示兜底 UI', () => {
    render(
      <ErrorBoundary>
        <BoomChild />
      </ErrorBoundary>,
    )
    expect(screen.getByText('组件出错了')).toBeInTheDocument()
    expect(screen.getAllByText(/⚠️/).length).toBeGreaterThan(0)
    expect(screen.getByText('刷新页面')).toBeInTheDocument()
    expect(screen.getByText('重试')).toBeInTheDocument()
  })

  it('dev 模式显示错误详情 (import.meta.env.DEV)', () => {
    // vitest 默认 Vite dev mode, DEV 应该 true
    render(
      <ErrorBoundary>
        <BoomChild />
      </ErrorBoundary>,
    )
    expect(screen.getByText(/Test boom/)).toBeInTheDocument()
  })

  it('重试按钮能清空 error 状态', () => {
    // 第一次 render 崩, 点重试后 BoomChild shouldThrow=false 就不崩
    let shouldThrow = true
    function DynamicBoom() {
      if (shouldThrow) throw new Error('boom')
      return <div>恢复后</div>
    }
    const { rerender } = render(
      <ErrorBoundary>
        <DynamicBoom />
      </ErrorBoundary>,
    )
    expect(screen.getByText('组件出错了')).toBeInTheDocument()

    // 改 shouldThrow + 点重试
    shouldThrow = false
    fireEvent.click(screen.getByText('重试'))
    rerender(
      <ErrorBoundary>
        <DynamicBoom />
      </ErrorBoundary>,
    )
    expect(screen.getByText('恢复后')).toBeInTheDocument()
  })

  it('多次崩 error 状态能恢复 (重试后还能崩)', () => {
    const { rerender } = render(
      <ErrorBoundary>
        <BoomChild />
      </ErrorBoundary>,
    )
    expect(screen.getByText('组件出错了')).toBeInTheDocument()

    // 第一次重试 (BoomChild shouldThrow=true 仍崩)
    fireEvent.click(screen.getByText('重试'))
    rerender(
      <ErrorBoundary>
        <BoomChild />
      </ErrorBoundary>,
    )
    expect(screen.getByText('组件出错了')).toBeInTheDocument()
  })
})
