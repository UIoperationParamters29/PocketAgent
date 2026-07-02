/**
 * SettingsScreen — edit BYOK config, codespace, see session info, wipe.
 */

import React, { useEffect, useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView, Alert, ActivityIndicator,
} from 'react-native';
import { colors, spacing, radius, typography } from '../theme/colors';
import {
  loadSessionConfig, saveSessionConfig, loadChannelSecret, saveChannelSecret,
  loadCodespaceName, saveCodespaceName, loadGithubPat, saveGithubPat, wipeAll,
  PROVIDER_PRESETS, ProviderPreset,
} from '../lib/secure-store';
import { SessionConfig } from '../lib/types';
import { useStore } from '../state/store';
import { useAgentSession } from '../hooks/useAgentSession';

export function SettingsScreen({ onWiped }: { onWiped: () => void }) {
  const session = useAgentSession();
  const store = useStore();
  const [pat, setPat] = useState('');
  const [channelSecret, setChannelSecret] = useState('');
  const [codespaceName, setCodespaceName] = useState('');
  const [cfg, setCfg] = useState<SessionConfig | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      setPat((await loadGithubPat()) || '');
      setChannelSecret((await loadChannelSecret()) || '');
      setCodespaceName((await loadCodespaceName()) || '');
      setCfg(await loadSessionConfig());
    })();
  }, []);

  const saveAll = async () => {
    setSaving(true);
    try {
      await saveGithubPat(pat.trim());
      await saveChannelSecret(channelSecret);
      await saveCodespaceName(codespaceName.trim());
      if (cfg) await saveSessionConfig(cfg);
      Alert.alert('Saved', 'Settings updated. Reconnect to apply.');
    } catch (e: any) {
      Alert.alert('Save failed', e.message);
    } finally {
      setSaving(false);
    }
  };

  const wipe = () => {
    Alert.alert('Wipe everything?', 'This removes all keys, secrets, and codespace name from this device.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Wipe', style: 'destructive', onPress: async () => {
        await wipeAll();
        onWiped();
      }},
    ]);
  };

  const pickPreset = (p: ProviderPreset) => {
    if (!cfg) return;
    if (p.id === 'custom') {
      setCfg({ ...cfg });
    } else {
      setCfg({ ...cfg, base_url: p.base_url, model: p.default_model });
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.scroll}>
      <Text style={styles.title}>Settings</Text>

      {/* Codespace */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Codespace</Text>
        <Text style={styles.label}>GitHub PAT</Text>
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
        <Text style={styles.label}>Codespace name</Text>
        <TextInput
          style={styles.input}
          value={codespaceName}
          onChangeText={setCodespaceName}
          placeholder="auto-detect on Wake"
          placeholderTextColor={colors.textTertiary}
          autoCapitalize="none"
          autoCorrect={false}
        />
        <Text style={styles.label}>Channel secret (PA_CHANNEL_SECRET)</Text>
        <TextInput
          style={styles.input}
          value={channelSecret}
          onChangeText={setChannelSecret}
          placeholder="32-char hex"
          placeholderTextColor={colors.textTertiary}
          autoCapitalize="none"
          autoCorrect={false}
        />
      </View>

      {/* LLM */}
      {cfg && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>LLM (BYOK)</Text>
          <Text style={styles.label}>Provider</Text>
          <View style={styles.presetGrid}>
            {PROVIDER_PRESETS.map(p => (
              <TouchableOpacity
                key={p.id}
                style={[styles.presetChip, cfg.base_url === p.base_url && styles.presetChipActive]}
                onPress={() => pickPreset(p)}
              >
                <Text style={[styles.presetChipText, cfg.base_url === p.base_url && styles.presetChipTextActive]}>{p.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <Text style={styles.label}>API key</Text>
          <TextInput
            style={styles.input}
            value={cfg.api_key}
            onChangeText={(v) => setCfg({ ...cfg, api_key: v })}
            placeholder="sk-..."
            placeholderTextColor={colors.textTertiary}
            autoCapitalize="none"
            autoCorrect={false}
            secureTextEntry
          />
          <Text style={styles.label}>Model</Text>
          <TextInput
            style={styles.input}
            value={cfg.model}
            onChangeText={(v) => setCfg({ ...cfg, model: v })}
            placeholder="gpt-4o-mini"
            placeholderTextColor={colors.textTertiary}
            autoCapitalize="none"
            autoCorrect={false}
          />
          <Text style={styles.label}>Base URL</Text>
          <TextInput
            style={styles.input}
            value={cfg.base_url}
            onChangeText={(v) => setCfg({ ...cfg, base_url: v })}
            placeholder="https://api.openai.com/v1"
            placeholderTextColor={colors.textTertiary}
            autoCapitalize="none"
            autoCorrect={false}
          />
        </View>
      )}

      {/* Session info */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Session</Text>
        <Text style={styles.kv}>session_id: <Text style={styles.kvVal}>{store.sessionId || '—'}</Text></Text>
        <Text style={styles.kv}>connection: <Text style={styles.kvVal}>{store.connStatus}</Text></Text>
        <Text style={styles.kv}>codespace: <Text style={styles.kvVal}>{store.codespaceName || '—'}</Text></Text>
        <Text style={styles.kv}>runtime_url: <Text style={styles.kvVal}>{store.runtimeUrl || '—'}</Text></Text>
        {store.lastError ? <Text style={styles.kvError}>last_error: {store.lastError}</Text> : null}
      </View>

      <View style={styles.actions}>
        <TouchableOpacity style={styles.saveBtn} onPress={saveAll} disabled={saving} activeOpacity={0.7}>
          {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveBtnText}>Save</Text>}
        </TouchableOpacity>
        <TouchableOpacity style={styles.wipeBtn} onPress={wipe} activeOpacity={0.7}>
          <Text style={styles.wipeBtnText}>Wipe all data</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.md, paddingTop: spacing.xl + spacing.sm },
  title: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.xxl, fontWeight: '700', marginBottom: spacing.lg },
  section: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, marginBottom: spacing.md, borderWidth: 1, borderColor: colors.border },
  sectionTitle: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.md, fontWeight: '600', marginBottom: spacing.sm },
  label: { color: colors.textSecondary, fontFamily: typography.mono, fontSize: typography.size.xs, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 1, marginTop: spacing.sm },
  input: { backgroundColor: colors.bg, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: spacing.md, color: colors.text, fontFamily: typography.mono, fontSize: typography.size.sm, borderWidth: 1, borderColor: colors.border, marginTop: spacing.xs },
  presetGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.xs },
  presetChip: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.pill, backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border },
  presetChipActive: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  presetChipText: { color: colors.textSecondary, fontFamily: typography.sans, fontSize: typography.size.sm, fontWeight: '500' },
  presetChipTextActive: { color: colors.accent },
  kv: { color: colors.textSecondary, fontFamily: typography.mono, fontSize: typography.size.xs, lineHeight: 20, marginTop: 2 },
  kvVal: { color: colors.text },
  kvError: { color: colors.error, fontFamily: typography.mono, fontSize: typography.size.xs, lineHeight: 18, marginTop: spacing.xs },
  actions: { gap: spacing.sm, marginBottom: spacing.xl },
  saveBtn: { backgroundColor: colors.accent, borderRadius: radius.md, paddingVertical: spacing.md, alignItems: 'center' },
  saveBtnText: { color: '#fff', fontFamily: typography.sans, fontSize: typography.size.md, fontWeight: '600' },
  wipeBtn: { backgroundColor: colors.errorSoft, borderRadius: radius.md, paddingVertical: spacing.md, alignItems: 'center', borderWidth: 1, borderColor: colors.error + '44' },
  wipeBtnText: { color: colors.error, fontFamily: typography.sans, fontSize: typography.size.md, fontWeight: '600' },
});
