import { describe, expect, it } from 'vitest'
import { isSpeakerTag } from '../../util/kbNoise'

describe('isSpeakerTag (same regex as backend kb/who.is_speaker_tag)', () => {
  it('speaker labels from recording transcripts count as pseudo-entities', () => {
    for (const s of ['Speaker A', 'speaker_c', 'speaker-1', 'SPEAKER b', '\u8bf4\u8bdd\u4eba 1', '\u8bf4\u8bdd\u4eba2', '\u53d1\u8a00\u4eba a', ' speaker a ']) expect(isSpeakerTag(s)).toBe(true)   // includes CJK "speaker" labels
  })
  it('real entities do not count', () => {
    for (const s of ['Facebook', 'speaker phone', 'speakers', '\u8bf4\u8bdd\u4eba\u4eec', '', 'app']) expect(isSpeakerTag(s)).toBe(false)   // CJK "speakers" (plural) is not a label
  })
})
