/**
 * useAgentSession — high-level hook that owns the WebSocket lifecycle
 * and routes incoming events into the zustand store.
 *
 * Usage:
 *   const { connect, disconnect, sendMessage, answerQuestion, isReady } = useAgentSession();
 *   connect();                          // connect to the codespace's runtime
 *   sendMessage('list files');          // send a user message
 *   answerQuestion(qid, [{header:'Tone', answer:'casual'}]);
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { AgentWS } from '../lib/agent-ws';
import { IncomingEvent, UserAnswer } from '../lib/types';
import { useStore } from '../state/store';
import { loadChannelSecret, loadSessionConfig } from '../lib/secure-store';

export function useAgentSession() {
  const wsRef = useRef<AgentWS | null>(null);
  const [isReady, setIsReady] = useState(false);

  const {
    setConnStatus, setSessionId, setLastError,
    addUserMessage, startAssistantStream, appendAssistantDelta, finalizeAssistantMessage,
    attachToolCall, attachToolResult, setTodos, setPendingQuestion, setOutline, setCompletion,
    setAgentBusy,
    startSubagent, appendSubagentDelta, finalizeSubagentMessage,
    attachSubagentToolCall, attachSubagentToolResult, endSubagent,
  } = useStore();

  const handleEvent = useCallback((evt: IncomingEvent) => {
    switch (evt.type) {
      case 'session.start':
        setSessionId(evt.session_id);
        setIsReady(true);
        break;

      case 'user.message':
        // The server echoes the user's message back. We already added it locally
        // (to avoid UI lag), so we skip if it matches the last user message.
        // (Simpler: rely on the local optimistic add; this is a no-op.)
        break;

      case 'assistant.delta':
        // Start a new assistant message on the first delta if none is streaming
        if (!useStore.getState().streamingMessageId) {
          startAssistantStream();
        }
        appendAssistantDelta(evt.content);
        break;

      case 'assistant.message':
        finalizeAssistantMessage(evt.content);
        break;

      case 'tool.call':
        attachToolCall(evt.call_id, evt.name, evt.args);
        break;

      case 'tool.result':
        attachToolResult(evt.call_id, evt.name, evt.ok, evt.output, evt.error, evt.duration_ms);
        break;

      case 'todo.update':
        setTodos(evt.todos);
        break;

      case 'user.question':
        setPendingQuestion({ question_id: evt.question_id, questions: evt.questions });
        break;

      case 'outline.update':
        setOutline({ document_type: evt.document_type, sections: evt.sections, design: evt.design });
        break;

      case 'session.complete':
        setCompletion({ project_type: evt.project_type, summary: evt.summary, ts: evt.ts });
        break;

      case 'subagent.start':
        startSubagent({
          subagent_id: evt.subagent_id,
          subagent_type: evt.subagent_type,
          description: evt.description,
          depth: evt.depth,
          started_ts: evt.ts,
          messages: [],
          toolCalls: [],
        });
        break;

      case 'subagent.assistant.delta':
        appendSubagentDelta(evt.subagent_id, evt.content);
        break;

      case 'subagent.assistant.message':
        finalizeSubagentMessage(evt.subagent_id, evt.content);
        break;

      case 'subagent.tool.call':
        attachSubagentToolCall(evt.subagent_id, evt.call_id, evt.name, evt.args);
        break;

      case 'subagent.tool.result':
        attachSubagentToolResult(evt.subagent_id, evt.call_id, evt.name, evt.ok, evt.output, evt.error);
        break;

      case 'subagent.end':
        endSubagent(evt.subagent_id);
        break;

      case 'session.end':
        setAgentBusy(false);
        // If streaming was in flight (no assistant.message), finalize with whatever we have
        if (useStore.getState().streamingMessageId) {
          const cur = useStore.getState().streamingText;
          finalizeAssistantMessage(cur);
        }
        break;

      case 'error':
        setLastError(`[${evt.kind}] ${evt.message}`);
        setAgentBusy(false);
        if (evt.kind === 'auth' || evt.kind === 'config') {
          // Fatal — disconnect
          wsRef.current?.close();
        }
        break;

      case 'warning':
        // Non-fatal — show as a system note? For now, just log.
        console.warn('Agent warning:', evt.message);
        break;

      default:
        // pong, subagent.session.end, subagent.user.message — no-op
        break;
    }
  }, [setSessionId, setIsReady, startAssistantStream, appendAssistantDelta, finalizeAssistantMessage, attachToolCall, attachToolResult, setTodos, setPendingQuestion, setOutline, setCompletion, setAgentBusy, startSubagent, appendSubagentDelta, finalizeSubagentMessage, attachSubagentToolCall, attachSubagentToolResult, endSubagent, setLastError]);

  const connect = useCallback(async () => {
    // Read connection config from secure store
    const [secret, cfg] = await Promise.all([loadChannelSecret(), loadSessionConfig()]);
    if (!cfg) {
      setLastError('Missing session config — complete onboarding first.');
      return false;
    }

    // The runtime URL is in the store (set by the codespace-wake logic)
    const url = useStore.getState().runtimeUrl;
    if (!url) {
      setLastError('No runtime URL — wake the codespace first.');
      return false;
    }

    // Tear down any existing connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    const wsUrl = url.replace(/^http/, 'ws') + '/agent';
    const ws = new AgentWS({
      url: wsUrl,
      channelSecret: secret || '',  // empty = open mode (runtime accepts any)
      sessionConfig: cfg,
      onEvent: handleEvent,
      onStatus: (s) => {
        setConnStatus(s);
        // If error, also surface the WS client's last error message
        if (s === 'error' && wsRef.current) {
          const wsErr = wsRef.current.getLastError();
          if (wsErr) setLastError(wsErr);
        }
      },
    });
    wsRef.current = ws;
    ws.connect();
    return true;
  }, [handleEvent, setConnStatus, setLastError]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setIsReady(false);
  }, []);

  const sendMessage = useCallback((content: string) => {
    if (!wsRef.current) return false;
    // Optimistic local add
    addUserMessage(content);
    return wsRef.current.send({ type: 'user.message', content });
  }, [addUserMessage]);

  const answerQuestion = useCallback((questionId: string, answer: UserAnswer[]) => {
    if (!wsRef.current) return false;
    setPendingQuestion(null);
    return wsRef.current.send({ type: 'user.answer', question_id: questionId, answer });
  }, [setPendingQuestion]);

  const resetSession = useCallback(() => {
    wsRef.current?.send({ type: 'session.reset' });
  }, []);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  return { connect, disconnect, sendMessage, answerQuestion, resetSession, isReady };
}
