import { useState } from "react";
import Light from "./Light.jsx";
import Tag from "./Tag.jsx";

const FILTER_WORDS = { base: "same base", barista: "same barista status", organic: "same organic status" };
const RULE_WORDS = { pass: "Authorised", fail: "Not authorised", unknown: "To verify" };

function pct(x) {
  return `${Math.round(100 * x)} %`;
}

function Pattern({ p }) {
  if (p.kind === "median") {
    return (
      <li>
        Median {p.item}: {p.without}
        {p.unit} without the function, {p.with}
        {p.unit} with it.
      </li>
    );
  }
  return (
    <li>
      {p.item[0].toUpperCase() + p.item.slice(1)}: {pct(p.without)} of products without the function, {pct(p.with)} with it.
    </li>
  );
}

export default function OptionRow({ option, rank, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const pr = option.precedent;
  const model = option.model;
  const panelId = `evidence-${option.function}`;

  return (
    <li className={`option option-${option.light}`}>
      <div className="option-head">
        <span className="option-rank" aria-label={`Rank ${rank}`}>{rank}</span>
        <div className="option-title">
          <h3>Remove the {option.label.toLowerCase()}</h3>
          <p className="option-additives">{option.additives.map((a) => `${a.code} ${a.name}`).join(", ")}</p>
        </div>
        <Light light={option.light} />
        <dl className="option-figures">
          <div>
            <dt>Peers without it</dt>
            <dd>
              {pr.n_without.value} of {pr.n_peers.value} <Tag tag={pr.share_without.tag} />
            </dd>
          </div>
          {model && (
            <div>
              <dt>Model says needed</dt>
              <dd>
                {pct(model.probability.value)} <Tag tag="model" />
              </dd>
            </div>
          )}
        </dl>
        <button className="link-button" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(!open)}>
          {open ? "Hide evidence" : "Show evidence"}
        </button>
      </div>

      <p className="option-explanation">
        {option.explanation.text}
        {option.explanation.source === "llm" && <span className="muted"> (written by the LLM from the evidence below)</span>}
      </p>
      <ul className="option-reasons">
        {option.reasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>

      {open && (
        <div className="evidence" id={panelId}>
          <section>
            <h4>Hard rules</h4>
            <ul className="plain">
              {option.additives.map((a) => (
                <li key={a.code}>
                  {a.code} {a.name}: {RULE_WORDS[a.status]}
                  {!a.verified && <span className="muted"> (draft rule table, not yet verified)</span>}
                </li>
              ))}
            </ul>
            {option.claims_lost.length > 0 ? (
              <p>
                Removing it voids {option.claims_lost.map((c) => `“${c.label}” (${c.threshold})`).join(" and ")}. <Tag tag="estimated" />
              </p>
            ) : (
              <p className="muted">No current nutrition claim depends on it.</p>
            )}
          </section>

          <section>
            <h4>Market precedent</h4>
            <p>
              Compared with {pr.n_peers.value} products with the {pr.filters.map((f) => FILTER_WORDS[f]).join(", ")}.{" "}
              {pct(pr.share_without.value)} of them work without this function.
              {option.edge.is_edge && " This formula is far from all of them, so treat the comparison with care."}
            </p>
            {model && (
              <p>
                Model estimate {pct(model.probability.value)}
                {model.drivers.length > 0 && `, mostly from ${model.drivers.map((d) => `${d.feature} (${d.effect})`).join(", ")}`}.
                {model.beats_baseline === false && " This model does not beat its base-type baseline, so weigh it lightly."}
              </p>
            )}
            {option.substitutions.length > 0 && (
              <>
                <p>What products without it do differently:</p>
                <ul className="plain">
                  {option.substitutions.map((p, i) => (
                    <Pattern key={i} p={p} />
                  ))}
                </ul>
              </>
            )}
            {option.twins.length > 0 && (
              <div className="table-wrap">
                <table>
                  <caption>Closest products without it</caption>
                  <thead>
                    <tr>
                      <th scope="col">Barcode</th>
                      <th scope="col">Product</th>
                      <th scope="col">Brand</th>
                      <th scope="col" className="num">Base %</th>
                      <th scope="col" className="num">Protein</th>
                      <th scope="col" className="num">Fat</th>
                      <th scope="col" className="num">Sugars</th>
                      <th scope="col">Other additives</th>
                    </tr>
                  </thead>
                  <tbody>
                    {option.twins.map((t) => (
                      <tr key={t.code}>
                        <td className="code">{t.code}</td>
                        <td>{t.name}</td>
                        <td>
                          {t.brands}
                          {t.retailer_brand && <span className="muted"> (retailer)</span>}
                        </td>
                        <td className="num">
                          {t.base_pct}
                          {t.base_pct_estimated && <span title="Not declared, estimated from similar products">*</span>}
                        </td>
                        <td className="num">{t.protein}</td>
                        <td className="num">{t.fat}</td>
                        <td className="num">{t.sugars}</td>
                        <td>{t.additives.join(", ") || "None"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section>
            <h4>Physical feasibility (not predicted)</h4>
            <p className="muted">The data has no texture or stability measurements. Test these before deciding:</p>
            <ul className="checklist">
              {option.lab_checklist.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </li>
  );
}
