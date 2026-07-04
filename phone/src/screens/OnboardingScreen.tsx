/**
 * Onboarding screen — first-run setup.
 * v0.5: simplified. Just BYOK LLM config (provider/key/model).
 * No GitHub PAT, no codespace, no channel secret — the runtime runs in Termux.
 */

import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView, Alert, Linking, ActivityIndicator, Modal, FlatList,
} from 'react-native';
import { colors, spacing, radius, typography } from '../theme/colors';
import { PROVIDER_PRESETS, ProviderPreset, saveSessionConfig, setOnboarded } from '../lib/secure-store';
import { fetchModels, verifyLlmConfig, ModelInfo } from '../lib/llm';
import { SessionConfig } from '../lib/types';

export function OnboardingScreen({ onDone }: { onDone: () => void }) {
  const [preset, setPreset] = useState<ProviderPreset>(PROVIDER_PRESETS.find(p => p.id === 'custom') || PROVIDER_PRESETS[0]);
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [saving, setSaving] = useState(false);

  const [models, setModels] = useState<ModelInfo[]>([]);
  const [fetchingModels, setFetchingModels] = useState(false);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [testingLlm, setTestingLlm] = useState(false);
  const [llmTestResult, setLlmTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  const pickPreset = (p: ProviderPreset) => {
    setPreset(p);
    if (p.id !== 'custom') {
      setBaseUrl(p.base_url);
      setModel(p.default_model);
    }
    setModels([]);
    setLlmTestResult(null);
  };

  const doFetchModels = async () => {
    setFetchingModels(true);
    try {
      const list = await fetchModels(baseUrl, apiKey);
      setModels(list);
      if (list.length > 0) setShowModelPicker(true);
      else Alert.alert('No models', 'Provider returned 0 models.');
    } catch (e: any) { Alert.alert('Fetch failed', e.message); }
    finally { setFetchingModels(false); }
  };

  const doTestLlm = async () => {
    setTestingLlm(true); setLlmTestResult(null);
    const r = await verifyLlmConfig(baseUrl, apiKey, model);
    setLlmTestResult(r.ok ? { ok: true, message: `✓ Connected. Reply: ${r.reply?.slice(0, 50) || '(empty)'}` } : { ok: false, message: `✗ ${r.error}` });
    setTestingLlm(false);
  };

  const finish = async () => {
    if (!apiKey) { Alert.alert('Missing API key'); return; }
    if (!baseUrl) { Alert.alert('Missing base URL'); return; }
    if (!model) { Alert.alert('Missing model'); return; }
    setSaving(true);
    try {
      const cfg: SessionConfig = { base_url: baseUrl, api_key: apiKey, model };
      await saveSessionConfig(cfg);
      await setOnboarded();
      onDone();
    } catch (e: any) { Alert.alert('Save failed', e.message); }
    finally { setSaving(false); }
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

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Connect your LLM</Text>
          <Text style={styles.sectionDesc}>Bring your own key. PocketAgent works with any OpenAI-compatible provider.</Text>

          <Text style={styles.label}>Provider</Text>
          <View style={styles.presetGrid}>
            {PROVIDER_PRESETS.map(p => (
              <TouchableOpacity key={p.id} style={[styles.presetChip, preset.id === p.id && styles.presetChipActive]} onPress={() => pickPreset(p)}>
                <Text style={[styles.presetChipText, preset.id === p.id && styles.presetChipTextActive]}>{p.label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={styles.label}>API key</Text>
          <TextInput style={styles.input} value={apiKey} onChangeText={(v) => { setApiKey(v); setLlmTestResult(null); setModels([]); }} placeholder="sk-..." placeholderTextColor={colors.textTertiary} autoCapitalize="none" autoCorrect={false} secureTextEntry />

          <Text style={styles.label}>Base URL</Text>
          <TextInput style={styles.input} value={baseUrl} onChangeText={(v) => { setBaseUrl(v); setLlmTestResult(null); setModels([]); }} placeholder="https://api.openai.com/v1" placeholderTextColor={colors.textTertiary} autoCapitalize="none" autoCorrect={false} />

          <Text style={styles.label}>Model</Text>
          <View style={styles.modelRow}>
            <TextInput style={[styles.input, { flex: 1 }]} value={model} onChangeText={setModel} placeholder="gpt-4o-mini" placeholderTextColor={colors.textTertiary} autoCapitalize="none" autoCorrect={false} />
            <TouchableOpacity style={[styles.fetchBtn, (!baseUrl || !apiKey || fetchingModels) && styles.btnDisabled]} onPress={doFetchModels} disabled={!baseUrl || !apiKey || fetchingModels}>
              {fetchingModels ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.fetchBtnText}>Fetch</Text>}
            </TouchableOpacity>
          </View>

          <TouchableOpacity style={[styles.testBtn, (!baseUrl || !apiKey || !model || testingLlm) && styles.btnDisabled]} onPress={doTestLlm} disabled={!baseUrl || !apiKey || !model || testingLlm}>
            {testingLlm ? <ActivityIndicator color={colors.accent} /> : <Text style={styles.testBtnText}>Test connection</Text>}
          </TouchableOpacity>
          {llmTestResult && <Text style={[styles.testResult, llmTestResult.ok ? styles.testOk : styles.testFail]}>{llmTestResult.message}</Text>}

          <TouchableOpacity style={[styles.btn, saving && styles.btnDisabled]} onPress={finish} disabled={saving} activeOpacity={0.7}>
            {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>Finish setup</Text>}
          </TouchableOpacity>
        </View>

        <View style={styles.termuxNote}>
          <Text style={styles.termuxNoteTitle}>📱 Next step: install Termux</Text>
          <Text style={styles.termuxNoteDesc}>
            After setup, you'll install Termux and run the PocketAgent runtime. The app will guide you — it takes 2 minutes.
          </Text>
        </View>
      </ScrollView>

      <Modal visible={showModelPicker} animationType="slide" transparent={true} onRequestClose={() => setShowModelPicker(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>Pick a model ({models.length})</Text>
            <FlatList
              data={models}
              keyExtractor={(m) => m.id}
              renderItem={({ item }) => (
                <TouchableOpacity style={[styles.modelItem, item.id === model && styles.modelItemSelected]} onPress={() => { setModel(item.id); setShowModelPicker(false); setLlmTestResult(null); }}>
                  <Text style={styles.modelItemId}>{item.id}</Text>
                  {item.label && item.label !== item.id ? <Text style={styles.modelItemLabel}>{item.label}</Text> : null}
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
  section: { gap: spacing.sm },
  sectionTitle: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.lg, fontWeight: '600' },
  sectionDesc: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.sm, lineHeight: 20 },
  label: { color: colors.textSecondary, fontFamily: typography.mono, fontSize: typography.size.xs, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 1, marginTop: spacing.md },
  input: { backgroundColor: colors.surface, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: spacing.md, color: colors.text, fontFamily: typography.mono, fontSize: typography.size.sm, borderWidth: 1, borderColor: colors.border },
  btn: { backgroundColor: colors.accent, borderRadius: radius.md, paddingVertical: spacing.md, alignItems: 'center', marginTop: spacing.lg },
  btnDisabled: { backgroundColor: colors.surfaceHover },
  btnText: { color: '#fff', fontFamily: typography.sans, fontSize: typography.size.md, fontWeight: '600' },
  presetGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.xs },
  presetChip: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.pill, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  presetChipActive: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  presetChipText: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.sm, fontWeight: '500' },
  presetChipTextActive: { color: colors.accent },
  modelRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'stretch' },
  fetchBtn: { backgroundColor: colors.surfaceAlt, borderRadius: radius.md, paddingHorizontal: spacing.md, justifyContent: 'center', borderWidth: 1, borderColor: colors.accent },
  fetchBtnText: { color: colors.accent, fontFamily: typography.mono, fontSize: typography.size.sm, fontWeight: '600' },
  testBtn: { backgroundColor: 'transparent', borderRadius: radius.md, paddingVertical: spacing.md, alignItems: 'center', marginTop: spacing.sm, borderWidth: 1, borderColor: colors.accent },
  testBtnText: { color: colors.accent, fontFamily: typography.sans, fontSize: typography.size.sm, fontWeight: '600' },
  testResult: { fontFamily: typography.mono, fontSize: typography.size.xs, marginTop: spacing.xs, padding: spacing.sm, borderRadius: radius.sm },
  testOk: { color: colors.success, backgroundColor: colors.successSoft },
  testFail: { color: colors.error, backgroundColor: colors.errorSoft },
  termuxNote: { marginTop: spacing.xl, padding: spacing.md, backgroundColor: colors.surfaceAlt, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  termuxNoteTitle: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.sm, fontWeight: '600', marginBottom: spacing.xs },
  termuxNoteDesc: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.xs, lineHeight: 18 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', alignItems: 'center', padding: spacing.lg },
  modalContent: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, width: '100%', maxHeight: '80%' },
  modalTitle: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.lg, fontWeight: '600', marginBottom: spacing.md },
  modelItem: { paddingVertical: spacing.md, paddingHorizontal: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle, gap: 2 },
  modelItemSelected: { backgroundColor: colors.accentSoft, borderRadius: radius.sm },
  modelItemId: { color: colors.text, fontFamily: typography.mono, fontSize: typography.size.sm },
  modelItemLabel: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.xs },
  modalClose: { marginTop: spacing.md, paddingVertical: spacing.md, alignItems: 'center' },
  modalCloseText: { color: colors.accent, fontFamily: typography.sans, fontSize: typography.size.md, fontWeight: '600' },
});
