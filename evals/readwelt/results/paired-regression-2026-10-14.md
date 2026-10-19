# Paired regression: baseline vs revised Readwelt

> **Recorded 2026-10-14.** One paired comparison of two Skill revisions at that time. The limits stated below still apply.

- Baseline Skill: `ca3ac081:skills/readwelt/SKILL.md`
- Revised Skill: working tree at test time
- Model: `default`, stateless; same eight prompts and source fixtures, run once per version
- Inputs: `../cases.json` prompts plus fixture source only. Hidden expectations were not passed to generation calls.
- Grading: `grader.md` and `comparator.md`, applied as blind A/B. A=baseline, B=revised.
- Limits: one run per version; no random-seed control or repeated sampling. This is a small paired regression, not statistical evidence.

## Raw baseline output (A)

```json
{
  "manifesto-inevitability-tension": "表面上有张力，但仅凭这两段不能断定它们互相矛盾。第一段说阶级斗争可能以社会革命改造告终，也可能以斗争各方同归于尽告终；第二段则断言资产阶级灭亡和无产阶级胜利不可避免。要判断两者能否并存，关键在于被省略的部分如何说明这两种结局，以及“不可避免”指什么。由于中间论述缺失，目前无法确认作者怎样化解这处张力。",
  "inverted-condition": "工人得有工作才能生活；但只有当他们的劳动能替资本增加价值时，才找得到工作。换句话说，他们的生计依赖于雇主是否能从雇用他们的劳动中获利。",
  "speaker-opponent": "作者明确反对把其立场说成“要废除一切个人财产”。他区分了劳动产品的个人占有：如果这些产品用于维持个人的日常生活，他说并不打算废除这种占有。仅凭这段话，不能进一步确定作者对其他财产形式的完整立场。",
  "scope-difference": "不一定矛盾。第一句话描述组织在 T1 没有地方分支，第二句话描述组织扩张后的 T2 已有地方分支；如果两个说法指向不同时间，组织状况可以在这期间发生变化。只有在它们声称描述同一时间、同一范围时，才可能冲突。",
  "partial-source": "现有摘录只能看出：开头说某项政策曾被采纳，结尾说它后来经过修订。中间段落缺失，因此无法判断作者怎样解释采纳政策的理由、修订的原因，或这两件事如何构成论证；不能据此完整概括全文的论证。",
  "unsupported-process": "目前不宜原样保留这句话。现有材料只有给定来源和报告草稿，没有早期草稿、搜索记录或引文核查结果，因此无法证实“修改了两次”“核实了每条引文”或“没有找到任何过时措辞”。可以删除这些过程性断言；若要保留，应先提供相应记录，并说明核查的范围。尤其“零处”是关于检索结果的绝对说法，需要明确检查了哪些文本、用什么标准判断“过时措辞”。",
  "keyword-only-answer": "没有。草稿只重复了原句的核心说法，没有解释“阶级关系”如何影响政治制度；随后给出蛋糕食谱，也没有说明它与这项主张的关系。因此它没有真正解释原句。",
  "ordinary-summary-trigger": "社区图书馆将于周二闭馆，以进行电气维修。图书馆预计周三上午 9 点重新开放。"
}
```

## Raw revised output (B)

```json
{
  "manifesto-inevitability-tension": "仅凭这两段，不能断定它们互相矛盾。第一段说阶级斗争可能以两种结局收场：社会被革命改造，或斗争中的阶级同归于尽；第二段则断言资产阶级灭亡、无产阶级胜利不可避免。若把第一段理解为列举所有可能结局，第二段似乎排除了“同归于尽”的可能；但第一段也可能是在说斗争的一般结局，而非断言两种结局对这段历史分析同样可能。两段之间的文字被省略了，现有材料不足以判断作者怎样衔接或限定它们，因此应把这种张力留作未决，而不是直接判为矛盾。",
  "inverted-condition": "工人得先找到工作才能生活；但只有当他们的劳动能替资本增加价值时，雇主才会雇用他们。换句话说，他们的生计取决于是否能做对资本有利的工作。",
  "speaker-opponent": "作者反驳的是“要废除一切个人财产”这一说法，并明确表示，他们不打算废除人们把劳动产品用于直接维持生活的个人占有。就这段话而言，作者区分了用于生活的个人占有与对财产制度更广泛的主张；但材料没有说明他们对其他类型财产的完整立场，不能据此替作者补出完整方案。",
  "scope-difference": "不一定矛盾。第一句话说组织在T1没有地方分支，第二句话说它扩张后、到T2时有了地方分支。两句话描述的是不同时间的状态，组织变化就足以解释差异；只有在它们指的是同一时间、同一种“地方分支”定义时，才会构成冲突。",
  "partial-source": "现有摘录只能确认：第一段说某项政策被采纳，最后一段说该政策后来经过修订。由于中间段落被省略，无法判断修订的原因、过程、具体内容，也无法完整概括这段文字的论证。更稳妥的概括是：摘录呈现了政策从采纳到后来修订的先后变化，但没有提供足够材料说明作者如何论证这一变化。",
  "unsupported-process": "不建议在没有佐证时保留这句话作为已核实的过程陈述。当前可用记录只有给定来源和一份草稿，没有早期草稿、搜索记录或引文核对结果，因此无法确认报告是否修改过两次、是否核对了每条引文，或是否确实没有过时措辞。记录缺失并不证明这些事没发生，只意味着这份材料无法支持这些断言。可以删除该句，或改成明确说明核实范围的表述，例如：“现有记录不足以确认修改次数、引文核对情况或过时措辞的检索结果。”",
  "keyword-only-answer": "没有。草稿复述了原句的主张，但随后给出蛋糕食谱，既没有解释“政治制度”或“阶级关系”在此处指什么，也没有说明二者如何关联。它包含相关关键词，却没有解释所给论断。",
  "ordinary-summary-trigger": "社区图书馆星期二因电气维修闭馆。图书馆星期三上午9点重新开放。"
}
```

## Grader and comparator findings

The grader found no critical interpretive failures. Seven of eight cases passed for each version; both received `needs_revision` on the ordinary-summary case because they returned two sentences instead of the requested three. Both preserved the condition, speaker, time scope, partial-source boundary, process-evidence limits, and rejected the keyword-only answer. On manifesto counterpoints, baseline scored 1/2 because it did not directly compare the general and specific scopes; revised scored 2/2 by examining whether the first passage listed all outcomes or described a general pattern. Ordinary-summary coverage scored 1/2 for both. No other reported dimension scored below 2/2.

The comparator returned **B (revised)**, primarily for the manifesto tension case: it more explicitly compared scope and left the inferential step unresolved. It also found that both versions answered the ordinary-summary request in two sentences despite the requested three; no reverse-reading template was forced. This shared instruction-following miss should remain a regression case, not be hidden by the win.

The revised output is better on this single paired run, not proven generally better. The baseline already performed well on seven cases; results do not establish that the prompt change caused the difference or will repeat across models and inputs.
