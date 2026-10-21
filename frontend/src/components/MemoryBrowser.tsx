import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { usePoll } from '../util/poll'
import { useIngestActive } from '../util/ingestActive'
import { createTopic, listClusters, memoryEntities, memoryTopics, topicEntityLinks } from '../api'
import type { EntityNode, TopicCluster, TopicEntityLink, TopicNode } from '../api'
import KnowledgeGraph from './KnowledgeGraph'
import { isSpeakerTag } from '../util/kbNoise'
import Icon from './Icon'
import { getLang, t } from '../i18n'

/** CJK numerals for the level filter buttons (the English UI uses Arabic numerals). */
const CJK_NUM = '\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341'


/** depth(root) = 0 -- "level 1" in the UI means depth 0, "level 2" depth <= 1, etc.
 * Same reachability-with-cycle-guard shape as closureFactCounts in
 * KnowledgeGraph, just walking parents instead of children. */
function topicDepths(topics: TopicNode[]): Map<string, number> {
  const byCode = new Map(topics.map((t) => [t.code, t]))
  const cache = new Map<string, number>()
  const visiting = new Set<string>()
  function depthOf(code: string): number {
    if (cache.has(code)) return cache.get(code)!
    if (visiting.has(code)) return 0
    visiting.add(code)
    const parents = (byCode.get(code)?.parents ?? []).filter((p) => byCode.has(p) && p !== code)
    const d = parents.length === 0 ? 0 : 1 + Math.max(...parents.map(depthOf))
    visiting.delete(code)
    cache.set(code, d)
    return d
  }
  const out = new Map<string, number>()
  for (const t of topics) out.set(t.code, depthOf(t.code))
  return out
}

/**
 * Knowledge-base visualization: overview / topic map / timeline / facts table.
 * Evidence tracing is the point -- expanding a fact in the facts table fetches /facts/{id}/sources on demand, rather than
 * querying every record's source on the list page.
 */

