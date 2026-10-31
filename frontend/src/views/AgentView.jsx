import { useEffect, useRef, useState } from "react";
import { agentHealth, agentRewrite } from "../agentApi.js";

const EXAMPLE = [
  { name: "Eau", grams: "860" },
  { name: "Avoine", grams: "120" },
  { name: "Huile de tournesol", grams: "12" },
  { name: "Phosphate dipotassique", grams: "2" },
  { name: "Carbonate de calcium", grams: "1.2" },
  { name: "Sel", grams: "1" },
  { name: "Stabilisant : gomme gellane", grams: "0.3" },
  { name: "Vitamines (D2, B12)", grams: "0.02" },
];
const EMPTY_ROWS = [
  { name: "", grams: "" },
  { name: "", grams: "" },
  { name: "", grams: "" },
];
const GRADES = ["A", "B", "C", "D", "E"];
const CATEGORIES = [
  ["beverage", "Drink"],
  ["food", "Food"],
];
const GRADE_BANDS = {
  beverage: [
    ["A", "Water only"],
    ["B", "Score 2 or less"],
    ["C", "3 to 6"],
    ["D", "7 to 9"],
    ["E", "10 or more"],
  ],
  food: [
    ["A", "Score 0 or less"],
    ["B", "1 to 2"],
    ["C", "3 to 10"],
    ["D", "11 to 18"],
    ["E", "19 or more"],
  ],
};

const fmt = (v, digits = 2) => Number(v).toLocaleString("en", { maximumFractionDigits: digits });
const fmtG = (g) => `${fmt(g)} g`;
const norm = (s) => s.toLowerCase().replace(/[.\s]+$/, "").replace(/\s+/g, " ").trim();
const totalOf = (items) => items.reduce((s, i) => s + i.grams, 0);

// "Avoine 120 g, Sel 0,5 g" -> rows. Commas inside parentheses or before a digit don't split.
function parseList(text) {
  return text
    .split(/,(?!\d)(?![^()]*\))/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((part) => {
      const m = part.match(/\s*(\d+(?:[.,]\d+)?)\s*g\.?\s*$/i);
      return m ? { name: part.slice(0, m.index).trim(), grams: m[1].replace(",", ".") } : { name: part, grams: "" };
    });
}

function NutriBadge({ grade }) {
  return <span className={`ns-badge ns-${grade}`}>Nutri-Score {grade}</span>;
}

// The five-letter scale with the current grade raised, as on a pack.
function NutriScale({ grade }) {
  return (
    <span className="ns-scale" role="img" aria-label={`Nutri-Score ${grade}`}>
      {GRADES.map((g) => (
        <span key={g} className={`ns-letter ns-${g}${g === grade ? " is-current" : ""}`} aria-hidden="true">
          {g}
        </span>
      ))}
    </span>
  );
}

function points(before, after) {
  const d = after - before;
  return `${d > 0 ? "+" : d < 0 ? "−" : "±"}${Math.abs(d)} point${Math.abs(d) === 1 ? "" : "s"}`;
}

// The LLM's composition for one ingredient, per 100 g of that ingredient.
function Composition({ c }) {
  if (!c) return null;
  return (
    <span className="agent-composition">
      {fmt(c.kcal, 0)} kcal · sugars {fmt(c.sugars, 1)} · sat. fat {fmt(c.sat_fat, 1)} · salt {fmt(c.salt, 2)} · fibre{" "}
      {fmt(c.fibre, 1)} · protein {fmt(c.protein, 1)}
    </span>
  );
}

