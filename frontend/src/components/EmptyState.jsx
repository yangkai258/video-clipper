import Icon from '../Icon'  // eslint-disable-line no-unused-vars

export default function EmptyState({ icon, title, hint, action }) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon || <Icon name="film" size={32} />}</div>
      <div className="empty-title">{title}</div>
      {hint && <div className="empty-hint">{hint}</div>}
      {action}
    </div>
  )
}
