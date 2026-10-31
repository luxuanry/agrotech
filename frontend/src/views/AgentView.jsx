import { useEffect, useRef, useState } from "react";
import { agentHealth, agentRewrite } from "../agentApi.js";

const EXAMPLE =
  "Eau, avoine 12%, huile de tournesol, phosphate dipotassique, carbonate de calcium, sel, stabilisant : gomme gellane, vitamines (D2, B12)";

const NOVA_GROUPS = [
  [1, "Unprocessed or minimally processed", "Whole foods as they come: grains, milk, fruit, nuts."],
  [2, "Processed culinary ingredients", "Oils, butter, sugar, salt: extracted from foods, used in cooking."],
  [3, "Processed foods", "Foods with salt, sugar or oil added: bread, cheese, tinned vegetables."],
  [4, "Ultra-processed foods", "Industrial formulas built on additives and extracts: emulsifiers, flavourings, isolates, syrups."],
];

// Split on commas that are not inside parentheses, like the classifier does.
function splitIngredients(text) {
  return text
    .split(/,(?![^()]*\))/)
    .map((s) => s.trim())
    .filter(Boolean);
}

const norm = (s) => s.toLowerCase().replace(/[.\s]+$/, "").replace(/\s+/g, " ").trim();
const AMOUNT_RE = /(\d+(?:[.,]\d+)?)\s?%/;

// "avoine 12%" -> { name: "avoine", amount: "12 %" }
function parseIngredient(item) {
  const m = item.match(AMOUNT_RE);
  if (!m) return { name: item, amount: null };
  const name = item.replace(m[0], "").replace(/\s+/g, " ").replace(/\s+([),:])/g, "$1").replace(/\(\s*\)/g, "").trim();
  return { name, amount: `${m[1].replace(",", ".")} %` };
}

const pct = (p) => `${(p * 100).toFixed(p < 0.01 || p > 0.99 ? 1 : 0)}%`;

function points(before, after) {
  const d = (after - before) * 100;
  return `${d > 0 ? "+" : d < 0 ? "−" : "±"}${Math.abs(d).toFixed(1)} points`;
}

function NovaBadge({ group, large }) {
  return <span className={`nova-badge nova-${group}${large ? " nova-large" : ""}`}>NOVA {group}</span>;
}

function ScoreBar({ score, threshold }) {
  return (
    <div className="agent-bar" data-pass={score < threshold}>
      <div className="agent-bar-track">
        <div className="agent-bar-fill" style={{ width: `${score * 100}%` }} />
        {threshold != null && <div className="agent-bar-target" style={{ left: `${threshold * 100}%` }} title={`Target: below ${pct(threshold)}`} />}
      </div>
      <span className="agent-bar-value">{pct(score)}</span>
    </div>
  );
}

