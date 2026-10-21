
import type { TransactionSpec } from '@codemirror/state'
import { isolateHistory } from '@codemirror/commands'

export function aiSyncSpec(fresh: boolean): Pick<TransactionSpec, 'userEvent' | 'annotations'> {
  return fresh
    ? { userEvent: 'input.ai', annotations: [isolateHistory.of('before')] }
    : { userEvent: 'input.type.compose' }
}
