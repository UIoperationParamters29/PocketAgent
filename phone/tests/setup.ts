/** Jest setup — mock native modules that aren't available in Node. */

// Mock expo-secure-store with an in-memory store
const secureStore: Record<string, string> = {};
jest.mock('expo-secure-store', () => ({
  setItemAsync: jest.fn(async (key: string, value: string) => { secureStore[key] = value; }),
  getItemAsync: jest.fn(async (key: string) => secureStore[key] ?? null),
  deleteItemAsync: jest.fn(async (key: string) => { delete secureStore[key]; }),
  WHEN_UNLOCKED: 'WHEN_UNLOCKED',
  __reset: () => { for (const k of Object.keys(secureStore)) delete secureStore[k]; },
}));

// Mock @react-native-async-storage/async-storage
const asyncStore: Record<string, string> = {};
jest.mock('@react-native-async-storage/async-storage', () => ({
  setItem: jest.fn(async (k: string, v: string) => { asyncStore[k] = v; }),
  getItem: jest.fn(async (k: string) => asyncStore[k] ?? null),
  removeItem: jest.fn(async (k: string) => { delete asyncStore[k]; }),
}));

// Mock expo-status-bar (renders nothing)
jest.mock('expo-status-bar', () => ({ StatusBar: () => null }));

// Global fetch mock — tests can override per-test
global.fetch = jest.fn(async (url: any, init?: any) => {
  throw new Error(`fetch not mocked for ${url} — set up a per-test mock`);
}) as any;

// Reset all mocks between tests
beforeEach(() => {
  jest.clearAllMocks();
  (secureStore as any).__reset?.();
  for (const k of Object.keys(asyncStore)) delete (asyncStore as any)[k];
});
