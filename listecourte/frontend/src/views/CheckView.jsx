import { useState } from "react";
import { api } from "../api.js";
import Light from "../components/Light.jsx";
import Tag from "../components/Tag.jsx";

const BASES = [
  ["oat", "Oat"],
  ["soy", "Soy"],
  ["almond", "Almond"],
  ["rice", "Rice"],
  ["coconut", "Coconut"],
];
const DEFAULT_ROWS = [
  { id: "oat_hydrolysed", pct: "10" },
  { id: "sunflower_oil", pct: "1.2" },
  { id: "sea_salt", pct: "0.1" },
  { id: "calcium_carbonate", pct: "0.3" },
];
const OVERALL_WORDS = {
  green: "No rule fails and comparable products support every choice in this formula.",
  yellow: "Nothing fails outright, but some points need checking before a pilot trial.",
  red: "A hard rule fails, or the formula drops a function almost every comparable product keeps.",
};
const NUTRIENT_ROWS = [
  ["protein", "Protein", "g"],
  ["fat", "Fat", "g"],
  ["sugars", "Sugars", "g"],
  ["carbs", "Carbohydrates", "g"],
  ["salt", "Salt", "g"],
  ["calcium_mg", "Calcium", "mg"],
  ["kcal", "Energy", "kcal"],
];

