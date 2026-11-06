# Better Call Goodman

**AI says your part is safe. Goodman checks.**

AI models now answer engineering questions with confidence: "this bracket holds 20 kg with a safety factor of 2", "the arm clears the base through its full range", "this part is ready to mill". Those answers often sound right and are wrong.

Goodman is a design checker. It reads an AI's answer to a real design task, pulls out every engineering claim it makes, and checks each one with physics and geometry instead of opinion:

| Area | Owner | Checks |
| --- | --- | --- |
| Strength | Carlos | Stress, deflection, safety factor, buckling, fatigue, stress concentration |
| Simulation | Fabian | Collisions, clearances, range of motion |
| 3D printing (stretch) | Fabian | Overhangs, thin walls, bed contact, hole sizes |
| CNC milling (stretch) | Fabian | Inside corners, pocket depth, undercuts, hole depth, threads |

The name comes from John Goodman's 1899 fatigue line: stay under the line and the part survives.

Built for Mercor Hack Day at Georgia Tech, November 6, 2026.

## Specs

1. [Overview and plan](specs/00-overview.md): the problem, how Goodman works, who does what, timeline
2. [Formats](specs/01-formats.md): task, AI attempt, ground truth and result files
3. [Claim extraction](specs/02-claims.md): turning an AI answer into checkable claims
4. [Strength checker](specs/03-strength.md)
5. [Collision checker](specs/04-collision.md)
6. [3D printing checker](specs/05-printing.md) (stretch)
7. [CNC milling checker](specs/06-cnc.md) (stretch)
8. [Write-up and demo](specs/07-writeup-demo.md)
9. [Next step: automatic setup](specs/08-auto-setup.md): Goodman sets up each problem itself, measured against our hand-written setups
