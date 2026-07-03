/**
 * GitHub Codespaces API client — lets the phone wake/sleep the agent's
 * "own computer" on demand. Uses a GitHub PAT (stored in secure-store).
 *
 * API docs: https://docs.github.com/en/rest/codespaces/codespaces
 */

const API = 'https://api.github.com';

interface Codespace {
  name: string;
  state: 'Unknown' | 'Created' | 'Queued' | 'Provisioning' | 'Available' | 'Awaiting' | 'Unavailable' | 'Stopped' | 'Archived' | 'Deleted' | 'Moved';
  display_name?: string;
  repository: { full_name: string };
  machine: { display_name: string; cpus: number; memory_in_bytes: number };
  url: string;
  web_url: string;
  last_used_at: string;
  created_at: string;
  updated_at: string;
  idle_timeout_minutes: number;
}

export interface CodespaceStatus {
  name: string;
  state: Codespace['state'];
  repository: string;
  machine: string;
  last_used_at: string;
  /** The public port-forward URL on :8000 (if available). */
  runtime_url?: string;
}

function headers(pat: string): Record<string, string> {
  return {
    Authorization: `Bearer ${pat}`,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'Content-Type': 'application/json',
  };
}

async function gh<T>(pat: string, path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    ...init,
    headers: { ...headers(pat), ...(init?.headers || {}) },
  });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const body = await r.json();
      msg = body.message || msg;
    } catch {}
    throw new Error(`GitHub API: ${msg}`);
  }
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

// ---------- Codespace lifecycle ----------

export async function listCodespaces(pat: string): Promise<CodespaceStatus[]> {
  const data = await gh<{ codespaces: Codespace[] }>(pat, '/user/codespaces?per_page=20');
  return data.codespaces.map(c => ({
    name: c.name,
    state: c.state,
    repository: c.repository?.full_name || '',
    machine: c.machine?.display_name || '',
    last_used_at: c.last_used_at,
  }));
}

export async function createCodespace(
  pat: string,
  repoFullName: string,
  branch: string = 'main',
  machine: string = 'basicLinux32gb'
): Promise<CodespaceStatus> {
  // Get the repo ID first
  const repoResp = await gh<{ id: number }>(pat, `/repos/${repoFullName}`);
  const repoId = repoResp.id;
  const data = await gh<Codespace>(pat, '/user/codespaces', {
    method: 'POST',
    body: JSON.stringify({
      repository_id: repoId,
      ref: branch,
      machine,
    }),
  });
  return {
    name: data.name,
    state: data.state,
    repository: data.repository?.full_name || '',
    machine: data.machine?.display_name || '',
    last_used_at: data.last_used_at,
  };
}

export async function getCodespace(pat: string, name: string): Promise<CodespaceStatus> {
  const c = await gh<Codespace>(pat, `/user/codespaces/${name}`);
  return {
    name: c.name,
    state: c.state,
    repository: c.repository?.full_name || '',
    machine: c.machine?.display_name || '',
    last_used_at: c.last_used_at,
  };
}

export async function startCodespace(pat: string, name: string): Promise<CodespaceStatus> {
  const c = await gh<Codespace>(pat, `/user/codespaces/${name}/start`, { method: 'POST' });
  return {
    name: c.name,
    state: c.state,
    repository: c.repository?.full_name || '',
    machine: c.machine?.display_name || '',
    last_used_at: c.last_used_at,
  };
}

export async function stopCodespace(pat: string, name: string): Promise<void> {
  await gh(pat, `/user/codespaces/${name}/stop`, { method: 'POST' });
}

/** Poll until the codespace is Available (or fails). Returns the runtime URL. */
export async function waitUntilAvailable(
  pat: string,
  name: string,
  opts: { timeoutMs?: number; intervalMs?: number; onPoll?: (state: string) => void } = {}
): Promise<{ name: string; runtime_url: string }> {
  const timeoutMs = opts.timeoutMs ?? 180_000;
  const intervalMs = opts.intervalMs ?? 3_000;
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const status = await getCodespace(pat, name);
    opts.onPoll?.(status.state);
    if (status.state === 'Available') {
      // Codespace port-forward URL pattern: https://<name>-8000.app.github.dev
      return { name, runtime_url: `https://${name}-8000.app.github.dev` };
    }
    if (status.state === 'Unavailable' || status.state === 'Archived' || status.state === 'Deleted') {
      throw new Error(`Codespace entered bad state: ${status.state}`);
    }
    await new Promise(r => setTimeout(r, intervalMs));
  }
  throw new Error(`Codespace did not become Available within ${timeoutMs / 1000}s`);
}

/**
 * Fetch the runtime tunnel URL from the runtime-status branch.
 * The runtime inside the codespace commits a TUNNEL_URL.json file with the
 * public tunnel URL (from serveo.net) to the 'runtime-status' branch.
 * This lets the phone connect WITHOUT needing the codespace to be opened in a browser.
 *
 * Returns null if the tunnel URL isn't available (e.g., serveo is down or
 * postStartCommand hasn't run yet).
 */
export async function fetchTunnelUrl(pat: string, repo: string = 'UIoperationParamters29/PocketAgent'): Promise<string | null> {
  try {
    const r = await fetch(
      `https://api.github.com/repos/${repo}/contents/TUNNEL_URL.json?ref=runtime-status`,
      {
        headers: {
          Authorization: `Bearer ${pat}`,
          Accept: 'application/vnd.github+json',
        },
      }
    );
    if (!r.ok) return null;
    const data = await r.json();
    if (data.encoding === 'base64' && data.content) {
      const content = atob(data.content.replace(/\n/g, ''));
      const parsed = JSON.parse(content);
      return parsed.tunnel_url || null;
    }
    return null;
  } catch {
    return null;
  }
}

// ---------- Verify PAT scopes ----------

export interface PatInfo {
  login: string;
  scopes: string[];
  ok: boolean;
  missing: string[];
}

export async function verifyPat(pat: string): Promise<PatInfo> {
  const r = await fetch(`${API}/user`, { headers: headers(pat) });
  if (!r.ok) {
    return { login: '', scopes: [], ok: false, missing: ['valid'] };
  }
  const body = await r.json();
  const scopeHeader = r.headers.get('x-oauth-scopes') || '';
  const scopes = scopeHeader.split(',').map(s => s.trim()).filter(Boolean);
  const required = ['repo', 'codespace', 'workflow'];
  const missing = required.filter(s => !scopes.includes(s));
  return { login: body.login, scopes, ok: missing.length === 0, missing };
}
