// Turn the raw ChatGPT answer (copied from the page, where every math glyph sits on
// its own line and each equation appears twice: once as glyphs, once as linear
// text) into readable blocks. Display only: the raw text stays in attempt.json and
// is one click away in the UI. Each block keeps its [start, end) range in the raw
// answer so claim quotes (which are verbatim substrings) can be highlighted.

const MATH_CHAR = /[\u{1D400}-\u{1D7FF}​]/u;
const SHORT = 22;
// a short line that is still prose ("Cross-sectional area:", "8 mm rod")
const isProse = (t) => / /.test(t.trim()) && /[a-z]{3,}/.test(t) && !MATH_CHAR.test(t);

const norm = (s) => s.normalize("NFKC").replace(/[\s​:]/g, "");
const sortChars = (s) => [...s].sort().join("");

// Greedy: from the start of the group, find the shortest glyph span lines[a:k]
// whose characters reappear exactly in the next span lines[k:m] (the linear copy),
// keep the glyph span, skip the copy, repeat. Lines that never pair up are kept.
function dedupeMath(lines) {
  const n = lines.map(norm);
  const keep = [];
  let a = 0;
  while (a < lines.length) {
    let found = null;
    let glyph = "";
    for (let k = a + 1; k < lines.length && !found; k++) {
      glyph += n[k - 1];
      if (!glyph) continue;
      const target = sortChars(glyph);
      let copy = "";
      for (let m = k + 1; m <= lines.length; m++) {
        copy += n[m - 1];
        if (copy.length > glyph.length) break;
        if (copy.length === glyph.length && sortChars(copy) === target) { found = [k, m]; break; }
      }
    }
    if (!found) { keep.push(...lines.slice(a)); break; }
    keep.push(...lines.slice(a, found[0]));
    a = found[1];
  }
  return keep;
}

function joinMath(lines) {
  return lines
    .map((l) => l.normalize("NFKC").replace(/​/g, "").trim())
    .filter(Boolean)
    .join(" ")
    .replace(/(?<=^|\s)([A-Za-z])((?:\s[A-Za-z])+)(?=\s|$|[,.:;)])/g, (m) => m.replace(/\s/g, ""))
    .replace(/\s+([,.:;)])/g, "$1")
    .replace(/\(\s+/g, "(");
}

export function parseAnswer(raw) {
  const lines = [];
  let pos = 0;
  for (const text of raw.split("\n")) {
    lines.push({ text, start: pos, end: pos + text.length });
    pos += text.length + 1;
  }
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    if (!ln.text.trim()) {
      if (blocks.length && blocks[blocks.length - 1].type !== "gap") blocks.push({ type: "gap" });
      i++;
      continue;
    }
    // a run of short lines that contains math glyphs -> one equation line
    // (blank lines inside the run are part of the copied equation layout)
    let j = i;
    let hasMath = false;
    while (j < lines.length && lines[j].text.trim().length <= SHORT && !isProse(lines[j].text)) {
      if (MATH_CHAR.test(lines[j].text)) hasMath = true;
      j++;
    }
    while (j > i && !lines[j - 1].text.trim()) j--;
    if (hasMath && j - i >= 2) {
      const run = lines.slice(i, j).filter((l) => l.text.trim());
      blocks.push({
        type: "math",
        text: joinMath(dedupeMath(run.map((l) => l.text))),
        start: run[0].start,
        end: run[run.length - 1].end,
      });
      i = j;
      continue;
    }
    blocks.push({ type: "text", text: ln.text, start: ln.start, end: ln.end });
    i++;
  }
  return blocks;
}

// Locate each claim's quote in the raw answer. Returns [{id, start, end}] for
// the quotes found (verbatim first, then whitespace-insensitive).
export function locateQuotes(raw, claims) {
  const out = [];
  for (const c of claims || []) {
    const q = (c.quote || "").trim();
    if (!q) continue;
    let s = raw.indexOf(q);
    let e = s + q.length;
    if (s < 0) {
      const pattern = q.split(/\s+/).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+");
      const m = new RegExp(pattern).exec(raw);
      if (!m) continue;
      s = m.index;
      e = s + m[0].length;
    }
    out.push({ id: c.id, start: s, end: e });
  }
  return out;
}
