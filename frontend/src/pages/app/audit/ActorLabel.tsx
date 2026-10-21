import { Bot, ShieldCheck, User } from 'lucide-react'
import { ACTOR_KIND_LABEL, actorKind } from './auditData'

const ICONS = { person: User, agent: Bot, system: ShieldCheck }

/** Who did it, with an icon and a word so people, agents and the system read differently. */
export default function ActorLabel({ actor }: { actor: string }) {
  const kind = actorKind(actor)
  const Icon = ICONS[kind]
  return (
    <span className={`au-actor au-actor-${kind}`}>
      <span className="au-actor-icon" aria-hidden="true">
        <Icon size={14} />
      </span>
      <span className="au-actor-text">
        <span className="au-actor-name">{actor}</span>
        <span className="au-actor-kind">{ACTOR_KIND_LABEL[kind]}</span>
      </span>
    </span>
  )
}