export default function MemoryBrowser() {
  // Poll only while an ingest job is running (util/ingestActive.ts) -- there used to be three 3-second timers always on
  const live = useIngestActive()
  const [showCreate, setShowCreate] = useState(false)
  // When embedded in the middle pane the graph follows the container width -- a hard-coded 900 overflowed narrow panes and left a big blank on wide screens
  const graphHost = useRef<HTMLDivElement>(null)
  const [graphW, setGraphW] = useState(900)
  useEffect(() => {
    const el = graphHost.current
    if (!el) return
    const ro = new ResizeObserver(() => setGraphW(Math.max(320, Math.floor(el.clientWidth))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const [topics, setTopics] = useState<TopicNode[]>([])
  const [loaded, setLoaded] = useState(false)
  const [entities, setEntities] = useState<EntityNode[]>([])
  const [links, setLinks] = useState<TopicEntityLink[]>([])
  const [newTopicCode, setNewTopicCode] = useState('')
  const [newTopicParent, setNewTopicParent] = useState('')
  const [creatingTopic, setCreatingTopic] = useState(false)
  const [newTopicError, setNewTopicError] = useState('')
  const [maxLevel, setMaxLevel] = useState<number | null>(null)
  const [showEntities, setShowEntities] = useState(true)

  // The topic map shows **clusters** by default, not all topics. 196 nodes is not a picture; the measured cost was
  // that nobody could see the shape of their own knowledge base. Open a cluster to see the topics inside (see kb-architecture
  // 6.4 "aggregate view as default, full graph as drill-down").
  const [clusters, setClusters] = useState<TopicCluster[]>([])
  const [drilled, setDrilled] = useState<string | null>(null)
  useEffect(() => { listClusters().then((r) => setClusters(r.clusters)).catch(() => {}) }, [])

  // Topics/entities/co-occurrence edges are also produced continuously in the background during extraction; they used to be fetched only when switching into the tab,
  // once (with a length===0 gate too, so switching away and back never refetched) -- with this
  // tab open while new content was extracted, the graph never grew new nodes. Now polled like the facts table.
  const fetchAll = useCallback(() => {
    memoryTopics().then((t) => { setTopics(t); setLoaded(true) }).catch(() => {})
    memoryEntities().then(setEntities).catch(() => {})
    topicEntityLinks().then(setLinks).catch(() => {})
  }, [])
  useEffect(fetchAll, [fetchAll])
  // Every 3 seconds while an ingest runs, **not fetched while the window is hidden** -- one ingest may run for over ten minutes,
  // and these three endpoints are not cheap on a 20k-fact library (util/poll)
  usePoll(fetchAll, 3000, live)

  // On a large corpus extraction also pulls out ASR noise fragments (one/two-letter abbreviations, bare numbers, orphan entities with 0 citations)

  // with plenty of noise like "bb"/"bba"/"100 dollars" mixed in. That is extraction's fault (a known weakness of the model on dirty transcripts,
  // the same class of problem as kite-constraints.md #10/#11); here we only add a
  // display-layer fallback: zero-citation and too-short noise nodes are filtered by default, and this can be turned off to see everything.
  const [hideNoiseEntities, setHideNoiseEntities] = useState(true)
  const cleanEntities = useMemo(() => {
    if (!hideNoiseEntities) return entities
    return entities.filter((e) => e.fact_count > 0
      && e.code.replace(/[^a-zA-Z0-9\u4e00-\u9fa5]/g, '').length > 1
      && !isSpeakerTag(e.name ?? e.code))                    // speaker tags from recording transcripts are not entities
  }, [entities, hideNoiseEntities])
  const cleanEntityCodes = useMemo(() => new Set(cleanEntities.map((e) => e.code)), [cleanEntities])
  const cleanLinks = useMemo(
    () => (hideNoiseEntities ? links.filter((l) => cleanEntityCodes.has(l.entity)) : links),
    [links, cleanEntityCodes, hideNoiseEntities],
  )

  // With many topics the graph gets crowded; level filtering keeps only level-1/2/3 roots and their ancestor chains -- not
  // a plain depth-equality filter, which would also cut the edges through middle levels and hide the hierarchy.
  const depths = useMemo(() => topicDepths(topics), [topics])
  const visibleTopics = useMemo(
    () => (maxLevel === null ? topics : topics.filter((t) => (depths.get(t.code) ?? 0) < maxLevel)),
    [topics, depths, maxLevel],
  )
  const visibleTopicCodes = useMemo(() => new Set(visibleTopics.map((t) => t.code)), [visibleTopics])
  const levelFilteredLinks = useMemo(
    () => (maxLevel === null ? cleanLinks : cleanLinks.filter((l) => visibleTopicCodes.has(l.topic))),
    [cleanLinks, visibleTopicCodes, maxLevel],
  )
  // Entities have no notion of "level" -- the filter only affects the part tied to topic levels: an entity that
  // ever co-occurred with any topic keeps showing only while a topic it co-occurs with is still visible; entities that never
  // co-occurred with any topic (isolated nodes on the graph anyway) are unaffected by level filtering.
  const entityCodesWithAnyTopicLink = useMemo(() => new Set(cleanLinks.map((l) => l.entity)), [cleanLinks])
  const levelFilteredEntities = useMemo(() => {
    if (maxLevel === null) return cleanEntities
    const stillLinkedCodes = new Set(levelFilteredLinks.map((l) => l.entity))
    return cleanEntities.filter((e) => !entityCodesWithAnyTopicLink.has(e.code) || stillLinkedCodes.has(e.code))
  }, [cleanEntities, levelFilteredLinks, entityCodesWithAnyTopicLink, maxLevel])
  const visibleEntities = useMemo(() => (showEntities ? levelFilteredEntities : []), [showEntities, levelFilteredEntities])
  const visibleLinks = useMemo(() => (showEntities ? levelFilteredLinks : []), [showEntities, levelFilteredLinks])

  // The topic map grows to hundreds or thousands of nodes with corpus size (see the research: Capacities mitigates this with a
  // "local graph per node"; for now we use the simplest substitute, search by name -- level filtering
  // controls "how deep to look", this is "find that one directly".
  const [nodeQuery, setNodeQuery] = useState('')
  // Cluster view: draw each cluster as one node. KnowledgeGraph needs no change at all -- a cluster
  // is just a topic with no parent, and `fact_count` is all the facts inside it.
  // Edges between clusters: the more entities two clusters share, the more related. Each cluster takes its two strongest neighbors, drawn dashed

  const clusterEdges = useMemo<{ a: string; b: string }[]>(() => {
    const topicCluster = new Map<string, string>()
    for (const c of clusters) for (const tp of c.topics) topicCluster.set(tp, c.key)
    const entClusters = new Map<string, Map<string, number>>()
    for (const l of links) {
      const ck = topicCluster.get(l.topic)
      if (!ck) continue
      const m = entClusters.get(l.entity) ?? new Map<string, number>()
      m.set(ck, (m.get(ck) ?? 0) + l.weight)
      entClusters.set(l.entity, m)
    }
    const pair = new Map<string, number>()
    for (const m of entClusters.values()) {
      const ks = [...m.keys()]
      for (let i = 0; i < ks.length; i++) for (let j = i + 1; j < ks.length; j++) {
        const k = ks[i] < ks[j] ? ks[i] + '\u0000' + ks[j] : ks[j] + '\u0000' + ks[i]
        pair.set(k, (pair.get(k) ?? 0) + Math.min(m.get(ks[i])!, m.get(ks[j])!))
      }
    }
    const best = new Map<string, { key: string; w: number }[]>()
    for (const [k, w] of pair) {
      const [a, b] = k.split('\u0000')
      best.set(a, [...(best.get(a) ?? []), { key: b, w }])
      best.set(b, [...(best.get(b) ?? []), { key: a, w }])
    }
    const out = new Set<string>()
    for (const [a, list] of best) for (const n of list.sort((x, y) => y.w - x.w).slice(0, 2)) out.add(a < n.key ? a + '\u0000' + n.key : n.key + '\u0000' + a)
    return [...out].map((k) => { const [a, b] = k.split('\u0000'); return { a, b } })
  }, [clusters, links])
  const clusterNodes = useMemo<TopicNode[]>(() => clusters.map((c) => ({
    code: c.key, parents: [], status: c.merged ? 'candidate' : 'canonical',
    aliases: c.topics, fact_count: c.facts,
  })), [clusters])

  // Drill down: only the topics inside this cluster.
  const scopedTopics = useMemo(() => {
    if (!drilled) return visibleTopics
    const inside = new Set(clusters.find((c) => c.key === drilled)?.topics ?? [])
    return visibleTopics.filter((t) => inside.has(t.code))
  }, [visibleTopics, drilled, clusters])

  const searchedTopics = useMemo(() => {
    const q = nodeQuery.trim().toLowerCase()
    if (!q) return scopedTopics
    return scopedTopics.filter((t) =>
      t.code.toLowerCase().includes(q) || t.aliases.some((a) => a.toLowerCase().includes(q)))
  }, [scopedTopics, nodeQuery])
  const searchedEntities = useMemo(() => {
    const q = nodeQuery.trim().toLowerCase()
    if (!q) return visibleEntities
    return visibleEntities.filter((e) =>
      e.name.toLowerCase().includes(q) || e.code.toLowerCase().includes(q)
      || e.aliases.some((a) => a.toLowerCase().includes(q)))
  }, [visibleEntities, nodeQuery])
  const drilledEntityCodes = useMemo(() => {
    if (!drilled) return null
    const topicCodes = new Set(scopedTopics.map((t) => t.code))
    return new Set(visibleLinks.filter((l) => topicCodes.has(l.topic)).map((l) => l.entity))
  }, [drilled, scopedTopics, visibleLinks])
  const searchedLinks = useMemo(() => {
    const topicCodes = new Set(searchedTopics.map((t) => t.code))
    const entityCodes = new Set(searchedEntities.map((e) => e.code))
    if (!nodeQuery.trim() && !drilled) return visibleLinks
    return visibleLinks.filter((l) => topicCodes.has(l.topic) && entityCodes.has(l.entity))
  }, [visibleLinks, nodeQuery, drilled, searchedTopics, searchedEntities])

  // No entities in the cluster view: a cluster co-occurring with an entity says nothing, a cluster is several
  // topics combined, and nearly every cluster touches every common entity.
  const graphTopics = drilled === null && clusters.length ? clusterNodes : searchedTopics
  const graphEntities = drilled === null && clusters.length
    ? []
    : (drilledEntityCodes ? searchedEntities.filter((e) => drilledEntityCodes.has(e.code)) : searchedEntities)
  const graphLinks = drilled === null && clusters.length ? [] : searchedLinks

  // Clicking a topic/entity = open its page (a node in the tree)
  function filterByTopic(code: string) { window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'kb:topic:' + code })) }
  function filterByEntity(code: string) { window.dispatchEvent(new CustomEvent('open-virtual', { detail: 'kb:entity:' + code })) }

  async function submitNewTopic() {
    if (!newTopicCode.trim()) return
    setCreatingTopic(true)
    setNewTopicError('')
    try {
      const created = await createTopic(newTopicCode.trim(), newTopicParent)
      setTopics((prev) => [...prev, created])
      setNewTopicCode('')
      setNewTopicParent('')
    } catch (e) {
      setNewTopicError(String(e))
    } finally {
      setCreatingTopic(false)
    }
  }

  // **Do not write the shell as a component defined inside render**: each render is a new component type,
  // so the whole subtree (force-directed graph included) remounted on every 3-second poll -- the graph jumping, zoom snapping back,
  // dragged nodes returning home, all from this one cause (client-log caught a new simulation every 1.5s).

  // With no facts at all, draw nothing and give one sentence.
  const libraryEmpty = loaded && topics.every((t) => t.fact_count === 0) && entities.length === 0
  const body = libraryEmpty ? (
    <p className="muted" style={{ fontSize: 'var(--t-md)' }}>{t('No facts yet. Import meeting notes or save notes to the knowledge base, and a graph of topics and entities will grow here.')}</p>
  ) : (
    <>
        {(
          <div className="stack">
            {showCreate && <div className="filter-row">
              <input aria-label={t('New topic name')}
                placeholder={t('New topic name')}
                value={newTopicCode}
                onChange={(e) => setNewTopicCode(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && submitNewTopic()}
                style={{ width: 160 }}
              />
              <select aria-label={t('Parent topic')} value={newTopicParent} onChange={(e) => setNewTopicParent(e.target.value)}>
                <option value="">{t('(as a root topic)')}</option>
                {topics.map((t) => (
                  <option key={t.code} value={t.code}>{t.code}</option>
                ))}
              </select>
              <button onClick={submitNewTopic} disabled={!newTopicCode.trim() || creatingTopic} title={!newTopicCode.trim() ? t('Enter a topic name first') : undefined}>
                {creatingTopic ? <span className="spinner" /> : '+ ' + t('New topic')}
              </button>
              {newTopicError && <span className="muted" style={{ color: 'var(--del)' }}>{newTopicError}</span>}
            </div>}

            {/* Toolbar: one row of breadcrumbs (all clusters › a cluster), one row of filters. Level filtering is meaningless in the cluster view, so hide it */}
            {clusters.length > 0 && (
              <div className="filter-row" style={{ gap: 6 }}>
                <button className={'chip' + (drilled === null ? ' active' : '')} onClick={() => setDrilled(null)}>
                  <Icon n="bx-network-chart" />{t('All clusters')} <span className="chip-count">{clusters.length}</span>
                </button>
                {drilled !== null && (
                  <>
                    <Icon n="bx-chevron-right" className="muted" />
                    <span className="chip active"><Icon n="bx-hash" />{clusters.find((c) => c.key === drilled)?.label ?? drilled}</span>
                    <span className="muted" style={{ fontSize: 'var(--t-sm)' }}>
                      {t('{n} topics', { n: scopedTopics.length })} · {t('{n} facts', { n: clusters.find((c) => c.key === drilled)?.facts ?? 0 })}
                    </span>
                  </>
                )}
                {drilled === null && (
                  <span className="muted" style={{ fontSize: 'var(--t-sm)' }}>
                    {t('Click a cluster to see its topics and entities. Cluster = topics that keep appearing in the same meetings; dashed line = two clusters share many entities.')}
                  </span>
                )}
              </div>
            )}

            <div className="filter-row">
              <div className="quick-search" style={{ minWidth: 200 }}>
                <Icon n="bx-search" />
                <input aria-label={t('Find node')} placeholder={t('Find node…')} value={nodeQuery} onChange={(e) => setNodeQuery(e.target.value)} />
                {nodeQuery && <button className="icon-btn" title={t('Clear')} aria-label={t('Clear search')} onClick={() => setNodeQuery('')}><Icon n="bx-x" /></button>}
              </div>
              {(drilled !== null || clusters.length === 0) && (
                <>
                  <span className="muted" style={{ fontSize: 'var(--t-sm)' }}>{t('Level')}</span>
                  <button className={'chip' + (maxLevel === null ? ' active' : '')} onClick={() => setMaxLevel(null)}>{t('All')}</button>
                  {Array.from({ length: Math.max(1, ...depths.values()) + 1 }, (_, i) => i + 1).map((lvl) => (
                    <button key={lvl} className={'chip' + (maxLevel === lvl ? ' active' : '')} onClick={() => setMaxLevel(lvl)}>
                      {t('Level {n}', { n: getLang() === 'en' ? lvl : (CJK_NUM[lvl - 1] ?? lvl) })}
                    </button>
                  ))}
                  <button className={'chip' + (showEntities ? ' active' : '')} onClick={() => setShowEntities((v) => !v)} title={t('Show or hide entity nodes')}>
                    <Icon n="bx-user" />{t('Entities')}
                  </button>
                  <button className={'chip' + (hideNoiseEntities ? ' active' : '')} onClick={() => setHideNoiseEntities((v) => !v)}
                          title={t('Filter out noisy entities with zero citations or very short names (abbreviation fragments common in transcript extraction)')}>
                    <Icon n="bx-filter-alt" />{t('Filter noise')}
                  </button>
                </>
              )}
              <button className="chip" onClick={() => setShowCreate((v) => !v)} title={t('Add a topic manually')} style={{ marginInlineStart: 'auto' }}><Icon n="bx-plus" />{t('New topic')}</button>
            </div>

            <div ref={graphHost} />
            <KnowledgeGraph
              topics={graphTopics}
              entities={graphEntities}
              links={graphLinks}
              topicLinks={drilled === null && clusters.length ? clusterEdges : []}
              onSelect={(kind, code) => {
                if (kind !== 'topic') return filterByEntity(code)
                // In the cluster view clicking a node = drill into it; only inside a cluster does it mean "view facts"
                if (drilled === null && clusters.some((c) => c.key === code)) {
                  setDrilled(code)
                  setNodeQuery('')
                  return
                }
                filterByTopic(code)
              }}
              width={graphW}
              height={Math.max(520, Math.round(graphW * 0.72))}
            />
          </div>
        )}

      </>
  )
  return <div className="kb-browser">{body}</div>
}
