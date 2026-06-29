// ponytail: 衍生指标 (avg duration / avg score) 由父组件预算好传入,这里纯渲染
export default function ProjectMetrics({ clipsCount, collectionsCount, avgDuration, avgScore }) {
  return (
    <div className="pda-metrics">
      <div className="pda-metric">
        <div className="pda-metric-label">切片</div>
        <div className="pda-metric-value">{clipsCount}</div>
      </div>
      <div className="pda-metric">
        <div className="pda-metric-label">合集</div>
        <div className="pda-metric-value">{collectionsCount}</div>
      </div>
      <div className="pda-metric">
        <div className="pda-metric-label">平均时长</div>
        <div className="pda-metric-value">
          {avgDuration ? avgDuration.toFixed(1) : '—'}
          <span className="pda-metric-unit"> 秒</span>
        </div>
      </div>
      <div className="pda-metric">
        <div className="pda-metric-label">平均分</div>
        <div className="pda-metric-value">
          {avgScore ? avgScore.toFixed(1) : '—'}
        </div>
      </div>
    </div>
  )
}
