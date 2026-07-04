/**
 * PocketAgent UI components — clean, dark, z.ai-style cards.
 *
 * Polish (Phase 6):
 *  - Animated typing dots (3 pulsing dots while agent is thinking)
 *  - Code-block rendering in assistant messages (``` fences → dark inset block)
 *  - Smoother expand/collapse with spring LayoutAnimation
 *  - Better truncation ("show more / less" on tool results)
 *  - Haptic feedback on tool expand / question submit (iOS only, no-op on Android)
 *  - Color-coded tool icons with subtle background tint
 */

import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, LayoutAnimation, Platform, UIManager,
  ActivityIndicator, ScrollView, TextInput, Animated, Easing, TouchableWithoutFeedback,
} from 'react-native';
import { colors, spacing, radius, typography } from '../theme/colors';
import {
  AskableQuestion, ChatMessage, SubagentRun, Todo, ToolCall, ToolName, UserAnswer,
} from '../lib/types';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

const expand = () => LayoutAnimation.configureNext({
  duration: 220,
  update: { type: LayoutAnimation.Types.spring, springDamping: 0.78 },
  delete: { type: LayoutAnimation.Types.easeInEaseOut, property: LayoutAnimation.Properties.opacity },
  create: { type: LayoutAnimation.Types.easeInEaseOut, property: LayoutAnimation.Properties.opacity },
});

const haptic = () => {
  // expo-haptics would be nicer but adding a native module inflates the APK.
  // RN's ReactNative.Haptics isn't available without a native module either.
  // For now: no-op. We'll add expo-haptics in Phase 7 if user wants.
};

// ---------- ToolCallCard ----------

const TOOL_COLORS: Record<ToolName, string> = {
  Bash: colors.accent,
  Read: '#60A5FA',
  Write: '#60A5FA',
  Edit: '#60A5FA',
  Glob: '#A78BFA',
  Grep: '#A78BFA',
  LS: '#A78BFA',
  TodoWrite: '#FBBF24',
  Skill: '#22C55E',
  Task: '#F97316',
  AskUserQuestion: '#EC4899',
  Outline: '#06B6D4',
  Complete: '#10B981',
};

const TOOL_ICONS: Record<ToolName, string> = {
  Bash: '$', Read: 'RD', Write: 'WR', Edit: 'ED', Glob: 'GL', Grep: 'GR', LS: 'LS',
  TodoWrite: 'TD', Skill: 'SK', Task: 'TSK', AskUserQuestion: '?', Outline: 'OL', Complete: 'OK',
};

const PREVIEW_LIMIT = 800;

