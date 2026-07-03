/**
 * App-wide state via zustand. Holds connection config, codespace state,
 * chat history, todos, and the pending question (if any).
 */

import { create } from 'zustand';
import {
  AskableQuestion,
  ChatMessage,
  ConnStatus as WSConnStatus,
  OutlineDesign,
  OutlineSection,
  SubagentRun,
  Todo,
  ToolCall,
  ToolName,
} from '../lib/types';

export type ConnStatus = WSConnStatus | 'waking-codespace';

interface PendingQuestion {
  question_id: string;
  questions: AskableQuestion[];
}

interface CompletionInfo {
  project_type: string;
  summary: string;
  ts: number;
}

interface AppState {
  // Connection
  connStatus: ConnStatus;
  codespaceState: string | null;
  codespaceName: string | null;
  runtimeUrl: string | null;
  sessionId: string | null;
  lastError: string | null;

  // Chat
  messages: ChatMessage[];
  streamingText: string;        // accumulates assistant.delta until assistant.message
  streamingMessageId: string | null;
  isAgentBusy: boolean;         // true while a turn is in flight

  // Side-channel UI state
  todos: Todo[];
  pendingQuestion: PendingQuestion | null;
  outline: { document_type: string; sections: OutlineSection[]; design?: OutlineDesign } | null;
  completion: CompletionInfo | null;

  // Actions
  setConnStatus: (s: ConnStatus) => void;
  setCodespace: (state: string | null, name?: string | null, url?: string | null) => void;
  setSessionId: (id: string | null) => void;
  setLastError: (msg: string | null) => void;

  addUserMessage: (content: string) => void;
  startAssistantStream: () => void;
  appendAssistantDelta: (text: string) => void;
  finalizeAssistantMessage: (text: string) => void;
  attachToolCall: (call_id: string, name: ToolName, args: Record<string, any>) => void;
  attachToolResult: (call_id: string, name: ToolName, ok: boolean, output: string, error: string, duration_ms: number) => void;
  setTodos: (todos: Todo[]) => void;
  setPendingQuestion: (q: PendingQuestion | null) => void;
  setOutline: (o: AppState['outline']) => void;
  setCompletion: (c: CompletionInfo | null) => void;
  setAgentBusy: (busy: boolean) => void;

  // Subagent events
  startSubagent: (sub: SubagentRun) => void;
  appendSubagentDelta: (subagent_id: string, text: string) => void;
  finalizeSubagentMessage: (subagent_id: string, text: string) => void;
  attachSubagentToolCall: (subagent_id: string, call_id: string, name: ToolName, args: Record<string, any>) => void;
  attachSubagentToolResult: (subagent_id: string, call_id: string, name: ToolName, ok: boolean, output: string, error: string) => void;
  endSubagent: (subagent_id: string) => void;

  resetSession: () => void;
  clearChat: () => void;
}

let idCounter = 0;
const nextId = () => `m${Date.now()}_${idCounter++}`;

