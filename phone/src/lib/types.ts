/**
 * PocketAgent wire-protocol types — mirrors docs/PROTOCOL.md exactly.
 * Keep in sync with cloud/runtime/app/agent.py.
 */

// Re-export ConnStatus so callers can import everything from types.ts
export type { ConnStatus } from '../lib/agent-ws';

// ---------- Phone → Server ----------

export type OutgoingFrame =
  | { type: 'session.start'; channel_secret: string; session: SessionConfig; resume_session_id?: string | null }
  | { type: 'user.message'; content: string }
  | { type: 'user.answer'; question_id: string; answer: UserAnswer[] }
  | { type: 'session.reset' }
  | { type: 'session.cancel' }
  | { type: 'ping' };

export interface SessionConfig {
  base_url: string;
  api_key: string;
  model: string;
}

export interface UserAnswer {
  header: string;
  answer: string | string[];
}

// ---------- Server → Phone ----------

export type IncomingEvent =
  | { type: 'session.start'; session_id: string; workspace: string; model: string; base_url: string; resumed: boolean }
  | { type: 'user.message'; content: string; ts: number }
  | { type: 'assistant.delta'; content: string; ts: number }
  | { type: 'assistant.message'; content: string; ts: number }
  | { type: 'tool.call'; call_id: string; name: ToolName; args: Record<string, any>; ts: number }
  | { type: 'tool.result'; call_id: string; name: ToolName; ok: boolean; output: string; error: string; duration_ms: number; ts: number }
  | { type: 'todo.update'; todos: Todo[]; ts: number }
  | { type: 'user.question'; question_id: string; questions: AskableQuestion[]; ts: number }
  | { type: 'outline.update'; document_type: string; sections: OutlineSection[]; design?: OutlineDesign; ts: number }
  | { type: 'session.complete'; project_type: string; summary: string; ts: number }
  | { type: 'subagent.start'; subagent_id: string; subagent_type: string; description: string; depth: number; ts: number }
  | { type: 'subagent.end'; subagent_id: string; depth: number; ts: number }
  | { type: 'subagent.user.message'; content: string; subagent_id: string; ts: number }
  | { type: 'subagent.assistant.delta'; content: string; subagent_id: string; ts: number }
  | { type: 'subagent.assistant.message'; content: string; subagent_id: string; ts: number }
  | { type: 'subagent.tool.call'; call_id: string; name: ToolName; args: Record<string, any>; subagent_id: string; ts: number }
  | { type: 'subagent.tool.result'; call_id: string; name: ToolName; ok: boolean; output: string; error: string; subagent_id: string; ts: number }
  | { type: 'subagent.session.end'; reason: string; subagent_id: string; ts: number }
  | { type: 'warning'; message: string; ts: number }
  | { type: 'error'; message: string; kind: 'auth' | 'config' | 'protocol' | 'llm' | 'server'; ts: number }
  | { type: 'session.end'; reason: 'complete' | 'max_iterations' | 'cancelled'; total_ms?: number; iterations?: number; ts: number }
  | { type: 'session.reset.ack'; session_id: string }
  | { type: 'pong'; ts: number };

export type ToolName =
  | 'Bash' | 'Read' | 'Write' | 'Edit' | 'Glob' | 'Grep' | 'LS' | 'TodoWrite'
  | 'Skill' | 'Task' | 'AskUserQuestion' | 'Outline' | 'Complete';

export interface Todo {
  id: string;
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
  priority: 'high' | 'medium' | 'low';
}

export interface AskableQuestionOption {
  label: string;
  description: string;
  recommended?: boolean;
}

export interface AskableQuestion {
  question: string;
  header: string;
  type: 'single' | 'multi';
  options: AskableQuestionOption[];
}

export interface OutlineSection {
  index: number;
  title: string;
  task_brief: string;
  layout?: string;
}

export interface OutlineDesign {
  style_name?: string;
  palette?: { background?: string; primary?: string; accent?: string };
  typography?: string;
  reference?: string;
}

// ---------- Derived UI types ----------

/** A chat message — assembled from assistant.delta + assistant.message events. */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  ts: number;
  /** Tool calls attached to this assistant message (in order). */
  toolCalls?: ToolCall[];
  /** True while the assistant is still streaming this message. */
  streaming?: boolean;
  /** Subagents spawned from this message (Task tool calls). */
  subagents?: SubagentRun[];
}

export interface ToolCall {
  call_id: string;
  name: ToolName;
  args: Record<string, any>;
  result?: {
    ok: boolean;
    output: string;
    error: string;
    duration_ms: number;
  };
  /** True until tool.result arrives. */
  pending?: boolean;
}

export interface SubagentRun {
  subagent_id: string;
  subagent_type: string;
  description: string;
  depth: number;
  started_ts: number;
  ended_ts?: number;
  messages: ChatMessage[];
  toolCalls: ToolCall[];
}

// ---------- Workspace (file explorer) ----------

export interface WorkspaceNode {
  name: string;
  path: string;
  type: 'dir' | 'file';
  children?: WorkspaceNode[];
  size?: number;
}

export interface FileContent {
  ok: boolean;
  path?: string;
  truncated?: boolean;
  size?: number;
  content?: string;
  error?: string;
}
