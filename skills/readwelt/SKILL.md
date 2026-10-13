---
name: readwelt
description: Use Readwelt when a user wants to understand an article's argument, compressed premises, author's problem world, limits, or transferable method. Do not use for ordinary summaries, translation, isolated fact lookup, or unrelated questions.
---

# Readwelt

Readwelt is reverse reading: do not compress an article into a shorter article. First recover
what the article says, then expand the knowledge, conditions, and problem pressure that make the
article intelligible.

The final judge is the human reader. Your job is to make the article easier to return to, not to
replace the article with an authoritative-sounding interpretation.

## When to use

Use this Skill when the user wants to:

- understand an article, essay, paper, report, or chapter deeply;
- understand why the author asks this question or writes in this way;
- unpack concepts, background, assumptions, or shared knowledge compressed by the text;
- test where the argument holds or fails;
- transfer a method or mechanism to another problem.

Do not use it for ordinary summaries, translation, isolated fact lookup, codebase context, or
questions about a small passage unless the user asks for the full reverse-reading method.

## Input contract

Readwelt accepts text the host Agent can already read. Prefer content with stable headings,
paragraphs, pages, or other locations. Do not pretend to have read omitted material.

If the user's purpose is already clear, start reading without another question. Otherwise ask at
most one question:

> 这次你最想理解这篇文章的什么？

If the user does not answer, use the default purpose: recover the article's main line, problem
world, limits, and transferable method.

For a long article:

1. Read the whole available text once, marking candidate claims, reversals, and repeated concerns.
2. Identify the controlling claim and its pivot using the procedure in phase 1.
3. Map the section structure and record only claims, evidence, examples, and questions that bear on that reading.
4. Keep a compact working sheet of source locations, compressed concepts, and open questions.
5. Only after the available text has been covered, synthesize the reverse-reading report.

When a temporary working sheet is needed, use a plain Markdown file such as
`.readwelt-reading-notes.md`. It may contain coverage and evidence notes, but never hidden
chain-of-thought or unrestricted reasoning transcripts. For a short article, do not create a file.

If the article is only partially available, continue only with an explicit coverage notice. Never
write a full-article conclusion from unread sections.

## Non-negotiable order

Execute these phases in order. They are one reading workflow, not separate API calls:

```text
source map
  → identify the controlling claim and pivot
  → reconstruct the background line and text movement
  → decompress knowledge
  → reconstruct the author's problem world
  → test boundaries
  → transfer
```

Claim identification is the hard gate for the rest of the reading. Do not let section order,
repetition, vivid examples, or the title alone determine the article's center. Before explaining
background or producing an outline, be able to state what expectation the text sets up, what later
turn changes or sharpens it, and which claim best explains the whole route.

### 0. Map the source and its layers

Before interpreting a multi-document package, identify what each source is and how it was made:

- original speech, writing, data, or other primary material;
- transcript, translation, excerpt, or other transformation;
- commentary, tutorial, editorial framing, index, or prompt derived from it.

Record speaker/author only when the source supports the attribution. State transformation risks
such as machine transcription, OCR, excerpting, or unknown authorship. Do not merge layers into a
single “article voice”. For a single authored text, briefly confirm its source and proceed.

### 1. Identify the controlling claim and pivot

Read the whole available text before deciding what it is centrally about. Track the relationship
between the title, opening, explicit turns, and ending:

1. **Opening expectation:** what does the title or opening invite the reader to expect or assume?
2. **Pivot:** where does the author revise, reject, complicate, or redirect that expectation? Look
   for explicit self-corrections, contrastive turns, newly named unease, or a question that reframes
   earlier material.
3. **Controlling claim:** what claim best explains why the author makes that turn and how the ending
   resolves, deepens, or leaves it open?
4. **Whole-text test:** does this claim account for the opening, the pivot, the selection and
   function of later material, and the ending? Can a competing candidate explain those parts as
   well? A claim that explains only one section is supporting, not controlling. When the author
   explicitly revises the opening frame, give that later framing its argumentative weight rather
   than averaging the two frames into a neutral summary.
5. **Material hierarchy:** classify passages as central claim, support, illustration, side thread,
   or unresolved concern. Give examples only the weight their argumentative job earns; vividness,
   length, and count do not make them central.

Write a one- or two-sentence provisional reading and anchor it to the pivot and ending. For essays
without an explicit reversal, identify the passage that most strongly organizes the other claims;
do not invent a pivot. For interviews or genuinely multi-voice material, allow multiple unresolved
lines rather than forcing one thesis.

**Gate:** before continuing, state (a) the opening expectation, (b) the pivot or organizing passage,
(c) the controlling claim, and (d) one plausible alternative reading that the text does not support
as well. If these cannot be located in the text, continue reading instead of substituting a topic
summary.

### 2. Reconstruct the background line and text movement

