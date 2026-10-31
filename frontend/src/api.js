// Thin wrapper around the FastAPI endpoints. Errors carry the API's message.
async function request(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d) => d.msg).join("; ")
      : body.detail;
    throw new Error(detail || `Request failed with status ${res.status}`);
  }
  return body;
}

export const api = {
  meta: () => request("/meta"),
  search: (q) => request(`/products/search?q=${encodeURIComponent(q)}`),
  recommend: (payload) => request("/recommend", { method: "POST", body: JSON.stringify(payload) }),
  check: (payload) => request("/check", { method: "POST", body: JSON.stringify(payload) }),
  validation: () => request("/validation"),
};
