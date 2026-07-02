/**
 * Onboarding screen — first-run setup.
 * Collects: GitHub PAT, channel secret, BYOK LLM config (provider/key/model).
 * Saves to expo-secure-store.
 */

import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView, Alert, Linking, ActivityIndicator,
} from 'react-native';
import { colors, spacing, radius, typography } from '../theme/colors';
import { PROVIDER_PRESETS, ProviderPreset, saveChannelSecret, saveGithubPat, saveSessionConfig, setOnboarded } from '../lib/secure-store';
import { verifyPat } from '../lib/codespaces';
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

  // ---- Step 1: Channel secret + BYOK ----
  const pickPreset = (p: ProviderPreset) => {
    setPreset(p);
    if (p.id !== 'custom') {
      setBaseUrl(p.base_url);
      setModel(p.default_model);
    }
  };

  const generateSecret = () => {
    // 32 hex chars = 128 bits of entropy
    const chars = '0123456789abcdef';
    let s = '';
    for (let i = 0; i < 32; i++) s += chars[Math.floor(Math.random() * 16)];
    setChannelSecret(s);
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
        <Text style={styles.title}>PocketAgent</Text>
        <Text style={styles.subtitle}>Your AI agent, with its own computer, on your phone.</Text>

        {/* Progress dots */}
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
              onChangeText={setApiKey}
              placeholder={preset.key_prefix || 'sk-...'}
              placeholderTextColor={colors.textTertiary}
              autoCapitalize="none"
              autoCorrect={false}
              secureTextEntry
            />

            <Text style={styles.label}>Model</Text>
            <TextInput
              style={styles.input}
              value={model}
              onChangeText={setModel}
              placeholder="gpt-4o-mini"
              placeholderTextColor={colors.textTertiary}
              autoCapitalize="none"
              autoCorrect={false}
            />

            <Text style={styles.label}>Base URL</Text>
            <TextInput
              style={styles.input}
              value={baseUrl}
              onChangeText={setBaseUrl}
              placeholder="https://api.openai.com/v1"
              placeholderTextColor={colors.textTertiary}
              autoCapitalize="none"
              autoCorrect={false}
            />

            <Text style={styles.label}>Channel secret</Text>
            <Text style={styles.sectionDesc}>A shared secret between your phone and the codespace runtime. Generate one now, then set the same value as <Text style={styles.code}>PA_CHANNEL_SECRET</Text> when you start the codespace.</Text>
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

            <TouchableOpacity
              style={[styles.btn, saving && styles.btnDisabled]}
              onPress={finish}
              disabled={saving}
              activeOpacity={0.7}
            >
              {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>Finish setup</Text>}
            </TouchableOpacity>

            <TouchableOpacity onPress={() => setStep(0)}>
              <Text style={styles.backLink}>← Back</Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: spacing.xxl * 2 },
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
  link: { color: colors.accent, fontFamily: typography.sans, fontSize: typography.size.sm, marginTop: spacing.xs },
  backLink: { color: colors.textTertiary, fontFamily: typography.sans, fontSize: typography.size.sm, textAlign: 'center', marginTop: spacing.md },
  error: { color: colors.error, fontFamily: typography.sans, fontSize: typography.size.sm, marginTop: spacing.xs },
  code: { fontFamily: typography.mono, backgroundColor: colors.surfaceAlt, paddingHorizontal: 4, paddingVertical: 1, borderRadius: 4 },
  presetGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.xs },
  presetChip: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.pill, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  presetChipActive: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  presetChipText: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.sm, fontWeight: '500' },
  presetChipTextActive: { color: colors.accent },
  secretRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'stretch' },
  genBtn: { backgroundColor: colors.surfaceAlt, borderRadius: radius.md, paddingHorizontal: spacing.md, justifyContent: 'center', borderWidth: 1, borderColor: colors.border },
  genBtnText: { color: colors.text, fontFamily: typography.mono, fontSize: typography.size.sm },
});
