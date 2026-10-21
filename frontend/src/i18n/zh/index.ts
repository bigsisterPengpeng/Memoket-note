/**
 * Chinese dictionary: key = English source text, value = Chinese. Split into shards by
 * origin (`common.ts` for phrases used in many places) and merged here. A key may appear
 * in only one shard (`scripts/check-i18n.mts` rejects duplicates).
 */
import { COMMON } from './common'
import { APP } from './app'
import { COMPONENTS_A } from './components_a'
import { COMPONENTS_B } from './components_b'
import { EDITOR } from './editor'
import { UTIL } from './util'
import { TEMPLATES } from './templates'
import { SETTINGS } from './settings'
import { VOICE } from './voice'

export const ZH: Record<string, string> = {
  ...COMMON,
  ...APP,
  ...COMPONENTS_A,
  ...COMPONENTS_B,
  ...EDITOR,
  ...UTIL,
  ...TEMPLATES,
  ...SETTINGS,
  ...VOICE,
}
