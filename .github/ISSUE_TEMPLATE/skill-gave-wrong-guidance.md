---
name: A skill gave wrong or misleading guidance
about: The assistant did the wrong thing, or reported something the data does not support
labels: bug
---

**Which skill**
whisper-investigate / whisper-bulk-triage / whisper-cypher / whisper-brand-protection — or "not sure".

**What you asked**
The question, as close to verbatim as you can.

**What the assistant did**
Which tools it called, in what order, and what it told you. Paste the answer if you can.

**What it should have done**

**Was an empty result reported as clean?**
This is the highest-priority class of bug here. If the assistant said an indicator was safe, clean, or
had no threats, and the underlying response actually said the graph had never seen it, say so — that
alone is enough to file.

**Environment**
Client (Claude Code, Claude.ai, Cursor, …), how you installed the skills, and whether the connector was
signed in.
