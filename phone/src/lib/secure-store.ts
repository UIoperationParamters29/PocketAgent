/**
 * Secure storage for BYOK keys + connection config.
 * Uses expo-secure-store (Android Keystore / iOS Keychain — hardware-backed).
 */

import * as SecureStore from 'expo-secure-store';
import { SessionConfig } from './types';

const KEYS = {
  githubPat:     'pa_github_pat',     // GitHub PAT for Codespaces control
  channelSecret: 'pa_channel_secret', // PA_CHANNEL_SECRET for the runtime
  sessionConfig: 'pa_session_config', // BYOK LLM config (provider/key/model)
  codespaceName: 'pa_codespace_name', // last-used codespace name
  onboarded:     'pa_onboarded',      // '1' after onboarding complete
} as const;

// ---------- Generic helpers ----------

export async function readSecure(key: string): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(key);
  } catch {
    return null;
  }
}

export async function writeSecure(key: string, value: string): Promise<void> {
  await SecureStore.setItemAsync(key, value, {
    keychainAccessible: SecureStore.WHEN_UNLOCKED,
  });
}

export async function deleteSecure(key: string): Promise<void> {
  await SecureStore.deleteItemAsync(key);
}

// ---------- App-specific ----------

export async function loadGithubPat(): Promise<string | null> {
  return readSecure(KEYS.githubPat);
}

export async function saveGithubPat(pat: string): Promise<void> {
  await writeSecure(KEYS.githubPat, pat);
}

export async function loadChannelSecret(): Promise<string | null> {
  return readSecure(KEYS.channelSecret);
}

export async function saveChannelSecret(secret: string): Promise<void> {
  await writeSecure(KEYS.channelSecret, secret);
}

export async function loadSessionConfig(): Promise<SessionConfig | null> {
  const raw = await readSecure(KEYS.sessionConfig);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SessionConfig;
  } catch {
    return null;
  }
}

export async function saveSessionConfig(cfg: SessionConfig): Promise<void> {
  await writeSecure(KEYS.sessionConfig, JSON.stringify(cfg));
}

export async function loadCodespaceName(): Promise<string | null> {
  return readSecure(KEYS.codespaceName);
}

export async function saveCodespaceName(name: string): Promise<void> {
  await writeSecure(KEYS.codespaceName, name);
}

export async function isOnboarded(): Promise<boolean> {
  return (await readSecure(KEYS.onboarded)) === '1';
}

export async function setOnboarded(): Promise<void> {
  await writeSecure(KEYS.onboarded, '1');
}

export async function wipeAll(): Promise<void> {
  for (const k of Object.values(KEYS)) {
    await deleteSecure(k);
  }
}

// ---------- Preset providers ----------

export interface ProviderPreset {
  id: string;
  label: string;
  base_url: string;
  default_model: string;
  key_prefix: string; // hint for the input
  signup_url: string;
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    id: 'openai',
    label: 'OpenAI',
    base_url: 'https://api.openai.com/v1',
    default_model: 'gpt-4o-mini',
    key_prefix: 'sk-...',
    signup_url: 'https://platform.openai.com/api-keys',
  },
  {
    id: 'zai',
    label: 'z.ai GLM',
    base_url: 'https://api.z.ai/api/pallet/v1',
    default_model: 'glm-4.6',
    key_prefix: '...',
    signup_url: 'https://z.ai',
  },
  {
    id: 'openrouter',
    label: 'OpenRouter',
    base_url: 'https://openrouter.ai/api/v1',
    default_model: 'anthropic/claude-3.5-sonnet',
    key_prefix: 'sk-or-...',
    signup_url: 'https://openrouter.ai/keys',
  },
  {
    id: 'groq',
    label: 'Groq',
    base_url: 'https://api.groq.com/openai/v1',
    default_model: 'llama-3.3-70b-versatile',
    key_prefix: 'gsk_...',
    signup_url: 'https://console.groq.com/keys',
  },
  {
    id: 'mistral',
    label: 'Mistral',
    base_url: 'https://api.mistral.ai/v1',
    default_model: 'mistral-large-latest',
    key_prefix: '...',
    signup_url: 'https://console.mistral.ai/api-keys',
  },
  {
    id: 'ollama',
    label: 'Ollama (local)',
    base_url: 'http://10.0.2.2:11434/v1', // Android emulator -> host
    default_model: 'llama3.2',
    key_prefix: 'ollama',
    signup_url: 'https://ollama.ai',
  },
  {
    id: 'custom',
    label: 'Custom (OpenAI-compatible)',
    base_url: '',
    default_model: '',
    key_prefix: '',
    signup_url: '',
  },
];
