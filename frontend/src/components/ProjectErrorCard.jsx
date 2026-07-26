import Icon from '../Icon'
import { friendlyError } from '../projectView'

export default function ProjectErrorCard({ errorMessage, onRetry }) {
  const err = friendlyError(errorMessage)
  return (
    <div className="pda-error-card">
      <div className="pda-error-title"><Icon name="alert" size={14} style={{ verticalAlign: '-2px', marginRight: 4 }} />{err.title}</div>
      <div className="pda-error-hint">{err.hint}</div>
      <details className="pda-error-detail">
        <summary>查看原始错误</summary>
        <code>{errorMessage.slice(0, 400)}</code>
      </details>
      <button className="btn btn-primary btn-sm" style={{ marginTop: 'var(--space-3)' }} onClick={onRetry}><Icon name="refresh" size={11} style={{ verticalAlign: '-1px', marginRight: 3 }} />重新处理</button>
    </div>
  )
}
