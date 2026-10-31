import { useEffect, useState } from "react";
import { api } from "../api.js";
import IngredientStatement from "../components/IngredientStatement.jsx";
import OptionRow from "../components/OptionRow.jsx";
import Tag from "../components/Tag.jsx";

const BASE_WORDS = { oat: "Oat", soy: "Soy", almond: "Almond", rice: "Rice", coconut: "Coconut", other: "Other base" };
const EMPTY_FORM = { name: "", ingredients_text: "", protein: "", fat: "", sugars: "", carbs: "", calcium_mg: "", barista: false, organic: false };

function ProductSearch({ onPick }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState([]);
  useEffect(() => {
    if (q.trim().length < 2) {
      setHits([]);
      return;
    }
    const id = setTimeout(() => api.search(q).then(setHits).catch(() => setHits([])), 250);
    return () => clearTimeout(id);
  }, [q]);

  return (
    <div className="field">
      <label htmlFor="search">Barcode, name or brand</label>
      <input id="search" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. barista, avoine, 3560070" autoComplete="off" />
      {hits.length > 0 && (
        <ul className="hits">
          {hits.map((h) => (
            <li key={h.code}>
              <button type="button" onClick={() => onPick(h.code)}>
                <span className="hit-name">{h.name}</span>
                <span className="hit-meta">
                  {h.brands}, {h.code}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {q.trim().length >= 2 && hits.length === 0 && <p className="muted small">No match in the current dataset.</p>}
    </div>
  );
}

function ManualForm({ onSubmit, busy }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const num = (v) => (v === "" ? null : Number(v));

  function submit(e) {
    e.preventDefault();
    onSubmit({
      name: form.name || null,
      ingredients_text: form.ingredients_text,
      protein: num(form.protein),
      fat: num(form.fat),
      sugars: num(form.sugars),
      carbs: num(form.carbs),
      calcium_mg: num(form.calcium_mg),
      barista: form.barista,
      organic: form.organic,
    });
  }

  return (
    <form onSubmit={submit} className="manual">
      <div className="field">
        <label htmlFor="m-name">Product name</label>
        <input id="m-name" value={form.name} onChange={set("name")} placeholder="Boisson avoine barista" />
      </div>
      <div className="field">
        <label htmlFor="m-ing">Ingredient list, as on the pack</label>
        <textarea id="m-ing" rows={4} value={form.ingredients_text} onChange={set("ingredients_text")} required placeholder="Eau, avoine 12%, huile de tournesol, phosphate dipotassique, sel, stabilisant : gomme gellane" />
      </div>
      <fieldset className="grid-fields">
        <legend>Per 100 ml</legend>
        {[
          ["protein", "Protein (g)"],
          ["fat", "Fat (g)"],
          ["sugars", "Sugars (g)"],
          ["carbs", "Carbohydrates (g)"],
          ["calcium_mg", "Calcium (mg)"],
        ].map(([k, label]) => (
          <div className="field" key={k}>
            <label htmlFor={`m-${k}`}>{label}</label>
            <input id={`m-${k}`} type="number" step="0.01" min="0" inputMode="decimal" value={form[k]} onChange={set(k)} required={["protein", "fat", "sugars"].includes(k)} />
          </div>
        ))}
      </fieldset>
      <div className="checks">
        <label>
          <input type="checkbox" checked={form.barista} onChange={set("barista")} /> Barista version
        </label>
        <label>
          <input type="checkbox" checked={form.organic} onChange={set("organic")} /> Organic
        </label>
      </div>
      <button className="primary" disabled={busy}>
        {busy ? "Analysing…" : "Get recommendations"}
      </button>
    </form>
  );
}

function Results({ result, catalog }) {
  const p = result.product;
  const marks = result.options.flatMap((o) => o.additives.map((a) => ({ code: a.code, light: o.light })));
  const claims = p.claims.filter((c) => c.eligible);

  return (
    <div className="results">
      <header className="product-head">
        <h2>{p.name || "Your formula"}</h2>
        <p className="muted">
          {[p.brands, p.code && p.code !== "INPUT" ? p.code : null, BASE_WORDS[p.base], p.barista ? "barista" : null, p.organic ? "organic" : null]
            .filter(Boolean)
            .join(", ")}
        </p>
      </header>

      <IngredientStatement text={p.ingredients_text} marks={marks} catalog={catalog} />

      <dl className="nutrition-strip">
        {[
          ["protein", "Protein", "g"],
          ["fat", "Fat", "g"],
          ["sugars", "Sugars", "g"],
          ["calcium_mg", "Calcium", "mg"],
          ["base_pct", "Base", "%"],
        ].map(([k, label, unit]) => (
          <div key={k}>
            <dt>{label}</dt>
            <dd>
              {p.nutrition[k].value ?? "?"} {unit} <Tag tag={p.nutrition[k].tag} />
            </dd>
          </div>
        ))}
      </dl>
      <p className="claims-line">
        {claims.length ? `Supports these claims today: ${claims.map((c) => c.label.toLowerCase()).join(", ")}.` : "Supports no nutrition claim today."}
      </p>

      {result.non_compliant.length > 0 && (
        <div className="alert" role="alert">
          {result.non_compliant.map((a) => a.code).join(", ")} fails a hard rule for this product (for example, not on the organic list). It has to change regardless of
          the ranking.
        </div>
      )}

      {result.options.length === 0 ? (
        <p className="empty">No stabiliser, emulsifier, acidity regulator or calcium salt was found in this ingredient list, so there is nothing to rank.</p>
      ) : (
        <>
          <h2 className="section-title">Options, most supported first</h2>
          <ol className="options">
            {result.options.map((o, i) => (
              <OptionRow key={o.function} option={o} rank={i + 1} defaultOpen={i === 0} />
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

export default function RecommendView({ meta }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [manual, setManual] = useState(false);

  async function run(payload) {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.recommend(payload));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workspace">
      <aside className="panel">
        <h2 className="panel-title">Current formula</h2>
        <div className="segmented" role="group" aria-label="Input method">
          <button type="button" aria-pressed={!manual} onClick={() => setManual(false)}>
            Find a product
          </button>
          <button type="button" aria-pressed={manual} onClick={() => setManual(true)}>
            Type a formula
          </button>
        </div>
        {manual ? <ManualForm onSubmit={run} busy={busy} /> : <ProductSearch onPick={(code) => run({ code })} />}
      </aside>
      <section className="stage" aria-live="polite">
        {error && <div className="alert" role="alert">{error}</div>}
        {busy && !result && <p className="muted">Analysing…</p>}
        {result ? (
          <Results result={result} catalog={meta.additives} />
        ) : (
          !busy && (
            <div className="empty">
              <p>Pick a product or type a formula. You will see which additives comparable French products already do without, the closest of those products, and the lab trials to run first.</p>
            </div>
          )
        )}
      </section>
    </div>
  );
}
