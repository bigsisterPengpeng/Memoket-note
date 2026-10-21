import { useEffect, useMemo, useRef, useState } from 'react'
import type { MouseEvent as ReactMouseEvent } from 'react'
import { drag as d3drag } from 'd3-drag'
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from 'd3-force'
import { select as d3select } from 'd3-selection'
import { zoom as d3zoom, zoomIdentity, type ZoomBehavior } from 'd3-zoom'
import type { EntityNode, TopicEntityLink, TopicNode } from '../api'
import Icon from './Icon'
import { t } from '../i18n'

/**
 * One force-directed graph for topics AND entities together.
 *
 * These used to be two disconnected sections -- a topic DAG above a plain
 * entity list -- and there was no way to see how they related, because in
 * KITE's data model there IS no direct schema link between a topic and an
 * entity: each fact carries its own `topics` and `entities` arrays
 * independently, so the only real relationship is which topics and entities
 * keep showing up on the same facts. This draws that: topic<->entity edges
 * here are co-occurrence, aggregated server-side (topic_entity_links()) --
 * not a stored relation, a derived one. Entity<->entity edges ARE a stored
 * relation (Entity.rels), drawn the same way. Three edge kinds share one
 * graph: topic hierarchy (solid, arrowed), entity relations (solid, arrowed,
 * a different color), topic<->entity co-occurrence (dashed, unarrowed --
 * it's symmetric, "shown up together", not a direction).
 *
 * Topics render as circles, entities as squares, so the two node kinds stay
 * visually distinguishable inside one shared layout.
 *
 * Interaction model (deliberately not "click = jump away"): hover shows a
 * cheap, instant detail card (no network call -- everything in it is data
 * this component already has); only that card's own "View details" button
 * navigates to the full facts table. A plain click instead focuses the
 * clicked node's immediate neighborhood -- everything else dims -- so you
 * can explore the graph's structure without leaving it every time you touch
 * a node. At a few thousand nodes, both node size and the zoom-triggered
 * level-of-detail (labels only render once zoomed in past a threshold) scale
 * with how many nodes are actually on screen, not a fixed absolute size --
 * the whole point being that opening this with a large knowledge base still
 * reads as a legible overview first, with detail reserved for zooming into
 * a region, rather than a crowded mess at 100%.
 */

type NodeKind = 'topic' | 'entity'

type GraphNode = {
  id: string
  kind: NodeKind
  code: string
  label: string
  factCount: number
  status: string
  aliases: string[]
  x?: number; y?: number; fx?: number | null; fy?: number | null
}
type GraphLink = { source: string; target: string; kind: 'hierarchy' | 'relation' | 'cooccur' }
type SimLink = { source: string | GraphNode; target: string | GraphNode; kind: GraphLink['kind'] }

const DEFAULT_WIDTH = 900
const DEFAULT_HEIGHT = 560
const MIN_R = 16
const R_SCALE = 6
const MIN_SCALE = 0.05
const MAX_SCALE = 12

const MAX_FIT_SCALE = 1.4
// Below this zoom level, labels/detail hide and nodes render as plain dots --
// an "abstract point map" overview; zooming in past it reveals detail. This
// is what makes "local zoom" actually mean something: at the overview level
// nothing is readable by design, so zooming into a region is the only way to
// read anything, rather than everything being crammed-but-technically-
// visible at every zoom level.
const LOD_ZOOM_THRESHOLD = 1.4
// With few nodes (111 in the cluster view, dozens of search hits) labels are always shown — the "see the shape, then zoom"
// LOD was designed for two thousand nodes; with a hundred-odd circles and no names, users just see a pile of bubbles

const LABELS_ALWAYS_BELOW = 150
// Node count at which density scaling kicks in at full strength (below this,
// scale stays 1 -- a handful of nodes shouldn't shrink just because the
// formula technically applies).
const DENSITY_BASELINE = 40


// base hit ~2200 topics+entities, and mounting that many <g>/<line> elements
// PLUS binding d3-drag to each one PLUS running dozens of simulation ticks
// (each touching every node/link's DOM attributes) is all synchronous,
// blocking-the-main-thread work -- reported directly as "it freezes as soon as I enter"
// (freezes on entry). The 305-node stress test this was tuned against never
// caught this because it never tried an order of magnitude more nodes.
// Hard-cap what actually gets simulated/rendered to the highest-fact-count
// nodes; MemoryBrowser's own search box (which filters topics/entities
// BEFORE they reach this component) is the existing way to reach a specific
// node outside the top of this list -- a search hit is a small filtered set,
// well under the cap, so it's never capped away.
export const MAX_RENDERED_NODES = 400

/** More nodes -> smaller nodes, so the graph's *default* (non-zoomed)
 * legibility degrades gracefully instead of nodes overlapping into a solid
 * mass once there are hundreds/thousands of them. Relative to node count,
 * not a fixed absolute radius -- sqrt rather than linear so it doesn't
 * shrink to illegible dust at the scale this app's real data reaches
 * (~2000 entities -> ~0.14x, still distinguishable once you zoom in). */
