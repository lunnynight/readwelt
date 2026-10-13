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

1. Identify its section structure.
2. Read the article section by section.
3. Keep a compact working sheet of section claims, source locations, compressed concepts, and open
   questions.
4. Only after the available text has been covered, synthesize the reverse-reading report.

When a temporary working sheet is needed, use a plain Markdown file such as
`.readwelt-reading-notes.md`. It may contain coverage and evidence notes, but never hidden
chain-of-thought or unrestricted reasoning transcripts. For a short article, do not create a file.

If the article is only partially available, continue only with an explicit coverage notice. Never
write a full-article conclusion from unread sections.

## Non-negotiable order

Execute these phases in order. They are one reading workflow, not six separate API calls:

```text
article mainline
  → article structure
  → knowledge decompression
  → author's problem world
  → boundary test
  → transfer
```

### 1. Recover the article's mainline

Use only the article. Establish:

- the question the author is answering;
- the core claim and major claims;
- the evidence for each claim;
- the reasoning chain;
- gaps the article itself leaves unresolved.

Do not introduce external history, theory, or biography here. Do not replace the author's wording
with your preferred thesis.

### 2. Recover the article's structure

Distinguish the roles of passages:

- question, definition, premise, evidence, example, objection, qualification, conclusion;
- the author's claim versus a quoted or rejected claim;
- a temporary hypothesis versus a settled conclusion.

Describe how the argument moves, not merely what each paragraph mentions.

### 3. Decompress what the article assumes

Only after phases 1–2 are stable, identify:

- concepts the text does not fully define;
- knowledge it assumes the reader already has;
- historical, institutional, technical, or disciplinary conditions it compresses;
- reasoning steps that are obvious to the author but not to an ordinary reader;
- verification targets and conflicts.

For each item, explain why it is needed to understand a specific part of the article. Do not append
a generic background-knowledge list.

### 4. Reconstruct the author's problem world

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

### 5. Test the boundaries

Check the claims against their conditions:

- time, place, institution, class, culture, and technology;
- definitions and evidence types;
- causal assumptions;
- counterexamples and alternatives;
- missing evidence;
- what the article itself acknowledges or ignores.

Do not manufacture objections merely to sound critical. State where a claim holds, where it needs
qualification, and where it may fail.

### 6. Transfer only what survives

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

## 0. 先说这篇文章要解决什么

## 1. 文章自己的主线

## 2. 文章是怎样论证的

## 3. 文章压缩掉了哪些知识

## 4. 让作者能够这样写的世界

## 5. 文章看见了什么，没看见什么

## 6. 结论在哪些条件下成立

## 7. 可以迁移什么

## 8. 还没有理解清楚的地方

## 附录：关键原文片段
```

The report may be shorter or longer according to the article. Prefer a readable main explanation
plus detailed evidence over a rigid word count. The section on the author's problem world must
explain the chain from conditions to question to article choices; it must not become a biography.

End with 3–7 concrete follow-up questions or reading gaps when they exist. Do not invent questions
just to fill a quota.

## Final self-check

Before returning the report, check:

1. Did I recover the article's internal mainline before using external context?
2. Did I distinguish the author's claim from my interpretation?
3. Can every important judgment be located in the article or labelled as external/inferred?
4. Did each background item explain a real difficulty in understanding the article?
5. Did I reconstruct the author's problem world rather than biography or private psychology?
6. Did I preserve competing explanations and unresolved gaps?
7. Did I test the conditions and failure modes before proposing transfer?
8. Did I disclose unread or unavailable sections?
9. Does this report help a human return to the article instead of pretending to replace it?
