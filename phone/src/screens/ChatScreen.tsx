/**
 * ChatScreen — the main PocketAgent UI.
 *
 * Top bar: codespace wake/sleep control + connection status.
 * Middle: chat history (FlatList, inverted-ish for chat UX).
 * Bottom: ChatInput.
 *
 * Side cards render inline in the message stream:
 *   - TodoList (sticky above chat)
 *   - QuestionCard (when pendingQuestion is set)
 *   - OutlineCard (when outline is set)
 *   - CompleteCard (when completion is set)
 */

import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator, Alert,
} from 'react-native';
import { colors, spacing, radius, typography } from '../theme/colors';
import { useStore } from '../state/store';
import { useAgentSession } from '../hooks/useAgentSession';
import {
  MessageBubble, ChatInput, TodoList, QuestionCard, OutlineCard, CompleteCard, StatusBar,
} from '../components';
import { ChatMessage } from '../lib/types';
import {
  loadGithubPat, loadCodespaceName, saveCodespaceName,
} from '../lib/secure-store';
import { getCodespace, startCodespace, stopCodespace, waitUntilAvailable, listCodespaces, createCodespace } from '../lib/codespaces';

export function ChatScreen() {
  const store = useStore();
  const session = useAgentSession();
  const flatListRef = useRef<FlatList<ChatMessage>>(null);
  const [waking, setWaking] = useState(false);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (store.messages.length > 0) {
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 50);
    }
  }, [store.messages.length, store.streamingText]);

  const wakeCodespace = useCallback(async () => {
    if (waking) return;
    setWaking(true);
    store.setConnStatus('waking-codespace');
    try {
      const pat = await loadGithubPat();
      if (!pat || !pat.trim()) {
        Alert.alert(
          'No GitHub PAT',
          'Go to Settings → GitHub PAT and paste a Personal Access Token with the repo, codespace, workflow scopes.',
          [{ text: 'OK' }]
        );
        return;
      }

      let name = await loadCodespaceName();
      if (!name) {
        // List codespaces; if any exist, use the first PocketAgent one (or the first overall)
        let list;
        try {
          list = await listCodespaces(pat);
        } catch (e: any) {
          Alert.alert(
            'GitHub API error',
            `Couldn't list your codespaces: ${e.message}\n\nCheck that your PAT has the 'codespace' scope.`,
            [{ text: 'OK' }]
          );
          return;
        }
        if (list.length === 0) {
          // No codespace exists — offer to create one
          Alert.alert(
            'No codespace yet',
            'You don\'t have any codespaces. PocketAgent can create one for you from the PocketAgent repo.',
            [
              { text: 'Cancel', style: 'cancel' },
              { text: 'Create it', onPress: async () => {
                try {
                  store.setCodespace('Provisioning', null, null);
                  const cs = await createCodespace(pat, 'UIoperationParamters29/PocketAgent');
                  await saveCodespaceName(cs.name);
                  store.setCodespace(cs.state, cs.name, null);
                  // Continue with the wake flow
                  setTimeout(() => wakeCodespace(), 500);
                } catch (e: any) {
                  Alert.alert('Create failed', e.message);
                  store.setConnStatus('error');
                }
              }},
            ]
          );
          return;
        }
        name = list[0].name;
        await saveCodespaceName(name);
      }
      store.setCodespace(null, name, null);

      // Check state; start if stopped
      let status;
      try {
        status = await getCodespace(pat, name);
      } catch (e: any) {
        Alert.alert(
          'Codespace not found',
          `Couldn't find codespace "${name}": ${e.message}\n\nGo to Settings → Codespace name and clear it to re-detect, or create a new one on github.com/codespaces.`,
          [{ text: 'OK' }]
        );
        return;
      }
      store.setCodespace(status.state, name, null);
      if (status.state !== 'Available') {
        try {
          await startCodespace(pat, name);
        } catch (e: any) {
          Alert.alert('Start failed', `Couldn't start codespace: ${e.message}`);
          return;
        }
      }

      // Wait for Available + derive runtime URL
      let result;
      try {
        result = await waitUntilAvailable(pat, name, {
          timeoutMs: 240_000,
          intervalMs: 3_000,
          onPoll: (s) => store.setCodespace(s, name, null),
        });
      } catch (e: any) {
        Alert.alert(
          'Codespace timeout',
          `Codespace didn't become Available in time: ${e.message}\n\nIt may still be provisioning. Try Wake again in a minute, or open it once at github.com/codespaces to speed things up.`,
          [{ text: 'OK' }]
        );
        return;
      }
      store.setCodespace('Available', name, result.runtime_url);

      // Now connect the WS
      const ok = await session.connect();
      if (!ok) {
        // session.connect already set the error message
        Alert.alert(
          'Connect failed',
          'Codespace is up but the WebSocket connection failed. Make sure:\n• The codespace was opened in a browser at least once (to register the port forward)\n• PA_CHANNEL_SECRET matches between the app and your Codespaces secrets\n• The runtime is running inside the codespace (open the codespace, check the terminal)',
          [{ text: 'OK' }]
        );
      }
    } catch (e: any) {
      Alert.alert('Wake failed', `${e.message || e}`);
      store.setConnStatus('error');
    } finally {
      setWaking(false);
    }
  }, [waking, store, session]);

  const sleepCodespace = useCallback(async () => {
    const pat = await loadGithubPat();
    const name = await loadCodespaceName();
    if (!pat || !name) return;
    Alert.alert('Stop codespace?', 'The codespace will keep its 15GB of storage but stop consuming your free core-hours.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Stop', style: 'destructive', onPress: async () => {
        session.disconnect();
        try { await stopCodespace(pat, name); store.setCodespace('Stopped', name, null); } catch (e: any) { Alert.alert('Stop failed', e.message); }
      } },
    ]);
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

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      {/* Top bar */}
      <View style={styles.topBar}>
        <Text style={styles.brand}>PocketAgent</Text>
        <View style={styles.topActions}>
          {store.codespaceName ? (
            <TouchableOpacity style={styles.csBadge} onPress={isConnected ? sleepCodespace : wakeCodespace} disabled={waking}>
              {waking ? (
                <ActivityIndicator size="small" color={colors.warning} />
              ) : (
                <View style={[styles.csDot, { backgroundColor: isConnected ? colors.success : colors.warning }]} />
              )}
              <Text style={styles.csBadgeText}>{store.codespaceState || '—'}</Text>
            </TouchableOpacity>
          ) : null}
          {!isConnected && !waking && (
            <TouchableOpacity style={styles.wakeBtn} onPress={wakeCodespace}>
              <Text style={styles.wakeBtnText}>Wake</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>

      <StatusBar status={store.connStatus} codespaceState={store.codespaceState} />

      {/* Error banner — shows the actual error when connection fails */}
      {store.connStatus === 'error' && store.lastError && (
        <TouchableOpacity
          style={styles.errorBanner}
          onPress={() => Alert.alert('Connection error', store.lastError + '\n\nCommon fixes:\n1. Open the codespace once at github.com/codespaces (registers the port forward)\n2. In the codespace terminal, run: curl http://localhost:8000/ — if it fails, the runtime isn\'t running. Run: bash /workspaces/PocketAgent/cloud/.devcontainer/start-runtime.sh\n3. If the channel secret doesn\'t match: clear it in Settings → Channel secret (use open mode), OR stop+start the codespace after setting the secret')}
        >
          <Text style={styles.errorBannerText} numberOfLines={3}>⚠️ {store.lastError}</Text>
          <Text style={styles.errorBannerHint}>Tap for help →</Text>
        </TouchableOpacity>
      )}

      {/* Side cards (todos, outline, completion) */}
      <View style={styles.sideCards}>
        {store.todos.length > 0 && <TodoList todos={store.todos} />}
        {store.outline && (
          <OutlineCard
            documentType={store.outline.document_type}
            sections={store.outline.sections}
            design={store.outline.design}
          />
        )}
        {store.completion && (
          <CompleteCard
            projectType={store.completion.project_type}
            summary={store.completion.summary}
          />
        )}
      </View>

      {/* Chat history */}
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
              Tell it what you need. It has its own Linux computer — it can run scripts, install tools, read & write files, and ship deliverables to download/.
            </Text>
            <View style={styles.emptyHints}>
              <Text style={styles.emptyHint}>·  Try: "make a bar chart of my sales"</Text>
              <Text style={styles.emptyHint}>·  Try: "search the web for X"</Text>
              <Text style={styles.emptyHint}>·  Try: "generate an image of Y"</Text>
            </View>
          </View>
        }
      />

      {/* Pending question */}
      {store.pendingQuestion && (
        <View style={styles.questionOverlay}>
          <QuestionCard
            questions={store.pendingQuestion.questions}
            onAnswer={onAnswer}
          />
        </View>
      )}

      {/* Input */}
      <ChatInput
        onSend={onSend}
        disabled={!isConnected || store.isAgentBusy || !!store.pendingQuestion}
        placeholder={isConnected ? (store.isAgentBusy ? 'Agent is working…' : 'Message your agent…') : 'Wake the codespace first'}
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
});
