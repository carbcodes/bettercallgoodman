# 07 · Write-up and demo

**Owner:** Carlos · **Start:** 3:15 at the latest, earlier if strength is done.

## Write-up (submit page)

Short, with one section per question the judges ask:

1. **What we built**: one paragraph, Goodman turns an AI's design answer into claims and checks each with physics and geometry.
2. **How it checks**: the pipeline diagram from 00, plus why the AI only extracts and never judges.
3. **What we found**: the results table from `results/summary.md` (accepted / caught / false alarm / missed per area), plus the 2–3 most interesting mistakes the AI made, each quoted.
4. **Correct answers**: a link to each `truth.yaml`, whose `why` holds the hand calc and source.
5. **Limits**: what we don't model (dynamic loads beyond fatigue, contact friction, manufacturing tolerances), and how many cases we ran (small sample, honest about it).
6. **AI attempts**: model, date, interface, plus a link to the `attempt.json` files.

## Demo (3 minutes)

| Time | Show |
| --- | --- |
| 0:00–0:20 | The problem: an AI's confident "safe, SF = 2" on a real part |
| 0:20–1:30 | One task end to end: the prompt, the AI's answer, the claims Goodman extracted (with quotes), the check, and the red flag with *why* (stress heatmap or collision render) |
| 1:30–2:10 | The control case: Goodman **accepts** a correct answer, so it isn't just flagging everything |
| 2:10–2:40 | The results table across all tasks |
| 2:40–3:00 | Why it matters: hardware fails in the real world, and this is the check before you print, machine or ship |

Rehearse it twice with a timer. Have the result files open in tabs in case anything live breaks.

## Submission checklist

- [ ] Code runs from a clean clone with the README's setup steps
- [ ] Every task has `prompt.md`, `truth.yaml` (with `why`), `attempt.json`, `claims.json`, `result.json`
- [ ] `results/summary.md` is generated, not typed by hand
- [ ] Every attempt has the same model, the date and the exact prompt
- [ ] At least one control case per area comes out `accepted`
- [ ] Zip uploaded to hackerhousecampus.com/mercor/submit **before 4:00**
