// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const calls = vi.hoisted(() => ({ obsidian: vi.fn(), remotes: vi.fn(), toast: vi.fn(), action: vi.fn() }))
vi.mock('../../api', async () => ({ ...await vi.importActual<Record<string, unknown>>('../../api'), exportObsidian: calls.obsidian, noteRemotes: calls.remotes }))
vi.mock('../../toast', () => ({ toast: calls.toast, toastAction: calls.action }))
import ExportNotePanel from '../ExportNotePanel'
import ExportBack from '../ExportBack'
import { exportOutcome, remoteUrl, VAULT_KEY } from '../../util/useExportBack'

let root: Root | undefined
let host: HTMLDivElement
beforeEach(() => {
  localStorage.clear()
  calls.obsidian.mockReset().mockResolvedValue({ written: 0, skipped: 0, conflicts: ['Maple report.md'] })
  calls.remotes.mockReset().mockResolvedValue([])
  calls.toast.mockClear()
  calls.action.mockClear()
})
afterEach(async () => {
  await act(async () => { root?.unmount() })
  root = undefined
  document.body.innerHTML = ''
})
async function mount(library = false) {
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => { root!.render(library ? <ExportBack /> : <ExportNotePanel noteId="fictional-maple" title="Fictional Maple report" onClose={() => {}} onMarkdown={() => {}} />) })
}
function button(text: string) {
  const result = Array.from(host.querySelectorAll('button')).find(el => el.textContent === text)
  expect(result).toBeDefined(); return result!
}
async function typeVault(value: string) {
  const input = host.querySelector<HTMLInputElement>('[aria-label="Obsidian vault folder path"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}
async function click(el: HTMLElement) { await act(async () => { el.click() }) }

it('reports the kept existing file and leaves overwrite off', async () => {
  await mount(); await typeVault('/fictional/vault-a'); await click(button('Write to Obsidian'))
  expect(calls.obsidian).toHaveBeenCalledWith('/fictional/vault-a', ['fictional-maple'], false)
  expect(host.querySelector('[role="status"]')?.textContent).toContain('Existing files kept: Maple report.md')
  expect(host.querySelector<HTMLInputElement>('[type="checkbox"]')?.checked).toBe(false)
  expect(calls.toast).toHaveBeenCalledWith('Kept the existing file. Review it before choosing overwrite.', 'error')
})
it('requires a new overwrite choice after the vault or destination changes', async () => {
  await mount(); await typeVault('/fictional/vault-a')
  await click(host.querySelector<HTMLInputElement>('[type="checkbox"]')!); await click(button('Write to Obsidian'))
  expect(calls.obsidian).toHaveBeenLastCalledWith('/fictional/vault-a', ['fictional-maple'], true)
  await typeVault('/fictional/vault-b')
  expect(host.querySelector<HTMLInputElement>('[type="checkbox"]')?.checked).toBe(false)
  await click(host.querySelector<HTMLInputElement>('[type="checkbox"]')!); await click(button('Notion'))
  expect(host.querySelector<HTMLInputElement>('[type="checkbox"]')?.checked).toBe(false)
})
it('resets library overwrite when the vault changes', async () => {
  await mount(true); await typeVault('/fictional/vault-a'); await click(host.querySelector<HTMLInputElement>('[type="checkbox"]')!)
  await typeVault('/fictional/vault-b')
  expect(host.querySelector<HTMLInputElement>('[type="checkbox"]')?.checked).toBe(false)
})
it('clears the earlier result when a new export fails', async () => {
  await mount(); await typeVault('/fictional/vault-a'); await click(button('Write to Obsidian'))
  expect(host.querySelector('[role="status"]')).not.toBeNull()
  calls.obsidian.mockRejectedValueOnce(new Error('Connection unavailable'))
  await click(button('Write to Obsidian'))
  expect(host.querySelector('[role="status"]')).toBeNull()
  expect(calls.action).toHaveBeenCalledWith('Connection unavailable', 'Copy', expect.any(Function), 15000, 'error')
})
it('reports attachment repair and failures truthfully', () => {
  expect(exportOutcome({ skipped: 1, assets_written: 2 }, 'obsidian')).toMatchObject({ kind: 'ok', text: 'Restored 2 attachments; note text is unchanged.' })
  expect(exportOutcome({ written: 0, failed: ['Maple.md: No space left'] }, 'obsidian')).toMatchObject({ kind: 'error' })
  expect(exportOutcome({ written: 0, skipped: 0 }, 'obsidian')).toMatchObject({ kind: 'none', text: 'No notes to export' })
  expect(exportOutcome({ updated: 1 }, 'notion')).toMatchObject({ kind: 'ok', text: 'Exported 1 notes back' })
})
it('opens the recorded vault after the input changes and supports old receipts', () => {
  localStorage.setItem(VAULT_KEY, '/fictional/vault-b')
  const saved = { platform: 'obsidian', remote_id: 'fictional-hash', remote_path: 'Maple.md', remote_rev: '/fictional/vault-a', exported_at: '' }
  expect(decodeURIComponent(remoteUrl(saved))).toBe('obsidian://open?path=/fictional/vault-a/Maple.md')
  expect(decodeURIComponent(remoteUrl({ ...saved, remote_rev: '' }))).toBe('obsidian://open?path=/fictional/vault-b/Maple.md')
})
