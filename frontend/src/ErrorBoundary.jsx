/**
 * ErrorBoundary — React 16+ 错误边界 (v2.2.30)
 * 任何子组件崩了, 兜底显示"刷新重试" + 错误详情, 不让 Topbar 全挂.
 *
 * 用法:
 *   <ErrorBoundary>
 *     <SomeRiskyComponent />
 *   </ErrorBoundary>
 *
 * 设计取舍:
 * - 静默 console.error 防 dev 模式红屏刷屏
 * - dev 模式 (import.meta.env.DEV) 显示 stack trace 帮 debug
 * - 生产环境只显示友好提示 + 错误摘要
 * - "重试"按钮清空 state, 给一次重新渲染机会; 不行就强制刷新
 */
import React from 'react'

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error) {
    // 触发 fallback UI
    return { error }
  }

  componentDidCatch(error, errorInfo) {
    // 存 stack trace (dev 模式显示)
    this.setState({ errorInfo })
    // 静默 React 18 dev 模式那个红屏 console.error
    if (typeof console !== 'undefined' && console.error) {
      console.error('[ErrorBoundary] caught:', error, errorInfo)
    }
  }

  handleReset = () => {
    this.setState({ error: null, errorInfo: null })
  }

  handleReload = () => {
    if (typeof window !== 'undefined' && window.location) {
      window.location.reload()
    }
  }

  render() {
    const { error, errorInfo } = this.state
    const { children, fallback } = this.props

    if (!error) return children

    // 自定义 fallback (可选)
    if (fallback) return fallback(error, this.handleReset, this.handleReload)

    const isDev = typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.DEV
    const errorMsg = (error && (error.message || String(error))) || '未知错误'

    return (
      <div
        style={{
          padding: '32px 24px',
          margin: '16px',
          border: '1px solid var(--border, #e5e7eb)',
          borderRadius: '12px',
          background: 'var(--bg-elevated, #fef2f2)',
          color: 'var(--text, #1f2937)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <div
            style={{
              fontSize: '24px',
              width: 40,
              height: 40,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: '#fee2e2',
              borderRadius: '50%',
            }}
          >
            ⚠️
          </div>
          <div>
            <div style={{ fontSize: '16px', fontWeight: 600 }}>组件出错了</div>
            <div style={{ fontSize: '13px', color: 'var(--text-muted, #6b7280)', marginTop: 2 }}>
              这部分页面渲染失败, 但其他功能还在. 刷新页面或重试一次试试.
            </div>
          </div>
        </div>

        {isDev && (
          <details
            style={{
              marginTop: 12,
              padding: 12,
              background: 'var(--bg, #fff)',
              border: '1px solid var(--border, #e5e7eb)',
              borderRadius: 8,
              fontSize: '12px',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
              maxHeight: 200,
              overflow: 'auto',
            }}
          >
            <summary style={{ cursor: 'pointer', fontWeight: 600, marginBottom: 8 }}>
              错误详情 (仅开发环境)
            </summary>
            <div style={{ color: '#dc2626', marginBottom: 8 }}>{errorMsg}</div>
            {errorInfo && errorInfo.componentStack && (
              <pre style={{ whiteSpace: 'pre-wrap', margin: 0, color: '#6b7280' }}>
                {errorInfo.componentStack}
              </pre>
            )}
          </details>
        )}

        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button
            onClick={this.handleReset}
            style={{
              padding: '8px 16px',
              border: '1px solid var(--border, #d1d5db)',
              background: 'var(--bg, #fff)',
              color: 'var(--text, #1f2937)',
              borderRadius: 8,
              fontSize: '13px',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            重试
          </button>
          <button
            onClick={this.handleReload}
            style={{
              padding: '8px 16px',
              border: 'none',
              background: 'var(--accent, #2563eb)',
              color: '#fff',
              borderRadius: 8,
              fontSize: '13px',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            刷新页面
          </button>
        </div>
      </div>
    )
  }
}
