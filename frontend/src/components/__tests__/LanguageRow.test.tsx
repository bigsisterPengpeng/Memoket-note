// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it } from 'vitest'
import LanguageRow from '../LanguageRow'
import { getLang, setLang } from '../../i18n'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

it('shows English language names in English mode and can switch to Chinese and back', async () => {
  setLang('en')
  const el = document.createElement('div')
  document.body.appendChild(el)
  const root = createRoot(el)
  try {
    await act(async () => root.render(<LanguageRow />))
    const options = () => [...el.querySelectorAll('option')].map((o) => o.textContent)
    expect(options()).toEqual(['English', 'Chinese'])
    expect(el.textContent).not.toMatch(/[\u3400-\u9fff]/)
    const select = el.querySelector('select')!
    await act(async () => {
      select.value = 'zh'
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
    expect(getLang()).toBe('zh')
    expect(select.getAttribute('aria-label')).toBe('\u754c\u9762\u8bed\u8a00')
    expect(options()[1]).toBe('\u4e2d\u6587')
    await act(async () => {
      select.value = 'en'
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
    expect(getLang()).toBe('en')
    expect(options()).toEqual(['English', 'Chinese'])
  } finally {
    await act(async () => root.unmount())
    el.remove()
    setLang('en')
  }
})