Use the provisional claim to recover how the text arrives there. Explain this as a connected account
for a reader who has not read the source—not as a list of topics.

Recover, where present:

1. **Starting situation:** what was happening; who is speaking to whom, responding to what, or acting
   within which concrete circumstance?
2. **Problem pressure:** what changed, failed, was contested, or became urgent? Why would someone in
   this situation need an answer?
3. **Question formation:** how does that pressure become the question the text addresses? What
   alternative questions or concerns appear along the way?
4. **Route through the text:** how do examples, analogies, objections, or topic shifts build toward
   or complicate the controlling claim?
5. **Claim formation:** which earlier moment does each major claim answer, and what role does it
   play in the controlling line?

For conversation, interview, or multi-voice material, reconstruct the exchange: who introduces a
topic, what the other person asks or adds, where the subject shifts, and whether a later claim
answers, extends, or merely sits beside an earlier one.

Anchor this account in source locations and concrete moments. Mark missing links. If the available
text does not establish the real-world situation, say what can and cannot be reconstructed; do not
invent a plausible backstory. External context may be added later, clearly labelled, but cannot
substitute for reading the text's own opening, transitions, and conclusion.

**Gate:** an unfamiliar reader should be able to retell the concrete situation, how the question
forms, why the pivot matters, and how the text arrives at its controlling claim. If the account
could be produced from headings or topic labels alone, return to the source and restore the sequence.

### 3. Recover the article's structure

Distinguish the roles of passages:

- controlling claim, supporting claim, premise, evidence, example, objection, qualification, and
  conclusion;
- the author's claim versus a quoted or rejected claim;
- a temporary hypothesis versus a settled conclusion;
- material central to the line versus material that adds texture or opens a side question.

Describe transitions, not merely topics. Explain how each major passage supports, qualifies,
complicates, or distracts from the controlling claim. Preserve digressions and discontinuities where
they matter; do not retrofit them into a tidy proof.

### 4. Decompress what the article assumes

Only after phases 1–3 are stable, identify the unstated knowledge needed to understand the
article's claims in their own setting. Treat familiar words as possible compression points:
ask what they mean here, rather than importing a default definition.

Start from the article's actual subject and evidence. When relevant, reconstruct the practice or
system it describes:

- What are people actually doing? What steps, decisions, inputs, and outputs are hidden behind a
  broad label such as “creating”, “working”, or “using a tool”?
- What can the named tools or institutions do in this context, and what are their limits? Separate
  observed use from expectation, analogy, and promotional claim.
- Which kinds of knowledge, judgment, coordination, or responsibility belong to different people
  or roles? Do not collapse distinct practices just because they share a name.
- What material and social conditions shape who can participate and how: access, skill, time,
  money, infrastructure, relationships, institutions, or other constraints evidenced by the text?
- Which terms carry a specialist or community meaning that an unfamiliar reader may not share?

These are investigative questions, not a mandatory checklist. Follow only the branches needed to
explain a specific passage or claim. Use concrete instances from the text before generalizing.

Where the article depends on historical change, construct a **historical snapshot**: place the
events and text in time; recover the relevant earlier baseline; identify what changed and for
whom; then describe the conditions represented by the article. Compare groups, places, tools, or
generations only when the source makes that contrast relevant. Do not substitute today's
conditions for the article's, or turn a one-time observation into a timeless trend.

Use the source first. Add external background only when needed to explain a specific compression
point; cite it and mark it `[外部背景]`. If the text does not establish a capability, practice,
timeline, or access condition, mark it `[未决]` and say what evidence would settle it.

For each item, explain which passage or claim it unlocks. Do not append a generic background list.

### 5. Reconstruct the author's problem world

“Author's problem world” means the reality, knowledge, and problem pressure that make the author's
question, concepts, observations, and argumentative choices possible and necessary. It does not
mean a biography or a diagnosis of private psychology.

Build this chain where the evidence permits:

```text
world condition
  → problem pressure
  → author's question
  → chosen concepts and observation angle
  → argumentative choices
  → article claims
```

Ask:

- What conditions make this problem important?
- What does the author see as a problem?
- What concepts make the problem legible?
- Why might this argumentative route have been selected?
- What does the author leave out?
- What competing explanation also fits the available evidence?

Do not turn a plausible motive into an author fact. Preserve competing explanations when the
evidence cannot choose between them.

### 6. Test the boundaries

Check the claims against their conditions:

- time, place, institution, class, culture, and technology;
- definitions and evidence types;
- causal assumptions;
- counterexamples and alternatives;
- missing evidence;
- what the article itself acknowledges or ignores.

Do not manufacture objections merely to sound critical. State where a claim holds, where it needs
qualification, and where it may fail.

### 7. Transfer only what survives

Do not extract a principle from an attractive sentence. For every proposed transfer, state:

- the original method or mechanism;
- why it works;
- required conditions;
- what cannot be transferred;
- a new-domain example;
- a failure test.

