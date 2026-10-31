// Provenance marker shown next to every number: where does this value come from?
const TAG_HELP = {
  sourced: "From Open Food Facts product data",
  sample: "From the synthetic sample dataset, not a real product",
  estimated: "Computed from other values, with stated assumptions",
  assumed: "Placeholder value, to be replaced with a sourced one",
  model: "Model output (M2), not a measurement",
};

export default function Tag({ tag }) {
  if (!tag) return null;
  return (
    <span className={`tag tag-${tag}`} title={TAG_HELP[tag] || tag}>
      {tag}
    </span>
  );
}