export const useStore = create<AppState>((set, get) => ({
  connStatus: 'disconnected',
  codespaceState: null,
  codespaceName: null,
  runtimeUrl: null,
  sessionId: null,
  lastError: null,

  messages: [],
  streamingText: '',
  streamingMessageId: null,
  isAgentBusy: false,

  todos: [],
  pendingQuestion: null,
  outline: null,
  completion: null,

  setConnStatus: (s) => set({ connStatus: s, lastError: s === 'error' ? get().lastError : null }),
  setCodespace: (state, name, url) => set((st) => ({
    codespaceState: state !== undefined ? state : st.codespaceState,
    codespaceName: name !== undefined ? name : st.codespaceName,
    runtimeUrl: url !== undefined ? url : st.runtimeUrl,
  })),
  setSessionId: (id) => set({ sessionId: id }),
  setLastError: (msg) => set({ lastError: msg }),

  addUserMessage: (content) => set((st) => ({
    messages: [...st.messages, { id: nextId(), role: 'user', content, ts: Date.now() / 1000 }],
    isAgentBusy: true,
    pendingQuestion: null, // clear any stale UI question on new user message
  })),

  startAssistantStream: () => set((st) => {
    const id = nextId();
    return {
      streamingMessageId: id,
      streamingText: '',
      messages: [...st.messages, { id, role: 'assistant', content: '', ts: Date.now() / 1000, streaming: true, toolCalls: [] }],
    };
  }),

  appendAssistantDelta: (text) => set((st) => {
    if (!st.streamingMessageId) return st;
    return {
      streamingText: st.streamingText + text,
      messages: st.messages.map(m => m.id === st.streamingMessageId ? { ...m, content: m.content + text } : m),
    };
  }),

  finalizeAssistantMessage: (text) => set((st) => {
    if (!st.streamingMessageId) return st;
    return {
      streamingText: '',
      streamingMessageId: null,
      messages: st.messages.map(m => m.id === st.streamingMessageId ? { ...m, content: text, streaming: false } : m),
    };
  }),

  attachToolCall: (call_id, name, args) => set((st) => {
    if (!st.streamingMessageId) return st;
    const tc: ToolCall = { call_id, name, args, pending: true };
    return {
      messages: st.messages.map(m => m.id === st.streamingMessageId
        ? { ...m, toolCalls: [...(m.toolCalls || []), tc] }
        : m),
    };
  }),

  attachToolResult: (call_id, _name, ok, output, error, duration_ms) => set((st) => ({
    messages: st.messages.map(m => m.toolCalls
      ? { ...m, toolCalls: m.toolCalls.map(tc => tc.call_id === call_id ? { ...tc, result: { ok, output, error, duration_ms }, pending: false } : tc) }
      : m),
  })),

  setTodos: (todos) => set({ todos }),
  setPendingQuestion: (q) => set({ pendingQuestion: q }),
  setOutline: (o) => set({ outline: o }),
  setCompletion: (c) => set({ completion: c }),
  setAgentBusy: (busy) => set({ isAgentBusy: busy }),

  startSubagent: (sub) => set((st) => {
    if (!st.streamingMessageId) return st;
    return {
      messages: st.messages.map(m => m.id === st.streamingMessageId
        ? { ...m, subagents: [...(m.subagents || []), sub] }
        : m),
    };
  }),

  appendSubagentDelta: (subagent_id, text) => set((st) => ({
    messages: st.messages.map(m => m.subagents
      ? { ...m, subagents: m.subagents.map(s => {
          if (s.subagent_id !== subagent_id) return s;
          const last = s.messages[s.messages.length - 1];
          if (last && last.streaming) {
            return { ...s, messages: [...s.messages.slice(0, -1), { ...last, content: last.content + text }] };
          }
          return { ...s, messages: [...s.messages, { id: nextId(), role: 'assistant', content: text, ts: Date.now() / 1000, streaming: true }] };
        }) }
      : m),
  })),

  finalizeSubagentMessage: (subagent_id, text) => set((st) => ({
    messages: st.messages.map(m => m.subagents
      ? { ...m, subagents: m.subagents.map(s => {
          if (s.subagent_id !== subagent_id) return s;
          const last = s.messages[s.messages.length - 1];
          if (last && last.streaming) {
            return { ...s, messages: [...s.messages.slice(0, -1), { ...last, content: text, streaming: false }] };
          }
          return { ...s, messages: [...s.messages, { id: nextId(), role: 'assistant', content: text, ts: Date.now() / 1000 }] };
        }) }
      : m),
  })),

  attachSubagentToolCall: (subagent_id, call_id, name, args) => set((st) => ({
    messages: st.messages.map(m => m.subagents
      ? { ...m, subagents: m.subagents.map(s => s.subagent_id === subagent_id
          ? { ...s, toolCalls: [...s.toolCalls, { call_id, name, args, pending: true }] }
          : s) }
      : m),
  })),

  attachSubagentToolResult: (subagent_id, call_id, _name, ok, output, error) => set((st) => ({
    messages: st.messages.map(m => m.subagents
      ? { ...m, subagents: m.subagents.map(s => s.subagent_id === subagent_id
          ? { ...s, toolCalls: s.toolCalls.map(tc => tc.call_id === call_id ? { ...tc, result: { ok, output, error, duration_ms: 0 }, pending: false } : tc) }
          : s) }
      : m),
  })),

  endSubagent: (subagent_id) => set((st) => ({
    messages: st.messages.map(m => m.subagents
      ? { ...m, subagents: m.subagents.map(s => s.subagent_id === subagent_id ? { ...s, ended_ts: Date.now() / 1000 } : s) }
      : m),
  })),

  resetSession: () => set({
    messages: [],
    streamingText: '',
    streamingMessageId: null,
    todos: [],
    pendingQuestion: null,
    outline: null,
    completion: null,
    isAgentBusy: false,
    sessionId: null,
  }),

  clearChat: () => set({
    messages: [],
    streamingText: '',
    streamingMessageId: null,
    todos: [],
    pendingQuestion: null,
    outline: null,
    completion: null,
    isAgentBusy: false,
  }),
}));
