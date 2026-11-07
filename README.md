# Does a multi-agent code reviewer beat one good pass?

I planned to build an AI code-review service with the design everyone draws: three specialist
reviewer agents (correctness, security, contract) and a verifier agent that checks their work.
Before I wrote the product, I set a kill rule and tested it against a single-pass reviewer.

**The multi-agent design lost.** It cost 3x as much and found fewer bugs. I dropped it.

## The setup

- **Real code.** 6 merged pull requests from open-source projects (Tailwind CSS x2, Vite,
  Express, better-auth, Laravel Jetstream), 48 to 277 changed lines each. Each review got the
  diff plus 200 lines of context around every touched file.
- **Planted bugs.** One agent planted 2 realistic bugs in each PR, 12 in total. Examples: a
  guard that checks `!server?.hot` instead of `!server`, and a regression test whose input
  makes it pass with or without the fix. The ground truth is in
  [`harness/ground-truth.json`](harness/ground-truth.json).
- **Arm A:** one reviewer pass with a strict-evidence prompt ("quote the lines; an empty list
  is a valid answer").
- **Arm B:** three lens reviewers, then a verifier that re-checks each finding and merges
  duplicates.
- **The judge.** A stronger model labels every surviving finding as real or not real. It sees
  the findings shuffled, with no labels to show which arm wrote them. It also lists bugs that
  nobody reported.
- **The kill rule, set before the run:** Arm B must beat Arm A on precision by 20 points, or
  the fan-out is not worth 3x the cost.

## Results (12 planted bugs)

| Arm | Raw findings | After verifier | Planted bugs found | Precision (judge) |
|---|---|---|---|---|
| A: one pass | 9 | n/a | **9 of 12** | 8 of 9 |
| B: three lenses + verifier | 19 | 9 | 8 of 12 | 8 of 9 |

On the 6 clean PRs, both arms had zero false positives.

## What I learned

1. **The evidence-gated prompt was what gave precision.** A single pass that must quote its
   lines almost never invents a bug. The verifier added no precision on top of that.
2. **The model tier drives recall, not the number of passes.** The stronger judge model found
   all 12 plants, including every plant the reviewer arms missed.
3. **A verifier only helps when it is stronger than the reviewer.** Both arms reported the
   right line for one plant with the wrong explanation of the damage. The same-tier verifier
   kept it. The stronger judge rejected it and gave the correct mechanism.
4. **De-duplication is worth keeping.** The verifier collapsed 19 findings to 9 and lost
   nothing real.
5. **Most of the specialist lenses added nothing.** The security lens found nothing on 5 of 6
   PRs, and the correctness and contract lenses mostly found the same bugs.

## The decision

I dropped the fan-out. The new design is one strong-model review with the evidence prompt, one
strong-model check of each finding's mechanism, and de-duplication against comments already on
the PR. It is cheaper and catches more.

## Caveats I would want a reviewer to call out

- **The sample is small:** 6 PRs and 12 plants. This result was enough to kill a design, not
  to publish a benchmark.
- **The planter and the judge were the same model family.** Shared priors could inflate the
  judge's recall on the plants. I ran a bias check with the smaller model as judge on 2 packs.
  Its real/not-real labels matched the stronger judge every time. It also missed the same
  plants as the smaller reviewers did. So I treat "the stronger model found 12 of 12" as
  likely but not proven. I treat "the smaller model found about 9 of 12" as solid.

## Reproduce the scores

```bash
cd harness
python3 score.py
```

| File | What it is |
|---|---|
| `prs.json`, `pick_prs.py` | How the PRs were chosen |
| `pack.py` | Builds a review pack: the diff plus context windows |
| `packs/`, `packs-planted/` | The clean packs and the packs with planted bugs |
| `ground-truth.json` | Every planted bug: file, line, kind, original and planted code |
| `prompts/` | Every reviewer, verifier and judge prompt |
| `stage.py` | Shuffles the findings and strips the labels before the judge sees them |
| `out/`, `out-planted/` | Raw model outputs per arm and per pack |
| `score.py` | Matches findings to plants (same file, within 25 lines) and totals the judge labels |

The runs used Claude models, Sonnet for the reviewers and Opus for the planter and the judge.
I ran them in September 2026. The packs quote short excerpts of MIT-licensed open-source
projects for review purposes; those excerpts stay under their projects' licenses.

Kyle Gardner, [github.com/kb-gardner](https://github.com/kb-gardner)
