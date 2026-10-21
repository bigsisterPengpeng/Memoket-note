export type ParsedSkill = { name: string; description: string; content: string }

/**
 * Parse a third-party Claude Skill's SKILL.md (YAML frontmatter + markdown body).
 * Only handles the common single-line "key: value" frontmatter, plus YAML folded/literal block scalars
 * ("key: >"/"key: |" followed by indented continuation lines) -- real SKILL.md files (e.g. Anthropic's
 * official discernment-nudge) almost all write description this way; without recognizing it the parse
 * yields a lone ">" character, more misleading than leaving it empty. Other complex YAML (nested
 * structures, multi-value lists) is not handled; such a field is skipped. This is not meant to be a real YAML
 * parser, which would be over-engineering for the two fields name/description.
 *
 * Only extracts name/description (to fill the form) + the body (as content). The bundled scripts/references
 * common in SKILL.md are naturally dropped -- the MEMOKET_NOTE backend calls the raw
 * chat completions API and has no mechanism to "run" those scripts; this is a known constraint explicitly
 * agreed with the user, not something this function forgot to do.
 */
export function parseSkillMd(raw: string): ParsedSkill {
  const text = raw.replace(/^﻿/, '').trim()
  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/)
  if (!match) {
    // No frontmatter: the whole text is the body, name/description left empty for the user to fill in
    return { name: '', description: '', content: text }
  }
  const [, frontmatter, body] = match
  const lines = frontmatter.split('\n')
  const fields: Record<string, string> = {}
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^([A-Za-z_][\w-]*):\s*(.*)$/)
    if (!m) continue
    const key = m[1].trim()
    const rest = m[2].trim()
    if (/^[|>][+-]?$/.test(rest)) {
      // Block scalar: the value is on the following more-indented lines; folded (">") joins with spaces, literal ("|")
      // keeps newlines, until a line whose indent returns to the key's level (or shallower).
      const folded = rest[0] === '>'
      const continued: string[] = []
      let j = i + 1
      while (j < lines.length && (lines[j] === '' || /^\s+\S/.test(lines[j]))) {
        continued.push(lines[j].trim())
        j++
      }
      fields[key] = continued.filter((l) => l !== '').join(folded ? ' ' : '\n')
      i = j - 1
    } else {
      fields[key] = rest.replace(/^["']|["']$/g, '')
    }
  }
  return {
    name: fields.name || '',
    description: fields.description || '',
    content: body.trim(),
  }
}
