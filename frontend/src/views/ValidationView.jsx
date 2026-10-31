import { useEffect, useState } from "react";
import { api } from "../api.js";

function share(x) {
  return x == null ? "n/a" : `${Math.round(100 * x)} %`;
}

export default function ValidationView() {
  const [v, setV] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.validation().then(setV).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="alert" role="alert">{error}</div>;
  if (!v) return <p className="muted page-pad">Running cross-validation and the backtest…</p>;

  return (
    <div className="validation">
      <section>
        <h2>Does the model beat a base-type baseline?</h2>
        <p className="lede">
          For each additive function, five-fold cross-validated AUC of the gradient-boosting model, against a baseline that only knows whether the drink is oat, soy,
          almond, rice or coconut. A model that loses is reported as losing.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Function</th>
                <th scope="col" className="num">Products</th>
                <th scope="col" className="num">Using it</th>
                <th scope="col" className="num">AUC model</th>
                <th scope="col" className="num">AUC baseline</th>
                <th scope="col">Result</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(v.models).map(([f, m]) => (
                <tr key={f}>
                  <th scope="row">{m.label}</th>
                  <td className="num">{m.n}</td>
                  <td className="num">{m.positives ?? "n/a"}</td>
                  <td className="num">{m.auc_model ?? "n/a"}</td>
                  <td className="num">{m.auc_baseline ?? "n/a"}</td>
                  <td>{m.status === "skipped" ? `Not trained: ${m.reason}` : m.beats_baseline ? "Beats baseline" : "Loses to baseline"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>Backtest: hide a product, see if the light agrees with it</h2>
        <p className="lede">
          We hide a product that already works without a function and ask whether removing that function has precedent. Green or yellow means the tool supports what the
          product actually does. As a contrast, we run the same test on products that use the function: if they also get green as often, the light does not
          discriminate.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Function</th>
                <th scope="col" className="num">Products without it, supported</th>
                <th scope="col" className="num">Green, without it</th>
                <th scope="col" className="num">Green, with it</th>
                <th scope="col">Discriminates</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(v.backtest).map(([f, b]) => (
                <tr key={f}>
                  <th scope="row">{b.label}</th>
                  <td className="num">
                    {share(b.supported_share)} <span className="muted">(n={b.clean.n})</span>
                  </td>
                  <td className="num">{share(b.clean.green_share)}</td>
                  <td className="num">
                    {share(b.contrast.green_share)} <span className="muted">(n={b.contrast.n})</span>
                  </td>
                  <td>{b.discriminates == null ? "n/a" : b.discriminates ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2>Expert review</h2>
        <p className="lede">Twenty suggestions reviewed by a formulation expert. Result to be added after the review.</p>
      </section>
    </div>
  );
}
