/**
 * FilesScreen — workspace file explorer.
 * Fetches the workspace tree from /workspace, lets the user browse + read files.
 */

import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { colors, spacing, radius, typography } from '../theme/colors';
import { useStore } from '../state/store';
import { WorkspaceNode, FileContent } from '../lib/types';
import { loadChannelSecret } from '../lib/secure-store';

export function FilesScreen() {
  const runtimeUrl = useStore(s => s.runtimeUrl);
  const [tree, setTree] = useState<WorkspaceNode | null>(null);
  const [path, setPath] = useState<string[]>([]); // stack of dir names
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<FileContent | null>(null);
  const [viewingName, setViewingName] = useState<string>('');

  const fetchTree = useCallback(async () => {
    if (!runtimeUrl) return;
    setLoading(true);
    setError(null);
    try {
      const secret = await loadChannelSecret();
      const r = await fetch(`${runtimeUrl}/workspace?depth=3`, {
        headers: secret ? { Authorization: `Bearer ${secret}` } : {},
      });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      setTree(await r.json());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [runtimeUrl]);

  useEffect(() => { fetchTree(); }, [fetchTree]);

  const readFile = useCallback(async (path: string) => {
    if (!runtimeUrl) return;
    setLoading(true);
    setError(null);
    try {
      const secret = await loadChannelSecret();
      const r = await fetch(`${runtimeUrl}/file?path=${encodeURIComponent(path)}`, {
        headers: secret ? { Authorization: `Bearer ${secret}` } : {},
      });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const data: FileContent = await r.json();
      if (!data.ok) throw new Error(data.error || 'read failed');
      setViewing(data);
      setViewingName(path);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [runtimeUrl]);

  // Walk the tree following the path stack
  const currentNode = (() => {
    if (!tree) return null;
    let node = tree;
    for (const seg of path) {
      const next = node.children?.find(c => c.name === seg && c.type === 'dir');
      if (!next) return node;
      node = next;
    }
    return node;
  })();

  if (!runtimeUrl) {
    return (
      <View style={styles.empty}>
        <Text style={styles.emptyText}>Start the runtime in Termux first.</Text>
      </View>
    );
  }

  if (viewing) {
    return (
      <View style={styles.container}>
        <View style={styles.fileHeader}>
          <TouchableOpacity onPress={() => setViewing(null)}>
            <Text style={styles.backLink}>← Back</Text>
          </TouchableOpacity>
          <Text style={styles.fileName} numberOfLines={1}>{viewingName}</Text>
          {viewing.truncated && <Text style={styles.truncated}>truncated</Text>}
        </View>
        <FlatList
          data={(viewing.content || '').split('\n')}
          keyExtractor={(_, i) => String(i)}
          renderItem={({ item, index }) => (
            <View style={styles.codeLine}>
              <Text style={styles.lineNumber}>{index + 1}</Text>
              <Text style={styles.codeText}>{item}</Text>
            </View>
          )}
          contentContainerStyle={styles.codeList}
        />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Workspace</Text>
        <TouchableOpacity onPress={fetchTree} disabled={loading}>
          {loading ? <ActivityIndicator size="small" color={colors.accent} /> : <Text style={styles.refresh}>↻</Text>}
        </TouchableOpacity>
      </View>

      {/* Breadcrumb */}
      {path.length > 0 && (
        <View style={styles.breadcrumb}>
          <TouchableOpacity onPress={() => setPath([])}>
            <Text style={styles.crumbLink}>root</Text>
          </TouchableOpacity>
          {path.map((seg, i) => (
            <View key={i} style={styles.crumbSeg}>
              <Text style={styles.crumbSep}>/</Text>
              <TouchableOpacity onPress={() => setPath(path.slice(0, i + 1))}>
                <Text style={styles.crumbLink}>{seg}</Text>
              </TouchableOpacity>
            </View>
          ))}
        </View>
      )}

      {error && <Text style={styles.error}>{error}</Text>}

      <FlatList
        data={currentNode?.children || []}
        keyExtractor={(item) => item.path}
        renderItem={({ item }) => (
          <TouchableOpacity
            style={styles.row}
            onPress={() => {
              if (item.type === 'dir') {
                setPath([...path, item.name]);
              } else {
                readFile(item.path);
              }
            }}
          >
            <View style={[styles.rowIconWrap, { backgroundColor: item.type === 'dir' ? colors.accentSoft : colors.surfaceAlt }]}>
              <Text style={[styles.rowIcon, { color: item.type === 'dir' ? colors.accent : colors.textSecondary }]}>
                {item.type === 'dir' ? '📁' : fileIcon(item.name)}
              </Text>
            </View>
            <View style={styles.rowText}>
              <Text style={styles.rowName}>{item.name}</Text>
              {item.type === 'file' && item.size != null && (
                <Text style={styles.rowMeta}>{formatBytes(item.size)}</Text>
              )}
            </View>
            <Text style={styles.rowChevron}>{item.type === 'dir' ? '›' : '▸'}</Text>
          </TouchableOpacity>
        )}
        ListEmptyComponent={
          !loading ? <Text style={styles.emptyText}>No files here.</Text> : null
        }
        contentContainerStyle={styles.list}
      />
    </View>
  );
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b}B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)}KB`;
  return `${(b / 1024 / 1024).toFixed(1)}MB`;
}

function fileIcon(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() || '';
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext)) return '🖼️';
  if (['pdf'].includes(ext)) return '📕';
  if (['docx', 'doc'].includes(ext)) return '📘';
  if (['xlsx', 'xls', 'csv'].includes(ext)) return '📗';
  if (['pptx', 'ppt'].includes(ext)) return '📙';
  if (['py'].includes(ext)) return '🐍';
  if (['js', 'ts', 'tsx', 'jsx'].includes(ext)) return '📜';
  if (['md', 'txt'].includes(ext)) return '📝';
  if (['json', 'yaml', 'yml', 'toml'].includes(ext)) return '⚙️';
  if (['zip', 'tar', 'gz', 'rar'].includes(ext)) return '🗜️';
  return '📄';
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: spacing.md, paddingTop: spacing.xl + spacing.sm, paddingBottom: spacing.sm },
  title: { color: colors.text, fontFamily: typography.sans, fontSize: typography.size.lg, fontWeight: '700' },
  refresh: { color: colors.accent, fontSize: 22 },
  breadcrumb: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', paddingHorizontal: spacing.md, paddingBottom: spacing.sm, gap: spacing.xs },
  crumbSeg: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  crumbLink: { color: colors.accent, fontFamily: typography.mono, fontSize: typography.size.sm },
  crumbSep: { color: colors.textTertiary, fontFamily: typography.mono, fontSize: typography.size.sm },
  list: { padding: spacing.md },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.md, paddingHorizontal: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.borderSubtle },
  rowIconWrap: { width: 36, height: 36, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
  rowIcon: { fontSize: 16 },
  rowText: { flex: 1 },
  rowName: { color: colors.text, fontFamily: typography.mono, fontSize: typography.size.sm },
  rowMeta: { color: colors.textTertiary, fontFamily: typography.mono, fontSize: typography.size.xs, marginTop: 2 },
  rowChevron: { color: colors.textTertiary, fontSize: 18, fontWeight: '300' },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.bg },
  emptyText: { color: colors.textTertiary, fontFamily: typography.sans, fontSize: typography.size.sm },
  error: { color: colors.error, fontFamily: typography.sans, fontSize: typography.size.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },

  fileHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingHorizontal: spacing.md, paddingTop: spacing.xl + spacing.sm, paddingBottom: spacing.sm },
  backLink: { color: colors.accent, fontFamily: typography.sans, fontSize: typography.size.sm },
  fileName: { flex: 1, color: colors.text, fontFamily: typography.mono, fontSize: typography.size.sm },
  truncated: { color: colors.warning, fontFamily: typography.mono, fontSize: typography.size.xs },
  codeList: { padding: spacing.md },
  codeLine: { flexDirection: 'row', gap: spacing.md, paddingVertical: 1 },
  lineNumber: { color: colors.textTertiary, fontFamily: typography.mono, fontSize: typography.size.xs, minWidth: 32, textAlign: 'right' },
  codeText: { flex: 1, color: colors.text, fontFamily: typography.mono, fontSize: typography.size.xs, lineHeight: 18 },
});
