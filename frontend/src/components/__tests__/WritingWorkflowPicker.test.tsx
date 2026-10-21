// @vitest-environment jsdom
/**
 * The writing mode picker holds 104 cards: category tabs + search + compact cards + one detail block.
 * A real React root is mounted and clicked / typed into -- static HTML cannot show whether search
 * really filters.
 */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it } from 'vitest'

import WritingWorkflowPicker from '../WritingWorkflowPicker'
import { setLang } from '../../i18n'
import { ZH } from '../../i18n/zh'
import { EMPTY_INTENT, type DocIntent } from '../../util/docIntent'
import { TEMPLATE_CATEGORIES, WRITING_TEMPLATES } from '../../editor/writingTemplates'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const HAN = /[\u3400-\u9fff]/
let root: Root | null = null
let el: HTMLDivElement | null = null
afterEach(async () => {
  setLang('en')
  if (root) await act(async () => { root!.unmount() })
  el?.remove(); root = null; el = null
})

async function mount(props: Partial<Parameters<typeof WritingWorkflowPicker>[0]> = {}) {
  if (root) await act(async () => { root!.unmount() })
  el?.remove()
  el = document.createElement('div'); document.body.appendChild(el)
  root = createRoot(el)
  const selected: string[] = []
  await act(async () => {
    root!.render(<WritingWorkflowPicker intent={props.intent ?? EMPTY_INTENT} resume={false}
      onSelect={(id) => selected.push(id)} onCustom={() => {}} onClose={() => {}} {...props} />)
  })
  return { el: document.body.querySelector<HTMLElement>('.workflow-picker')!, selected }
}
const cards = (e: HTMLElement) => [...e.querySelectorAll<HTMLButtonElement>('.workflow-card')]
const tabs = (e: HTMLElement) => [...e.querySelectorAll<HTMLButtonElement>('[role="tab"]')]
const titles = (e: HTMLElement) => cards(e).map((c) => c.querySelector('.workflow-card-title')?.textContent?.trim())
const typeSearch = async (e: HTMLElement, value: string) => {
  const input = e.querySelector<HTMLInputElement>('.workflow-search input')!
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
  await act(async () => { setter.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })) })
}

