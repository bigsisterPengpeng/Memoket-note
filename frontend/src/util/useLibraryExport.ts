import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getUser } from '../api'
import { t } from '../i18n'
import { toastAction } from '../toast'
import { friendlyError } from './friendlyError'
import { downloadLibrary } from './markdownExport'

export function useLibraryExport(flush: () => Promise<void>) {
  const latest = useRef(flush)
  const pending = useRef(false)
  const [busy, setBusy] = useState(false)
  useLayoutEffect(() => { latest.current = flush }, [flush])

  useEffect(() => {
    let active = true
    async function run() {
      if (!active || pending.current) return
      pending.current = true
      setBusy(true)
      const user = getUser()
      try {
        await latest.current()
        if (active) downloadLibrary(user)
      } catch (error) {
        if (active) toastAction(
          t('Export cancelled: open notes could not be saved. {err}', { err: friendlyError(error) }),
          t('Retry export'), () => { void run() }, 15000, 'error',
        )
      } finally {
        pending.current = false
        if (active) setBusy(false)
      }
    }
    const onExport = () => { void run() }
    window.addEventListener('export-all', onExport)
    return () => { active = false; window.removeEventListener('export-all', onExport) }
  }, [])
  return busy
}
