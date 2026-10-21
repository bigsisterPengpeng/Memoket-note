import Logo from './Logo'
import type { Note } from '../api'
import { displayTitle } from '../util/displayTitle'
import { SHORTCUT_GROUPS } from '../shortcuts'
import { fmtShortcut } from '../util/keys'
import { fmtDate } from '../util/time'
import Icon from './Icon'
import { t } from '../i18n'


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
          <p className="muted" style={{ margin: '2px 0 0', fontSize: 'var(--t-md)' }}>{t('An agent-native writing workspace')}</p>
          <p className="muted" style={{ margin: '2px 0 0', fontSize: 'var(--t-md)' }}>
            {notes.length === 0 ? t('Start with a note or an import.') : t('{n} notes · {facts} knowledge base facts', { n: notes.length, facts: factCount.toLocaleString() })}
          </p>
        </div>
      </div>

      <div className="welcome-cards">
        <button className="welcome-card" onClick={onNew}>
          <Icon n="bx-plus" />
          <b>{t('New note')}</b>
          <span className="muted">{t('Click “Continue” mid-draft; it checks your knowledge base before writing on.')}</span>
          <kbd>{fmtShortcut('⌘N')}</kbd>
        </button>
        <button className="welcome-card" onClick={onImport}>
          <Icon n="bx-import" />
          <b>{t('Import')}</b>
          <span className="muted">{t('Markdown, Obsidian, Evernote, Notion, Apple Notes, or a batch of recordings / PDFs into the knowledge base.')}</span>
        </button>
        <button className="welcome-card" onClick={() => onOpen(factCount > 0 ? 'kb' : 'app:import')}>
          <Icon n="bx-data" />
          <b>{t('Knowledge base')}</b>
          <span className="muted">{factCount > 0 ? t('Overview, topic map, timeline — every node is a page.') : t('Still empty — import one meeting recording to fill it.')}</span>
        </button>
        {/* Only the desktop app can capture; showing it on the web build would just lead to "use the desktop app".
            It is here because **new users never click that monitor icon in the left bar for no reason** --
            a feature that is off by default, if never introduced once, might as well not exist. */}
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
