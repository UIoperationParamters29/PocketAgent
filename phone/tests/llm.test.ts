/** Unit tests for the LLM helpers (fetchModels, verifyLlmConfig). */

import { fetchModels, verifyLlmConfig } from '../src/lib/llm';

function mockResponse(body: any, status = 200) {
  return {
    ok: status < 400,
    status,
    statusText: 'OK',
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as any;
}

describe('llm helpers', () => {
  it('fetchModels returns sorted list', async () => {
    (global.fetch as any) = jest.fn(async () => mockResponse({
      data: [
        { id: 'gpt-4o' },
        { id: 'gpt-3.5-turbo' },
        { id: 'gpt-4o-mini' },
      ],
    }));
    const models = await fetchModels('https://api.openai.com/v1', 'sk-test');
    expect(models.length).toBe(3);
    // Should be sorted alphabetically
    expect(models[0].id).toBe('gpt-3.5-turbo');
    expect(models[1].id).toBe('gpt-4o');
    expect(models[2].id).toBe('gpt-4o-mini');
  });

  it('fetchModels handles display_name + max_input_tokens', async () => {
    (global.fetch as any) = jest.fn(async () => mockResponse({
      data: [
        { id: 'near_glm_5', display_name: 'GLM 5', max_input_tokens: 200000 },
      ],
    }));
    const models = await fetchModels('https://api.test.com/v1', 'sk-test');
    expect(models[0].label).toBe('GLM 5');
    expect(models[0].context_window).toBe(200000);
  });

  it('fetchModels throws on 401 with helpful message', async () => {
    (global.fetch as any) = jest.fn(async () => mockResponse(
      { error: { message: 'Invalid API key' } },
      401
    ));
    await expect(fetchModels('https://api.test.com/v1', 'bad-key'))
      .rejects.toThrow(/Auth failed.*Invalid API key/);
  });

  it('fetchModels throws on 404 with model-manual hint', async () => {
    (global.fetch as any) = jest.fn(async () => mockResponse({ message: 'Not found' }, 404));
    await expect(fetchModels('https://api.test.com/v1', 'sk-test'))
      .rejects.toThrow(/Models endpoint not found.*manually/);
  });

  it('fetchModels strips trailing slash from base_url', async () => {
    const fetchMock = jest.fn(async () => mockResponse({ data: [] }));
    (global.fetch as any) = fetchMock;
    await fetchModels('https://api.test.com/v1/', 'sk-test');
    expect(fetchMock).toHaveBeenCalledWith('https://api.test.com/v1/models', expect.anything());
  });

  it('fetchModels throws if base_url is empty', async () => {
    await expect(fetchModels('', 'sk-test')).rejects.toThrow(/Base URL is required/);
  });

  it('fetchModels throws if api_key is empty', async () => {
    await expect(fetchModels('https://api.test.com/v1', '')).rejects.toThrow(/API key is required/);
  });

  it('verifyLlmConfig returns ok=true on 200 with content', async () => {
    (global.fetch as any) = jest.fn(async () => mockResponse({
      choices: [{ message: { content: 'OK' } }],
    }));
    const r = await verifyLlmConfig('https://api.test.com/v1', 'sk-test', 'gpt-4o-mini');
    expect(r.ok).toBe(true);
    expect(r.reply).toBe('OK');
  });

  it('verifyLlmConfig returns ok=false on 401', async () => {
    (global.fetch as any) = jest.fn(async () => mockResponse(
      { error: { message: 'Bad key' } },
      401
    ));
    const r = await verifyLlmConfig('https://api.test.com/v1', 'bad', 'gpt-4o-mini');
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/Bad key/);
  });

  it('verifyLlmConfig returns ok=false on missing fields', async () => {
    const r = await verifyLlmConfig('', 'sk', 'model');
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/Missing/);
  });

  it('verifyLlmConfig handles network error', async () => {
    (global.fetch as any) = jest.fn(async () => { throw new Error('Network error'); });
    const r = await verifyLlmConfig('https://api.test.com/v1', 'sk', 'model');
    expect(r.ok).toBe(false);
    expect(r.error).toMatch(/Network error/);
  });
});
