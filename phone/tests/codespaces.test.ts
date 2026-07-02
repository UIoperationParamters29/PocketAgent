/** Unit tests for the codespaces API client. */

import {
  verifyPat,
  listCodespaces,
  getCodespace,
  startCodespace,
  stopCodespace,
  createCodespace,
  waitUntilAvailable,
} from '../src/lib/codespaces';

// Helper to build a fetch mock that returns different responses per URL/method
function mockFetch(routes: Array<{ url: string; method?: string; status?: number; body: any; headers?: Record<string, string> }>) {
  return jest.fn(async (url: string, init?: any) => {
    const method = (init?.method) || 'GET';
    const match = routes.find(r => r.url === url && (r.method || 'GET') === method);
    if (!match) throw new Error(`No mock for ${method} ${url}`);
    return {
      ok: (match.status || 200) < 400,
      status: match.status || 200,
      statusText: 'OK',
      json: async () => match.body,
      text: async () => JSON.stringify(match.body),
      headers: new Map(Object.entries(match.headers || {})),
    } as any;
  });
}

describe('codespaces client', () => {
  const TEST_PAT = 'ghp_test123';

  it('verifyPat returns ok when scopes are present', async () => {
    (global.fetch as any) = mockFetch([
      { url: 'https://api.github.com/user', body: { login: 'testuser', id: 123 } , headers: { 'x-oauth-scopes': 'repo, codespace, workflow' } },
    ]);
    const info = await verifyPat(TEST_PAT);
    expect(info.ok).toBe(true);
    expect(info.login).toBe('testuser');
    expect(info.missing).toEqual([]);
  });

  it('verifyPat reports missing scopes', async () => {
    (global.fetch as any) = mockFetch([
      { url: 'https://api.github.com/user', body: { login: 'testuser' }, headers: { 'x-oauth-scopes': 'repo' } },
    ]);
    const info = await verifyPat(TEST_PAT);
    expect(info.ok).toBe(false);
    expect(info.missing).toContain('codespace');
    expect(info.missing).toContain('workflow');
  });

  it('verifyPat returns ok=false on 401', async () => {
    (global.fetch as any) = mockFetch([
      { url: 'https://api.github.com/user', status: 401, body: { message: 'Bad credentials' } },
    ]);
    const info = await verifyPat(TEST_PAT);
    expect(info.ok).toBe(false);
  });

  it('listCodespaces maps response to CodespaceStatus', async () => {
    (global.fetch as any) = mockFetch([
      { url: 'https://api.github.com/user/codespaces?per_page=20', body: {
        codespaces: [
          { name: 'cs1', state: 'Available', repository: { full_name: 'test/repo' }, machine: { display_name: '2 cores' }, last_used_at: '2026-01-01' },
          { name: 'cs2', state: 'Stopped', repository: { full_name: 'test/repo2' }, machine: { display_name: '4 cores' }, last_used_at: '2026-01-02' },
        ],
      } },
    ]);
    const list = await listCodespaces(TEST_PAT);
    expect(list.length).toBe(2);
    expect(list[0].name).toBe('cs1');
    expect(list[0].state).toBe('Available');
    expect(list[1].state).toBe('Stopped');
  });

  it('listCodespaces throws on API error', async () => {
    (global.fetch as any) = mockFetch([
      { url: 'https://api.github.com/user/codespaces?per_page=20', status: 403, body: { message: 'Forbidden' } },
    ]);
    await expect(listCodespaces(TEST_PAT)).rejects.toThrow(/Forbidden/);
  });

  it('getCodespace returns single codespace', async () => {
    (global.fetch as any) = mockFetch([
      { url: 'https://api.github.com/user/codespaces/cs1', body: {
        name: 'cs1', state: 'Available', repository: { full_name: 'test/repo' }, machine: { display_name: '2 cores' }, last_used_at: '2026-01-01',
      } },
    ]);
    const cs = await getCodespace(TEST_PAT, 'cs1');
    expect(cs.name).toBe('cs1');
    expect(cs.state).toBe('Available');
  });

  it('startCodespace POSTs to /start', async () => {
    const fetchMock = mockFetch([
      { url: 'https://api.github.com/user/codespaces/cs1/start', method: 'POST', body: {
        name: 'cs1', state: 'Starting', repository: { full_name: 'test/repo' }, machine: { display_name: '2 cores' }, last_used_at: '2026-01-01',
      } },
    ]);
    (global.fetch as any) = fetchMock;
    const cs = await startCodespace(TEST_PAT, 'cs1');
    expect(cs.state).toBe('Starting');
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.github.com/user/codespaces/cs1/start',
      expect.objectContaining({ method: 'POST' })
    );
  });

  it('stopCodespace POSTs to /stop', async () => {
    const fetchMock = mockFetch([
      { url: 'https://api.github.com/user/codespaces/cs1/stop', method: 'POST', status: 204, body: undefined },
    ]);
    (global.fetch as any) = fetchMock;
    await stopCodespace(TEST_PAT, 'cs1');
    expect(fetchMock).toHaveBeenCalled();
  });

  it('createCodespace creates from repo name', async () => {
    const fetchMock = mockFetch([
      { url: 'https://api.github.com/repos/test/repo', body: { id: 999 } },
      { url: 'https://api.github.com/user/codespaces', method: 'POST', body: {
        name: 'new-cs', state: 'Provisioning', repository: { full_name: 'test/repo' }, machine: { display_name: '2 cores' }, last_used_at: '2026-01-01',
      } },
    ]);
    (global.fetch as any) = fetchMock;
    const cs = await createCodespace(TEST_PAT, 'test/repo');
    expect(cs.name).toBe('new-cs');
    expect(cs.state).toBe('Provisioning');
    // Verify the POST body had the right repo_id
    const createCall = fetchMock.mock.calls[1];
    const body = JSON.parse(createCall[1].body);
    expect(body.repository_id).toBe(999);
  });

  it('waitUntilAvailable polls until Available', async () => {
    let state = 'Queued';
    (global.fetch as any) = jest.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ name: 'cs1', state, repository: {}, machine: {}, last_used_at: '' }),
    })) as any;

    // Toggle state to Available after 2 polls
    setTimeout(() => { state = 'Available'; }, 100);

    const result = await waitUntilAvailable(TEST_PAT, 'cs1', { intervalMs: 50, timeoutMs: 5000 });
    expect(result.name).toBe('cs1');
    expect(result.runtime_url).toContain('cs1-8000.app.github.dev');
  });

  it('waitUntilAvailable throws on timeout', async () => {
    (global.fetch as any) = jest.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ name: 'cs1', state: 'Queued', repository: {}, machine: {}, last_used_at: '' }),
    })) as any;

    await expect(
      waitUntilAvailable(TEST_PAT, 'cs1', { intervalMs: 20, timeoutMs: 100 })
    ).rejects.toThrow(/did not become Available/);
  });

  it('waitUntilAvailable calls onPoll with state', async () => {
    let state = 'Queued';
    (global.fetch as any) = jest.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ name: 'cs1', state, repository: {}, machine: {}, last_used_at: '' }),
    })) as any;

    const polledStates: string[] = [];
    setTimeout(() => { state = 'Available'; }, 100);
    await waitUntilAvailable(TEST_PAT, 'cs1', {
      intervalMs: 30, timeoutMs: 5000,
      onPoll: (s) => polledStates.push(s),
    });
    expect(polledStates.length).toBeGreaterThan(0);
    expect(polledStates).toContain('Queued');
  });
});
