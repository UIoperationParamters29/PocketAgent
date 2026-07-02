/**
 * LLM provider helpers — model auto-fetch, key validation.
 */

export interface ModelInfo {
  id: string;
  label?: string;
  context_window?: number;
}

/**
 * Fetch the list of models from an OpenAI-compatible /models endpoint.
 * Returns a list of {id, label} pairs. If the endpoint doesn't support /models
 * or the key is invalid, throws with a helpful message.
 */
export async function fetchModels(base_url: string, api_key: string): Promise<ModelInfo[]> {
  if (!base_url) throw new Error('Base URL is required');
  if (!api_key) throw new Error('API key is required');

  // Normalize: strip trailing slash
  const url = base_url.replace(/\/$/, '') + '/models';

  const r = await fetch(url, {
    headers: { Authorization: `Bearer ${api_key}` },
  });

  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const body = await r.json();
      msg = body.error?.message || body.message || msg;
    } catch {}
    if (r.status === 401) throw new Error(`Auth failed (401): ${msg}. Check your API key.`);
    if (r.status === 404) throw new Error(`Models endpoint not found (404). The provider may not support /models — enter the model name manually.`);
    throw new Error(`Failed to fetch models: ${msg}`);
  }

  const data = await r.json();
  const models: ModelInfo[] = (data.data || data.models || []).map((m: any) => ({
    id: m.id || m.name,
    label: m.display_name || m.id || m.name,
    context_window: m.max_input_tokens || m.context_length,
  }));
  // Sort alphabetically by id
  models.sort((a, b) => a.id.localeCompare(b.id));
  return models;
}

/**
 * Verify that a (base_url, api_key, model) triple works by sending a tiny
 * chat completion. Returns true on success, throws with a helpful message
 * otherwise.
 */
export async function verifyLlmConfig(base_url: string, api_key: string, model: string): Promise<{ ok: boolean; reply?: string; error?: string }> {
  if (!base_url || !api_key || !model) {
    return { ok: false, error: 'Missing base_url, api_key, or model' };
  }
  const url = base_url.replace(/\/$/, '') + '/chat/completions';
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${api_key}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
        max_tokens: 20,
      }),
    });
    if (!r.ok) {
      let msg = `${r.status} ${r.statusText}`;
      try {
        const body = await r.json();
        msg = body.error?.message || body.message || msg;
      } catch {}
      return { ok: false, error: msg };
    }
    const data = await r.json();
    const reply = data.choices?.[0]?.message?.content || '(empty)';
    return { ok: true, reply };
  } catch (e: any) {
    return { ok: false, error: e.message };
  }
}
