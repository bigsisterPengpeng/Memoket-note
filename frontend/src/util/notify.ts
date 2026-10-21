/** Send a system notification when the window is not in the foreground -- Smart Continue / sectioned writing / ingest that ran for minutes has finished,
 *  and the user has most likely switched to another window. Not sent in the foreground (the toast is right there). Electron's renderer
 *  can use Web Notification directly; if denied or unsupported, stay silent. */
export function notifyIfHidden(title: string, body = ''): void {
  try {
    if (typeof Notification === 'undefined') return
    if (!document.hidden && document.hasFocus()) return
    if (Notification.permission === 'denied') return
    const fire = () => { try { new Notification(title, { body, silent: true }) } catch { /* does not matter */ } }
    if (Notification.permission === 'granted') fire()
    else void Notification.requestPermission().then((p) => { if (p === 'granted') fire() })
  } catch { /* does not matter */ }
}
