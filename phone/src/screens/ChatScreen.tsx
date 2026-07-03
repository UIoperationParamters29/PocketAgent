/**
 * ChatScreen — the main PocketAgent UI.
 *
 * Architecture v0.5: the agent runtime runs in Termux ON THE PHONE.
 * The APK is a thin UI that connects to ws://127.0.0.1:8080/agent.
 * No codespaces, no cloud, no CC, no egress issues.
 *
 * If the runtime isn't running, show setup instructions.
 */

import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator, Alert, Linking,
} from 'react-native';
import { colors, spacing, radius, typography } from '../theme/colors';
import { useStore } from '../state/store';
import { useAgentSession } from '../hooks/useAgentSession';
import {
  MessageBubble, ChatInput, TodoList, QuestionCard, OutlineCard, CompleteCard, StatusBar,
} from '../components';
import { ChatMessage } from '../lib/types';
import { loadSessionConfig } from '../lib/secure-store';

const RUNTIME_URL = 'http://127.0.0.1:8080';

export function ChatScreen() {
  const store = useStore();
  const session = useAgentSession();
  const flatListRef = useRef<FlatList<ChatMessage>>(null);
  const [checking, setChecking] = useState(false);
  const [runtimeUp, setRuntimeUp] = useState<boolean | null>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (store.messages.length > 0) {
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 50);
    }
  }, [store.messages.length, store.streamingText]);

  // Check if the Termux runtime is running
  const checkRuntime = useCallback(async () => {
    setChecking(true);
    try {
      const r = await fetch(`${RUNTIME_URL}/`, { method: 'GET' });
      if (r.ok) {
        const data = await r.json();
        if (data.name === 'PocketAgent Runtime') {
          setRuntimeUp(true);
          store.setCodespace('Available', 'termux', RUNTIME_URL);
          return true;
        }
      }
      setRuntimeUp(false);
      return false;
    } catch (e) {
      setRuntimeUp(false);
      return false;
    } finally {
      setChecking(false);
    }
  }, [store]);

  // Check on mount
  useEffect(() => {
    checkRuntime();
  }, [checkRuntime]);

  // Connect to the runtime
  const connect = useCallback(async () => {
    const cfg = await loadSessionConfig();
    if (!cfg) {
      Alert.alert('No LLM config', 'Complete onboarding first to set your LLM provider + key.');
      return;
    }
    store.setCodespace('Available', 'termux', RUNTIME_URL);
    await session.connect();
  }, [session, store]);

  const onSend = useCallback((text: string) => {
    session.sendMessage(text);
  }, [session]);

  const onAnswer = useCallback((answers: any[]) => {
    if (store.pendingQuestion) {
      session.answerQuestion(store.pendingQuestion.question_id, answers);
    }
  }, [session, store.pendingQuestion]);

  const isConnected = store.connStatus === 'connected';

  // ---- Runtime not running — show setup instructions ----
  if (runtimeUp === false) {
    return (
      <View style={styles.container}>
        <View style={styles.topBar}>
          <Text style={styles.brand}>PocketAgent</Text>
        </View>
        <View style={styles.setupContainer}>
          <View style={styles.setupLogo}>
            <Text style={styles.setupLogoText}>P</Text>
          </View>
          <Text style={styles.setupTitle}>Runtime not detected</Text>
          <Text style={styles.setupDesc}>
            PocketAgent needs the Termux runtime running on your phone. Setup takes 2 minutes:
          </Text>

          <View style={styles.stepsContainer}>
            <Text style={styles.stepTitle}>1. Install Termux</Text>
            <Text style={styles.stepDesc}>
              Download from F-Droid (not Play Store — the Play Store version is outdated):
            </Text>
            <TouchableOpacity onPress={() => Linking.openURL('https://f-droid.org/packages/com.termux/')}>
              <Text style={styles.link}>https://f-droid.org/packages/com.termux/</Text>
            </TouchableOpacity>

            <Text style={[styles.stepTitle, { marginTop: spacing.md }]}>2. Open Termux, run:</Text>
            <View style={styles.codeBlock}>
              <Text style={styles.codeText} selectable>pkg install python git ripgrep -y{'\n'}pip install pocketagent-runtime{'\n'}pocketagent-start</Text>
            </View>

            <Text style={[styles.stepTitle, { marginTop: spacing.md }]}>3. Come back here</Text>
            <Text style={styles.stepDesc}>Tap "Check again" once the runtime is running.</Text>
          </View>

          <TouchableOpacity
            style={styles.checkBtn}
            onPress={checkRuntime}
            disabled={checking}
            activeOpacity={0.7}
          >
            {checking ? <ActivityIndicator color="#fff" /> : <Text style={styles.checkBtnText}>Check again</Text>}
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  // ---- Runtime is up — show the chat ----
  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.topBar}>
        <Text style={styles.brand}>PocketAgent</Text>
        <View style={styles.topActions}>
          <View style={styles.csBadge}>
            <View style={[styles.csDot, { backgroundColor: isConnected ? colors.success : (runtimeUp ? colors.warning : colors.textTertiary) }]} />
            <Text style={styles.csBadgeText}>{runtimeUp ? (isConnected ? 'connected' : 'runtime up') : 'no runtime'}</Text>
          </View>
          {!isConnected && runtimeUp && (
            <TouchableOpacity style={styles.wakeBtn} onPress={connect}>
              <Text style={styles.wakeBtnText}>Connect</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>

      <StatusBar status={store.connStatus} codespaceState={store.codespaceState} />

      {store.connStatus === 'error' && store.lastError && (
        <TouchableOpacity
          style={styles.errorBanner}
          onPress={() => Alert.alert('Connection error', store.lastError + '\n\nMake sure Termux is running: pocketagent-start')}
        >
          <Text style={styles.errorBannerText} numberOfLines={3}>⚠️ {store.lastError}</Text>
          <Text style={styles.errorBannerHint}>Tap for help →</Text>
        </TouchableOpacity>
      )}

      {/* Side cards */}
      <View style={styles.sideCards}>
        {store.todos.length > 0 && <TodoList todos={store.todos} />}
        {store.outline && (
          <OutlineCard documentType={store.outline.document_type} sections={store.outline.sections} design={store.outline.design} />
        )}
        {store.completion && (
          <CompleteCard projectType={store.completion.project_type} summary={store.completion.summary} />
        )}
      </View>

      <FlatList
        ref={flatListRef}
        data={store.messages}
        keyExtractor={(m) => m.id}
        renderItem={({ item }) => <MessageBubble msg={item} />}
        contentContainerStyle={styles.chatList}
        onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: false })}
        ListEmptyComponent={
          <View style={styles.empty}>
            <View style={styles.emptyLogo}>
              <Text style={styles.emptyLogoText}>P</Text>
            </View>
            <Text style={styles.emptyTitle}>Your agent is ready</Text>
            <Text style={styles.emptyDesc}>
              Tell it what you need. It has its own Linux computer (Termux) — it can run scripts, install tools, read & write files, and ship deliverables.
            </Text>
            <View style={styles.emptyHints}>
              <Text style={styles.emptyHint}>·  Try: "make a bar chart of my sales"</Text>
              <Text style={styles.emptyHint}>·  Try: "list what's in my workspace"</Text>
              <Text style={styles.emptyHint}>·  Try: "write a Python script that..."</Text>
            </View>
          </View>
        }
      />

      {store.pendingQuestion && (
        <View style={styles.questionOverlay}>
          <QuestionCard questions={store.pendingQuestion.questions} onAnswer={onAnswer} />
        </View>
      )}

      <ChatInput
        onSend={onSend}
        disabled={!isConnected || store.isAgentBusy || !!store.pendingQuestion}
        placeholder={isConnected ? (store.isAgentBusy ? 'Agent is working…' : 'Message your agent…') : 'Tap Connect first'}
      />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: spacing.md, paddingTop: spacing.xl + spacing.sm, paddingBottom: spacing.sm, backgroundColor: colors.bg },
  brand: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.lg, fontWeight: '700' },
  topActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  csBadge: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, backgroundColor: colors.surfaceAlt, paddingHorizontal: spacing.md, paddingVertical: spacing.xs, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border },
  csDot: { width: 8, height: 8, borderRadius: 4 },
  csBadgeText: { color: colors.textSecondary, fontFamily: typography.mono, fontSize: typography.size.xs },
  wakeBtn: { backgroundColor: colors.accent, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.pill },
  wakeBtnText: { color: '#fff', fontFamily: typography.sans, fontSize: typography.size.sm, fontWeight: '600' },
  chatList: { padding: spacing.md, paddingTop: spacing.sm },
  empty: { padding: spacing.xl, alignItems: 'center', gap: spacing.sm, marginTop: spacing.xl * 2 },
  emptyLogo: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.accent, alignItems: 'center', justifyContent: 'center', marginBottom: spacing.md },
  emptyLogoText: { color: '#fff', fontFamily: typography.sans, fontSize: 32, fontWeight: '800' },
  emptyTitle: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.lg, fontWeight: '600' },
  emptyDesc: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.sm, lineHeight: 20, textAlign: 'center', maxWidth: 300 },
  emptyHints: { marginTop: spacing.lg, gap: spacing.xs, alignSelf: 'stretch' },
  emptyHint: { color: colors.textTertiary, fontFamily: typography.mono, fontSize: typography.size.xs, textAlign: 'center' },
  questionOverlay: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, backgroundColor: colors.bg, borderTopWidth: 1, borderTopColor: colors.border },
  sideCards: { paddingHorizontal: spacing.md, paddingVertical: spacing.xs, gap: spacing.xs },
  errorBanner: { backgroundColor: colors.errorSoft, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.error + '33' },
  errorBannerText: { color: colors.error, fontFamily: typography.sans, fontSize: typography.size.xs, lineHeight: 16 },
  errorBannerHint: { color: colors.accent, fontFamily: typography.mono, fontSize: 10, marginTop: 2 },

  // Setup screen
  setupContainer: { flex: 1, padding: spacing.xl, alignItems: 'center' },
  setupLogo: { width: 80, height: 80, borderRadius: 20, backgroundColor: colors.accent, alignItems: 'center', justifyContent: 'center', marginBottom: spacing.lg, marginTop: spacing.xl },
  setupLogoText: { color: '#fff', fontFamily: typography.sans, fontSize: 44, fontWeight: '800' },
  setupTitle: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.xl, fontWeight: '700', marginBottom: spacing.sm },
  setupDesc: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.sm, lineHeight: 20, textAlign: 'center', marginBottom: spacing.xl },
  stepsContainer: { width: '100%', backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border },
  stepTitle: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.md, fontWeight: '600', marginBottom: spacing.xs },
  stepDesc: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.sm, lineHeight: 18, marginBottom: spacing.xs },
  link: { color: colors.accent, fontFamily: typography.mono, fontSize: typography.size.xs, marginBottom: spacing.sm },
  codeBlock: { backgroundColor: colors.bg, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.xs, borderWidth: 1, borderColor: colors.border },
  codeText: { color: colors.accent, fontFamily: typography.mono, fontSize: typography.size.xs, lineHeight: 20 },
  checkBtn: { backgroundColor: colors.accent, borderRadius: radius.md, paddingVertical: spacing.md, alignItems: 'center', marginTop: spacing.xl, width: '100%' },
  checkBtnText: { color: '#fff', fontFamily: typography.sans, fontSize: typography.size.md, fontWeight: '600' },
});
