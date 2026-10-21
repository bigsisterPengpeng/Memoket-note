
export function splitSkillName(raw: string): { head: string; note: string } {
  const name = (raw ?? '').trim()
  const m = /^(.*\S)\s*[\uff08(]([^\uff08()\uff09]*)[\uff09)]$/.exec(name)   // full-width or ASCII parentheses
  if (!m || !m[1] || !m[2].trim()) return { head: name, note: '' }
  return { head: m[1], note: m[2].trim() }
}
