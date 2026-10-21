/**
 * Local graph: "what's around this thing" on topic / entity pages. Capacities uses a "local graph per node"
 * to ease the unreadable whole graph — the whole graph is 126 topics + 1220 entities; the local graph draws only this one and its neighbors.
 * Reuses KnowledgeGraph directly; with fewer than 150 nodes it spreads out by itself and labels stay visible.
 */
import type { EntityNode, TopicEntityLink, TopicNode } from '../../api'
import KnowledgeGraph from '../KnowledgeGraph'
import type { KbActions } from './KbBits'

export default function LocalGraph({ topics, entities, links, actions, height = 320 }: {
  topics: TopicNode[]; entities: EntityNode[]; links: TopicEntityLink[]; actions: KbActions; height?: number
}) {
  if (topics.length + entities.length < 2) return null
  return (
    <div className="local-graph">
      <KnowledgeGraph
        topics={topics} entities={entities} links={links} height={height}
        onSelect={(kind, code) => actions.onOpen((kind === 'topic' ? 'kb:topic:' : 'kb:entity:') + code)}
      />
    </div>
  )
}
