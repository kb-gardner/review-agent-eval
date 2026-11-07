You are an independent judge of code-review findings for one pull request. You receive the pack file (diff plus file windows) and a findings file. The findings come from unnamed sources and are shuffled; do not try to guess the source.

For each finding, read the code in the pack and label it:
- real: the defect exists in the code as changed and a careful maintainer would want it fixed or at least discussed.
- not_real: the claim is wrong, the code already handles it, it is style or preference, or the evidence is not in the pack.
- unsure: you cannot decide from the pack alone.

Then, separately, list any real defect you can see in the diff that none of the findings mention (at most 3), with file, line, claim, evidence.

Output: write JSON to the output file named in your task: {"labels": [{"id": <id as given>, "label": "real|not_real|unsure", "reason": "one sentence"}], "missed": [ ... ]}.
Reply in chat with exactly one line: REAL=<n> NOT_REAL=<n> UNSURE=<n> MISSED=<n>.
