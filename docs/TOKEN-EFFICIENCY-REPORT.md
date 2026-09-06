# Cole Retrieval Token-Efficiency Report

## Scope and evidence

On 2026-09-06 the user performed a five-question comparison of direct Codex knowledge-base access,
Neptune, and a separate skill-guided reference run. The intention was to validate that Neptune's skill-guided knowledge-base retrieval preserves the intended retrieval behavior while reducing and stabilizing token usage compared with direct Codex access to the same knowledge base.

The gpt-6-astra model was used, with low effort. 

## Questions and order

The reported execution order was **Q2 → Q3 → Q4 → Q1 → Q13**.

| ID | Exact question from the supplied summary |
|---|---|
| Q2 | How are chunking and a knowledge base related? |
| Q3 | When is RAG useful and what role does chunking play? |
| Q4 | What does Cole mean when he says an LLM gets into “the dumb zone”? |
| Q1 | Why does chunking matter in RAG? |
| Q13 | What is OpenClaw, Pi, and n8n separately, in comparison to each other, and to what extent are they preferred by Cole? |

## Reported usage

For the measured five-question sequence, “Used tokens” is the reported metric.
- Direct Codex knowledge-base access used **83.4K** tokens.
- Neptune used **59.6K** tokens: about **28.5% less**.

| Approach | Reported sequence usage | Comparison |
|---|---:|---|
| Direct Codex KB access | 83.4K | Baseline |
| Neptune | 59.6K | 23.8K lower than direct access; approximately 28.5% less |
| Separate skill-guided reference | 59.0K | Neptune is 0.6K higher; approximately 1.0% more |

Calculations from the rounded figures:

- Reduction relative to direct access: `(83.4 − 59.6) / 83.4 × 100 ≈ 28.5%`.
- Neptune relative to the reference: `(59.6 − 59.0) / 59.0 × 100 ≈ 1.0%`.

### Startup and first question

| Component | Neptune | Skill-guided reference |
|---|---:|---:|
| Separately reported startup | 13.4K | Not separately reported |
| First Q2, excluding Neptune's separate startup | 9.1K | Not separately reported |
| Neptune startup + Q2 / reference initial Q2 | 22.5K | 22.5K |

The combined values match **at the reported precision**. This supports comparing
startup plus the first answer rather than comparing Neptune's 9.1K Q2 alone against
the reference's 22.5K initial Q2. 

### Per-question variation

The supplied summary reports Neptune's post-startup question usage as approximately
**7.5K–11.5K**, with substantially wider variation for direct retrieval.

## Conclusion

The results strongly indicate that Neptune reproduced the intended skill-guided retrieval behavior. It reduced total used-token consumption by about **28.5%** in this workload and made per-question cost substantially more predictable.

