import Icon from '../Icon'  // eslint-disable-line no-unused-vars

// ponytail: 面包屑导航 (替代 Topbar 写死的简单实现)
// 用法:
//   <Breadcrumb items={[{label:'切片项目', to:'/', icon:'list'}, {label:project.name, icon:'film'}]} />
//   <Breadcrumb items={[{label:'工作台'}, {label:'切片项目', to:'/'}, {label: project.name, icon:'film'}]} />
//  - items 数组, 最后一项不可点击 (current)
//  - to 可选, 无 to 渲染纯文本
//  - onClick 优先于 to
export default function Breadcrumb({ items = [], onNavigate }) {
  if (!items.length) return null

  return (
    <nav className="breadcrumb" aria-label="breadcrumb">
      {items.map((item, idx) => {
        const isLast = idx === items.length - 1
        const handleClick = () => {
          if (isLast) return
          if (item.onClick) {
            item.onClick()
            return
          }
          if (onNavigate && item.to !== undefined) {
            onNavigate(item.to)
          }
        }

        const content = (
          <>
            {item.icon && <Icon name={item.icon} size={12} style={{ verticalAlign: '-1px', marginRight: 4 }} />}
            {item.label}
          </>
        )

        return (
          <span key={idx} style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            {isLast || (!item.to && !item.onClick) ? (
              <span className="breadcrumb-current">{content}</span>
            ) : (
              <button
                className="breadcrumb-link"
                onClick={handleClick}
                type="button"
              >
                {content}
              </button>
            )}
            {!isLast && <span className="breadcrumb-sep"><Icon name="chevronRight" size={10} /></span>}
          </span>
        )
      })}
    </nav>
  )
}