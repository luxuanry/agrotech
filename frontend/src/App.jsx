import { useEffect, useState } from "react";
import { api } from "./api.js";
import CheckView from "./views/CheckView.jsx";
import RecommendView from "./views/RecommendView.jsx";
import ValidationView from "./views/ValidationView.jsx";

const TABS = [
  ["recommend", "Recommend"],
  ["check", "Check a formula"],
  ["validation", "Validation"],
];

function initialTab() {
  const hash = window.location.hash.replace("#", "");
  return TABS.some(([id]) => id === hash) ? hash : "recommend";
}

export default function App() {
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState(initialTab);

  useEffect(() => {
    api.meta().then(setMeta).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    window.location.hash = tab;
  }, [tab]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>ListeCourte</h1>
          <p>Shorter ingredient lists for retailer-brand plant drinks, backed by the French market.</p>
        </div>
        <nav className="tabs" role="tablist" aria-label="Mode">
          {TABS.map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>
      </header>

      {meta?.data.is_sample && (
        <p className="sample-banner">
          Sample data: these {meta.data.n_products} products are invented for development. Build the real table with <code>scripts/build_from_off.py</code>.
        </p>
      )}

      <main>
        {error && (
          <div className="alert page-pad" role="alert">
            Cannot reach the API ({error}). Start it with <code>uvicorn app.main:app --port 8000</code> in the backend folder.
          </div>
        )}
        {meta && tab === "recommend" && <RecommendView meta={meta} />}
        {meta && tab === "check" && <CheckView meta={meta} />}
        {meta && tab === "validation" && <ValidationView />}
      </main>

      {meta && (
        <footer className="footer">
          Data: {meta.data.source}
          {!meta.data.is_sample && ", Open Food Facts contributors, Open Database License"}. Rule thresholds: EU Regulation 1924/2006 (claims). Additive rule table is a
          draft until verified.
        </footer>
      )}
    </div>
  );
}
