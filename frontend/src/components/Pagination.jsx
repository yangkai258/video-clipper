// ponytail: 通用分页,setPage 同时支持值和 updater 函数
export default function Pagination({ currentPage, totalPages, onPageChange }) {
  if (totalPages <= 1) return null
  const goPrev = () => onPageChange(p => Math.max(1, p - 1))
  const goNext = () => onPageChange(p => Math.min(totalPages, p + 1))
  const atStart = currentPage === 1
  const atEnd = currentPage >= totalPages
  return (
    <div className="pda-pagination">
      <button className="btn btn-ghost btn-sm" disabled={atStart} onClick={goPrev} style={{ opacity: atStart ? 0.4 : 1 }}>← 上一页</button>
      {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
        <button key={p} className={`btn btn-sm ${currentPage === p ? 'btn-primary' : 'btn-ghost'}`} onClick={() => onPageChange(p)}>{p}</button>
      ))}
      <button className="btn btn-ghost btn-sm" disabled={atEnd} onClick={goNext} style={{ opacity: atEnd ? 0.4 : 1 }}>下一页 →</button>
    </div>
  )
}
