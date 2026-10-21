/** "Pseudo-entities" in the knowledge base: speaker labels from recording transcripts (Speaker A / speaker_c / the CJK "speaker 1"...).
 *  Extraction treats them as entities, with the most facts of all -- the entity index, the home page top list, topic page local graphs and the topic map
 *  all need to recognize them. Defined once, used in four places. */
// Letter labels must have a separator (Speaker A / speaker_c), otherwise "speakers" and "speaker phone" would count; number labels may be glued on (Speaker1 / the CJK "speaker2")
export const SPEAKER_TAG = /^(speaker(?:[\s_-][a-z]|[\s_-]?\d{1,2})|\u8bf4\u8bdd\u4eba(?:\s?[a-z]|\s?\d{1,2})|\u53d1\u8a00\u4eba(?:\s?[a-z]|\s?\d{1,2}))$/i

export function isSpeakerTag(name: string): boolean {
  return SPEAKER_TAG.test((name ?? '').trim())
}
