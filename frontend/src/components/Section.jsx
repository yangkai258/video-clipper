import Icon from '../Icon'

export default function Section({ title, icon, children }) {
  return (
    <div style={{ marginBottom: 'var(--space-5)' }}>
      <div style={{
        fontSize: 'var(--text-sm)',
        fontWeight: 600,
        color: 'var(--text-bright)',
        marginBottom: 'var(--space-3)',
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        paddingBottom: 'var(--space-2)',
        borderBottom: '1px solid var(--border-subtle)',
      }}>{icon && <Icon name={icon} size={14} />}{title}</div>
      <div style={{ display: 'grid', gap: 'var(--space-2)' }}>{children}</div>
    </div>
  )
}