describe('WritingWorkflowPicker', () => {
  it('opens on Favorites: 12 tabs, 4 cards, the detail shows the four rules of the first card', async () => {
    const { el } = await mount()
    expect(el.getAttribute('aria-label')).toBe('Writing mode picker')
    expect(el.parentElement).toBe(document.body)
    expect(tabs(el)).toHaveLength(12)
    expect(tabs(el).map((b) => b.textContent)).toEqual(TEMPLATE_CATEGORIES.map((c) => c.label))
    expect(tabs(el)[0].getAttribute('aria-selected')).toBe('true')
    expect(titles(el)).toEqual(['Daily report template', 'Weekly report template', 'Journal template', 'Meeting notes template'])
    // Compact cards: the rules are not printed on the card, only in the detail
    expect(el.querySelectorAll('.workflow-card b')).toHaveLength(0)
    const detail = el.querySelector('.workflow-detail')!
    expect(detail.textContent).toContain('Daily report template')
    expect([...detail.querySelectorAll('b')].map((b) => b.textContent)).toEqual(['Sourcing', 'Writing', 'Checks', 'Finish'])
    expect(detail.textContent).toContain("Look first for today's records")
    expect(el.querySelector('.workflow-count')?.textContent).toBe('4 templates')
    expect(el.textContent).not.toMatch(HAN)
  })

  it('a tab switches category with matching card count; hovering / focusing a card moves the detail to it', async () => {
    const { el } = await mount()
    const product = tabs(el).find((b) => b.textContent === 'Product')!
    await act(async () => { product.click() })
    expect(product.getAttribute('aria-selected')).toBe('true')
    expect(cards(el)).toHaveLength(WRITING_TEMPLATES.filter((x) => x.category === 'product').length)
    const rfc = cards(el).find((c) => c.textContent?.includes('RFC / design doc'))!
    await act(async () => { rfc.dispatchEvent(new MouseEvent('mouseenter', { bubbles: false })); rfc.focus() })
    expect(el.querySelector('.workflow-detail')?.textContent).toContain('RFC / design doc')
    expect(rfc.classList.contains('workflow-card-preview')).toBe(true)
    expect(rfc.classList.contains('preview')).toBe(false)
  })

  it('previews every Engineering card on mouse hover without selecting it, then supports keyboard preview', async () => {
    const { el, selected } = await mount({ initialCategory: 'engineering' })
    const templates = WRITING_TEMPLATES.filter((item) => item.category === 'engineering')
    const buttons = cards(el)
    for (const [index, template] of templates.entries()) {
      await act(async () => {
        buttons[index].dispatchEvent(new MouseEvent('mouseover', { bubbles: true, relatedTarget: document.body }))
      })
      const detail = el.querySelector('.workflow-detail')!
      expect(detail.querySelector('.workflow-detail-title')?.textContent).toBe(template.label)
      for (const rule of Object.values(template.contract)) expect(detail.textContent).toContain(rule)
      expect(buttons[index].classList.contains('workflow-card-preview')).toBe(true)
      expect(el.querySelector('.preview')).toBeNull()
    }
    expect(selected).toEqual([])
    await act(async () => {
      buttons.at(-1)!.dispatchEvent(new MouseEvent('mouseout', { bubbles: true, relatedTarget: document.body }))
    })
    expect(el.querySelector('.workflow-detail-title')?.textContent).toBe(templates[0].label)
    await act(async () => { buttons.at(-1)!.focus() })
    expect(el.querySelector('.workflow-detail-title')?.textContent).toBe(templates.at(-1)!.label)
    expect(selected).toEqual([])
  })

  it('search spans every category in English and Chinese and tags each card with its category; empty state; a tab clears the search', async () => {
    const { el } = await mount()
    await typeSearch(el, 'postmortem')
    expect(titles(el)).toEqual(['Incident postmortem'])
    expect(el.querySelector('.workflow-card-cat')?.textContent).toBe('Reports')
    await typeSearch(el, ZH['Incident postmortem'])
    expect(titles(el)).toContain('Incident postmortem')
    expect(tabs(el).every((b) => b.getAttribute('aria-selected') === 'false')).toBe(true)
    await typeSearch(el, 'xyzzy-no-such')
    expect(cards(el)).toHaveLength(0)
    expect(el.querySelector('.workflow-empty')?.textContent).toBe('No matching templates')
    expect(el.querySelector('.workflow-detail')).toBeNull()
    await act(async () => { tabs(el).find((b) => b.textContent === 'Engineering')!.click() })
    expect(el.querySelector<HTMLInputElement>('.workflow-search input')!.value).toBe('')
    expect(cards(el)).toHaveLength(WRITING_TEMPLATES.filter((x) => x.category === 'engineering').length)
  })

  it('keeps the keyboard preview during scroll-induced mouse entry until the pointer moves', async () => {
    const { el, selected } = await mount({ initialCategory: 'engineering' })
    const buttons = cards(el)
    await act(async () => { buttons.at(-1)!.focus() })
    expect(el.querySelector('.workflow-detail-title')?.textContent).toBe('Tech debt proposal')
    await act(async () => {
      buttons[1].dispatchEvent(new MouseEvent('mouseover', { bubbles: true, relatedTarget: document.body }))
    })
    expect(el.querySelector('.workflow-detail-title')?.textContent).toBe('Tech debt proposal')
    await act(async () => { buttons[1].dispatchEvent(new MouseEvent('mousemove', { bubbles: true })) })
    expect(el.querySelector('.workflow-detail-title')?.textContent).toBe('Runbook')
    expect(selected).toEqual([])
  })

  it('tabs are keyboard reachable: Left / Right / Home / End switch category and move focus (roving tabindex)', async () => {
    const { el } = await mount()
    const list = el.querySelector<HTMLDivElement>('[role="tablist"]')!
    expect(tabs(el).filter((b) => b.tabIndex === 0)).toHaveLength(1)
    await act(async () => { list.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })) })
    expect(tabs(el)[1].getAttribute('aria-selected')).toBe('true')
    expect(document.activeElement).toBe(tabs(el)[1])
    await act(async () => { list.dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true })) })
    expect(tabs(el)[11].getAttribute('aria-selected')).toBe('true')
    await act(async () => { list.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })) })
    expect(tabs(el)[0].getAttribute('aria-selected')).toBe('true')
    await act(async () => { list.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true })) })
    expect(tabs(el)[11].getAttribute('aria-selected')).toBe('true')
  })

  it('clicking a card selects it in one step; the current workflow card says "In use" and sets the default category', async () => {
    const intent: DocIntent = { ...EMPTY_INTENT, goal: 'x', source: 'user', workflow: 'engineering' }
    const { el, selected } = await mount({ intent })
    expect(tabs(el).find((b) => b.getAttribute('aria-selected') === 'true')?.textContent).toBe('Engineering')
    const adr = cards(el).find((c) => c.textContent?.includes('Architecture decision record'))!
    await act(async () => { adr.click() })
    expect(selected).toEqual(['adr'])

    const { el: el2 } = await mount({ intent: { ...intent, workflow: 'weekly' } })
    const weekly = cards(el2).find((c) => c.textContent?.includes('Weekly report template'))!
    expect(weekly.className).toContain('active')
    expect(weekly.querySelector('em')?.textContent).toBe('In use')
  })

  it('Chinese UI: tabs, cards, detail and search box are Chinese, and English search still works', async () => {
    setLang('zh')
    const { el } = await mount({ initialCategory: 'ops' })
    expect(tabs(el).map((b) => b.textContent)).toContain(ZH['Operations & finance'])
    expect(el.querySelector('.workflow-search input')?.getAttribute('placeholder')).toBe(ZH['Search template names or descriptions'])
    expect(titles(el)[0]).toBe(ZH['Budget memo'])
    expect(el.querySelector('.workflow-detail b')?.textContent).toBe(ZH['Sourcing'])
    await typeSearch(el, 'Journal')
    expect(titles(el)).toEqual([ZH['Journal template'], ZH['Gratitude journal'], ZH['Decision journal']])
  })
})
