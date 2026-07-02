/** Unit tests for the zustand store — verifies event → state mapping. */

import { useStore } from '../src/state/store';
import { ChatMessage } from '../src/lib/types';

describe('store', () => {
  beforeEach(() => {
    useStore.getState().resetSession();
  });

  it('starts empty', () => {
    const s = useStore.getState();
    expect(s.messages).toEqual([]);
    expect(s.todos).toEqual([]);
    expect(s.pendingQuestion).toBeNull();
    expect(s.outline).toBeNull();
    expect(s.completion).toBeNull();
    expect(s.isAgentBusy).toBe(false);
  });

  it('addUserMessage adds a user message + sets busy', () => {
    useStore.getState().addUserMessage('hello');
    const s = useStore.getState();
    expect(s.messages.length).toBe(1);
    expect(s.messages[0].role).toBe('user');
    expect(s.messages[0].content).toBe('hello');
    expect(s.isAgentBusy).toBe(true);
  });

  it('startAssistantStream + appendAssistantDelta + finalizeAssistantMessage', () => {
    const { addUserMessage, startAssistantStream, appendAssistantDelta, finalizeAssistantMessage } = useStore.getState();
    addUserMessage('hi');
    startAssistantStream();
    appendAssistantDelta('Hello ');
    appendAssistantDelta('world');
    let s = useStore.getState();
    expect(s.streamingMessageId).not.toBeNull();
    expect(s.messages.length).toBe(2); // user + assistant
    expect(s.messages[1].content).toBe('Hello world');
    expect(s.messages[1].streaming).toBe(true);

    finalizeAssistantMessage('Hello world!');
    s = useStore.getState();
    expect(s.streamingMessageId).toBeNull();
    expect(s.messages[1].content).toBe('Hello world!');
    expect(s.messages[1].streaming).toBe(false);
  });

  it('attachToolCall + attachToolResult', () => {
    const { addUserMessage, startAssistantStream, attachToolCall, attachToolResult } = useStore.getState();
    addUserMessage('ls');
    startAssistantStream();
    attachToolCall('call_1', 'Bash', { command: 'ls' });
    let s = useStore.getState();
    expect(s.messages[1].toolCalls?.length).toBe(1);
    expect(s.messages[1].toolCalls?.[0].name).toBe('Bash');
    expect(s.messages[1].toolCalls?.[0].pending).toBe(true);

    attachToolResult('call_1', 'Bash', true, 'file1\nfile2', '', 42);
    s = useStore.getState();
    expect(s.messages[1].toolCalls?.[0].pending).toBe(false);
    expect(s.messages[1].toolCalls?.[0].result?.ok).toBe(true);
    expect(s.messages[1].toolCalls?.[0].result?.output).toBe('file1\nfile2');
    expect(s.messages[1].toolCalls?.[0].result?.duration_ms).toBe(42);
  });

  it('setTodos updates the todo list', () => {
    useStore.getState().setTodos([
      { id: '1', content: 'task A', status: 'completed', priority: 'high' },
      { id: '2', content: 'task B', status: 'in_progress', priority: 'medium' },
    ]);
    expect(useStore.getState().todos.length).toBe(2);
  });

  it('setPendingQuestion + setPendingQuestion(null)', () => {
    const { setPendingQuestion } = useStore.getState();
    setPendingQuestion({ question_id: 'q1', questions: [] });
    expect(useStore.getState().pendingQuestion?.question_id).toBe('q1');
    setPendingQuestion(null);
    expect(useStore.getState().pendingQuestion).toBeNull();
  });

  it('setOutline', () => {
    useStore.getState().setOutline({
      document_type: 'pdf',
      sections: [{ index: 1, title: 'Intro', task_brief: 'first' }],
    });
    const s = useStore.getState();
    expect(s.outline?.document_type).toBe('pdf');
    expect(s.outline?.sections.length).toBe(1);
  });

  it('setCompletion', () => {
    useStore.getState().setCompletion({ project_type: 'document', summary: 'done', ts: 123 });
    expect(useStore.getState().completion?.project_type).toBe('document');
  });

  it('setAgentBusy', () => {
    useStore.getState().setAgentBusy(true);
    expect(useStore.getState().isAgentBusy).toBe(true);
    useStore.getState().setAgentBusy(false);
    expect(useStore.getState().isAgentBusy).toBe(false);
  });

  it('startSubagent + endSubagent', () => {
    const { addUserMessage, startAssistantStream, startSubagent, endSubagent } = useStore.getState();
    addUserMessage('delegate');
    startAssistantStream();
    startSubagent({
      subagent_id: 'sub1',
      subagent_type: 'general-purpose',
      description: 'test',
      depth: 1,
      started_ts: 1,
      messages: [],
      toolCalls: [],
    });
    let s = useStore.getState();
    expect(s.messages[1].subagents?.length).toBe(1);

    endSubagent('sub1');
    s = useStore.getState();
    expect(s.messages[1].subagents?.[0].ended_ts).toBeDefined();
  });

  it('resetSession clears everything', () => {
    const s = useStore.getState();
    s.addUserMessage('x');
    s.setTodos([{ id: '1', content: 'a', status: 'pending', priority: 'high' }]);
    s.setCompletion({ project_type: 'x', summary: 'y', ts: 1 });
    s.resetSession();
    const after = useStore.getState();
    expect(after.messages).toEqual([]);
    expect(after.todos).toEqual([]);
    expect(after.completion).toBeNull();
  });
});
