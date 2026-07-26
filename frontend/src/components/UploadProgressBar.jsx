import Icon from '../Icon'
import { formatBytes, formatSpeed, formatTime } from '../ChunkedUploader'

export default function UploadProgressBar({ state, progress, error, onPause, onResume, onCancel }) {
  const { received, total, speed } = progress
  const pct = total > 0 ? Math.min(100, (received / total) * 100) : 0
  const remain = speed > 0 ? (total - received) / speed : null

  const stateLabel = {
    uploading: '上传中',
    resuming: '恢复中',
    pausing: '暂停中',
    paused: '已暂停',
    retrying: '重试中',
    finalizing: '合并中',
    done: '完成',
    error: '出错',
  }[state] || state

  return (
    <div className="upload-progress" style={{
      position: 'absolute', top: 'calc(100% + 8px)', right: 0,
      width: '420px', background: 'var(--bg-elevated)',
      border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)',
      padding: 'var(--space-4)', boxShadow: 'var(--shadow-md)',
      zIndex: 100
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-2)' }}>
        <span style={{
          fontFamily: 'var(--text-mono)', fontSize: 'var(--text-xs)',
          color: state === 'error' ? 'var(--danger)' : 'var(--accent)',
          fontWeight: 600
        }}>{stateLabel}</span>
        <span style={{ fontFamily: 'var(--text-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
          {formatBytes(received)} / {formatBytes(total)}
        </span>
      </div>

      {/* 进度条 */}
      <div style={{
        height: '8px', background: 'var(--bg-base)', borderRadius: '4px',
        overflow: 'hidden', marginBottom: 'var(--space-2)'
      }}>
        <div style={{
          width: `${pct}%`, height: '100%',
          background: state === 'error' ? 'var(--danger)' : 'var(--accent)',
          transition: 'width 0.2s ease-out'
        }} />
      </div>

      {/* 数字行 */}
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        fontFamily: 'var(--text-mono)', fontSize: 'var(--text-xs)',
        color: 'var(--text-muted)', marginBottom: 'var(--space-3)'
      }}>
        <span>{pct.toFixed(1)}%</span>
        <span>{formatSpeed(speed)}</span>
        <span>剩余 {formatTime(remain)}</span>
      </div>

      {/* 网络慢提示（速度 < 200 KB/s 且已传 > 1MB） */}
      {received > 1024 * 1024 && speed > 0 && speed < 200 * 1024 && (
        <div style={{
          padding: 'var(--space-2) var(--space-3)', marginBottom: 'var(--space-3)',
          background: 'rgba(234, 179, 8, 0.1)', color: '#b45309',
          borderRadius: 'var(--radius-sm)', fontSize: 'var(--text-xs)',
          border: '1px solid rgba(234, 179, 8, 0.3)'
        }}>
          <Icon name="warning" size={12} style={{ verticalAlign: '-2px', marginRight: 3 }} />网络较慢（{formatSpeed(speed)}）。建议：本地用 ffmpeg 转 720p 再传，文件小 3-5 倍
        </div>
      )}

      {error && (
        <div style={{
          padding: 'var(--space-2) var(--space-3)', marginBottom: 'var(--space-3)',
          background: 'var(--danger-soft)', color: 'var(--danger)',
          borderRadius: 'var(--radius-sm)', fontSize: 'var(--text-xs)'
        }}>
          {error}
        </div>
      )}

      {/* 控制按钮 */}
      <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
        {state === 'uploading' && (
          <button className="btn btn-ghost btn-sm" onClick={onPause} style={{ flex: 1 }}>暂停</button>
        )}
        {state === 'paused' && (
          <button className="btn btn-primary btn-sm" onClick={onResume} style={{ flex: 1 }}>继续</button>
        )}
        {(state === 'uploading' || state === 'paused' || state === 'error') && (
          <button className="btn btn-ghost btn-sm btn-danger" onClick={onCancel} style={{ flex: 1 }}>取消</button>
        )}
        {state === 'finalizing' && (
          <span style={{ flex: 1, textAlign: 'center', color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
            正在合并分片并创建项目…
          </span>
        )}
      </div>
    </div>
  )
}
