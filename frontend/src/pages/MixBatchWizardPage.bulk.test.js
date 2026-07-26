// v2.2.56 batch wizard bulkAddVariations 测试
// 测跨 variation 一键生成 N 变体 (1 候选 = 1 变体)
import { describe, it, expect } from 'vitest'

// 复刻 MixBatchWizardPage bulkAddVariations filter 逻辑
function filterCandidates(candidates, activeSource, activeProject) {
  return candidates.filter(c => {
    if (activeSource !== 'all' && c.source_type !== activeSource) return false
    if (activeSource !== 'library' && activeProject !== 'all' && c.source_project_name !== activeProject) return false
    return true
  })
}

function bulkAddVariations(filtered, existingVariations) {
  if (filtered.length === 0) return null  // alert + skip
  if (filtered.length > 30) {
    // confirm 对话框: user 决定
  }
  return filtered.map((c, idx) => ({
    name: c.title ? `${c.title.slice(0, 16)}` : `变体 ${existingVariations.length + idx + 1}`,
    script_text: '',
    candidate_clip_ids: [c.id],
  }))
}

const CANDIDATES = [
  { id: 'a', title: '防水产品 1', source_type: 'project', source_project_name: 'P1' },
  { id: 'b', title: '防水产品 2', source_type: 'project', source_project_name: 'P1' },
  { id: 'c', title: '广告宣传', source_type: 'library', source_project_name: '资源库' },
  { id: 'd', title: '室内讲解', source_type: 'library', source_project_name: '资源库' },
  { id: 'e', title: '工地现场', source_type: 'project', source_project_name: 'P2' },
]

describe('batch bulkAddVariations', () => {
  it('source=library 全部 → 2 个变体 (c, d)', () => {
    const filtered = filterCandidates(CANDIDATES, 'library', 'all')
    expect(filtered.map(c => c.id)).toEqual(['c', 'd'])
    const vars = bulkAddVariations(filtered, [])
    expect(vars.length).toBe(2)
    expect(vars[0].candidate_clip_ids).toEqual(['c'])
    expect(vars[1].candidate_clip_ids).toEqual(['d'])
  })

  it('source=project + project=P1 → 2 个变体 (a, b)', () => {
    const filtered = filterCandidates(CANDIDATES, 'project', 'P1')
    const vars = bulkAddVariations(filtered, [])
    expect(vars.map(v => v.candidate_clip_ids[0])).toEqual(['a', 'b'])
  })

  it('source=all → 5 个变体', () => {
    const filtered = filterCandidates(CANDIDATES, 'all', 'all')
    const vars = bulkAddVariations(filtered, [])
    expect(vars.length).toBe(5)
  })

  it('空 candidates → null (skip alert)', () => {
    const filtered = filterCandidates([], 'all', 'all')
    expect(bulkAddVariations(filtered, [])).toBeNull()
  })

  it('变体名截断到 16 字', () => {
    const c = [{ id: 'x', title: '超长标题超长标题超长标题超长标题超长', source_type: 'library', source_project_name: 'R' }]
    const vars = bulkAddVariations(c, [])
    expect(vars[0].name.length).toBeLessThanOrEqual(16)
  })

  it('无 title → 变体 N (兜底)', () => {
    const c = [{ id: 'x', title: '', source_type: 'library', source_project_name: 'R' }]
    const vars = bulkAddVariations(c, [{ name: 'V0' }])  // 已有 1 个
    expect(vars[0].name).toBe('变体 2')  // existingVariations.length (1) + idx (0) + 1 = 2
  })

  it('N>30 → 提示 confirm (实际 confirm 返回值由 UI 决定)', () => {
    const big = Array.from({ length: 50 }, (_, i) => ({ id: `c${i}`, title: `T${i}`, source_type: 'library', source_project_name: 'R' }))
    const vars = bulkAddVariations(big, [])
    expect(vars.length).toBe(50)  // 返回所有, confirm 由 caller 处理
  })

  it('append 到已有 (不清空 existing)', () => {
    const existing = [{ name: 'V0', candidate_clip_ids: ['old'] }]
    const filtered = filterCandidates(CANDIDATES, 'library', 'all')
    const newVars = bulkAddVariations(filtered, existing)
    // 用 setState updater pattern: [...existing, ...newVars]
    const all = [...existing, ...newVars]
    expect(all.length).toBe(3)  // 1 existing + 2 new
    expect(all[0].candidate_clip_ids).toEqual(['old'])
    expect(all[1].candidate_clip_ids).toEqual(['c'])
  })
})
