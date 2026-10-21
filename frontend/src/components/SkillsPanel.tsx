import { useEffect, useState } from 'react'
import { splitSkillName } from '../util/skillName'
import { friendlyError } from '../util/friendlyError'
import * as api from '../api'
import type { Skill, SkillIn, SkillScope } from '../api'
import { parseSkillMd } from '../skillImport'
import { toast, toastAction } from '../toast'
import Icon from './Icon'
import { t } from '../i18n'

const EMPTY_FORM: SkillIn = { name: '', description: '', scopes: [], content: '', enabled: true }

/**
 * The management panel after the writing prompt system was turned into "skills": each skill is an extra instruction stacked
 * after the base prompt of some generation call site (scope); skills can be toggled, reordered,
 * and user-created. Which call sites a request applies to is decided by scopes -- reordering uses up/down
 * arrows, not drag and drop; enough, and no extra DnD dependency.
 */
export default function SkillsPanel({ onClose, embedded = false }: { onClose?: () => void; embedded?: boolean }) {
  const [skills, setSkills] = useState<Skill[]>([])
  const [scopes, setScopes] = useState<SkillScope[]>([])
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState<'new' | string | null>(null)
  const [form, setForm] = useState<SkillIn>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  // Import a third-party skill: paste SKILL.md text / fetch from a URL / upload a .md file, pick
  // one; once parsed they all land in the same review form, the same "preview before saving" flow as
  // manual creation and AI generation, never persisted straight after parsing.
  const [showImport, setShowImport] = useState(false)
  const [importRaw, setImportRaw] = useState('')
  const [importUrl, setImportUrl] = useState('')
  const [importFetching, setImportFetching] = useState(false)

  const [showGenerate, setShowGenerate] = useState(false)
  const [generateGoal, setGenerateGoal] = useState('')
  const [generating, setGenerating] = useState(false)


  function reload() {
    return Promise.all([api.listSkills(), api.listSkillScopes()]).then(([s, sc]) => {
      setSkills(s)
      setScopes(sc)
      setLoading(false)
    }).catch((e) => { setLoading(false); toast(t('Could not load skills: {err}', { err: friendlyError(e) }), 'error') })
  }
  useEffect(() => { void reload() }, [])

  function scopeLabel(value: string) {
    return scopes.find((s) => s.value === value)?.label ?? value
  }

  async function toggle(skill: Skill) {
    try {
      const updated = await api.toggleSkill(skill.id)
      setSkills((prev) => prev.map((s) => (s.id === skill.id ? updated : s)))
    } catch (e) { toast(t('Could not toggle: {err}', { err: friendlyError(e) }), 'error') }
  }

  async function move(skill: Skill, dir: -1 | 1) {
    const idx = skills.findIndex((s) => s.id === skill.id)
    const swapWith = idx + dir
    if (swapWith < 0 || swapWith >= skills.length) return
    const next = [...skills]
    ;[next[idx], next[swapWith]] = [next[swapWith], next[idx]]
    setSkills(next) // optimistic update, so the panel appears to move immediately
    await api.reorderSkills(next.map((s) => s.id))
  }

  function startEdit(skill: Skill) {
    setEditing(skill.id)
    setForm({ name: skill.name, description: skill.description, scopes: skill.scopes,
              content: skill.content, enabled: skill.enabled })
  }

  function startNew() {
    setEditing('new')
    setForm(EMPTY_FORM)
  }

  /** All three entry points (paste text / URL / file) go through this one function after parsing -- name/
   * description are filled if they can be parsed; scopes are always left empty: a SKILL.md is written for
   * Claude Code's own agent loop and does not know which MEMOKET_NOTE
   * scope it maps to, so the user must choose. */
  function applyImportedText(raw: string) {
    const parsed = parseSkillMd(raw)
    setForm({ name: parsed.name, description: parsed.description, scopes: [],
              content: parsed.content, enabled: true })
    setShowImport(false)
    setImportRaw('')
    setImportUrl('')
    setEditing('new')
    if (!parsed.name) {
      toast(t('No standard SKILL.md frontmatter found; name and description are left empty, the body is filled in — check that the content is right'))
    }
  }

  async function fetchImportUrl() {
    if (!importUrl.trim()) return
    setImportFetching(true)
    try {
      const res = await fetch(importUrl.trim())
      if (!res.ok) throw new Error(`${res.status}`)
      const text = await res.text()
      applyImportedText(text)
    } catch (e) {
      toast(t('Fetch failed: {err} — most likely a cross-origin restriction; paste the SKILL.md content manually instead', { err: friendlyError(e) }), 'error')
    } finally {
      setImportFetching(false)
    }
  }

  function handleFileUpload(file: File | undefined) {
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => applyImportedText(String(reader.result ?? ''))
    reader.readAsText(file)
  }

  async function generate() {
    if (!generateGoal.trim()) return
    setGenerating(true)
    try {
      const draft = await api.generateSkill(generateGoal.trim())
      setForm(draft)
      setShowGenerate(false)
      setGenerateGoal('')
      setEditing('new')
    } catch (e) {
      toast(t('Generation failed: {err}', { err: friendlyError(e) }), 'error')
    } finally {
      setGenerating(false)
    }
  }

  function toggleFormScope(value: string) {
    setForm((f) => ({
      ...f,
      scopes: f.scopes.includes(value) ? f.scopes.filter((v) => v !== value) : [...f.scopes, value],
    }))
  }

  async function save() {
    if (!form.name.trim() || !form.content.trim() || form.scopes.length === 0) {
      toast(t('Name, scope and content are all required'), 'error')
      return
    }
    setSaving(true)
    try {
      if (editing === 'new') {
        await api.createSkill(form)
      } else if (editing) {
        await api.updateSkill(editing, form)
      }
      setEditing(null)
      void reload()
    } catch (e) {
      toast(t('Save failed: {err}', { err: friendlyError(e) }), 'error')
    } finally {
      setSaving(false)
    }
  }


  function remove(skill: Skill) {
    setSkills((prev) => prev.filter((s) => s.id !== skill.id))
    let undone = false
    const timer = setTimeout(() => {
      if (!undone) api.deleteSkill(skill.id).catch((e) => { toast(t('Delete failed: {err}', { err: friendlyError(e) }), 'error'); void reload() })
    }, 5000)
    toastAction(t('Deleted “{name}”', { name: skill.name }), t('Undo'), () => {
      undone = true
      clearTimeout(timer)
      void reload()
    })
  }

  /** "Delete" on a built-in is really restore defaults: the directory is removed and the next listing re-seeds the factory copy.
   *  No optimistic update -- what matters here is **seeing it return to its original state**, not seeing it disappear. */
  async function restore(skill: Skill) {
    try {
      await api.deleteSkill(skill.id)
      await reload()
      toast(t('“{name}” reset to default', { name: splitSkillName(skill.name).head }))
    } catch (e) {
      toast(t('Restore failed: {err}', { err: friendlyError(e) }), 'error')
    }
  }

  return (
    <div className={embedded ? 'embedded-panel' : 'palette-backdrop'} onClick={embedded ? undefined : onClose}>
      <div
        className={embedded ? '' : 'panel-dialog skills-dialog'}
        onClick={(e) => e.stopPropagation()}
      >
        {!embedded && (
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h2 style={{ margin: 0 }}><Icon n="bx-extension" /> {t('Writing Skills')}</h2>
            <button className="icon-btn" title={t('Close (Esc)')} aria-label={t('Close')} onClick={onClose}><Icon n="bx-x" /></button>
          </div>
        )}
        <p className="muted" style={{ fontSize: 'var(--t-md)', margin: '6px 0 12px' }}>
          {t('Each skill is an extra instruction layered on top of the base rules of a generation action (Continue / Verify / Rewrite…); you can toggle, reorder and create them.')}
        </p>
        {}
        <p className="muted skills-rule" style={{ fontSize: 'var(--t-sm)', margin: '0 0 12px', lineHeight: 1.7 }}>
          <strong>{t('When it applies: ')}</strong>{t('Enabled skills with a ticked scope are ')}<strong>{t('included in full automatically')}</strong>
          {t(' when that feature runs (the round cards under “Agent activity” list which ones were included). Skills without a scope (the default for imported third-party Skills) only go on the “available skills” list, ')}
          {t('loaded by the model only when needed in Smart Continue, section writing and ')}<code>/</code>{t(' block generation — ')}<strong>{t('on demand')}</strong>{t('; one-shot features such as Continue, Verify, Rewrite and Polish have no tools and never load them.')}
        </p>

        {loading ? (
          <span className="spinner" />
        ) : editing ? (
          <div className="stack">
            <input aria-label={t('Skill name')}
              placeholder={t('Name')}
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
            <input aria-label={t('Skill description')}
              placeholder={t('One-line description (optional)')}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
            <div>
              <div className="muted" style={{ fontSize: 'var(--t-sm)', marginBottom: 4 }}>{t('Scope (pick at least one)')}</div>
              <div className="row" style={{ flexWrap: 'wrap', gap: 4 }}>
                {scopes.map((sc) => (
                  <label
                    key={sc.value}
                    className="badge"
                    style={{ cursor: 'pointer', background: form.scopes.includes(sc.value) ? 'var(--accent)' : undefined,
                            color: form.scopes.includes(sc.value) ? '#fff' : undefined }}
                  >
                    <input
                      type="checkbox"
                      checked={form.scopes.includes(sc.value)}
                      onChange={() => toggleFormScope(sc.value)}
                      style={{ display: 'none' }}
                    />
                    {sc.label}
                  </label>
                ))}
              </div>
            </div>
            <textarea aria-label={t('Skill content')}
              rows={6}
              placeholder={t('The instruction itself — appended verbatim after the base rules of the matching action')}
              value={form.content}
              onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
            />
            <label className="row" style={{ fontSize: 'var(--t-md)' }}>
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
              />
              {t('Enabled')}
            </label>
            <div className="row">
              <button className="primary" onClick={save} disabled={saving}>
                {saving ? <span className="spinner" /> : t('Save')}
              </button>
              <button onClick={() => setEditing(null)}>{t('Cancel')}</button>
            </div>
          </div>
        ) : showImport ? (
          <div className="stack">
            <p className="muted" style={{ fontSize: 'var(--t-sm)' }}>
              {t('Import a Claude Skill’s SKILL.md (yaml frontmatter + markdown body) — only name/description/body are used; the scripts and reference files that skill packs often ship are not (MEMOKET_NOTE calls the raw API and cannot "run" them).')}
            </p>
            <div className="row">
              <input aria-label={t('SKILL.md file URL')}
                placeholder={t('Raw file URL of SKILL.md (e.g. raw.githubusercontent.com/...)')}
                value={importUrl}
                onChange={(e) => setImportUrl(e.target.value)}
                style={{ flex: 1 }}
              />
              <button onClick={fetchImportUrl} disabled={importFetching || !importUrl.trim()} title={!importUrl.trim() ? t('Enter the SKILL.md address first') : undefined}>
                {importFetching ? <span className="spinner" /> : t('Fetch')}
              </button>
            </div>
            <label className="muted" style={{ fontSize: 'var(--t-sm)', cursor: 'pointer' }}>
              {t('Or upload a local .md file')}
              <input type="file" accept=".md,.markdown,.txt" style={{ display: 'none' }}
                     onChange={(e) => handleFileUpload(e.target.files?.[0])} />
            </label>
            <textarea aria-label={t('SKILL.md content')}
              rows={8}
              placeholder={t('Or paste the SKILL.md content here')}
              value={importRaw}
              onChange={(e) => setImportRaw(e.target.value)}
            />
            <div className="row">
              <button className="primary" onClick={() => applyImportedText(importRaw)} disabled={!importRaw.trim()}
                      title={!importRaw.trim() ? t('Paste the skill content into the box above first') : undefined}>
                {t('Parse and preview')}
              </button>
              <button onClick={() => { setShowImport(false); setImportRaw(''); setImportUrl('') }}>{t('Cancel')}</button>
            </div>
          </div>
        ) : showGenerate ? (
          <div className="stack">
            <p className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('Describe the writing behavior you want in a sentence or two and let the model draft a skill — you still get a preview; edit it, pick a scope, then save.')}</p>
            <textarea aria-label={t('What the generated skill should do')}
              rows={3}
              placeholder={t('e.g. When continuing, quote concrete meeting decisions verbatim instead of paraphrasing abstractly')}
              value={generateGoal}
              onChange={(e) => setGenerateGoal(e.target.value)}
            />
            <div className="row">
              <button className="primary" onClick={generate} disabled={generating || !generateGoal.trim()} title={!generateGoal.trim() ? t('Describe the writing you want first') : undefined}>
                {generating ? <span className="spinner" /> : t('Generate')}
              </button>
              <button onClick={() => { setShowGenerate(false); setGenerateGoal('') }}>{t('Cancel')}</button>
            </div>
          </div>
        ) : (
          <div className="stack">
            <div className="row">
              <button onClick={startNew}><Icon n="bx-plus" /> {t('New skill')}</button>
              <button onClick={() => setShowImport(true)}><Icon n="bx-download" /> {t('Import third-party Skill')}</button>
              <button onClick={() => setShowGenerate(true)}><Icon n="bx-brush-alt" /> {t('AI generate')}</button>
            </div>
            {skills.map((sk, i) => (
              <div key={sk.id} className="card">
                {}
                <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'nowrap', gap: 8 }}>
                  <div className="row" style={{ gap: 6, minWidth: 0, flexWrap: 'nowrap' }}>
                    <button
                      title={sk.enabled ? t('Click to dismiss') : t('Click to enable')}
                      onClick={() => toggle(sk)}
                      style={{ padding: '2px 8px', flexShrink: 0, borderColor: sk.enabled ? 'var(--ins)' : undefined,
                              color: sk.enabled ? 'var(--ins)' : 'var(--muted)' }}
                    >
                      {sk.enabled ? '● ' + t('Enabled') : '○ ' + t('Disabled')}
                    </button>
                    <strong title={sk.name} style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{splitSkillName(sk.name).head}</strong>
                    {sk.builtin && <span className="muted" style={{ fontSize: 'var(--t-xs)', flexShrink: 0 }} title={t('Ships with the app and cannot be deleted; turn it off with the switch on the left if you do not want it')}>{t('Built-in')}</span>}
                  </div>
                  <div className="row" style={{ gap: 2, flexShrink: 0, flexWrap: 'nowrap' }}>
                    <button className="icon-btn" aria-label={t('Move up')} onClick={() => move(sk, -1)} disabled={i === 0} title={t('Move up')}><Icon n="bx-chevron-up" /></button>
                    <button className="icon-btn" aria-label={t('Move down')} onClick={() => move(sk, 1)} disabled={i === skills.length - 1} title={t('Move down')}><Icon n="bx-chevron-down" /></button>
                    <button className="icon-btn" aria-label={t('Edit')} onClick={() => startEdit(sk)} title={t('Edit')}><Icon n="bx-pencil" /></button>
                    {/* Built-ins cannot be deleted: after deleting, the next listing re-seeds them from the factory copy (measured in a real run).
                        So what is offered here is what it really does -- restore defaults. If you do not want it, use the switch on the left. */}
                    {sk.builtin
                      ? <button className="icon-btn" aria-label={t('Reset to default')} onClick={() => restore(sk)} title={t('Reset to default: discard my edits to this skill; its switch and order return to default')}><Icon n="bx-reset" /></button>
                      : <button className="icon-btn" aria-label={t('Delete')} onClick={() => remove(sk)} title={t('Delete (undo within 5 seconds)')}><Icon n="bx-x" /></button>}
                  </div>
                </div>
                {/* Attribution ("inspired by brainstorming"): credit **that should stay**, it just should not crowd the title */}
                {splitSkillName(sk.name).note && (
                  <p className="muted" style={{ fontSize: 'var(--t-xs)', margin: '4px 0 0' }}>{splitSkillName(sk.name).note}</p>
                )}
                {sk.description && <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: '4px 0' }}>{sk.description}</p>}
                <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
                  {sk.scopes.map((s) => <span key={s} className="badge">{scopeLabel(s)}</span>)}
                  {sk.scopes.length === 0 && <span className="badge muted" title={t('No scope ticked: not included automatically; loaded on demand by the model only in features with tools')}>{t('No scope · loaded on demand by the model only')}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
