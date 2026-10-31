// Client for the NOVA rewriter agent (agent/src/nova_rewriter/server.py), proxied at /agent-api.

async function errorMessage(res) {
  const body = await res.json().catch(() => ({}));
  const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join("; ") : body.detail;
  return detail || `Request failed with status ${res.status}`;
}

export async function agentHealth() {
  const res = await fetch("/agent-api/health");
  if (!res.ok) throw new Error(await errorMessage(res));
  return res.json();
}

// Runs the rewrite loop and calls onEvent for every NDJSON event as it arrives.
export async function agentRewrite({ ingredients, threshold, maxRounds }, onEvent, signal) {
  const res = await fetch("/agent-api/rewrite", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ingredients, threshold, max_rounds: maxRounds }),
    signal,
  });
  if (!res.ok) throw new Error(await errorMessage(res));

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line));
    if (done) break;
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer));
}