## Evidence and certainty

Tag important judgments with exactly one of these labels:

- `[原文明确]` — directly stated or directly quotable from the article;
- `[由原文推断]` — a reasonable inference from the article, not directly stated;
- `[外部背景]` — material from outside the article used to explain it;
- `[竞争解释]` — a distinct evidence-based interpretation;
- `[未决]` — current material is insufficient to decide.

Never silently upgrade:

```text
[外部背景]      → [原文明确]
[由原文推断]    → author fact
[竞争解释]      → author's actual motive
[未决]          → conclusion
```

Use available search tools to verify external background when necessary. If no reliable source is
available, mark the item `[未决]` or `[外部背景｜待核实]`; do not fill the gap with confident
general knowledge.

Every important judgment needs a lightweight source reference:

- existing chapter, section, page, or paragraph location; and
- a short quotation when useful.

If the source has no stable locations, assign temporary paragraph references such as `[P12]` while
reading. Do not quote long passages merely to create an appearance of rigor.

## Report format


Return one reader-facing report with this order:

```markdown
# 文章标题

## 0. 先把现场还原出来

## 1. 这段文字怎样走到它的主张

## 2. 它怎样把问题变成论证

## 3. 读懂它需要补回哪些知识

## 4. 什么样的世界会让这个问题出现

## 5. 作者看见了什么，又没看见什么

## 6. 结论在哪些条件下成立

## 7. 可以迁移什么，不能迁移什么

## 8. 还没有理解清楚的地方

## 附录：关键原文片段
```

Section 0 is a concise source map for multi-source material: name each layer and its
transformation limits. For a single text, state its genre, speaker/author if known, and coverage.

Sections 1–2 are the reader-facing explanation, not an analyst's outline. Write in natural,
concrete prose. Keep a clear person or thing as the subject of each sentence; prefer verbs that
show what happened over stacked abstract nouns. Explain a concept before relying on it.

Make each paragraph do one job: state the moment or claim, show the source detail that supports
it, then explain why it matters to the next step. Name what a vague pointer such as “this”, “that
possibility”, or “the shift” refers to. If a sentence needs the reader to unpack several
transitions at once, split it and make the transitions explicit.

Do not narrate the analysis process (“the main line is…”, “the article then turns to…”) in place
of explaining the people, events, and reasoning. Avoid ornamental contrasts, repeated “not X but
Y” constructions, jargon, and abstract summaries when a concrete account would be clearer.
Preserve the author's uncertainty and complexity without making the prose itself obscure.

Section 1 must let an unfamiliar reader follow the situation, how the question forms, and why the
next idea arises. For conversation, include who says what to whom and how the exchange changes
direction. Do not start with a topic list or thesis label.

Section 2 explains the argument and its transitions. Keep quotation, inference, and outside
context distinct, but do not attach a bracketed label to every sentence. Put source references
where they help the reader check a claim; keep evidence tags light enough that they do not break
the sentence's flow. If the material does not support a coherent single line, show the breaks
rather than inventing one.

Section 3 explains only the background needed to understand the text. Where practice or historical
change matters, make the hidden steps, capabilities, roles, constraints, and relevant time
snapshot concrete. Follow the article's own evidence and distinctions; don't apply a fixed domain
template or import present-day conditions.

The report may be shorter or longer according to the article. Prefer a readable main explanation
plus detailed evidence over a rigid word count. The section on the author's problem world must
explain the chain from conditions to question to article choices; it must not become a biography.

End with 3–7 concrete follow-up questions or reading gaps when they exist. Do not invent questions
just to fill a quota.

## Final self-check

Before returning the report, check:

1. Did I map the source layers and their transformation limits before interpreting a multi-source package?
2. Can an unfamiliar reader retell the concrete situation, problem pressure, question formation, and route to the claims from section 1 alone?
3. Does section 1 explain why later ideas arise, rather than list themes or restate the thesis?
4. Did I distinguish the author's claim from my interpretation?
5. Can every important judgment be located in the text or labelled as external/inferred?
6. Did I unpack the specific activities, concepts, capabilities, roles, and constraints the text relies on, rather than importing a generic domain template?
7. Where timing changes the meaning, did I reconstruct the source's relevant historical snapshot and avoid silently applying present-day conditions?
8. Did each background item explain a real difficulty in understanding the text?
9. Did I reconstruct the author's problem world rather than biography or private psychology?
10. Did I preserve competing explanations, discontinuities, and unresolved gaps?
11. Did I test the conditions and failure modes before proposing transfer?
12. Did I disclose unread or unavailable sections?
13. Does this report help a human return to the text instead of pretending to replace it?
14. Does each paragraph make one clear move, with concrete subjects and references a reader can follow without rereading?
15. Read the report aloud: where wording sounds translated, abstract, or tangled, rewrite it before returning.
