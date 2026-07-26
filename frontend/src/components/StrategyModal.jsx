import Icon from '../Icon'  // eslint-disable-line no-unused-vars

// ponytail: 选择处理策略的 modal
// 收 7 个 props: state/handler 全部从 App 传入 (避免 useStrategy hook 内部闭包)
export default function StrategyModal({
  _pendingProject,
  setPendingProject,
  presets,
  customStyles,
  withSubtitle,
  setWithSubtitle,
  outputFormat,
  setOutputFormat,
  onSelect,
  onClose,
}) {
  return (
    <div className="modal-overlay">
      <div className="modal">
        <div className="modal-header">
          <div className="modal-title">
            <div className="modal-title-icon" />
            选择处理策略
          </div>
          <button className="btn btn-ghost btn-sm" onClick={() => { onClose(); setPendingProject(null) }} title="关闭">
            <Icon name="x" size={12} />
          </button>
        </div>

        <div className="modal-body">
          <div className="toggle-row">
            <div>
              <div className="toggle-info-label" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                像谱录制屏幕
                <span style={{
                  fontSize: 'var(--text-xs)', color: 'var(--accent)',
                  background: 'var(--accent-soft)',
                  padding: '1px var(--space-2)', borderRadius: '999px',
                  fontWeight: 500
                }}>
                  推荐启用
                </span>
              </div>
              <div className="toggle-info-hint">关 = 纯剪（更快）· 开 = 带字幕（更慢，但传播力更强）</div>
            </div>
            <div
              className={`toggle-switch ${withSubtitle ? 'on' : ''}`}
              onClick={() => setWithSubtitle(!withSubtitle)}
            />
          </div>

          {/* v2.1.28: 输出格式 — 处理前确定, 切完不再改 */}
          <div className="toggle-row">
            <div>
              <div className="toggle-info-label" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                <Icon name="monitor" size={12} style={{ verticalAlign: '-2px', marginRight: 3 }} />
                输出格式
                {outputFormat === '9:16-letterbox' && (
                  <span style={{
                    fontSize: 'var(--text-xs)', color: '#06b6d4',
                    background: 'rgba(6,182,212,0.15)',
                    padding: '1px var(--space-2)', borderRadius: '999px',
                    fontWeight: 500
                  }}>
                    抖音适配
                  </span>
                )}
              </div>
              <div className="toggle-info-hint">
                {outputFormat === 'original'
                  ? <><Icon name="film" size={12} style={{ verticalAlign: '-2px', marginRight: 3 }} />保持原比例</>
                  : <><Icon name="monitor" size={12} style={{ verticalAlign: '-2px', marginRight: 3 }} />9:16 上下黑边 (抖音适配)</>}
              </div>
            </div>
            <div
              className={`toggle-switch ${outputFormat === '9:16-letterbox' ? 'on' : ''}`}
              onClick={() => setOutputFormat(outputFormat === '9:16-letterbox' ? 'original' : '9:16-letterbox')}
            />
          </div>

          <div style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-muted)', margin: 'var(--space-4) 0 var(--space-2)' }}>
            预设策略
          </div>
          <div className="strategy-grid">
            {presets.map((p, _i) => (
              <button key={p.id} className="strategy-item" onClick={() => onSelect(p)}>
                <div className="strategy-icon">{p.name.split(' ')[0]}</div>
                <div className="strategy-body">
                  <div className="strategy-name">{p.name.split(' ').slice(1).join(' ') || p.name}</div>
                  <div className="strategy-desc">{p.description}</div>
                  <div className="strategy-meta">
                    <span>时长 <b>{p.target_duration}s</b></span>
                    <span>最多 <b>{p.max_clips}</b></span>
                  </div>
                </div>
              </button>
            ))}
          </div>

          {customStyles.length > 0 && (
            <>
              <div style={{ fontSize: 'var(--text-xs)', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-muted)', margin: 'var(--space-4) 0 var(--space-2)' }}>
                自定义风格
              </div>
              <div className="strategy-grid">
                {customStyles.map(s => (
                  <button key={s.id} className="strategy-item" onClick={() => onSelect(s)}>
                    <div className="strategy-icon"><Icon name="edit" size={14} /></div>
                    <div className="strategy-body">
                      <div className="strategy-name">{s.name}</div>
                      {s.description && <div className="strategy-desc">{s.description}</div>}
                      <div className="strategy-meta">
                        <span>时长 <b>{s.target_duration}s</b></span>
                        <span>最多 <b>{s.max_clips}</b></span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={() => { onClose(); setPendingProject(null) }}>取消</button>
        </div>
      </div>
    </div>
  )
}
