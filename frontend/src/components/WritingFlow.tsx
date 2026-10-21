import Icon from './Icon'
import { t } from '../i18n'

type Step = 'import' | 'memory' | 'write' | 'export'

const STEPS: { id: Step; icon: string; title: string; detail: string }[] = [
  { id: 'import', icon: 'bx-import', title: 'Import', detail: 'Start with the notes you already have.' },
  { id: 'memory', icon: 'bx-brain', title: 'Long-term memory', detail: 'Keep knowledge and its original sources across sessions.' },
  { id: 'write', icon: 'bx-edit-alt', title: 'Write', detail: 'Let the agent retrieve context, draft and revise.' },
  { id: 'export', icon: 'bx-export', title: 'Export', detail: 'Take Markdown with you or send notes to a connected tool.' },
]

export default function WritingFlow({ current }: { current?: Step }) {
  return (
    <ol className="writing-flow" aria-label={t('Your writing workflow')}>
      {STEPS.map((step) => (
        <li key={step.id} aria-current={current === step.id ? 'step' : undefined}>
          <Icon n={step.icon} />
          <strong>{t(step.title)}</strong>
          <span className="muted">{t(step.detail)}</span>
        </li>
      ))}
    </ol>
  )
}
