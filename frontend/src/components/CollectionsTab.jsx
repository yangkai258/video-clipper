import CollectionCard from './CollectionCard'  // eslint-disable-line no-unused-vars
import EmptyState from './EmptyState'  // eslint-disable-line no-unused-vars
import Icon from '../Icon'  // eslint-disable-line no-unused-vars

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
