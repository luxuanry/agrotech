// Traffic light: a coloured dot plus the word, so colour is never the only signal.
const WORDS = { green: "Green", yellow: "Yellow", red: "Red" };

export default function Light({ light, large = false }) {
  return (
    <span className={`light light-${light}${large ? " light-large" : ""}`}>
      <span className="light-dot" aria-hidden="true" />
      {WORDS[light] || light}
    </span>
  );
}
