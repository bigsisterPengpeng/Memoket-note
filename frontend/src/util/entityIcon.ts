
const ORG_SUFFIX = ['\u516c\u53f8', '\u79d1\u6280', '\u6709\u9650', '\u96c6\u56e2', '\u5de5\u5382', '\u5b9e\u9a8c\u5ba4', '\u7814\u7a76\u9662', '\u4e8b\u52a1\u6240', '\u94f6\u884c', '\u533b\u9662']
const EDU_SUFFIX = ['\u5927\u5b66', '\u5b66\u9662', '\u4e2d\u5b66', '\u5c0f\u5b66', '\u5b66\u6821', '\u9ad8\u4e2d', '\u9644\u4e2d', '\u4e66\u9662']

export const NEUTRAL_ENTITY_ICON = 'bx-purchase-tag'

export function entityIcon(name: string, etype = ''): string {
  const t = (etype || '').trim().toLowerCase()
  if (t) {
    if (t.startsWith('person') || t === '\u4eba' || t === '\u4eba\u7269') return 'bx-user'
    if (t.startsWith('place') || t.startsWith('loc') || t === '\u5730\u70b9') return 'bx-map'
    if (t.startsWith('org') || t === '\u673a\u6784' || t === '\u516c\u53f8') return 'bx-buildings'
    if (t.startsWith('product') || t === '\u4ea7\u54c1') return 'bx-package'
    return NEUTRAL_ENTITY_ICON
  }
  const s = (name || '').trim()
  if (EDU_SUFFIX.some((x) => s.endsWith(x))) return 'bx-book'
  if (ORG_SUFFIX.some((x) => s.endsWith(x))) return 'bx-buildings'
  return NEUTRAL_ENTITY_ICON
}
