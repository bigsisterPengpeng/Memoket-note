# A writing agent that remembers your work

[Watch the narrated workflow](media/agent-native-writing-workspace.mp4) ·
[English captions](media/agent-native-writing-workspace.en.vtt) ·
[Transcript](media/agent-native-writing-workspace.md)

The recording uses actual application interactions and a live GPT-4.1 run with
independently authored fictional data. Screen frames are sampled and edited,
waiting time is shortened, and the English narration is synthetic. It is not an
uninterrupted recording or a guarantee of model output quality.

## 1. Import the notes you already have

Open Import and choose **Notes + knowledge base**. Select the three Markdown
files in [`examples/maple-pilot/`](../examples/maple-pilot/). The shared file
importer preserves their titles and creation dates from front matter. The
recorded import extracts 14 facts from the three notes using the configured model.

Notion, Apple Notes, Obsidian and Evernote are also available in Import. See
[connections](connections.md) for setup and limits. The recording uses local files
and never reads a personal Notes library or a connected Notion account.

## 2. Return to long-term memory

Reopen the workspace and search for `Maple shelf labels` in the knowledge base.
The recorded validation restarts the backend between import and retrieval and
confirms that the same 14 fact identifiers remain available.

Open a fact to inspect its dated original words. Memory lives in the local KITE
library across notes and sessions. It is not limited to the current chat or draft.

## 3. Give the writing agent a task

Create a note named **Maple weekly update**. Select a writing template or set:

- Goal: a concise weekly update covering the plan, rehearsal evidence, blocker
  and next action.
- Audience: the Maple pilot team.
- Criteria: cite saved sources, write 150–220 words, distinguish the pilot opening
  from a public launch, and invent no owners or commitments.

Related memory appears beside the draft. Add relevant facts to Materials, then
run Smart Continue. The recorded run uses selected facts and retrieves additional
context. It produces a draft citing 10 saved facts.

The writing agent harness coordinates retrieval, writing, checks and stopping.
The Plan and Changes tabs expose the run and its edits. A check passing does not
establish factual accuracy or mean every task requirement has been satisfied.

## 4. Review the draft against its sources

The recorded model repeats the title and adds an unsupported timing claim about
a broader release happening after the trial. The reviewer removes the duplicate
heading and replaces that claim with what the source says: the team will review
accessibility feedback before making any public launch commitment.

The reviewed draft has 168 whitespace-delimited words including headings. All
10 source identifiers resolve to stored facts and readable original evidence.
Click a source link to inspect the source passage and the backlink to the draft.

The included [reviewed example](../examples/maple-weekly-update.md) preserves
those source identifiers from the recorded library. A fresh import can assign
different facts or IDs, so verify or regenerate citations in your own library.
Model wording and fact extraction can vary.

## 5. Take the draft with you

Click **Export** in the editor toolbar:

- **Download .md** saves the current draft without an account and preserves source
  identifiers. Those identifiers resolve inside the corresponding NOTE library.
- **Obsidian** writes the note into a selected existing local vault directory.
- **Notion** and **Feishu** use their configured account integrations. They have not
  been validated against live accounts in this demonstration.

The validation compares the actual Markdown download and the Obsidian export
against the reviewed saved draft. Both retain its body and all 10 source IDs.
The external tools themselves are not opened in the recording. This is explicit
import/export, not automatic live synchronization.