function densityScale(nodeCount: number): number {
  return Math.min(1, Math.sqrt(DENSITY_BASELINE / Math.max(nodeCount, 1)))
}

// Radius cap: cluster nodes have thousands of facts (sqrt(6000)*6 ≈ 465px); uncapped, one circle fills the canvas

const MAX_R = 44

function radiusOf(factCount: number, scale: number): number {
  return Math.min(MAX_R, (MIN_R + Math.sqrt(factCount) * R_SCALE) * scale)
}

/** All descendants of `code` (itself included), via the parents links -- a
 * plain reachability set, not `vocab.downset()`'s bounded/candidate-aware
 * version, but close enough for sizing a few dozen topic nodes. */
function descendantsOf(code: string, childrenOf: Map<string, string[]>): Set<string> {
  const seen = new Set<string>([code])
  const stack = [code]
  while (stack.length) {
    const cur = stack.pop()!
    for (const child of childrenOf.get(cur) ?? []) {
      if (!seen.has(child)) { seen.add(child); stack.push(child) }
    }
  }
  return seen
}

/** Topics: own fact_count is an exact-code match, so a root with all its
 * facts tagged onto specific children reads as empty even though clicking it
 * shows every one of those facts (facts_page() filters by descendant
 * closure, same as here). Sizing by closure instead makes a node's apparent
 * weight match what clicking it actually reveals. Computed as a proper
 * reachability SET (not summed per-branch) so a multi-parent topic doesn't
 * get double-counted under a shared ancestor. */
function closureFactCounts(topics: TopicNode[]): Map<string, number> {
  const childrenOf = new Map<string, string[]>()
  for (const t of topics) {
    for (const p of t.parents) {
      if (!childrenOf.has(p)) childrenOf.set(p, [])
      childrenOf.get(p)!.push(t.code)
    }
  }
  const byCode = new Map(topics.map((t) => [t.code, t]))
  const out = new Map<string, number>()
  for (const t of topics) {
    let total = 0
    for (const code of descendantsOf(t.code, childrenOf)) total += byCode.get(code)?.fact_count ?? 0
    out.set(t.code, total)
  }
  return out
}

function endpointId(x: string | GraphNode): string {
  return typeof x === 'string' ? x : x.id
}