export function ToolCallCard({ tc, subagent = false }: { tc: ToolCall; subagent?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const [showFull, setShowFull] = useState(false);
  const color = TOOL_COLORS[tc.name];
  const pending = tc.pending;
  const result = tc.result;

  const argPreview = (() => {
    if (tc.name === 'Bash') return tc.args.command?.slice(0, 200) || '';
    if (tc.name === 'Read') return tc.args.file_path || '';
    if (tc.name === 'Write') return `${tc.args.file_path} (${(tc.args.content || '').length} bytes)`;
    if (tc.name === 'Edit') return tc.args.file_path || '';
    if (tc.name === 'Glob') return tc.args.pattern || '';
    if (tc.name === 'Grep') return tc.args.pattern || '';
    if (tc.name === 'LS') return tc.args.path || '';
    if (tc.name === 'TodoWrite') return `${(tc.args.todos || []).length} todos`;
    if (tc.name === 'Skill') return tc.args.name || '(list)';
    if (tc.name === 'Task') return tc.args.description || '';
    if (tc.name === 'AskUserQuestion') return `${(tc.args.questions || []).length} question(s)`;
    if (tc.name === 'Outline') return `${(tc.args.sections || []).length} sections`;
    if (tc.name === 'Complete') return tc.args.project_type || '';
    return JSON.stringify(tc.args).slice(0, 100);
  })();

  const fullOutput = result?.output || '';
  const outputIsLong = fullOutput.length > PREVIEW_LIMIT;
  const outputToShow = showFull ? fullOutput : fullOutput.slice(0, PREVIEW_LIMIT);

  return (
    <View style={[styles.toolCard, subagent && styles.toolCardSubagent, { borderLeftColor: color }]}>
      <TouchableOpacity
        style={styles.toolHeader}
        onPress={() => { expand(); haptic(); setExpanded(!expanded); setShowFull(false); }}
        activeOpacity={0.6}
      >
        <View style={[styles.toolIcon, { backgroundColor: color + '22' }]}>
          <Text style={[styles.toolIconText, { color }]}>{TOOL_ICONS[tc.name]}</Text>
        </View>
        <View style={styles.toolHeaderText}>
          <Text style={styles.toolName}>{tc.name}</Text>
          <Text style={styles.toolArgPreview} numberOfLines={expanded ? undefined : 1}>{argPreview}</Text>
        </View>
        {pending ? (
          <View style={styles.toolPendingBadge}>
            <ActivityIndicator size="small" color={colors.textTertiary} />
          </View>
        ) : (
          <Text style={[styles.toolStatus, { color: result?.ok ? colors.success : colors.error }]}>
            {result?.ok ? `${result.duration_ms}ms` : 'ERR'}
          </Text>
        )}
        <Text style={styles.chevron}>{expanded ? '▾' : '▸'}</Text>
      </TouchableOpacity>

      {expanded && result && (
        <View style={styles.toolBody}>
          {result.error ? (
            <Text style={[styles.toolOutput, { color: colors.error }]}>{result.error}</Text>
          ) : null}
          <Text style={styles.toolOutput} selectable>{outputToShow}</Text>
          {outputIsLong && (
            <TouchableOpacity onPress={() => { expand(); setShowFull(!showFull); }} style={styles.showMoreBtn}>
              <Text style={styles.showMoreText}>
                {showFull ? '▾ show less' : `▸ show ${fullOutput.length - PREVIEW_LIMIT} more chars`}
              </Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      {expanded && !result && (
        <View style={styles.toolBody}>
          <View style={styles.toolRunningRow}>
            <ActivityIndicator size="small" color={color} />
            <Text style={styles.toolRunningText}>Running…</Text>
          </View>
        </View>
      )}
    </View>
  );
}

// ---------- Code-block renderer for assistant text ----------

function renderAssistantText(text: string) {
  // Split on ``` code fences. Even indices = prose, odd indices = code blocks.
  const parts = text.split(/```/);
  return parts.map((part, i) => {
    if (i % 2 === 1) {
      // Code block — strip optional language tag on first line
      const nl = part.indexOf('\n');
      const body = nl >= 0 ? part.slice(nl + 1) : part;
      return (
        <View key={i} style={styles.codeBlock}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <Text style={styles.codeBlockText} selectable>{body.replace(/\n$/, '')}</Text>
          </ScrollView>
        </View>
      );
    }
    return (
      <Text key={i} style={styles.assistantText} selectable>{part}</Text>
    );
  });
}

// ---------- MessageBubble ----------

export function MessageBubble({ msg, depth = 0 }: { msg: ChatMessage; depth?: number }) {
  if (msg.role === 'user') {
    return (
      <View style={styles.userRow}>
        <View style={styles.userBubble}>
          <Text style={styles.userText} selectable>{msg.content}</Text>
        </View>
      </View>
    );
  }

  // Assistant
  const showTyping = msg.streaming && !msg.content;
  return (
    <View style={styles.assistantRow}>
      <View style={styles.assistantBubble}>
        {msg.content ? (
          <View style={styles.assistantContent}>{renderAssistantText(msg.content)}</View>
        ) : showTyping ? (
          <TypingDots />
        ) : null}

        {msg.toolCalls && msg.toolCalls.length > 0 && (
          <View style={styles.toolCallList}>
            {msg.toolCalls.map(tc => <ToolCallCard key={tc.call_id} tc={tc} subagent={depth > 0} />)}
          </View>
        )}

        {msg.subagents && msg.subagents.length > 0 && (
          <View style={styles.subagentList}>
            {msg.subagents.map(sub => <SubagentCard key={sub.subagent_id} sub={sub} />)}
          </View>
        )}
      </View>
    </View>
  );
}

// ---------- TypingDots (3 pulsing dots) ----------

function TypingDots() {
  const dots = [useRef(new Animated.Value(0.3)).current, useRef(new Animated.Value(0.3)).current, useRef(new Animated.Value(0.3)).current];
  useEffect(() => {
    const anims: Animated.CompositeAnimation[] = [];
    dots.forEach((d, i) => {
      const anim = Animated.loop(
        Animated.sequence([
          Animated.delay(i * 160),
          Animated.timing(d, { toValue: 1, duration: 320, useNativeDriver: true, easing: Easing.inOut(Easing.ease) }),
          Animated.timing(d, { toValue: 0.3, duration: 320, useNativeDriver: true, easing: Easing.inOut(Easing.ease) }),
        ])
      );
      anim.start();
      anims.push(anim as any);
    });
    return () => anims.forEach(a => (a as any).stop());
  }, []);

  return (
    <View style={styles.typingRow}>
      {dots.map((d, i) => (
        <Animated.View key={i} style={[styles.typingDot, { opacity: d }]} />
      ))}
      <Text style={styles.typingLabel}>thinking</Text>
    </View>
  );
}

// ---------- SubagentCard ----------

function SubagentCard({ sub }: { sub: SubagentRun }) {
  const [expanded, setExpanded] = useState(false);
  const ended = sub.ended_ts != null;
  const color = TOOL_COLORS.Task;

  return (
    <View style={[styles.subagentCard, { borderLeftColor: color }]}>
      <TouchableOpacity
        style={styles.subagentHeader}
        onPress={() => { expand(); haptic(); setExpanded(!expanded); }}
        activeOpacity={0.6}
      >
        <View style={[styles.toolIcon, { backgroundColor: color + '22' }]}>
          <Text style={[styles.toolIconText, { color }]}>TSK</Text>
        </View>
        <View style={styles.toolHeaderText}>
          <Text style={styles.toolName}>Task · {sub.subagent_type}</Text>
          <Text style={styles.toolArgPreview} numberOfLines={1}>{sub.description}</Text>
        </View>
        {ended ? (
          <Text style={[styles.toolStatus, { color: colors.success }]}>done</Text>
        ) : (
          <View style={styles.toolPendingBadge}>
            <ActivityIndicator size="small" color={color} />
          </View>
        )}
        <Text style={styles.chevron}>{expanded ? '▾' : '▸'}</Text>
      </TouchableOpacity>

      {expanded && (
        <View style={styles.subagentBody}>
          {sub.messages.map(m => <MessageBubble key={m.id} msg={m} depth={1} />)}
          {sub.toolCalls.map(tc => <ToolCallCard key={tc.call_id} tc={tc} subagent />)}
        </View>
      )}
    </View>
  );
}

// ---------- TodoList ----------

const TODO_MARK = { pending: '○', in_progress: '◐', completed: '●' };
const TODO_COLOR = { pending: colors.textTertiary, in_progress: colors.accent, completed: colors.success };

export function TodoList({ todos }: { todos: Todo[] }) {
  if (todos.length === 0) return null;
  const completedCount = todos.filter(t => t.status === 'completed').length;
  return (
    <View style={styles.todoList}>
      <View style={styles.todoHeaderRow}>
        <Text style={styles.todoHeader}>Todos</Text>
        <Text style={styles.todoCount}>{completedCount}/{todos.length}</Text>
      </View>
      {todos.map((t, i) => (
        <View key={t.id || i} style={styles.todoRow}>
          <Text style={[styles.todoMark, { color: TODO_COLOR[t.status] }]}>{TODO_MARK[t.status]}</Text>
          <Text style={[styles.todoText, t.status === 'completed' && styles.todoTextDone]}>
            {t.content}
          </Text>
        </View>
      ))}
    </View>
  );
}

// ---------- QuestionCard (AskUserQuestion) ----------

export function QuestionCard({
  questions,
  onAnswer,
}: {
  questions: AskableQuestion[];
  onAnswer: (answers: UserAnswer[]) => void;
}) {
  const [selections, setSelections] = useState<Record<number, { label: string; custom?: string } | null>>({});

  const pick = (qi: number, label: string) => {
    expand();
    setSelections(s => ({ ...s, [qi]: { label } }));
  };

  const submit = () => {
    haptic();
    const answers: UserAnswer[] = questions.map((q, qi) => ({
      header: q.header,
      answer: selections[qi]?.label || '(no answer)',
    }));
    onAnswer(answers);
  };

  const allAnswered = questions.every((_, qi) => selections[qi]);

  return (
    <View style={styles.questionCard}>
      <View style={styles.questionHeaderRow}>
        <View style={[styles.toolIcon, { backgroundColor: TOOL_COLORS.AskUserQuestion + '22' }]}>
          <Text style={[styles.toolIconText, { color: TOOL_COLORS.AskUserQuestion }]}>?</Text>
        </View>
        <Text style={styles.questionHeader}>Questions for you</Text>
      </View>
      {questions.map((q, qi) => (
        <View key={qi} style={styles.questionBlock}>
          <Text style={styles.questionText}>{q.question}</Text>
          {q.header ? <Text style={styles.questionChip}>{q.header}</Text> : null}
          <View style={styles.optionList}>
            {q.options.map((opt, oi) => {
              const selected = selections[qi]?.label === opt.label;
              return (
                <TouchableOpacity
                  key={oi}
                  style={[styles.option, selected && styles.optionSelected, opt.recommended && !selected && styles.optionRecommended]}
                  onPress={() => pick(qi, opt.label)}
                  activeOpacity={0.6}
                >
                  <View style={styles.optionHeader}>
                    <Text style={[styles.optionLabel, selected && styles.optionLabelSelected]}>{opt.label}</Text>
                    {opt.recommended ? <Text style={styles.optionRecommendedTag}>recommended</Text> : null}
                  </View>
                  <Text style={styles.optionDesc} numberOfLines={3}>{opt.description}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>
      ))}
      <TouchableOpacity
        style={[styles.submitBtn, !allAnswered && styles.submitBtnDisabled]}
        onPress={submit}
        disabled={!allAnswered}
        activeOpacity={0.7}
      >
        <Text style={styles.submitBtnText}>Submit answer{questions.length > 1 ? 's' : ''}</Text>
      </TouchableOpacity>
    </View>
  );
}

// ---------- OutlineCard ----------

export function OutlineCard({
  documentType, sections, design,
}: {
  documentType: string;
  sections: { index: number; title: string; task_brief: string }[];
  design?: { style_name?: string; palette?: any; typography?: string; reference?: string };
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <View style={styles.outlineCard}>
      <TouchableOpacity style={styles.outlineHeader} onPress={() => { expand(); haptic(); setExpanded(!expanded); }} activeOpacity={0.6}>
        <View style={[styles.toolIcon, { backgroundColor: TOOL_COLORS.Outline + '22' }]}>
          <Text style={[styles.toolIconText, { color: TOOL_COLORS.Outline }]}>OL</Text>
        </View>
        <View style={styles.toolHeaderText}>
          <Text style={styles.toolName}>Outline · {documentType}</Text>
          <Text style={styles.toolArgPreview}>{sections.length} section(s)</Text>
        </View>
        <Text style={styles.chevron}>{expanded ? '▾' : '▸'}</Text>
      </TouchableOpacity>
      {expanded && (
        <View style={styles.outlineBody}>
          {design?.style_name && <Text style={styles.outlineMeta}>Style: {design.style_name}</Text>}
          {design?.typography && <Text style={styles.outlineMeta}>Type: {design.typography}</Text>}
          {design?.reference && <Text style={styles.outlineMeta}>Ref: {design.reference}</Text>}
          {sections.map(s => (
            <View key={s.index} style={styles.outlineSection}>
              <Text style={styles.outlineSectionTitle}>{s.index}. {s.title}</Text>
              <Text style={styles.outlineSectionBrief}>{s.task_brief}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

// ---------- CompleteCard ----------

export function CompleteCard({
  projectType, summary,
}: {
  projectType: string;
  summary: string;
}) {
  return (
    <View style={styles.completeCard}>
      <View style={[styles.toolIcon, { backgroundColor: TOOL_COLORS.Complete + '22' }]}>
        <Text style={[styles.toolIconText, { color: TOOL_COLORS.Complete }]}>✓</Text>
      </View>
      <View style={styles.toolHeaderText}>
        <Text style={styles.toolName}>Project complete · {projectType}</Text>
        <Text style={styles.completeSummary}>{summary}</Text>
      </View>
    </View>
  );
}

// ---------- ChatInput ----------

export function ChatInput({
  onSend, disabled, placeholder,
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  const [text, setText] = useState('');
  const [height, setHeight] = useState(44);
  const send = () => {
    const t = text.trim();
    if (!t || disabled) return;
    haptic();
    onSend(t);
    setText('');
    setHeight(44);
  };
  return (
    <View style={styles.inputBar}>
      <TextInput
        style={[styles.input, { height: Math.max(44, Math.min(120, height)) }]}
        value={text}
        onChangeText={setText}
        onContentSizeChange={(e) => setHeight(e.nativeEvent.contentSize.height + 20)}
        placeholder={placeholder || 'Message your agent…'}
        placeholderTextColor={colors.textTertiary}
        editable={!disabled}
        multiline
        maxLength={8000}
        onSubmitEditing={send}
        blurOnSubmit={false}
      />
      <TouchableOpacity
        style={[styles.sendBtn, (!text.trim() || disabled) && styles.sendBtnDisabled]}
        onPress={send}
        disabled={!text.trim() || disabled}
        activeOpacity={0.7}
      >
        <Text style={styles.sendBtnText}>↑</Text>
      </TouchableOpacity>
    </View>
  );
}

// ---------- StatusBar ----------

export function StatusBar({
  status, codespaceState,
}: {
  status: string;
  codespaceState?: string | null;
}) {
  const { color, label, pulse } = (() => {
    if (status === 'waking-codespace') return { color: colors.warning, label: `Starting runtime…`.trim(), pulse: true };
    if (status === 'connected') return { color: colors.success, label: 'Connected', pulse: false };
    if (status === 'connecting' || status === 'handshaking') return { color: colors.warning, label: 'Connecting…', pulse: true };
    if (status === 'reconnecting') return { color: colors.warning, label: 'Reconnecting…', pulse: true };
    if (status === 'error') return { color: colors.error, label: 'Connection error', pulse: false };
    return { color: colors.textTertiary, label: 'Disconnected', pulse: false };
  })();
  return (
    <View style={styles.statusBar}>
      <View style={[styles.statusDot, { backgroundColor: color }, pulse && styles.statusDotPulse]} />
      <Text style={styles.statusLabel} numberOfLines={1}>{label}</Text>
    </View>
  );
}

// ---------- Styles ----------

const styles = StyleSheet.create({
  userRow: { alignSelf: 'flex-end', maxWidth: '85%', marginVertical: spacing.xs },
  userBubble: { backgroundColor: colors.userBubble, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  userText: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.md, lineHeight: 22 },

  assistantRow: { alignSelf: 'flex-start', width: '100%', marginVertical: spacing.xs },
  assistantBubble: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.lg, gap: spacing.xs },
  assistantContent: { gap: spacing.xs },
  assistantText: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.md, lineHeight: 22 },

  codeBlock: { backgroundColor: '#0A0A0B', borderRadius: radius.md, padding: spacing.md, marginTop: spacing.xs, borderLeftWidth: 2, borderLeftColor: colors.borderSubtle },
  codeBlockText: { color: colors.textSecondary, fontFamily: typography.mono, fontSize: typography.size.xs, lineHeight: 18 },

  typingRow: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: spacing.xs },
  typingDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.accent, marginHorizontal: 1 },
  typingLabel: { color: colors.textTertiary, fontFamily: typography.sans, fontSize: typography.size.xs, fontStyle: 'italic', marginLeft: spacing.xs },

  toolCallList: { marginTop: spacing.sm, gap: spacing.xs },
  subagentList: { marginTop: spacing.sm, gap: spacing.xs },

  toolCard: { backgroundColor: colors.toolBg, borderRadius: radius.md, borderLeftWidth: 3, overflow: 'hidden' },
  toolCardSubagent: { backgroundColor: '#050506' },
  toolHeader: { flexDirection: 'row', alignItems: 'center', padding: spacing.sm, gap: spacing.sm },
  toolIcon: { width: 28, height: 28, borderRadius: radius.sm, alignItems: 'center', justifyContent: 'center' },
  toolIconText: { fontFamily: typography.mono, fontSize: 11, fontWeight: '700' },
  toolHeaderText: { flex: 1, gap: 2 },
  toolName: { color: colors.text, fontFamily: typography.mono, fontSize: typography.size.sm, fontWeight: '600' },
  toolArgPreview: { color: colors.textSecondary, fontFamily: typography.mono, fontSize: typography.size.xs, lineHeight: 16 },
  toolStatus: { fontFamily: typography.mono, fontSize: typography.size.xs, fontWeight: '600' },
  toolPendingBadge: { minWidth: 28, alignItems: 'center' },
  chevron: { color: colors.textTertiary, fontSize: typography.size.sm, marginLeft: spacing.xs },
  toolBody: { padding: spacing.sm, paddingTop: spacing.xs, borderTopWidth: 1, borderTopColor: colors.borderSubtle, marginTop: spacing.xs },
  toolOutput: { color: colors.textSecondary, fontFamily: typography.mono, fontSize: typography.size.xs, lineHeight: 18 },
  toolRunningRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  toolRunningText: { color: colors.textTertiary, fontFamily: typography.mono, fontSize: typography.size.xs },
  showMoreBtn: { marginTop: spacing.xs, paddingVertical: 2 },
  showMoreText: { color: colors.accent, fontFamily: typography.mono, fontSize: typography.size.xs, fontWeight: '600' },

  subagentCard: { backgroundColor: '#08080A', borderRadius: radius.md, borderLeftWidth: 3, overflow: 'hidden' },
  subagentHeader: { flexDirection: 'row', alignItems: 'center', padding: spacing.sm, gap: spacing.sm },
  subagentBody: { padding: spacing.sm, borderTopWidth: 1, borderTopColor: colors.borderSubtle, gap: spacing.xs },

  todoList: { backgroundColor: colors.surfaceAlt, borderRadius: radius.md, padding: spacing.md, marginVertical: spacing.sm, borderWidth: 1, borderColor: colors.border },
  todoHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.xs },
  todoHeader: { color: colors.textSecondary, fontFamily: typography.mono, fontSize: typography.size.xs, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 1 },
  todoCount: { color: colors.accent, fontFamily: typography.mono, fontSize: typography.size.xs, fontWeight: '600' },
  todoRow: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.sm, paddingVertical: 3 },
  todoMark: { fontFamily: typography.mono, fontSize: typography.size.md, lineHeight: 20 },
  todoText: { flex: 1, fontFamily: typography.sans, fontSize: typography.size.sm, lineHeight: 20, color: colors.text },
  todoTextDone: { color: colors.textTertiary, textDecorationLine: 'line-through' },

  questionCard: { backgroundColor: colors.surfaceAlt, borderRadius: radius.lg, padding: spacing.md, marginVertical: spacing.sm, borderWidth: 1, borderColor: TOOL_COLORS.AskUserQuestion + '44' },
  questionHeaderRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.sm },
  questionHeader: { color: TOOL_COLORS.AskUserQuestion, fontFamily: typography.mono, fontSize: typography.size.sm, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 },
  questionBlock: { marginBottom: spacing.md },
  questionText: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.md, fontWeight: '500', marginBottom: spacing.xs },
  questionChip: { alignSelf: 'flex-start', color: colors.textTertiary, fontFamily: typography.mono, fontSize: 10, paddingHorizontal: spacing.xs, paddingVertical: 2, borderRadius: 4, borderWidth: 1, borderColor: colors.border, marginBottom: spacing.sm },
  optionList: { gap: spacing.xs },
  option: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  optionSelected: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  optionRecommended: { borderColor: colors.textTertiary },
  optionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 },
  optionLabel: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.sm, fontWeight: '600' },
  optionLabelSelected: { color: colors.accent },
  optionRecommendedTag: { color: colors.textTertiary, fontFamily: typography.mono, fontSize: 9, textTransform: 'uppercase' },
  optionDesc: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.xs, lineHeight: 16 },
  submitBtn: { backgroundColor: colors.accent, borderRadius: radius.md, paddingVertical: spacing.md, alignItems: 'center', marginTop: spacing.sm },
  submitBtnDisabled: { backgroundColor: colors.surfaceHover },
  submitBtnText: { color: '#fff', fontFamily: typography.sans, fontSize: typography.size.md, fontWeight: '600' },

  outlineCard: { backgroundColor: colors.toolBg, borderRadius: radius.md, borderLeftWidth: 3, borderLeftColor: TOOL_COLORS.Outline, overflow: 'hidden', marginVertical: spacing.xs },
  outlineHeader: { flexDirection: 'row', alignItems: 'center', padding: spacing.sm, gap: spacing.sm },
  outlineBody: { padding: spacing.sm, borderTopWidth: 1, borderTopColor: colors.borderSubtle, gap: spacing.sm },
  outlineMeta: { color: colors.textTertiary, fontFamily: typography.mono, fontSize: typography.size.xs },
  outlineSection: { paddingLeft: spacing.sm, borderLeftWidth: 2, borderLeftColor: colors.border },
  outlineSectionTitle: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.sm, fontWeight: '600' },
  outlineSectionBrief: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.xs, lineHeight: 16, marginTop: 2 },

  completeCard: { backgroundColor: TOOL_COLORS.Complete + '11', borderRadius: radius.md, padding: spacing.md, flexDirection: 'row', alignItems: 'center', gap: spacing.sm, borderWidth: 1, borderColor: TOOL_COLORS.Complete + '33', marginVertical: spacing.xs },
  completeSummary: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.sm, lineHeight: 18, marginTop: 2 },

  inputBar: { flexDirection: 'row', alignItems: 'flex-end', gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border },
  input: { flex: 1, backgroundColor: colors.bg, borderRadius: radius.lg, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, color: colors.text, fontFamily: typography.sans, fontSize: typography.size.md, borderWidth: 1, borderColor: colors.border },
  sendBtn: { width: 44, height: 44, borderRadius: radius.pill, backgroundColor: colors.accent, alignItems: 'center', justifyContent: 'center' },
  sendBtnDisabled: { backgroundColor: colors.surfaceHover },
  sendBtnText: { color: '#fff', fontSize: 20, fontWeight: '700' },

  statusBar: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, paddingHorizontal: spacing.md, paddingVertical: spacing.xs, backgroundColor: colors.surfaceAlt, borderBottomWidth: 1, borderBottomColor: colors.border },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  statusDotPulse: { shadowColor: colors.warning, shadowOpacity: 0.8, shadowRadius: 6, shadowOffset: { width: 0, height: 0 }, elevation: 4 },
  statusLabel: { color: colors.textSecondary, fontFamily: typography.mono, fontSize: typography.size.xs, flex: 1 },
});
