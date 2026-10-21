import { useEffect, useRef, useState } from 'react'
import { useRestoreFocus } from '../util/restoreFocus'
import { blockPrecondition, MAX_PROMPT_CHARS, type SlashItem } from '../editor/slashMenu'
import Icon from './Icon'
import { t } from '../i18n'

/** The inline input box that pops up after `/` picks a feature that needs a prompt.
 *
 * The position is given by the caller from the screen coordinates of that `/` in the editor -- **not recomputed on page scroll**:
 * once it appears the user's next step is typing or pressing Esc, they will not scroll in between, so a set of
 * listeners for that is not worth it. */
export default function SlashPrompt({ item, x, y, busy, phase, onRun, onCancel }: {
  item: SlashItem
  x: number
  y: number
  busy: boolean
  phase: string
  onRun: (prompt: string) => void
  onCancel: () => void
}) {
  useRestoreFocus()   // After closing, focus returns to where it was before opening (editor / tree row)
  const [value, setValue] = useState('')

  // confirm with nothing typed, and the selected passage was wiped while the request still went out. Now the input stops it itself: no close, no send, one line of explanation.
  const [hint, setHint] = useState('')
  const ref = useRef<HTMLInputElement>(null)

  useEffect(() => { ref.current?.focus() }, [])
  // A (left) click outside / Esc anywhere counts as cancel -- same as SelectionMenu (capture phase, ahead of other click handlers).
  // Once running it does not close: the box then shows "Stop", and clicking elsewhere should not lose it.
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (busy) return
    function onDocMouseDown(e: MouseEvent) {
      if (e.button === 2) return
      if (box.current && !box.current.contains(e.target as Node)) onCancel()
    }
    function onDocKeyDown(e: KeyboardEvent) { if (e.key === 'Escape') onCancel() }
    document.addEventListener('mousedown', onDocMouseDown, true)
    document.addEventListener('keydown', onDocKeyDown)
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown, true)
      document.removeEventListener('keydown', onDocKeyDown)
    }
  }, [busy, onCancel])

  function run() {
    // The selection / body conditions are checked again upstream in `runBlock` (it has the editor); here we only check the input itself
    const why = blockPrecondition(item, value, 'x', 'x')
    if (why) { setHint(why); ref.current?.focus(); return }
    onRun(value)
  }

  const left = Math.min(Math.max(8, x), window.innerWidth - 420)
  const top = Math.min(y, window.innerHeight - 140)

  return (
    <div
      ref={box}
      className="palette"
      role="dialog" aria-label={t('AI block generation')}
      style={{ position: 'fixed', left, top, width: 400, padding: 10, zIndex: 260 }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div className="row" style={{ gap: 6, alignItems: 'center', marginBottom: 6 }}>
        <Icon n={item.icon} />
        <strong style={{ fontSize: 'var(--t-md)' }}>{t(item.label)}</strong>
        <span className="muted" style={{ fontSize: 'var(--t-xs)' }}>{t(item.hint)}</span>
      </div>
      <input aria-label={t('Instruction for the AI')}
        ref={ref}
        value={value}
        disabled={busy}
        placeholder={item.placeholder ? t(item.placeholder) : t('What should it do?')}
        maxLength={MAX_PROMPT_CHARS}
        aria-invalid={hint ? true : undefined}
        onChange={(e) => { setValue(e.target.value); if (hint) setHint('') }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.nativeEvent.isComposing) { e.preventDefault(); run() }
          if (e.key === 'Escape') { e.preventDefault(); onCancel() }
        }}
        style={{ width: '100%', boxSizing: 'border-box' }}
      />
      <div className="row" style={{ justifyContent: 'space-between', marginTop: 6, fontSize: 'var(--t-xs)' }}>
        <span className={hint ? '' : 'muted'} role={hint ? 'alert' : undefined} style={hint ? { color: 'var(--del)' } : undefined}>
          {busy ? <><span className="spinner" /> {phase || t('Running…')}</> : hint || t('Enter to start · Esc to cancel')}
        </span>
        {busy
          ? <button onClick={onCancel}>{t('Stop')}</button>
          : <button onClick={run}>{t('Start')}</button>}
      </div>
    </div>
  )
}
