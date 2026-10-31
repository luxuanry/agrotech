// The product's ingredient list, set large like a pack label. Each additive we
// analysed is marked in the colour of its traffic light.

function findRanges(text, marks, catalog) {
  const lower = text.toLowerCase();
  const ranges = [];
  for (const mark of marks) {
    const entry = catalog.find((a) => a.code === mark.code);
    const needles = [mark.code.toLowerCase(), ...(entry ? entry.aliases : [])];
    for (const needle of needles) {
      let from = 0;
      let idx;
      while ((idx = lower.indexOf(needle.toLowerCase(), from)) !== -1) {
        ranges.push({ start: idx, end: idx + needle.length, ...mark, name: entry?.name });
        from = idx + needle.length;
      }
    }
  }
  // Keep the earliest, longest match and drop anything overlapping it.
  ranges.sort((a, b) => a.start - b.start || b.end - a.end);
  const kept = [];
  for (const r of ranges) {
    if (!kept.length || r.start >= kept[kept.length - 1].end) kept.push(r);
  }
  return kept;
}

export default function IngredientStatement({ text, marks, catalog }) {
  if (!text) return null;
  const ranges = findRanges(text, marks, catalog);
  const parts = [];
  let cursor = 0;
  ranges.forEach((r, i) => {
    if (r.start > cursor) parts.push(text.slice(cursor, r.start));
    parts.push(
      <mark key={i} className={`mark mark-${r.light}`} title={`${r.code} ${r.name || ""}: ${r.light}`}>
        {text.slice(r.start, r.end)}
      </mark>
    );
    cursor = r.end;
  });
  parts.push(text.slice(cursor));
  return <p className="statement">{parts}</p>;
}