function AmountsTable({ text, original }) {
  const before = new Map(splitIngredients(original).map((it) => [norm(parseIngredient(it).name), parseIngredient(it).amount]));
  const rows = splitIngredients(text).map((it) => {
    const { name, amount } = parseIngredient(it);
    const key = norm(name);
    const was = before.has(key) ? before.get(key) : undefined;
    const status = was === undefined ? "new" : was !== amount ? "amount" : "kept";
    return { name, amount, was, status };
  });
  const LABEL = { new: "New", amount: "Amount changed", kept: "Kept" };
  return (
    <div className="table-wrap">
      <table className="agent-table">
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">Ingredient</th>
            <th scope="col" className="num">Amount</th>
            <th scope="col">Compared with the original</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={`row-${r.status}`}>
              <td className="muted">{i + 1}</td>
              <td>{r.name}</td>
              <td className="num">{r.amount || <span className="muted">not declared</span>}</td>
              <td>
                <span className={`agent-status status-${r.status}`}>{LABEL[r.status]}</span>
                {r.status === "amount" && <span className="muted small"> was {r.was || "not declared"}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Changes({ changes }) {
  if (!changes?.length) return null;
  return (
    <ul className="agent-changes">
      {changes.map((c, i) => {
        const [from, to] = String(c).split(/\s*->\s*/);
        return (
          <li key={i}>
            {to === undefined ? (
              c
            ) : (
              <>
                <span className="from">{from}</span>
                <span className="muted" aria-label="replaced by">→</span>
                <span className="to">{to}</span>
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function ScoreMeaning({ result, threshold }) {
  const { original, best } = result;
  return (
    <section className="agent-section">
      <h3>What the score means</h3>
      <dl className="agent-meaning">
        <div>
          <dt>NOVA group</dt>
          <dd>
            The NOVA system sorts foods into four groups by how much they are processed. The group shown is the one the
            classifier finds most likely for this ingredient list.
            <ul className="agent-groups">
              {NOVA_GROUPS.map(([g, name, help]) => (
                <li key={g} className={g === original.group || g === best.group ? "is-current" : undefined}>
                  <NovaBadge group={g} />
                  <span>
                    <strong>{name}.</strong> {help}
                    {g === original.group && <span className="muted"> Original.</span>}
                    {g === best.group && <span className="muted"> Rewritten.</span>}
                  </span>
                </li>
              ))}
            </ul>
          </dd>
        </div>
        <div>
          <dt>Probability of NOVA 4</dt>
          <dd>
            How likely the classifier thinks the list is ultra-processed, from 0 to 100%. The agent stops once it is below the
            target ({pct(threshold)}). Here it went from {pct(original.score)} to {pct(best.score)} (
            {points(original.score, best.score)}).
          </dd>
        </div>
        <div>
          <dt>Limits</dt>
          <dd>
            The classifier (hsilvosa/nova-group-classifier, about 97% accurate on Open Food Facts) reads the ingredient text
            only. List length and the number of ingredients count too, so shorter lists score lower on their own. It is a
            model estimate, not an official NOVA classification, and it does not check stability, taste or regulation.
          </dd>
        </div>
      </dl>
    </section>
  );
}

function verdict(result, rounds, threshold) {
  const { original, best, success } = result;
  if (success && best.round === 0) return `Already below the target (${pct(threshold)} probability of NOVA 4). No rewrite needed.`;
  if (success) return `Target reached in round ${best.round}: NOVA ${original.group} → NOVA ${best.group}.`;
  if (best.round === 0) return `No round improved on the original after ${rounds} round${rounds === 1 ? "" : "s"}.`;
  return `Target not reached after ${rounds} round${rounds === 1 ? "" : "s"}. Showing the lowest-scoring list.`;
}

export default function AgentView() {
  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState(null);
  const [input, setInput] = useState("");
  const [threshold, setThreshold] = useState(0.5);
  const [maxRounds, setMaxRounds] = useState(5);

  const [phase, setPhase] = useState("idle"); // idle | running | done | error
  const [attempts, setAttempts] = useState([]);
  const [roundErrors, setRoundErrors] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [runThreshold, setRunThreshold] = useState(0.5);
  const [copied, setCopied] = useState(false);
  const abortRef = useRef(null);

  useEffect(() => {
    agentHealth().then(setStatus).catch((e) => setStatusError(e.message));
  }, []);

  async function run() {
    const ingredients = input.trim();
    if (!ingredients || phase === "running") return;
    const controller = new AbortController();
    abortRef.current = controller;
    setPhase("running");
    setAttempts([]);
    setRoundErrors([]);
    setResult(null);
    setError(null);
    setRunThreshold(threshold);

    let finished = false;
    try {
      await agentRewrite(
        { ingredients, threshold, maxRounds },
        (ev) => {
          if (ev.type === "attempt") setAttempts((a) => [...a, ev.attempt]);
          else if (ev.type === "round_error") setRoundErrors((r) => [...r, ev]);
          else if (ev.type === "result") {
            finished = true;
            setResult(ev.result);
            setPhase("done");
          } else if (ev.type === "error") throw new Error(ev.message);
        },
        controller.signal
      );
      if (!finished) throw new Error("The agent stopped before returning a result.");
    } catch (e) {
      if (e.name === "AbortError") setPhase("idle");
      else {
        setError(e.message);
        setPhase("error");
      }
    } finally {
      abortRef.current = null;
    }
  }

  function copy() {
    navigator.clipboard.writeText(result.best.ingredients).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  const running = phase === "running";
  const rounds = attempts.slice(1);
  const roundsDone = rounds.length + roundErrors.length;
  const timeline = [
    ...rounds.map((a) => ({ kind: "attempt", round: a.round, a })),
    ...roundErrors.map((e) => ({ kind: "error", round: e.round, e })),
  ].sort((x, y) => x.round - y.round);

  return (
    <div className="workspace">
      <aside className="panel" aria-label="Agent input">
        <h2 className="panel-title">NOVA rewriter agent</h2>
        <p className="muted small">
          Paste an ingredient list, with percentages if you have them. An LLM rewrites it, the NOVA classifier scores each
          version, and the loop repeats until the list is no longer rated ultra-processed.
        </p>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            run();
          }}
        >
          <div className="field">
            <label htmlFor="a-ing">Ingredient list, as on the pack</label>
            <textarea
              id="a-ing"
              rows={7}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) run();
              }}
              placeholder={EXAMPLE}
              disabled={running}
            />
            <button type="button" className="link-button agent-example" onClick={() => setInput(EXAMPLE)} disabled={running}>
              Use an example
            </button>
          </div>

          <div className="grid-fields">
            <div className="field">
              <label htmlFor="a-threshold">Target: P(NOVA 4) below</label>
              <input
                id="a-threshold"
                type="number"
                min="0.05"
                max="0.95"
                step="0.05"
                value={threshold}
                onChange={(e) => setThreshold(Math.min(0.95, Math.max(0.05, Number(e.target.value) || 0.5)))}
                disabled={running}
              />
            </div>
            <div className="field">
              <label htmlFor="a-rounds">Max rounds</label>
              <input
                id="a-rounds"
                type="number"
                min="1"
                max="10"
                step="1"
                value={maxRounds}
                onChange={(e) => setMaxRounds(Math.min(10, Math.max(1, Math.round(Number(e.target.value)) || 5)))}
                disabled={running}
              />
            </div>
          </div>

          {running ? (
            <button type="button" className="primary agent-stop" onClick={() => abortRef.current?.abort()}>
              Stop
            </button>
          ) : (
            <button className="primary" disabled={!input.trim() || !status?.llm_configured}>
              Rewrite
            </button>
          )}
        </form>

        <p className="muted small">
          {statusError ? (
            <span className="error">
              Agent API offline. Start it in the <code>agent</code> folder with <code>uv run nova-rewriter-api</code>.
            </span>
          ) : status ? (
            status.llm_configured ? (
              <>Model: {status.model}</>
            ) : (
              <span className="error">GROQ_API_KEY is missing in agent/.env.</span>
            )
          ) : (
            "Connecting to the agent…"
          )}
        </p>
      </aside>

      <section className="stage" aria-live="polite">
        {phase === "idle" && !attempts.length && <p className="empty">The rewritten ingredient list and its scores appear here.</p>}

        {running && (
          <p className="agent-progress">
            <span className="agent-spinner" aria-hidden="true" />
            {attempts.length ? `Round ${roundsDone + 1} of ${maxRounds}…` : "Scoring the original list…"}
            {attempts[0] && (
              <span className="muted">
                {" "}
                Original: NOVA {attempts[0].group}, {pct(attempts[0].score)} probability of NOVA 4.
              </span>
            )}
          </p>
        )}

        {error && (
          <div className="alert" role="alert">
            {error}
          </div>
        )}

        {result && (
          <div className="results">
            <p className={`agent-verdict ${result.success ? "ok" : "warn"}`}>{verdict(result, rounds.length, runThreshold)}</p>

            <section className="agent-section">
              <h3>Score change</h3>
              <div className="agent-compare">
                {[
                  ["Original", result.original],
                  ["Rewritten", result.best],
                ].map(([label, a], i) => (
                  <div key={label} className="agent-compare-col">
                    <span className="muted small">{label}</span>
                    <NovaBadge group={a.group} large />
                    <span className="small">Probability of NOVA 4</span>
                    <ScoreBar score={a.score} threshold={runThreshold} />
                    {i === 1 && <span className="agent-delta">{points(result.original.score, result.best.score)}</span>}
                  </div>
                ))}
              </div>
              {result.best.changes?.length > 0 && (
                <div className="agent-changed">
                  <h3>What the agent changed</h3>
                  <Changes changes={result.best.changes} />
                </div>
              )}
            </section>

            <section className="agent-section">
              <div className="agent-section-head">
                <h3>Rewritten ingredients</h3>
                <button type="button" className="link-button" onClick={copy}>
                  {copied ? "Copied" : "Copy list"}
                </button>
              </div>
              <p className="statement agent-statement">{result.best.ingredients}</p>
              <AmountsTable text={result.best.ingredients} original={result.original.ingredients} />
            </section>

            <ScoreMeaning result={result} threshold={runThreshold} />
          </div>
        )}

        {timeline.length > 0 && (
          <details className="agent-rounds" open={running}>
            <summary>All rounds ({timeline.length})</summary>
            <ol>
              {timeline.map((item) =>
                item.kind === "attempt" ? (
                  <li key={`a${item.round}`} className={result?.best.round === item.round ? "is-best" : undefined}>
                    <div className="agent-round-head">
                      <strong>Round {item.round}</strong>
                      <NovaBadge group={item.a.group} />
                      <ScoreBar score={item.a.score} threshold={runThreshold} />
                    </div>
                    <p>{item.a.ingredients}</p>
                    <Changes changes={item.a.changes} />
                  </li>
                ) : (
                  <li key={`e${item.round}`} className="is-failed">
                    <div className="agent-round-head">
                      <strong>Round {item.round}</strong>
                      <span className="muted">LLM error, skipped</span>
                    </div>
                    <p className="muted small">{item.e.message}</p>
                  </li>
                )
              )}
            </ol>
          </details>
        )}
      </section>
    </div>
  );
}
