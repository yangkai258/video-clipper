function Row({ label, value }) {
  return (
    <div style={{ display: 'flex', gap: 'var(--space-3)', fontSize: 'var(--text-sm)' }}>
      <span style={{ minWidth: '110px', color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ flex: 1, color: 'var(--text-bright)' }}>{value}</span>
    </div>
  )
}