function RecipeTable({ items, original }) {
  const before = new Map(original.map((i) => [norm(i.name), i.grams]));
  const after = new Set(items.map((i) => norm(i.name)));
  const rows = [
    ...items.map((i) => {
      const was = before.get(norm(i.name));
      const status = was === undefined ? "new" : Math.abs(was - i.grams) > 1e-9 ? "amount" : "kept";
      return { ...i, was, status };
    }),
    ...original
      .filter((i) => !after.has(norm(i.name)))
      .map((i) => ({ name: i.name, grams: null, was: i.grams, status: "removed", per_100g: i.per_100g })),
  ];
  const LABEL = { new: "New", amount: "Amount changed", kept: "Kept", removed: "Removed" };
  return (
    <div className="table-wrap">
      <table className="agent-table">
        <thead>
          <tr>
            <th scope="col">Ingredient</th>
            <th scope="col" className="num">Amount</th>
            <th scope="col">Compared with the original</th>
            <th scope="col">Per 100 g of ingredient (g)</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={`row-${r.status}`}>
              <td>{r.name}</td>
              <td className="num">{r.grams == null ? "–" : fmtG(r.grams)}</td>
              <td>
                <span className={`agent-status status-${r.status}`}>{LABEL[r.status]}</span>
                {(r.status === "amount" || r.status === "removed") && <span className="muted small"> was {fmtG(r.was)}</span>}
              </td>
              <td className="small">
                <Composition c={r.per_100g} />
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Total</th>
            <td className="num">{fmtG(totalOf(items))}</td>
            <td className="muted small">was {fmtG(totalOf(original))}</td>
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function NutritionTable({ original, best, category }) {
  const rows = [
    ["energy", "Energy", (n) => `${fmt(n.kcal, 0)} kcal · ${fmt(n.kj, 0)} kJ`, "neg"],
    ["sugars", "Sugars", (n) => fmtG(n.sugars), "neg"],
    ["sat_fat", "Saturated fat", (n) => fmtG(n.sat_fat), "neg"],
    ["salt", "Salt", (n) => fmtG(n.salt), "neg"],
    ...(category === "beverage" ? [["sweeteners", "Non-nutritive sweeteners", (n) => (n.sweetener ? "Yes" : "No"), "neg"]] : []),
    ["protein", "Protein", (n) => fmtG(n.protein), "pos"],
    ["fibre", "Fibre", (n) => fmtG(n.fibre), "pos"],
    ["fvl", "Fruit, vegetables, legumes", (n) => `${fmt(n.fvl_pct, 0)} %`, "pos"],
  ];
  const pts = (a, key, sign) => {
    const p = a.breakdown.points[key];
    if (key === "protein" && !a.breakdown.protein_counted) return <span className="muted">not counted</span>;
    return p === 0 ? <span className="muted">0</span> : <span className={sign === "neg" ? "pts-neg" : "pts-pos"}>{sign === "neg" ? `+${p}` : `−${p}`}</span>;
  };
  const same = original === best;
  return (
    <div className="table-wrap">
      <table className="agent-table">
        <thead>
          <tr>
            <th scope="col">Per 100 g</th>
            <th scope="col" className="num">{same ? "Value" : "Original"}</th>
            <th scope="col" className="num">Points</th>
            {!same && (
              <>
                <th scope="col" className="num">Rewritten</th>
                <th scope="col" className="num">Points</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map(([key, label, value, sign]) => (
            <tr key={key}>
              <th scope="row">{label}</th>
              <td className="num">{value(original.nutrition)}</td>
              <td className="num">{pts(original, key, sign)}</td>
              {!same && (
                <>
                  <td className="num">{value(best.nutrition)}</td>
                  <td className="num">{pts(best, key, sign)}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Score</th>
            <td />
            <td className="num">{original.score}</td>
            {!same && (
              <>
                <td />
                <td className="num">{best.score}</td>
              </>
            )}
          </tr>
        </tfoot>
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

function ScoreMeaning({ result }) {
  const { original, best, category } = result;
  return (
    <section className="agent-section">
      <h3>What the score means</h3>
      <dl className="agent-meaning">
        <div>
          <dt>Nutri-Score</dt>
          <dd>
            Points for energy, sugars, saturated fat and salt{category === "beverage" && " (and sweeteners)"}, minus points for
            protein, fibre and the share of fruit, vegetables and legumes, all per 100 g. A lower score is better. Grades for{" "}
            {category === "beverage" ? "drinks" : "foods"} (2023 algorithm):
            <ul className="agent-groups">
              {GRADE_BANDS[category].map(([g, band]) => (
                <li key={g} className={g === original.grade || g === best.grade ? "is-current" : undefined}>
                  <NutriBadge grade={g} />
                  <span>
                    {band}.{g === original.grade && <span className="muted"> Original.</span>}
                    {g === best.grade && best !== original && <span className="muted"> Rewritten.</span>}
                  </span>
                </li>
              ))}
            </ul>
          </dd>
        </div>
        <div>
          <dt>Target</dt>
          <dd>The agent stops as soon as a recipe reaches Nutri-Score B or better.</dd>
        </div>
        <div>
          <dt>Limits</dt>
          <dd>
            The LLM gives each ingredient's composition per 100 g, and the Nutri-Score is calculated in code from those
            values and the grams. An ingredient keeps its first values for the whole run. Drinks are assumed to weigh 1 g
            per ml. The values are estimates, not a lab analysis or an official Nutri-Score, and the agent does not check
            stability, taste or regulation.
          </dd>
        </div>
      </dl>
    </section>
  );
}

function verdict(result, rounds) {
  const { original, best, success } = result;
  if (success && best.round === 0) return `Already Nutri-Score ${original.grade}. No rewrite needed.`;
  if (success) return `Target reached in round ${best.round}: Nutri-Score ${original.grade} → ${best.grade}.`;
  if (best.round === 0) return `No round improved on the original after ${rounds} round${rounds === 1 ? "" : "s"}.`;
  return `Nutri-Score B not reached after ${rounds} round${rounds === 1 ? "" : "s"}. Showing the lowest-scoring recipe.`;
}

function RecipeInput({ rows, setRows, disabled }) {
  const setRow = (i, key, value) => setRows(rows.map((r, j) => (j === i ? { ...r, [key]: value } : r)));
  const total = rows.reduce((s, r) => s + (Number(r.grams) || 0), 0);

  // Pasting a whole list ("Avoine 120 g, Sel 1 g") into a name box fills one row per ingredient.
  function onPaste(i, e) {
    const text = e.clipboardData.getData("text");
    if (!/,/.test(text)) return;
    const parsed = parseList(text);
    if (parsed.length < 2) return;
    e.preventDefault();
    const kept = rows.filter((r, j) => j !== i && (r.name.trim() || r.grams));
    setRows([...kept.slice(0, i), ...parsed, ...kept.slice(i)]);
  }

  return (
    <fieldset>
      <legend>Recipe, in grams</legend>
      <div className="ingredient-row agent-row-head" aria-hidden="true">
        <span>Ingredient</span>
        <span>g</span>
        <span />
      </div>
      {rows.map((r, i) => (
        <div className="ingredient-row" key={i}>
          <input
            type="text"
            aria-label={`Ingredient ${i + 1}`}
            placeholder={i === 0 ? "e.g. Avoine" : ""}
            value={r.name}
            onChange={(e) => setRow(i, "name", e.target.value)}
            onPaste={(e) => onPaste(i, e)}
            disabled={disabled}
          />
          <input
            type="number"
            aria-label={`Grams of ingredient ${i + 1}`}
            step="any"
            min="0"
            inputMode="decimal"
            value={r.grams}
            onChange={(e) => setRow(i, "grams", e.target.value)}
            disabled={disabled}
          />
          <button
            type="button"
            className="icon-button"
            aria-label={`Remove ingredient ${i + 1}`}
            onClick={() => setRows(rows.filter((_, j) => j !== i))}
            disabled={disabled || rows.length === 1}
          >
            ×
          </button>
        </div>
      ))}
      <div className="row-actions">
        <button type="button" className="link-button" onClick={() => setRows([...rows, { name: "", grams: "" }])} disabled={disabled}>
          Add ingredient
        </button>
        <span className="muted small">Total {fmtG(total)}</span>
      </div>
      <p className="muted small">Tip: paste a whole list such as "Avoine 120 g, Sel 1 g" into a name box.</p>
    </fieldset>
  );
}

export default function AgentView() {
  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState(null);
  const [rows, setRows] = useState(EMPTY_ROWS);
  const [category, setCategory] = useState("beverage");
  const [maxRounds, setMaxRounds] = useState(5);

  const [phase, setPhase] = useState("idle"); // idle | running | done | error
  const [attempts, setAttempts] = useState([]);
  const [roundErrors, setRoundErrors] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const abortRef = useRef(null);

  useEffect(() => {
    agentHealth().then(setStatus).catch((e) => setStatusError(e.message));
  }, []);

  const filled = rows.filter((r) => r.name.trim());
  const missingGrams = filled.some((r) => !(Number(r.grams) > 0));
  const canRun = filled.length > 0 && !missingGrams && status?.llm_configured;

  async function run() {
    if (!canRun || phase === "running") return;
    const items = filled.map((r) => ({ name: r.name.trim(), grams: Number(r.grams) }));
    const controller = new AbortController();
    abortRef.current = controller;
    setPhase("running");
    setAttempts([]);
    setRoundErrors([]);
    setResult(null);
    setError(null);

    let finished = false;
    try {
      await agentRewrite(
        { items, category, maxRounds },
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
        <h2 className="panel-title">Nutri-Score rewriter agent</h2>
        <p className="muted small">
          Enter the recipe in grams. An LLM changes the recipe, the Nutri-Score is calculated for each version, and the loop
          repeats until the recipe reaches Nutri-Score B or better.
        </p>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            run();
          }}
        >
          <div className="field">
            <label htmlFor="a-category">Product type</label>
            <select id="a-category" value={category} onChange={(e) => setCategory(e.target.value)} disabled={running}>
              {CATEGORIES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </div>

          <RecipeInput rows={rows} setRows={setRows} disabled={running} />
          <button
            type="button"
            className="link-button agent-example"
            onClick={() => {
              setRows(EXAMPLE);
              setCategory("beverage");
            }}
            disabled={running}
          >
            Use an example (oat drink)
          </button>

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

          {missingGrams && <p className="error small">Every ingredient needs an amount in grams.</p>}

          {running ? (
            <button type="button" className="primary agent-stop" onClick={() => abortRef.current?.abort()}>
              Stop
            </button>
          ) : (
            <button className="primary" disabled={!canRun}>
              Rewrite
            </button>
          )}
        </form>

        <p className="muted small">
          {statusError ? (
            <span className="error">
              Agent API offline. Start it in the <code>agent</code> folder with <code>uv run nutri-rewriter-api</code>.
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
        {phase === "idle" && !attempts.length && <p className="empty">The rewritten recipe and its Nutri-Score appear here.</p>}

        {running && (
          <p className="agent-progress">
            <span className="agent-spinner" aria-hidden="true" />
            {attempts.length ? `Round ${roundsDone + 1} of ${maxRounds}…` : "Estimating ingredient compositions and scoring the original recipe…"}
            {attempts[0] && (
              <span className="muted">
                {" "}
                Original: Nutri-Score {attempts[0].grade} (score {attempts[0].score}).
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
            <p className={`agent-verdict ${result.success ? "ok" : "warn"}`}>{verdict(result, rounds.length)}</p>

            <section className="agent-section">
              <h3>Nutri-Score change</h3>
              <div className="agent-compare">
                {[
                  ["Original", result.original],
                  ["Rewritten", result.best],
                ].map(([label, a], i) => (
                  <div key={label} className="agent-compare-col">
                    <span className="muted small">{label}</span>
                    <NutriScale grade={a.grade} />
                    <span className="small">
                      Score {a.score} ({a.breakdown.negative} negative − {a.breakdown.positive} positive points)
                    </span>
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
                <h3>Rewritten recipe</h3>
                <button type="button" className="link-button" onClick={copy}>
                  {copied ? "Copied" : "Copy list"}
                </button>
              </div>
              <p className="statement agent-statement">{result.best.ingredients}</p>
              <RecipeTable items={result.best.items} original={result.original.items} />
            </section>

            <section className="agent-section">
              <h3>Nutrition per 100 g and Nutri-Score points</h3>
              <NutritionTable original={result.original} best={result.best} category={result.category} />
            </section>

            <ScoreMeaning result={result} />
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
                      <NutriBadge grade={item.a.grade} />
                      <span className="muted small">Score {item.a.score}</span>
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
