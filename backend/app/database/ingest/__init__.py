"""External things -> text -> chunks. The first half of ingestion.

A recording, a PDF, a note exported from Notion: before entering the knowledge base each has to
become plain text and then be cut into chunks. That is all this package does, and it **does not
touch the knowledge base itself** - storing is ``kite/``'s job, and using what was stored is
``kb/``'s job.

    asr.py         audio -> text
    extract.py     PDF / DOCX / TXT / MD -> text
    importers.py   Notion / Obsidian / Apple Notes -> text
    chunking.py    text -> chunks

**Not here**: the two in ``media/`` (reading images, generating images) used to be filed here
because "both relate to external content" - but ``imagegen`` is text-to-image, the opposite
direction, and ``vision`` is the editor's image-to-table, unrelated to ingestion. Classify by
**who uses it**, not by feel.
"""