function FormulaForm({ meta, onSubmit, busy }) {
  const [base, setBase] = useState("oat");
  const [rows, setRows] = useState(DEFAULT_ROWS);
  const [additives, setAdditives] = useState(["E418"]);
  const [flags, setFlags] = useState({ barista: false, organic: true, vitamins: false });

  const total = rows.reduce((s, r) => s + (Number(r.pct) || 0), 0);
  const setRow = (i, key, value) => setRows(rows.map((r, j) => (j === i ? { ...r, [key]: value } : r)));
  const toggleAdditive = (code) => setAdditives(additives.includes(code) ? additives.filter((a) => a !== code) : [...additives, code]);
  const byFunction = Object.entries(meta.functions).map(([f, label]) => [label, meta.additives.filter((a) => a.function === f)]);

  function submit(e) {
    e.preventDefault();
    onSubmit({
      base,
      ingredients: rows.filter((r) => r.id && r.pct !== "").map((r) => ({ id: r.id, pct: Number(r.pct) })),
      additives,
      ...flags,
    });
  }

  return (
    <form onSubmit={submit}>
      <div className="field">
        <label htmlFor="c-base">Plant base</label>
        <select id="c-base" value={base} onChange={(e) => setBase(e.target.value)}>
          {BASES.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </div>

      <fieldset>
        <legend>Ingredients, % of the formula</legend>
        {rows.map((r, i) => (
          <div className="ingredient-row" key={i}>
            <select aria-label={`Ingredient ${i + 1}`} value={r.id} onChange={(e) => setRow(i, "id", e.target.value)}>
              {meta.ingredients.map((ing) => (
                <option key={ing.id} value={ing.id}>
                  {ing.label}
                </option>
              ))}
            </select>
            <input aria-label={`Percentage for ingredient ${i + 1}`} type="number" step="0.01" min="0" max="100" inputMode="decimal" value={r.pct} onChange={(e) => setRow(i, "pct", e.target.value)} />
            <button type="button" className="icon-button" aria-label={`Remove ingredient ${i + 1}`} onClick={() => setRows(rows.filter((_, j) => j !== i))}>
              ×
            </button>
          </div>
        ))}
        <div className="row-actions">
          <button type="button" className="link-button" onClick={() => setRows([...rows, { id: meta.ingredients[0].id, pct: "" }])}>
            Add ingredient
          </button>
          <span className={total > 100 ? "error small" : "muted small"}>
            {total.toFixed(2)} % entered, water makes up the rest
          </span>
        </div>
      </fieldset>

      <fieldset>
        <legend>Additives kept</legend>
        {byFunction.map(([label, list]) => (
          <div key={label} className="additive-group">
            <p className="group-label">{label}</p>
            {list.map((a) => (
              <label key={a.code} className="check-line">
                <input type="checkbox" checked={additives.includes(a.code)} onChange={() => toggleAdditive(a.code)} /> {a.code} {a.name}
              </label>
            ))}
          </div>
        ))}
      </fieldset>

      <div className="checks">
        {[
          ["barista", "Barista version"],
          ["organic", "Organic"],
          ["vitamins", "Added vitamins"],
        ].map(([k, l]) => (
          <label key={k}>
            <input type="checkbox" checked={flags[k]} onChange={(e) => setFlags({ ...flags, [k]: e.target.checked })} /> {l}
          </label>
        ))}
      </div>
      <button className="primary" disabled={busy || total > 100}>
        {busy ? "Checking…" : "Run health check"}
      </button>
    </form>
  );
}

function CheckResults({ r }) {
  return (
    <div className="results">
      <header className="verdict">
        <Light light={r.overall} large />
        <p>{OVERALL_WORDS[r.overall]}</p>
      </header>

      <div className="two-col">
        <section>
          <h3>Estimated nutrition, per 100 ml</h3>
          <table className="compact">
            <tbody>
              {NUTRIENT_ROWS.map(([k, label, unit]) => (
                <tr key={k}>
                  <th scope="row">{label}</th>
                  <td className="num">
                    {r.nutrition[k].value} {unit}
                  </td>
                  <td>
                    <Tag tag={r.nutrition[k].tag} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section>
          <h3>Nutrition claims</h3>
          <ul className="plain">
            {r.claims.map((c) => (
              <li key={c.id} className={c.eligible ? "" : "muted"}>
                {c.eligible ? "Supported" : "Not supported"}: {c.label} <span className="small">({c.threshold})</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section>
        <h3>Hard rules for the additives kept</h3>
        {r.rule_checks.length === 0 ? (
          <p className="muted">No additive kept, so no additive rule applies.</p>
        ) : (
          <ul className="rule-list">
            {r.rule_checks.map((c) => (
              <li key={c.code}>
                <Light light={c.light} /> {c.item}: {c.status === "unknown" ? "to verify" : c.status === "pass" ? "authorised" : "not authorised"}
                {!c.verified && <span className="muted"> (draft rule table)</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3>Each function against {r.peers.n} comparable products</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Function</th>
                <th scope="col">In formula</th>
                <th scope="col" className="num">Peers without it</th>
                <th scope="col" className="num">Model says needed</th>
                <th scope="col">Light</th>
              </tr>
            </thead>
            <tbody>
              {r.functions.map((f) => (
                <tr key={f.function}>
                  <th scope="row">{f.label}</th>
                  <td>{f.present ? "Yes" : "No"}</td>
                  <td className="num">
                    {f.n_without} of {f.n_peers} <Tag tag={f.share_without.tag} />
                  </td>
                  <td className="num">
                    {f.model_probability ? (
                      <>
                        {Math.round(100 * f.model_probability.value)} % <Tag tag="model" />
                      </>
                    ) : (
                      "n/a"
                    )}
                  </td>
                  <td>
                    <Light light={f.light} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {r.functions
          .filter((f) => !f.present && f.light !== "green")
          .map((f) => (
            <div key={f.function} className="note-block">
              <p>
                <strong>{f.label}:</strong> {f.note}
              </p>
              <ul className="checklist">
                {f.lab_checklist.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ))}
      </section>

      <section>
        <h3>Position in the market</h3>
        {r.outliers.length === 0 && !r.edge.is_edge ? (
          <p>The formula sits inside the range of comparable products.</p>
        ) : (
          <ul className="plain">
            {r.edge.is_edge && <li>The formula is further from its closest comparable product than 90 % of products are from theirs.</li>}
            {r.outliers.map((o) => (
              <li key={o.item}>
                {o.item}: {o.value}, at the {o.percentile}th percentile of peers (median {o.peer_median}).
              </li>
            ))}
          </ul>
        )}
      </section>

      <ul className="notes">
        {r.notes.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
    </div>
  );
}

export default function CheckView({ meta }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run(payload) {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.check(payload));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workspace">
      <aside className="panel">
        <h2 className="panel-title">Proposed formula</h2>
        <FormulaForm meta={meta} onSubmit={run} busy={busy} />
      </aside>
      <section className="stage" aria-live="polite">
        {error && <div className="alert" role="alert">{error}</div>}
        {result ? (
          <CheckResults r={result} />
        ) : (
          <div className="empty">
            <p>Enter the formula you plan to trial, with proportions. The check flags rule problems, lost claims, and functions that almost every comparable product keeps.</p>
          </div>
        )}
      </section>
    </div>
  );
}
