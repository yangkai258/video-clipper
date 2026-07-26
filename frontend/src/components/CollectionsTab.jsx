import CollectionCard from './CollectionCard'
import EmptyState from './EmptyState'
import Icon from '../Icon'

export default function CollectionsTab({ projectId, collections }) {
  if (collections.length === 0) {
    return <EmptyState icon={<Icon name="list" size={32} />} title="暂无合集" hint="合集是多个切片的组合" />
  }
  return (
    <div className="pda-grid">
      {collections.map((coll, i) => (
        <CollectionCard key={coll.id || i} coll={coll} index={i} projectId={projectId} />
      ))}
    </div>
  )
}