export default function KnowledgeGraph(
  { topics, entities, links, topicLinks = [], onSelect, width: widthProp = DEFAULT_WIDTH, height = DEFAULT_HEIGHT }: {
    topics: TopicNode[]
    entities: EntityNode[]
    links: TopicEntityLink[]
    /** Topic↔topic links (clusters sharing entities in the cluster view), drawn as dashed lines */
    topicLinks?: { a: string; b: string }[]
    onSelect: (kind: NodeKind, code: string) => void
    width?: number
    height?: number
  },
) {
  const [measuredW, setMeasuredW] = useState<number | null>(null)
  const width = measuredW ?? widthProp
  const nodeEls = useRef(new Map<string, SVGGElement>())
  const linkEls = useRef(new Map<number, SVGLineElement>())
  const simulationRef = useRef<ReturnType<typeof forceSimulation<GraphNode>> | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const zoomGroupRef = useRef<SVGGElement>(null)
  const zoomBehaviorRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null)
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [focusedId, setFocusedId] = useState<string | null>(null)
  const [hover, setHover] = useState<{ node: GraphNode; x: number; y: number } | null>(null)

  const closureCounts = useMemo(() => closureFactCounts(topics), [topics])

  const nodesKey = topics.map((t) => t.code).join(',') + '|' + entities.map((e) => e.code).join(',')

  // Keep one mutable node/link array across renders -- d3-force writes x/y/vx/vy
  // onto these objects in place, so recreating them every render would throw
  // away the simulation's progress.
  const allNodes = useMemo<GraphNode[]>(() => [
    ...topics.map((t): GraphNode => ({
      id: `topic:${t.code}`, kind: 'topic', code: t.code, label: t.code,
      factCount: closureCounts.get(t.code) ?? t.fact_count, status: t.status, aliases: t.aliases,
    })),
    ...entities.map((e): GraphNode => ({
      id: `entity:${e.code}`, kind: 'entity', code: e.code, label: e.name || e.code,
      factCount: e.fact_count, status: 'canonical', aliases: e.aliases,
    })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [nodesKey])

  // Cap by fact count (the richest/most-connected nodes are the most useful
  // default view), not by insertion order -- .filter() below keeps the same
  // object REFERENCES from allNodes (not clones), so d3-force mutations onto
  // a node that's within the cap still land on the one object this component
  // tracks for it everywhere else.
  const nodes = useMemo<GraphNode[]>(() => {
    if (allNodes.length <= MAX_RENDERED_NODES) return allNodes
    const keep = new Set(
      [...allNodes].sort((a, b) => b.factCount - a.factCount).slice(0, MAX_RENDERED_NODES).map((n) => n.id),
    )
    return allNodes.filter((n) => keep.has(n.id))
  }, [allNodes])

  const cappedCount = allNodes.length - nodes.length

  // topicIds/entityIds now reflect the CAPPED set -- graphLinks/neighborMap
  // below filter against these, so a link to a node that got capped away
  // simply doesn't get built, instead of forceLink() choking on a link that
  // references an id not present in `nodes`.
  const topicIds = useMemo(() => new Set(nodes.filter((n) => n.kind === 'topic').map((n) => n.id)), [nodes])
  const entityIds = useMemo(() => new Set(nodes.filter((n) => n.kind === 'entity').map((n) => n.id)), [nodes])

  const sizeScale = useMemo(() => densityScale(nodes.length), [nodes.length])
  // Start already in overview mode for a large graph instead of waiting for
  // the first zoom event to flip it -- otherwise every label on a couple
  // thousand nodes gets laid out and painted during the (now-shortened but
  // still real) force-settling animation before anyone's even zoomed.
  // useRef's initial value is fixed on first render only, so this can't live
  // above `nodes` -- it needs nodes.length to compute its own starting value.
  const startsInOverview = nodes.length > LABELS_ALWAYS_BELOW
  const small = nodes.length <= LABELS_ALWAYS_BELOW
  const labelsAlwaysRef = useRef(!startsInOverview)
  labelsAlwaysRef.current = nodes.length <= LABELS_ALWAYS_BELOW
  // Not React state on purpose -- this flips every animation frame during a
  // zoom gesture, and re-rendering the whole node list (thousands of <g>s)
  // that often would be the actual performance problem. A CSS class on the
  // zoom group is the cheap way to do LOD: the stylesheet decides what
  // "overview" looks like, this only decides when to flip the switch.
  const lodOverviewRef = useRef(startsInOverview)

  // Polling (see MemoryBrowser) hands this component a brand-new `links`
  // array reference every few seconds even when the co-occurrence pairs
  // haven't actually changed -- keying the memo on the array reference would
  // rebuild (and the effect below would then restart the whole simulation)
  // on every single poll tick. Key on content instead.
  const linksKey = links.map((l) => `${l.topic}>${l.entity}`).join(',') + '|' + topicLinks.map((l) => `${l.a}~${l.b}`).join(',')

  const graphLinks = useMemo<GraphLink[]>(() => {
    // Both endpoints have to survive the MAX_RENDERED_NODES cap, not just
    // the one each filter happened to check before -- a link whose target
    // got capped away is a link forceLink() would choke on (it references a
    // node id that isn't in `nodes`).
    const topicParent: GraphLink[] = topics.filter((t) => topicIds.has(`topic:${t.code}`)).flatMap((t) =>
      t.parents.filter((p) => topicIds.has(`topic:${p}`))
        .map((p) => ({ source: `topic:${p}`, target: `topic:${t.code}`, kind: 'hierarchy' as const })))
    const entityRel: GraphLink[] = entities.filter((e) => entityIds.has(`entity:${e.code}`)).flatMap((e) =>
      e.relations.filter(([, other]) => entityIds.has(`entity:${other}`))
        .map(([, other]) => ({ source: `entity:${e.code}`, target: `entity:${other}`, kind: 'relation' as const })))
    const cooccur: GraphLink[] = links
      .filter((l) => topicIds.has(`topic:${l.topic}`) && entityIds.has(`entity:${l.entity}`))
      .map((l) => ({ source: `topic:${l.topic}`, target: `entity:${l.entity}`, kind: 'cooccur' as const }))
    const tt: GraphLink[] = topicLinks
      .filter((l) => topicIds.has(`topic:${l.a}`) && topicIds.has(`topic:${l.b}`))
      .map((l) => ({ source: `topic:${l.a}`, target: `topic:${l.b}`, kind: 'cooccur' as const }))
    return [...topicParent, ...entityRel, ...cooccur, ...tt]
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodesKey, linksKey])

  // Adjacency built from the same source props as graphLinks, NOT from
  // graphLinks itself -- forceLink() mutates that array's source/target from
  // plain id strings into direct node-object references after the
  // simulation's first tick, so reading it for neighbor lookups would be
  // reading a moving target (string before the sim starts, object after).
  const neighborMap = useMemo(() => {
    const map = new Map<string, Set<string>>()
    const add = (a: string, b: string) => {
      if (!map.has(a)) map.set(a, new Set())
      if (!map.has(b)) map.set(b, new Set())
      map.get(a)!.add(b)
      map.get(b)!.add(a)
    }
    for (const t of topics) if (topicIds.has(`topic:${t.code}`)) for (const p of t.parents) if (topicIds.has(`topic:${p}`)) add(`topic:${p}`, `topic:${t.code}`)
    for (const e of entities) if (entityIds.has(`entity:${e.code}`)) for (const [, other] of e.relations) if (entityIds.has(`entity:${other}`)) add(`entity:${e.code}`, `entity:${other}`)
    for (const l of links) if (topicIds.has(`topic:${l.topic}`) && entityIds.has(`entity:${l.entity}`)) add(`topic:${l.topic}`, `entity:${l.entity}`)
    for (const l of topicLinks) if (topicIds.has(`topic:${l.a}`) && topicIds.has(`topic:${l.b}`)) add(`topic:${l.a}`, `topic:${l.b}`)
    return map
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodesKey, linksKey])

  const focusSet = useMemo(() => {
    if (!focusedId) return null
    return new Set([focusedId, ...(neighborMap.get(focusedId) ?? [])])
  }, [focusedId, neighborMap])

  useEffect(() => {
    if (nodes.length === 0) return

    // Charge/link-distance do NOT shrink with node count, only radius does
    // (sizeScale) -- that was the actual bug behind "a dark, crowded mass": the old
    // code scaled repulsion DOWN as density went up, which is backwards
    // (more nodes need more room to separate, not less), and on top of that
    // every node was hard-clamped into the visible width/height box every
    // tick regardless of zoom -- so 2000 nodes were being forced to
    // physically overlap inside a fixed ~900x560px area no matter how far
    // you zoomed out, since zooming only scales the *view* of that already-
    // saturated box, it can't un-overlap nodes that were squeezed together
    // in simulation space to begin with. Removing the clamp lets the
    // simulation spread across however much space it actually needs;
    // fitToView() (called once after the layout settles, see below) is what
    // brings that space into frame, not a boundary constraint.
    // Default alphaDecay (~0.0228) takes ~300 ticks to settle -- each tick
    // touches every node's DOM transform plus every link's x1/y1/x2/y2, so
    // at a couple thousand nodes that's a genuinely long, visibly janky
    // settling animation, not just a few frames. Decaying faster shortens
    // that window a lot; the graph still spreads out fine since sizeScale
    // already gives more nodes more collision radius to push apart with.
    const simulation = forceSimulation<GraphNode>(nodes)
      .alphaDecay(0.05)
      .alphaMin(0.01)
      // Small graphs (cluster view / search hits) must spread until labels are readable: repulsion, link distance and collision radius
      // all leave room for labels; the two-thousand-node graph still uses compact parameters, otherwise layout takes too long.
      .force('link', forceLink<GraphNode, SimLink>(graphLinks as SimLink[]).id((d) => d.id)
        .distance((l) => (l.kind === 'cooccur' ? 60 : 80) * (small ? 1.4 : 1)))
      // Small graphs (the cluster view has no links): separated by collision radius, gathered by centering force — with strong repulsion they get pushed

      .force('charge', forceManyBody().strength(small ? -40 : -140))
      .force('center', forceCenter(width / 2, height / 2))
      .force('x', forceX(width / 2).strength(small ? 0.08 : 0))
      .force('y', forceY(height / 2).strength(small ? 0.08 : 0))
      .force('collide', forceCollide<GraphNode>((d) => radiusOf(d.factCount, sizeScale) + (small ? 30 : 4)).iterations(2))
    simulationRef.current = simulation

    let settleFitDone = false
    // The fit at alpha < 0.25 is "get a viewable picture as soon as possible"; nodes keep spreading afterwards,
    // so fit once more when the layout really stops, otherwise outer nodes stay off-canvas.
    // Auto-fit only the first time this layout stops. Dragging a node restarts the simulation and fires
    // 'end' again — fitTo every time was exactly the user-reported "zoomed in, then it shrinks back".
    autoFitDoneRef.current = false
    simulation.on('end', () => {
      settledRef.current = true
      if (!autoFitDoneRef.current && !userZoomedRef.current) { autoFitDoneRef.current = true; fitTo() }
    })
    simulation.on('tick', () => {
      for (const n of nodes) {
        const el = nodeEls.current.get(n.id)
        if (el && n.x !== undefined && n.y !== undefined) {
          el.setAttribute('transform', `translate(${n.x}, ${n.y})`)
        }
      }
      // First time alpha decays enough to call the layout "settled", frame
      // whatever extent it actually spread out to -- this is what replaces
      // the old fixed-box clamp as "how the graph fits on screen at first
      // paint" (see fitTo below; deferred so it reads current x/y after the
      // simulation has had a moment to spread, not the initial random seed
      // positions from tick 0).
      if (!settleFitDone && simulation.alpha() < 0.25) {
        settleFitDone = true
        settledRef.current = true
        fitTo()
      }
      graphLinks.forEach((l, i) => {
        const el = linkEls.current.get(i)
        const source = l.source as unknown as GraphNode
        const target = l.target as unknown as GraphNode
        if (el && source.x !== undefined && target.x !== undefined) {
          el.setAttribute('x1', String(source.x))
          el.setAttribute('y1', String(source.y))
          el.setAttribute('x2', String(target.x))
          el.setAttribute('y2', String(target.y))
        }
      })
    })

    for (const n of nodes) {
      const el = nodeEls.current.get(n.id)
      if (!el) continue
      d3select(el).call(
        d3drag<SVGGElement, unknown>()
          .on('start', (event) => {
            if (!event.active) simulation.alphaTarget(0.3).restart()
            n.fx = n.x
            n.fy = n.y
          })
          .on('drag', (event) => {
            n.fx = event.x
            n.fy = event.y
          })
          .on('end', (event) => {
            if (!event.active) simulation.alphaTarget(0)
            n.fx = null
            n.fy = null
          }),
      )
    }

    return () => { simulation.stop() }
    // width/height as deps: entering/leaving fullscreen (or a window resize
    // while in it) changes the canvas size, and forceCenter closes over
    // whatever width/height it was built with -- needs a fresh simulation to
    // recenter on the new dimensions.
    // Size isn't in the deps: when embedded, a ResizeObserver jitter or the right pane widening would rerun the whole simulation,
    // nodes exploding again and auto-fitting again — users see "the graph jumps by itself". Size changes only move the centering force.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, graphLinks, sizeScale])

  useEffect(() => {
    const sim = simulationRef.current
    if (!sim) return
    sim.force('center', forceCenter(width / 2, height / 2))
    const fx = sim.force('x') as ReturnType<typeof forceX<GraphNode>> | null
    const fy = sim.force('y') as ReturnType<typeof forceY<GraphNode>> | null
    fx?.x(width / 2); fy?.y(height / 2)
  }, [width, height])

  // Polling (see MemoryBrowser) refreshes topics/entities every few seconds
  // while a background ingest is adding facts. When the *set* of nodes is
  // unchanged, `nodes` above stays the same array on purpose -- rebuilding
  // it would restart the simulation from scratch (every node re-explodes out
  // from the center, dragged positions lost) just because a fact_count went
  // up. Instead, patch the count directly onto the SAME node objects the
  // simulation is already tracking, and nudge it awake so collision spacing
  // catches up to the new radius -- existing layout stays put otherwise.
  useEffect(() => {
    let changed = false
    for (const n of nodes) {
      const next = n.kind === 'topic'
        ? closureCounts.get(n.code) ?? 0
        : entities.find((e) => e.code === n.code)?.fact_count ?? n.factCount
      if (next !== n.factCount) { n.factCount = next; changed = true }
    }
    if (changed) simulationRef.current?.alpha(0.3).restart()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, topics, entities])

  // Pan/zoom, set up once and left alone across data refreshes/polling --
  // rebuilding it on every nodes/links change would reset the user's current
  // view (exactly the "graph gets messy at scale" complaint this exists to
  // fix). Scroll-wheel zoom, drag-to-pan, and double-click-to-zoom-in are
  // d3-zoom's defaults; per-node drag (above) coexists with it out of the
  // box because d3-drag stops the originating pointer event from also
  // reaching the svg's pan handler -- the standard, well-tested d3-force +
  // d3-zoom + d3-drag combination, not something bolted on here.
  // BUG THIS FIXES: `nodes.length === 0` on the very first render (MemoryBrowser
  // starts topics/entities as [] and fetches them async) makes the component
  // return the "No topics or entities yet" placeholder instead of the <svg> -- so on
  // that first render svgRef.current is null. With a `[]`-deps effect, that
  // was the ONE AND ONLY time this ever ran: it bailed out on the null ref
  // and, because the deps array never changes, never got a second chance
  // once real data arrived and the <svg> actually mounted. zoomBehaviorRef
  // stayed null forever -- wheel/drag never attached to the real element,
  // and fitTo()'s own null-check made it silently no-op on every call. Keying
  // on `nodes.length > 0` instead means the effect body actually runs (and
  // this time succeeds) the first time the ref is real, then never again --
  // still "set up once", just once-when-actually-possible instead of
  // once-on-mount-regardless.
  const hasNodes = nodes.length > 0
  useEffect(() => {
    if (!svgRef.current || !zoomGroupRef.current) return
    const zoomGroup = zoomGroupRef.current
    // "zoom-in/out stutters" was reported even after the settling-time fixes
    // above -- because those addressed how long the *simulation* is
    // expensive, not that every continuous wheel/drag frame during an
    // ALREADY-settled interactive zoom still repaints every label and line
    // at the current LOD level. Text layout/painting is the expensive part
    // of an SVG repaint at this node count, more than the transform itself.
    // While a gesture is actively in progress, force overview-level
    // rendering (no labels, no lines) regardless of the zoom threshold, and
    // only restore real detail a beat after the gesture stops.
    let interactingTimer: ReturnType<typeof setTimeout> | null = null
    const zoom = d3zoom<SVGSVGElement, unknown>()
      .scaleExtent([MIN_SCALE, MAX_SCALE])
      .on('zoom', (event) => {
        // sourceEvent set = the user's wheel / drag; programmatic fitTo / reset has none
        if (event.sourceEvent) userZoomedRef.current = true
        zoomGroup.setAttribute('transform', event.transform.toString())
        const overview = !labelsAlwaysRef.current && event.transform.k < LOD_ZOOM_THRESHOLD
        if (overview !== lodOverviewRef.current) {
          lodOverviewRef.current = overview
          zoomGroup.classList.toggle('lod-overview', overview)
        }
        zoomGroup.classList.add('kg-interacting')
        if (interactingTimer) clearTimeout(interactingTimer)
        interactingTimer = setTimeout(() => zoomGroup.classList.remove('kg-interacting'), 150)
      })
    zoomBehaviorRef.current = zoom
    d3select(svgRef.current).call(zoom)
    // Initial framing comes from fitTo() once the simulation settles (see
    // the tick handler above), not a guessed scale here -- it frames
    // whatever extent the graph actually spread out to, which a formula
    // based only on node count can't know in advance.
    const svgEl = svgRef.current
    return () => {
      if (interactingTimer) clearTimeout(interactingTimer)
      if (svgEl) d3select(svgEl).on('.zoom', null)
    }
  }, [hasNodes])

  function resetZoom() {
    if (!svgRef.current || !zoomBehaviorRef.current) return
    d3select(svgRef.current).transition().duration(300)
      .call(zoomBehaviorRef.current.transform, zoomIdentity)
  }

  useEffect(() => {
    const el = svgRef.current
    if (!el) return
    const ro = new ResizeObserver(() => { const w = Math.floor(el.clientWidth); if (w > 0) setMeasuredW(w) })
    ro.observe(el)
    return () => ro.disconnect()
  }, [nodes.length])

  /** Frames a set of node ids (defaults to every node) -- fitting to content
   * rather than to the canvas box is the whole point, whether that's "all
   * nodes" ("Fit to window" button) or a focused neighborhood after a click.
   * `centerOn`, when given, pins that specific node's own coordinate to the
   * middle of the screen -- otherwise centering falls back to the bounding
   * box's centroid, which is generally NOT where the clicked node sits (its
   * neighbors are rarely distributed evenly around it), and "the clicked node
   * is in the middle" means the clicked node itself, not the average of its cluster. */
  const settledRef = useRef(false)
  const autoFitDoneRef = useRef(false)
  // Once the user has zoomed themselves, size changes no longer fit the window for them
  const userZoomedRef = useRef(false)
  useEffect(() => {
    if (!settledRef.current || userZoomedRef.current) return
    const t = setTimeout(() => fitTo(), 50)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [width, height])

  function fitTo(ids?: Set<string>, centerOn?: GraphNode) {
    if (!svgRef.current || !zoomBehaviorRef.current || nodes.length === 0) return
    const targets = ids ? nodes.filter((n) => ids.has(n.id)) : nodes
    if (targets.length === 0) return
    // Use the <svg>'s real size right now, not props: width/height in the simulation 'end' callback's
    // closure are the 900×560 of the first render, while the real size changed long ago after embedding — a fit

    const W = svgRef.current.clientWidth || width
    const H = svgRef.current.clientHeight || height
    const xs = targets.map((n) => n.x ?? W / 2)
    const ys = targets.map((n) => n.y ?? H / 2)
    const pad = small ? 36 : 80
    const x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad
    const y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad
    const boxW = Math.max(1, x1 - x0), boxH = Math.max(1, y1 - y0)
    const scale = Math.min(MAX_FIT_SCALE, Math.max(MIN_SCALE, Math.min(W / boxW, H / boxH)))
    const cx = centerOn?.x ?? (x0 + x1) / 2
    const cy = centerOn?.y ?? (y0 + y1) / 2
    const transform = zoomIdentity
      .translate(W / 2, H / 2)
      .scale(scale)
      .translate(-cx, -cy)
    d3select(svgRef.current).transition().duration(400)
      .call(zoomBehaviorRef.current.transform, transform)
  }

  /** Click focuses this node's immediate neighborhood: everything else is
   * unmounted (not just dimmed), and the view zooms so the clicked node
   * itself sits at the center of the screen with its neighbors arranged
   * around it -- not navigating away, staying in the graph is the point;
   * navigating to the facts table is now only the hover card's explicit
   * "View details" action. Clicking a different node while already focused
   * re-focuses onto that node's own neighborhood (drill further in); the
   * only way back to the full graph is the "Restore" button, not a second click
   * on the same node or on empty canvas -- deliberate, so the focused view
   * doesn't get accidentally cleared while exploring within it. */
  function handleNodeClick(n: GraphNode) {
    // A node with zero neighbors (isolated, or its only neighbors got
    // capped out of MAX_RENDERED_NODES) used to make a click do literally
    // nothing -- reported directly as "can't click a topic". Focusing on just
    // itself still does something visible (singles it out, centers it),
    // instead of the click being silently swallowed.
    const neighbors = neighborMap.get(n.id) ?? new Set<string>()
    setFocusedId(n.id)
    fitTo(new Set([n.id, ...neighbors]), n)
  }

  function clearFocus() {
    setFocusedId(null)
    fitTo()
  }

  function handleNodeEnter(n: GraphNode, e: ReactMouseEvent) {
    if (hoverTimer.current) clearTimeout(hoverTimer.current)
    const x = e.clientX, y = e.clientY
    hoverTimer.current = setTimeout(() => setHover({ node: n, x, y }), 150)
  }
  function handleNodeLeave() {
    if (hoverTimer.current) clearTimeout(hoverTimer.current)
    hoverTimer.current = setTimeout(() => setHover(null), 200)
  }
  function keepHoverOpen() {
    if (hoverTimer.current) clearTimeout(hoverTimer.current)
  }

  if (nodes.length === 0) return <p className="muted">{t('No topics or entities yet — save some content first.')}</p>

  const hoverTop = hover ? Math.max(12, Math.min(hover.y + 14, window.innerHeight - 160)) : 12

  return (
    // overflow: hidden, not auto -- panning is now d3-zoom's job (drag the
    // canvas), not the browser's native scrollbars; both at once would let
    // two independent "where am I looking" mechanisms fight each other.
    <div style={{ position: 'relative', overflow: 'hidden', border: '1px solid var(--line)', borderRadius: 'var(--r)' }}>
      <div className="row" style={{ padding: '8px 10px 0', fontSize: 'var(--t-sm)', justifyContent: 'space-between' }}>
        <div className="row">
          <span className="muted">
            <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 'var(--r-circle)',
                           border: '1.5px solid var(--accent)', marginRight: 4, verticalAlign: -1 }} />
            {t('Topic')}
          </span>
          <span className="muted">
            <span style={{ display: 'inline-block', width: 10, height: 10,
                           border: '1.5px solid var(--ins)', marginRight: 4, verticalAlign: -1 }} />
            {t('Entity')}
          </span>
          <span className="muted">{t('Dashed line = appear in the same fact')}</span>
          {focusedId && <span className="badge ok">{t('Focused: {id} and its connected nodes', { id: focusedId.split(':')[1] })}</span>}
        </div>
        <div className="row">
          {focusedId
            ? <button className="chip active" onClick={clearFocus} title={t('Exit focus and show all nodes')}><Icon n="bx-undo" />{t('Show all')}</button>
            : (
              <>
                <button className="icon-btn" onClick={() => fitTo()} title={t('Fit to window: zoom to fit all nodes')}><Icon n="bx-expand" /></button>
                <button className="icon-btn" onClick={resetZoom} title={t('Reset view: back to 100%')}><Icon n="bx-reset" /></button>
              </>
            )}
        </div>
      </div>
      <p className="muted" style={{ padding: '4px 10px 0', fontSize: 'var(--t-xs)', margin: 0 }}>
        {t('Scroll to zoom · drag to pan · hover for a summary · click a node to focus it and its connections (then “Show all”) · “View details” on the card opens its page.')}
        {cappedCount > 0 && (
          <> {t('Showing only the top {shown} nodes by fact count (of {all}) — the other {rest} can be found by name with the search box above.', { shown: nodes.length, all: allNodes.length, rest: cappedCount })}</>
        )}
      </p>
      <svg ref={svgRef} width="100%" height={height} style={{ display: 'block', cursor: 'grab' }}>
        <defs>
          <marker id="kg-arrow" viewBox="0 0 8 8" refX="7" refY="4"
                  markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L8 4 L0 8 z" fill="var(--muted)" />
          </marker>
          <marker id="kg-arrow-rel" viewBox="0 0 8 8" refX="7" refY="4"
                  markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L8 4 L0 8 z" fill="var(--ins)" />
          </marker>
        </defs>

        <g ref={zoomGroupRef} className={'kg-zoom-group' + (startsInOverview ? ' lod-overview' : '')}>

        {graphLinks.map((l, i) => {
          // Focused: unmount non-neighborhood links entirely rather than
          // dim them -- "hide everything else", not "faded but still cluttering the
          // view". The tick handler's ref lookups already tolerate a
          // missing element (see the `if (el && ...)` guard above), so
          // skipping the element here is safe -- the simulation keeps
          // running for hidden nodes/links, they just don't render.
          if (focusSet && !(focusSet.has(endpointId(l.source)) && focusSet.has(endpointId(l.target)))) return null
          return (
            <line
              key={i}
              ref={(el) => {
                if (!el) { linkEls.current.delete(i); return }
                linkEls.current.set(i, el)
                // A remounted link (focus cleared, or a different node
                // clicked) is a BRAND NEW DOM element with no x1/y1/x2/y2 --
                // if the simulation has already settled (alpha < alphaMin,
                // tick stopped firing), nothing else will ever position it,
                // and it renders at (0,0). Position it immediately from
                // whatever x/y its endpoints already have (forceLink()
                // resolves l.source/target from ids into the actual node
                // objects after the first tick, so this reads live data,
                // not stale/default).
                const source = l.source as unknown as GraphNode
                const target = l.target as unknown as GraphNode
                if (source?.x !== undefined && target?.x !== undefined) {
                  el.setAttribute('x1', String(source.x))
                  el.setAttribute('y1', String(source.y))
                  el.setAttribute('x2', String(target.x))
                  el.setAttribute('y2', String(target.y))
                }
              }}
              stroke={l.kind === 'relation' ? 'var(--ins)' : 'var(--muted)'}
              strokeWidth={1.4}
              strokeDasharray={l.kind === 'cooccur' ? '3 3' : undefined}
              markerEnd={l.kind === 'cooccur' ? undefined : `url(#${l.kind === 'relation' ? 'kg-arrow-rel' : 'kg-arrow'})`}
            />
          )
        })}

        {nodes.map((n) => {
          if (focusSet && !focusSet.has(n.id)) return null
          const deprecated = n.status === 'deprecated'
          const candidate = n.status === 'candidate'
          const empty = n.factCount === 0
          const r = radiusOf(n.factCount, sizeScale)
          const label = n.label.length > 18 ? n.label.slice(0, 17) + '…' : n.label
          const color = n.kind === 'topic' ? 'var(--accent)' : 'var(--ins)'
          return (
            <g
              key={n.id}
              ref={(el) => {
                if (!el) { nodeEls.current.delete(n.id); return }
                nodeEls.current.set(n.id, el)
                // Same fix as the <line> ref below: a remounted node (focus
                // cleared/changed) has no transform until the next tick, and
                // the simulation may have already settled and stopped
                // ticking -- reported directly as "after clicking Restore, it doesn't restore,
                // the display is wrong" (nodes piling up at the origin instead of
                // their actual laid-out positions). n.x/n.y persist on the
                // node object across mount/unmount since d3-force mutates
                // the object in place, not the DOM.
                if (n.x !== undefined && n.y !== undefined) {
                  el.setAttribute('transform', `translate(${n.x}, ${n.y})`)
                }
              }}
              style={{ cursor: 'pointer' }}
              onClick={(e) => { e.stopPropagation(); handleNodeClick(n) }}
              onMouseEnter={(e) => handleNodeEnter(n, e)}
              onMouseLeave={handleNodeLeave}
            >
              {n.kind === 'topic' ? (
                <circle
                  r={r}
                  fill="var(--kg-node-fill)"
                  opacity={empty ? 0.4 : (deprecated ? 0.55 : 1)}
                  stroke={deprecated ? 'var(--muted)' : color}
                  strokeDasharray={candidate ? '4 3' : undefined}
                />
              ) : (
                <rect
                  x={-r * 0.8} y={-r * 0.8} width={r * 1.6} height={r * 1.6} rx={4}
                  fill="var(--kg-node-fill)"
                  opacity={empty ? 0.4 : 1}
                  stroke={color}
                />
              )}
              <text textAnchor="middle" dy={4} fontSize={12} fill="var(--fg)"
                    style={{ textDecoration: deprecated ? 'line-through' : 'none', pointerEvents: 'none' }}>
                {label}
              </text>
            </g>
          )
        })}

        </g>
      </svg>

      {hover && (
        <div
          className="card kg-hover-card"
          style={{
            position: 'fixed',
            left: Math.max(12, Math.min(hover.x + 14, window.innerWidth - 272)),
            top: hoverTop,
            maxHeight: Math.max(0, window.innerHeight - hoverTop - 12),
            width: 260, zIndex: 50,
          }}
          onMouseEnter={keepHoverOpen}
          onMouseLeave={handleNodeLeave}
        >
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <strong style={{ fontSize: 'var(--t-md)' }}>{hover.node.label}</strong>
            <span className="badge">{hover.node.kind === 'topic' ? t('Topic') : t('Entity')}</span>
          </div>
          <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: '6px 0 0' }}>
            {t('{n} facts', { n: hover.node.factCount })}
            {hover.node.kind === 'topic' && ` · ${hover.node.status}`}
          </p>
          {hover.node.aliases.length > 0 && (
            <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: '4px 0 0' }}>
              {t('Aliases: {aliases}', { aliases: hover.node.aliases.join(t(', ')) })}
            </p>
          )}
          {hover.node.factCount === 0 ? (
            <p className="muted" style={{ fontSize: 'var(--t-sm)', margin: '8px 0 0' }}>{t('Nothing yet')}</p>
          ) : (
            <button
              style={{ marginTop: 8, width: '100%' }}
              onClick={() => { onSelect(hover.node.kind, hover.node.code); setHover(null) }}
            >
              {t('View details ({n} facts) →', { n: hover.node.factCount })}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
