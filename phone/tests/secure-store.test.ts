/** Unit tests for secure-store helpers. */

import {
  saveGithubPat, loadGithubPat,
  saveChannelSecret, loadChannelSecret,
  saveSessionConfig, loadSessionConfig,
  saveCodespaceName, loadCodespaceName,
  isOnboarded, setOnboarded,
  wipeAll,
  PROVIDER_PRESETS,
} from '../src/lib/secure-store';
import { SessionConfig } from '../src/lib/types';

describe('secure-store', () => {
  it('round-trips GitHub PAT', async () => {
    await saveGithubPat('ghp_test123');
    expect(await loadGithubPat()).toBe('ghp_test123');
  });

  it('round-trips channel secret', async () => {
    await saveChannelSecret('abcdef0123456789');
    expect(await loadChannelSecret()).toBe('abcdef0123456789');
  });

  it('round-trips session config (BYOK)', async () => {
    const cfg: SessionConfig = {
      base_url: 'https://api.openai.com/v1',
      api_key: 'sk-test',
      model: 'gpt-4o-mini',
    };
    await saveSessionConfig(cfg);
    const loaded = await loadSessionConfig();
    expect(loaded).toEqual(cfg);
  });

  it('round-trips codespace name', async () => {
    await saveCodespaceName('improved-orbit-xyz');
    expect(await loadCodespaceName()).toBe('improved-orbit-xyz');
  });

  it('handles onboarded flag', async () => {
    expect(await isOnboarded()).toBe(false);
    await setOnboarded();
    expect(await isOnboarded()).toBe(true);
  });

  it('returns null for unset values', async () => {
    await wipeAll();
    expect(await loadGithubPat()).toBeNull();
    expect(await loadChannelSecret()).toBeNull();
    expect(await loadSessionConfig()).toBeNull();
    expect(await loadCodespaceName()).toBeNull();
    expect(await isOnboarded()).toBe(false);
  });

  it('PROVIDER_PRESETS has 9 entries including Anthropic + Gemini', () => {
    expect(PROVIDER_PRESETS.length).toBe(9);
    const ids = PROVIDER_PRESETS.map(p => p.id);
    expect(ids).toContain('openai');
    expect(ids).toContain('zai');
    expect(ids).toContain('anthropic');
    expect(ids).toContain('gemini');
    expect(ids).toContain('openrouter');
    expect(ids).toContain('groq');
    expect(ids).toContain('mistral');
    expect(ids).toContain('ollama');
    expect(ids).toContain('custom');
  });

  it('every preset has a base_url and default_model (except custom)', () => {
    for (const p of PROVIDER_PRESETS) {
      if (p.id === 'custom') continue;
      expect(p.base_url).toBeTruthy();
      expect(p.default_model).toBeTruthy();
      expect(p.label).toBeTruthy();
    }
  });
});
