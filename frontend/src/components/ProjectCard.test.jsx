/**
 * v2.2.40 列表卡片"存到资源库"按钮测试
 *
 * User 反馈: 资源库 UX, 列表看不到"加到资源库"按钮, 必须进 ProjectDetail 才能批量存.
 * 修: ProjectCard 加 onSaveToLibrary prop, 调 POST /library/from-project 批量加.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import React from 'react'

// mock react-router-dom (ProjectCard 用 useNavigate)
vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}))

import ProjectCard from './ProjectCard'
import Icon from '../Icon'

// 简单 Icon mock, 避免 jsdom svg 问题
vi.mock('../Icon', () => ({
  default: ({ name, size, style }) => <span data-icon={name} style={style} />,
}))


const baseProject = {
  id: 'proj-1',
  name: '测试项目',
  status: 'completed',
  clip_count: 5,
  video_duration: 60,
  has_subtitle: true,
  created_at: '2026-07-26T00:00:00Z',
  style_name: '默认',
  style_id: '_default',
}

describe('ProjectCard v2.2.40 存到资源库按钮', () => {
  it('completed 项目显示"存到资源库"按钮', () => {
    const onSaveToLibrary = vi.fn()
    render(<ProjectCard project={baseProject} onStart={vi.fn()} onDelete={vi.fn()} onSaveToLibrary={onSaveToLibrary} />)
    const btn = screen.getByText('存到资源库')
    expect(btn).toBeInTheDocument()
  })

  it('pending 项目不显示"存到资源库"按钮', () => {
    const onSaveToLibrary = vi.fn()
    render(<ProjectCard project={{ ...baseProject, status: 'pending' }} onStart={vi.fn()} onDelete={vi.fn()} onSaveToLibrary={onSaveToLibrary} />)
    expect(screen.queryByText('存到资源库')).toBeNull()
  })

  it('failed 项目不显示"存到资源库"按钮 (没 clip 可存)', () => {
    const onSaveToLibrary = vi.fn()
    render(<ProjectCard project={{ ...baseProject, status: 'failed', clip_count: 0 }} onSaveToLibrary={onSaveToLibrary} />)
    expect(screen.queryByText('存到资源库')).toBeNull()
  })

  it('completed 但 clip_count=0 不显示按钮', () => {
    const onSaveToLibrary = vi.fn()
    render(<ProjectCard project={{ ...baseProject, clip_count: 0 }} onSaveToLibrary={onSaveToLibrary} />)
    expect(screen.queryByText('存到资源库')).toBeNull()
  })

  it('点"存到资源库"调用 onSaveToLibrary(project)', () => {
    const onSaveToLibrary = vi.fn()
    render(<ProjectCard project={baseProject} onSaveToLibrary={onSaveToLibrary} />)
    fireEvent.click(screen.getByText('存到资源库'))
    expect(onSaveToLibrary).toHaveBeenCalledTimes(1)
    expect(onSaveToLibrary).toHaveBeenCalledWith(baseProject)
  })

  it('点"存到资源库"不触发 card 整体 onClick (navigate) — e.stopPropagation', () => {
    const onCardClick = vi.fn()
    const onSaveToLibrary = vi.fn()
    const { container } = render(
      <div onClick={onCardClick}>
        <ProjectCard project={baseProject} onSaveToLibrary={onSaveToLibrary} />
      </div>
    )
    fireEvent.click(screen.getByText('存到资源库'))
    expect(onSaveToLibrary).toHaveBeenCalledTimes(1)
    // card 整体 navigate 不应被触发 (e.stopPropagation 在 actions div 上)
    expect(onCardClick).not.toHaveBeenCalled()
  })

  it('没传 onSaveToLibrary 不报错 (兼容老用法)', () => {
    render(<ProjectCard project={baseProject} />)
    fireEvent.click(screen.getByText('存到资源库'))
    // 不 throw, 不调
  })
})
