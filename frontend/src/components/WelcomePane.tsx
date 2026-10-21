import Logo from './Logo'
import type { Note } from '../api'
import { displayTitle } from '../util/displayTitle'
import { SHORTCUT_GROUPS } from '../shortcuts'
import { fmtShortcut } from '../util/keys'
import { fmtDate } from '../util/time'
import Icon from './Icon'
import { t } from '../i18n'
import WritingFlow from './WritingFlow'


export default function WelcomePane({ notes, factCount, onNew, onImport, onOpen, onOpenNote, onShortcuts }: {
  notes: Note[]
  factCount: number
  onNew: () => void
  onImport: () => void
  onOpen: (virtualId: string) => void
  onOpenNote: (n: Note) => void
  onShortcuts: () => void
}) {
  const recent = [...notes].sort((a, b) => (b.updated_at > a.updated_at ? 1 : -1)).slice(0, 6)
  const keys = SHORTCUT_GROUPS.flatMap((g) => g.items).filter((i) => ['⌘N / ⌘T', '⌘K / ⌘J', '/', '@'].includes(i.keys))
  return (
    <div className="welcome">
      <div className="row" style={{ gap: 12, alignItems: 'center' }}>
        <Logo size={40} />
        <div>
          <h2 style={{ margin: 0 }}>MEMOKET NOTE</h2>
          <p className="muted" style={{ margin: '2px 0 0', fontSize: 'var(--t-md)' }}>
            {notes.length === 0 ? t('Start with a note or an import.') : t('{n} notes · {facts} knowledge base facts', { n: notes.length, facts: factCount.toLocaleString() })}
          </p>
        </div>
      </div>

      <div className="welcome-intro">
        <h1>{t('A writing agent that remembers your work.')}</h1>
        <p className="muted">{t('An agent-native writing workspace. Bring your notes, put past knowledge to work, and take your next draft with you.')}</p>
      </div>
      <WritingFlow />

      <div className="welcome-cards">
        <button className="welcome-card" onClick={onImport}>
          <Icon n="bx-import" />
          <b>{t('Bring your notes')}</b>
          <span className="muted">{t('Import from Notion, Apple Notes on macOS, Obsidian, Evernote or local files.')}</span>
        </button>
        <button className="welcome-card" onClick={onNew}>
          <Icon n="bx-plus" />
          <b>{t('Start a draft')}</b>
          <span className="muted">{t('Choose a writing goal. Continue retrieves relevant knowledge before writing.')}</span>
          <kbd>{fmtShortcut('⌘N')}</kbd>
        </button>
        <button className="welcome-card" onClick={() => onOpen(factCount > 0 ? 'kb' : 'app:import')}>
          <Icon n="bx-data" />
          <b>{t('Explore your memory')}</b>
          <span className="muted">{factCount > 0 ? t('Revisit saved facts, dates and source evidence, ready for your next draft.') : t('Import notes and extract knowledge to build a memory you can return to.')}</span>
        </button>
        {window.memoketDesktop?.journey && (
          <button className="welcome-card" onClick={() => onOpen('app:journey')}>
            <Icon n="bx-desktop" />
            <b>{t('Screen activity')}</b>
            <span className="muted">{t('Notes what you are doing every little while and compiles a daily summary in the evening. Off by default; it tells you what it records before you turn it on.')}</span>
          </button>
        )}
      </div>

      {recent.length > 0 && (
        <section>
          <p className="muted palette-group" style={{ marginInline: 0 }}>{t('Recently edited')}</p>
          <div className="welcome-recent">
            {recent.map((n) => (
              <a key={n.id} className="kb-link" onClick={() => onOpenNote(n)}>
                <Icon n={(n.icon || 'bx-note')} /> <span className="ellipsis">{displayTitle(n)}</span>
                <span className="muted" style={{ marginInlineStart: 'auto', fontSize: 'var(--t-xs)' }}>{fmtDate(n.updated_at)}</span>
              </a>
            ))}
          </div>
        </section>
      )}

      <section>
        <p className="muted palette-group" style={{ marginInline: 0 }}>{t('Common shortcuts')} <a className="link" onClick={onShortcuts}>{t('All')} {fmtShortcut('⌘/')}</a></p>
        <div className="welcome-keys">
          {keys.map((k) => <div key={k.keys} className="shortcut-row"><kbd>{fmtShortcut(t(k.keys))}</kbd><span>{t(k.what)}</span></div>)}
        </div>
      </section>
    </div>
  )
}
