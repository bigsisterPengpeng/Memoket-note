import { createElement, createRef } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { EditorView } from '@codemirror/view'

import ChangeLayersPanel from '../ChangeLayersPanel'
import { changesTabHasContent } from '../../util/changeLayers'
import appSrc from '../../App.tsx?raw'

describe('per-change accept / revert forms visible writing feedback', () => {
  it('still shows how much was kept last time after the change layers are burned', () => {
    const html = renderToStaticMarkup(createElement(ChangeLayersPanel, {
      viewRef: createRef<EditorView>(),
      tick: 0,
      feedback: {
        accepted: 4, reverted: 2, decided: 6,
        latest: { layer_id: 'l1', label: 'Smart Continue', accepted: 1, reverted: 2, decided_at: '2026-09-24T10:00:00Z' },
        items: [],
      },
    }))
    expect(html).toContain('Last time AI changed 3 places and you kept 1')
    expect(html).toContain('Reverted 2; kept 4 of the last 6 decisions')
    expect(html).toContain('The next Smart Continue will treat these decisions as writing constraints for this note')
  })

  it('the Changes tab still has content when only long-term feedback remains', () => {
    expect(changesTabHasContent({ layers: 0, settled: 0, runs: 0, stuck: 0, feedback: 3 })).toBe(true)
    expect(changesTabHasContent({ layers: 0, settled: 0, runs: 0, stuck: 0, feedback: 0 })).toBe(false)
  })

  it('waits for per-change decisions to really be persisted before running, not treating an in-flight PUT as saved', () => {
    expect(appSrc).toContain('await flushChangeLayers()')
    expect(appSrc).toMatch(/const r = await api\.saveChangeLayers[\s\S]+layersSaved\.current = \{ noteId: id, payload \}/)
    const call = appSrc.indexOf('const r = await api.saveChangeLayers')
    const mark = appSrc.indexOf('layersSaved.current = { noteId: id, payload }', call)
    expect(mark).toBeGreaterThan(call)
  })
})
