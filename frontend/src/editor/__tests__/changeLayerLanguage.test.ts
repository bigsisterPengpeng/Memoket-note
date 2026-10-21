import { EditorState } from '@codemirror/state'
import { afterEach, describe, expect, it } from 'vitest'
import { setLang } from '../../i18n'
import { contentTag, layerLabel, layerSource, restoreLayers, serializeLayers, type SavedLayer } from '../../util/changeLayers'
import { addLayer, diffParts, roundDiffField } from '../roundDiff'

afterEach(() => setLang('en'))

describe('stored change labels across interface languages', () => {
  it('translates app-owned labels and undo numbers without changing custom Chinese labels', () => {
    setLang('en')
    expect(layerLabel('\u6da6\u8272')).toBe('Polish')
    expect(layerLabel('\u683c\u5f0f\u5316')).toBe('Format')
    expect(layerLabel('\u6392\u7248')).toBe('Formatting')
    expect(layerSource('\u6392\u7248')).toBe('format')
    expect(layerLabel('\u81ea\u5b9a\u4e49\u63d0\u793a')).toBe('Custom prompt')
    expect(layerLabel('\u64a4\u6389\u7b2c 12 \u8f6e')).toBe('Undo round 12')
    expect(layerSource('\u64a4\u6389\u7b2c 12 \u8f6e')).toBe('undo_round')
    const custom = '\u6211\u7684\u7b14\u8bb0\u4fee\u6539'
    expect(layerLabel(custom)).toBe(custom)
    expect(layerLabel('\u6da6\u8272\u6211\u7684\u7b14\u8bb0')).toBe('\u6da6\u8272\u6211\u7684\u7b14\u8bb0')
    setLang('zh')
    expect(layerLabel('Polish')).toBe('\u6da6\u8272')
    expect(layerLabel('Undo round 12')).toBe('\u64a4\u6389\u7b2c 12 \u8f6e')
    expect(layerLabel(custom)).toBe(custom)
  })

  it('stores English action keys while keeping Chinese edit content intact', () => {
    setLang('zh')
    const before = '\u4eca\u5929'
    const after = '\u4eca\u5929\u597d'
    let state = EditorState.create({ doc: before, extensions: [roundDiffField] })
    state = state.update({ changes: { from: 0, to: before.length, insert: after },
      effects: addLayer.of({ label: '\u6da6\u8272', parts: diffParts(before, after) }) }).state
    const saved = serializeLayers(state)
    expect(saved).toHaveLength(1)
    expect(saved[0].label).toBe('Polish')
    expect(saved[0].source).toBe('polish')
    expect(saved[0].hunks[0].ins).toBe('\u597d')
    setLang('en')
    const restored = restoreLayers(saved, after)
    expect(restored.layers[0].label).toBe('Polish')
    expect(restored.conflicts).toEqual([])
    expect(after.slice(restored.hunks[0].from, restored.hunks[0].to)).toBe('\u597d')
    expect(state.doc.toString()).toBe(after)
  })

  it('reopens legacy Chinese labels in English, including conflict notices', () => {
    setLang('en')
    const old: SavedLayer = { id: 'legacy', label: '\u6da6\u8272', source: 'polish', seq: 0,
      state: 'on', at: '2026-01-01T00:00:00Z', content_tag: contentTag('old'),
      hunks: [{ k: 0, from: 0, to: 3, del: '', ins: 'old', state: 'pending' }] }
    const restored = restoreLayers([old], 'old')
    expect(restored.layers[0].label).toBe('Polish')
    expect(restored.hunks).toHaveLength(1)
    const conflict = restoreLayers([old], 'new')
    expect(conflict.conflicts).toEqual(['Polish: “old”'])
    expect(conflict.stuck[0].label).toBe('Polish')
    expect(old.label).toBe('\u6da6\u8272')
  })
})
