/**
 * Onboarding screen — first-run setup.
 * Collects: GitHub PAT, channel secret, BYOK LLM config (provider/key/model).
 * Now with: model auto-fetch, LLM connection test, auto-create codespace.
 */

import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView, Alert, Linking, ActivityIndicator, Modal, FlatList,
} from 'react-native';
import { colors, spacing, radius, typography } from '../theme/colors';
import { PROVIDER_PRESETS, ProviderPreset, saveChannelSecret, saveGithubPat, saveSessionConfig, saveCodespaceName, setOnboarded } from '../lib/secure-store';
import { verifyPat, createCodespace, waitUntilAvailable } from '../lib/codespaces';
import { fetchModels, verifyLlmConfig, ModelInfo } from '../lib/llm';
import { SessionConfig } from '../lib/types';

export function OnboardingScreen({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState<0 | 1 | 2>(0);
  const [pat, setPat] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [patError, setPatError] = useState<string | null>(null);

  const [channelSecret, setChannelSecret] = useState('');
  const [preset, setPreset] = useState<ProviderPreset>(PROVIDER_PRESETS[0]);
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState(PROVIDER_PRESETS[0].default_model);
  const [baseUrl, setBaseUrl] = useState(PROVIDER_PRESETS[0].base_url);
  const [saving, setSaving] = useState(false);

  // Model fetching
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [modelFetchError, setModelFetchError] = useState<string | null>(null);

  // LLM connection test
  const [testingLlm, setTestingLlm] = useState(false);
  const [llmTestResult, setLlmTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  // Auto-create codespace
  const [createCs, setCreateCs] = useState(true);
  const [creatingCs, setCreatingCs] = useState(false);

  // ---- Step 0: GitHub PAT ----
  const verifyAndContinue = async () => {
    setVerifying(true);
    setPatError(null);
    try {
      const info = await verifyPat(pat.trim());
      if (!info.ok) {
        setPatError(`Missing scopes: ${info.missing.join(', ')}. Edit your PAT at github.com/settings/tokens to add them.`);
        return;
      }
      setStep(1);
    } catch (e: any) {
      setPatError(e.message || 'Verification failed');
    } finally {
      setVerifying(false);
    }
  };

  // ---- Step 1: BYOK + channel secret + codespace ----
  const pickPreset = (p: ProviderPreset) => {
    setPreset(p);
    if (p.id !== 'custom') {
      setBaseUrl(p.base_url);
      setModel(p.default_model);
    }
    // Reset state when preset changes
    setModels([]);
    setLlmTestResult(null);
    setModelFetchError(null);
  };

  const generateSecret = () => {
    const chars = '0123456789abcdef';
    let s = '';
    for (let i = 0; i < 32; i++) s += chars[Math.floor(Math.random() * 16)];
    setChannelSecret(s);
  };

  const doFetchModels = async () => {
    setFetchingModels(true);
    setModelFetchError(null);
    try {
      const list = await fetchModels(baseUrl, apiKey);
      setModels(list);
      if (list.length > 0) {
        setShowModelPicker(true);
      } else {
        setModelFetchError('Provider returned 0 models. Enter the model name manually.');
      }
    } catch (e: any) {
      setModelFetchError(e.message);
    } finally {
      setFetchingModels(false);
    }
  };

  const doTestLlm = async () => {
    setTestingLlm(true);
    setLlmTestResult(null);
    try {
      const result = await verifyLlmConfig(baseUrl, apiKey, model);
      if (result.ok) {
        setLlmTestResult({ ok: true, message: `✓ Connected. Reply: ${result.reply?.slice(0, 50) || '(empty)'}` });
      } else {
        setLlmTestResult({ ok: false, message: `✗ ${result.error}` });
      }
    } catch (e: any) {
      setLlmTestResult({ ok: false, message: e.message });
    } finally {
      setTestingLlm(false);
    }
  };

  const finish = async () => {
    if (!channelSecret) { Alert.alert('Missing channel secret', 'Generate one or paste the one your codespace was started with.'); return; }
    if (!apiKey && preset.id !== 'ollama') { Alert.alert('Missing API key', 'Paste your LLM provider API key.'); return; }
    if (!baseUrl) { Alert.alert('Missing base URL', 'Set the OpenAI-compatible base URL for your provider.'); return; }
    if (!model) { Alert.alert('Missing model', 'Set the model name to use.'); return; }

    setSaving(true);
    try {
      const cfg: SessionConfig = { base_url: baseUrl, api_key: apiKey || 'ollama', model };
      await saveGithubPat(pat.trim());
      await saveChannelSecret(channelSecret);
      await saveSessionConfig(cfg);

      // Optionally auto-create the codespace
      if (createCs) {
        setCreatingCs(true);
        try {
          const cs = await createCodespace(pat.trim(), 'UIoperationParamters29/PocketAgent');
          await saveCodespaceName(cs.name);
          // Wait for it to be Available (so the user doesn't have to)
          try {
            const result = await waitUntilAvailable(pat.trim(), cs.name, {
              timeoutMs: 240_000,
              intervalMs: 4_000,
            });
            // Don't store the runtime URL here — the ChatScreen's Wake will derive it
          } catch (e: any) {
            // Codespace created but didn't become Available in time — that's OK,
            // user can tap Wake later.
            Alert.alert('Codespace created', `Name: ${cs.name}. It's still provisioning — tap Wake on the next screen in a minute.`);
          }
        } catch (e: any) {
          Alert.alert('Codespace creation failed', `${e.message}\n\nYou can create one manually on github.com/codespaces.`);
        } finally {
          setCreatingCs(false);
        }
      }

      await setOnboarded();
      onDone();
    } catch (e: any) {
      Alert.alert('Save failed', e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <View style={styles.logoWrap}>
          <View style={styles.logo}>
            <Text style={styles.logoText}>P</Text>
          </View>
        </View>
        <Text style={styles.title}>PocketAgent</Text>
        <Text style={styles.subtitle}>Your AI agent, with its own computer, on your phone.</Text>

        <View style={styles.progress}>
          {[0, 1].map(i => (
            <View key={i} style={[styles.progressDot, step >= i && styles.progressDotActive]} />
          ))}
        </View>

        {step === 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>1. GitHub Token</Text>
            <Text style={styles.sectionDesc}>
              PocketAgent uses GitHub Codespaces as the agent's "own computer." Create a Personal Access Token with the
              <Text style={styles.code}> repo, codespace, workflow</Text> scopes.
            </Text>
            <TouchableOpacity onPress={() => Linking.openURL('https://github.com/settings/tokens/new?scopes=repo,codespace,workflow')}>
              <Text style={styles.link}>Open github.com/settings/tokens →</Text>
            </TouchableOpacity>
            <TextInput
              style={styles.input}
              value={pat}
              onChangeText={setPat}
              placeholder="ghp_..."
              placeholderTextColor={colors.textTertiary}
              autoCapitalize="none"
              autoCorrect={false}
              secureTextEntry
            />
            {patError && <Text style={styles.error}>{patError}</Text>}
            <TouchableOpacity
              style={[styles.btn, !pat.trim() && styles.btnDisabled]}
              onPress={verifyAndContinue}
              disabled={!pat.trim() || verifying}
              activeOpacity={0.7}
            >
              {verifying ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.btnText}>Verify & continue</Text>
              )}
            </TouchableOpacity>
          </View>
        )}

        {step === 1 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>2. Connect your LLM</Text>
            <Text style={styles.sectionDesc}>Bring your own key. PocketAgent works with any OpenAI-compatible provider.</Text>

            <Text style={styles.label}>Provider</Text>
            <View style={styles.presetGrid}>
              {PROVIDER_PRESETS.map(p => (
                <TouchableOpacity
                  key={p.id}
                  style={[styles.presetChip, preset.id === p.id && styles.presetChipActive]}
                  onPress={() => pickPreset(p)}
                >
                  <Text style={[styles.presetChipText, preset.id === p.id && styles.presetChipTextActive]}>{p.label}</Text>
                </TouchableOpacity>
              ))}
            </View>

            {preset.signup_url ? (
              <TouchableOpacity onPress={() => Linking.openURL(preset.signup_url)}>
                <Text style={styles.link}>Get a {preset.label} API key →</Text>
              </TouchableOpacity>
            ) : null}

            <Text style={styles.label}>API key</Text>
            <TextInput
              style={styles.input}
              value={apiKey}
              onChangeText={(v) => { setApiKey(v); setLlmTestResult(null); setModels([]); }}
              placeholder={preset.key_prefix || 'sk-...'}
              placeholderTextColor={colors.textTertiary}
              autoCapitalize="none"
              autoCorrect={false}
              secureTextEntry
            />

            <Text style={styles.label}>Base URL</Text>
            <TextInput
              style={styles.input}
              value={baseUrl}
              onChangeText={(v) => { setBaseUrl(v); setLlmTestResult(null); setModels([]); }}
              placeholder="https://api.openai.com/v1"
              placeholderTextColor={colors.textTertiary}
              autoCapitalize="none"
              autoCorrect={false}
            />

            <Text style={styles.label}>Model</Text>
            <View style={styles.modelRow}>
              <TextInput
                style={[styles.input, { flex: 1 }]}
                value={model}
                onChangeText={setModel}
                placeholder="gpt-4o-mini"
                placeholderTextColor={colors.textTertiary}
                autoCapitalize="none"
                autoCorrect={false}
              />
              <TouchableOpacity
                style={[styles.fetchBtn, (!baseUrl || !apiKey || fetchingModels) && styles.btnDisabled]}
                onPress={doFetchModels}
                disabled={!baseUrl || !apiKey || fetchingModels}
              >
                {fetchingModels ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.fetchBtnText}>Fetch</Text>}
              </TouchableOpacity>
            </View>
            {modelFetchError && <Text style={styles.error}>{modelFetchError}</Text>}
            {models.length > 0 && (
              <Text style={styles.hint}>{models.length} models fetched — tap Fetch again to pick</Text>
            )}

            {/* Test connection */}
            <TouchableOpacity
              style={[styles.testBtn, (!baseUrl || !apiKey || !model || testingLlm) && styles.btnDisabled]}
              onPress={doTestLlm}
              disabled={!baseUrl || !apiKey || !model || testingLlm}
            >
              {testingLlm ? <ActivityIndicator color={colors.accent} /> : <Text style={styles.testBtnText}>Test connection</Text>}
            </TouchableOpacity>
            {llmTestResult && (
              <Text style={[styles.testResult, llmTestResult.ok ? styles.testOk : styles.testFail]}>
                {llmTestResult.message}
              </Text>
            )}

            <Text style={styles.label}>Channel secret (PA_CHANNEL_SECRET)</Text>
            <Text style={styles.sectionDesc}>A shared secret between your phone and the codespace runtime. Generate one now, then set the same value as <Text style={styles.code}>PA_CHANNEL_SECRET</Text> in your Codespaces secrets at github.com/settings/codespaces.</Text>
            <View style={styles.secretRow}>
              <TextInput
                style={[styles.input, { flex: 1 }]}
                value={channelSecret}
                onChangeText={setChannelSecret}
                placeholder="32-char hex secret"
                placeholderTextColor={colors.textTertiary}
                autoCapitalize="none"
                autoCorrect={false}
              />
              <TouchableOpacity style={styles.genBtn} onPress={generateSecret}>
                <Text style={styles.genBtnText}>Generate</Text>
              </TouchableOpacity>
            </View>

            {/* Auto-create codespace */}
            <TouchableOpacity style={styles.checkboxRow} onPress={() => setCreateCs(!createCs)}>
              <View style={[styles.checkbox, createCs && styles.checkboxChecked]} />
              <Text style={styles.checkboxLabel}>Auto-create PocketAgent codespace now</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.btn, (saving || creatingCs) && styles.btnDisabled]}
              onPress={finish}
              disabled={saving || creatingCs}
              activeOpacity={0.7}
            >
              {saving || creatingCs ? (
                <View style={styles.btnLoadingRow}>
                  <ActivityIndicator color="#fff" />
                  <Text style={styles.btnText}>{creatingCs ? 'Creating codespace…' : 'Saving…'}</Text>
                </View>
              ) : (
                <Text style={styles.btnText}>Finish setup</Text>
              )}
            </TouchableOpacity>

            <TouchableOpacity onPress={() => setStep(0)}>
              <Text style={styles.backLink}>← Back</Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>

      {/* Model picker modal */}
      <Modal visible={showModelPicker} animationType="slide" transparent={true} onRequestClose={() => setShowModelPicker(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Pick a model ({models.length})</Text>
            <FlatList
              data={models}
              keyExtractor={(m) => m.id}
              renderItem={({ item }) => (
                <TouchableOpacity
                  style={[styles.modelItem, item.id === model && styles.modelItemSelected]}
                  onPress={() => { setModel(item.id); setShowModelPicker(false); setLlmTestResult(null); }}
                >
                  <Text style={styles.modelItemId}>{item.id}</Text>
                  {item.label && item.label !== item.id ? <Text style={styles.modelItemLabel}>{item.label}</Text> : null}
                  {item.context_window ? <Text style={styles.modelItemCtx}>{(item.context_window / 1000).toFixed(0)}K ctx</Text> : null}
                </TouchableOpacity>
              )}
              style={{ maxHeight: 400 }}
            />
            <TouchableOpacity style={styles.modalClose} onPress={() => setShowModelPicker(false)}>
              <Text style={styles.modalCloseText}>Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: spacing.xxl * 2 },
  logoWrap: { alignItems: 'center', marginBottom: spacing.lg },
  logo: { width: 80, height: 80, borderRadius: 20, backgroundColor: colors.accent, alignItems: 'center', justifyContent: 'center' },
  logoText: { color: '#fff', fontFamily: typography.sans, fontSize: 44, fontWeight: '800' },
  title: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.xxl, fontWeight: '700', textAlign: 'center' },
  subtitle: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.md, textAlign: 'center', marginTop: spacing.sm, marginBottom: spacing.xl },
  progress: { flexDirection: 'row', justifyContent: 'center', gap: spacing.sm, marginBottom: spacing.xl },
  progressDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.surfaceHover },
  progressDotActive: { backgroundColor: colors.accent },
  section: { gap: spacing.sm },
  sectionTitle: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.lg, fontWeight: '600' },
  sectionDesc: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.sm, lineHeight: 20 },
  label: { color: colors.textSecondary, fontFamily: typography.mono, fontSize: typography.size.xs, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 1, marginTop: spacing.md },
  input: { backgroundColor: colors.surface, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: spacing.md, color: colors.text, fontFamily: typography.mono, fontSize: typography.size.sm, borderWidth: 1, borderColor: colors.border },
  btn: { backgroundColor: colors.accent, borderRadius: radius.md, paddingVertical: spacing.md, alignItems: 'center', marginTop: spacing.lg },
  btnDisabled: { backgroundColor: colors.surfaceHover },
  btnText: { color: '#fff', fontFamily: typography.sans, fontSize: typography.size.md, fontWeight: '600' },
  btnLoadingRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  link: { color: colors.accent, fontFamily: typography.sans, fontSize: typography.size.sm, marginTop: spacing.xs },
  backLink: { color: colors.textTertiary, fontFamily: typography.sans, fontSize: typography.size.sm, textAlign: 'center', marginTop: spacing.md },
  error: { color: colors.error, fontFamily: typography.sans, fontSize: typography.size.sm, marginTop: spacing.xs },
  hint: { color: colors.textTertiary, fontFamily: typography.mono, fontSize: typography.size.xs, marginTop: spacing.xs },
  code: { fontFamily: typography.mono, backgroundColor: colors.surfaceAlt, paddingHorizontal: 4, paddingVertical: 1, borderRadius: 4 },
  presetGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.xs },
  presetChip: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.pill, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  presetChipActive: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  presetChipText: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.sm, fontWeight: '500' },
  presetChipTextActive: { color: colors.accent },
  secretRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'stretch' },
  genBtn: { backgroundColor: colors.surfaceAlt, borderRadius: radius.md, paddingHorizontal: spacing.md, justifyContent: 'center', borderWidth: 1, borderColor: colors.border },
  genBtnText: { color: colors.text, fontFamily: typography.mono, fontSize: typography.size.sm },

  modelRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'stretch' },
  fetchBtn: { backgroundColor: colors.surfaceAlt, borderRadius: radius.md, paddingHorizontal: spacing.md, justifyContent: 'center', borderWidth: 1, borderColor: colors.accent },
  fetchBtnText: { color: colors.accent, fontFamily: typography.mono, fontSize: typography.size.sm, fontWeight: '600' },

  testBtn: { backgroundColor: 'transparent', borderRadius: radius.md, paddingVertical: spacing.md, alignItems: 'center', marginTop: spacing.sm, borderWidth: 1, borderColor: colors.accent },
  testBtnText: { color: colors.accent, fontFamily: typography.sans, fontSize: typography.size.sm, fontWeight: '600' },
  testResult: { fontFamily: typography.mono, fontSize: typography.size.xs, marginTop: spacing.xs, padding: spacing.sm, borderRadius: radius.sm },
  testOk: { color: colors.success, backgroundColor: colors.successSoft },
  testFail: { color: colors.error, backgroundColor: colors.errorSoft },

  checkboxRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginTop: spacing.md, paddingVertical: spacing.sm },
  checkbox: { width: 20, height: 20, borderRadius: 4, borderWidth: 2, borderColor: colors.border },
  checkboxChecked: { backgroundColor: colors.accent, borderColor: colors.accent },
  checkboxLabel: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.sm, flex: 1 },

  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', alignItems: 'center', padding: spacing.lg },
  modalContent: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, width: '100%', maxHeight: '80%' },
  modalTitle: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.lg, fontWeight: '600', marginBottom: spacing.md },
  modelItem: { paddingVertical: spacing.md, paddingHorizontal: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle, gap: 2 },
  modelItemSelected: { backgroundColor: colors.accentSoft, borderRadius: radius.sm },
  modelItemId: { color: colors.text, fontFamily: typography.mono, fontSize: typography.size.sm },
  modelItemLabel: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.xs },
  modelItemCtx: { color: colors.textTertiary, fontFamily: typography.mono, fontSize: typography.size.xs },
  modalClose: { marginTop: spacing.md, paddingVertical: spacing.md, alignItems: 'center' },
  modalCloseText: { color: colors.accent, fontFamily: typography.sans, fontSize: typography.size.md, fontWeight: '600' },
});
