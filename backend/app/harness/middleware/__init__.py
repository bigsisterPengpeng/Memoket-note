"""Capabilities, packaged one per file.

Each one is unaware of the loop and can be unit-tested by constructing a
``State`` and calling one hook. That isolation is the point: "one harness has
it, the other doesn't" happened four times (find_repeats, compact_context,
record_harness_run, material-exhausted) and every one was an oversight rather
than a decision.

``BASE`` is on by default. Opt-out has to be written down; opt-in is how
things get forgotten.
"""

from ._order import OrderError, describe, verify
from .best_of import BestOf
from .checks import Checks
from .checklist import Checklist
from .compact import Compact
from .cost import Cost
from .cross_run import CrossRun
from .done import DoneCriteria
from .workflow import WorkflowCriteria
from .feedback import UserFeedbackCriteria
from .edits import Edits
from .facts import Facts
from .history import History
from .ledger import Ledger
from .repair import Repair
from .replan import Replan
from .runtime import Runtime
from .repeats import Repeats
from .save import Save
from .sections import Sections
from .skills import Skills
from .supersede import Supersede
from .provenance import Provenance

# Where each one runs. Two on the same hook execute in list order, and that
# sometimes matters -- see the ``after`` declarations, which ``verify()``
# enforces rather than trusting.
#   middleware   hook              why there
#   ---------------------------------------------------------------------
#   Skills       before_round      the menu must exist before gather:
#                                  gather is the only call with tools
#   Facts        after_prepare     fold this round's haul into the run's
#   Provenance   after_prepare     after Facts: show what the tools returned


#   Repeats      before_judge      dup_hints is evidence for the scoring call
#   Checks       before_judge      after Repeats: it may skip scoring entirely,
#                                  and dup_hints is still wanted next round


#   BestOf       after_judge       needs the score to rank the round


#   History      after_run         final scores only exist at the end


#   ---- not in BASE, attached per Mode via extra_mw ----


#   Revise       before_produce    fix what's written before writing more


#   Save         after_produce     persist each round
#   Repair       after_judge       weak inner quality -> next round repairs
#                                  instead of writing more
#   Runtime      after_judge       feed the round's signals back into the
#                                  next round's run parameters
#   Replan       after_judge       adjust the skeleton, under constraints
BASE: tuple = (Cost(), Skills(), Facts(), Provenance(), Ledger(), Supersede(),
               Repeats(), Checks(), BestOf(), CrossRun(), History(), Edits())

# Not in BASE, attached per-Mode via extra_mw:
#   Revise  -- "fix what's already written before writing more"; only
#              long-form needs it. Block generation rewrites the whole block.


#   Save    -- persist every round; blocks aren't persisted at all.
#   Repair  -- repair-instead-of-continue; long-form only.
#   Runtime / Replan -- note_harness only.

__all__ = ["BASE", "BestOf", "Checklist", "Checks", "Compact", "Cost", "CrossRun", "DoneCriteria", "WorkflowCriteria", "UserFeedbackCriteria",
           "Edits", "Facts", "History",
           "Ledger",
           "Sections",
           "OrderError", "Provenance", "Repair", "Replan", "Repeats",
           "Runtime", "Save", "Skills", "Supersede", "describe", "verify"]
