import ClipCard from './ClipCard'
import Pagination from './Pagination'
import EmptyState from './EmptyState'
import Icon from '../Icon'

const ITEMS_PER_PAGE = 12

export default function ClipsTab({ projectId, clips, withSubtitle, currentPage, onPageChange }) {
  if (clips.length === 0) {
    return <EmptyState icon={<Icon name="film" size={32} />} title="暂无切片" hint="处理完成后切片会出现在这里" />
  }
  const totalPages = Math.max(1, Math.ceil(clips.length / ITEMS_PER_PAGE))
  const start = (currentPage - 1) * ITEMS_PER_PAGE
  const pageClips = clips.slice(start, start + ITEMS_PER_PAGE)
  return (
    <>
      <div className="pda-grid-header">
        <span>显示 {start + 1} - {Math.min(start + ITEMS_PER_PAGE, clips.length)} / {clips.length}</span>
        <span>第 {currentPage} / {totalPages} 页</span>
      </div>
      <div className="pda-grid">
        {pageClips.map((clip, i) => (
          <ClipCard
            key={clip.id || i}
            clip={clip}
            index={i}
            projectId={projectId}
            withSubtitle={withSubtitle}
          />
        ))}
      </div>
      <Pagination currentPage={currentPage} totalPages={totalPages} onPageChange={onPageChange} />
    </>
  )
}
