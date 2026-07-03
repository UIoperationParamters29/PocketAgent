/**
 * PocketAgent theme — clean, dark, z.ai-inspired.
 * Accent: z.ai green (#10A37F). Monospace for code, system sans for UI.
 */

export const colors = {
  // Backgrounds
  bg:           '#0E0E10',   // app background (z.ai dark)
  surface:      '#18181B',   // cards, input bar
  surfaceAlt:   '#1F1F23',   // elevated cards, headers
  surfaceHover: '#27272A',   // pressed state

  // Borders & dividers
  border:       '#27272A',
  borderSubtle: '#1F1F23',

  // Text
  text:         '#FAFAFA',   // primary
  textSecondary:'#A1A1AA',   // secondary
  textTertiary: '#71717A',   // tertiary / hints

  // Accent (z.ai green)
  accent:       '#10A37F',
  accentHover:  '#0E8A6A',
  accentSoft:   'rgba(16, 163, 127, 0.12)',

  // Semantic
  error:        '#EF4444',
  errorSoft:    'rgba(239, 68, 68, 0.12)',
  warning:      '#F59E0B',
  warningSoft:  'rgba(245, 158, 11, 0.12)',
  success:      '#22C55E',
  successSoft:  'rgba(34, 197, 94, 0.12)',

  // Roles (chat bubbles)
  userBubble:   '#1F1F23',
  agentBubble:  '#18181B',
  toolBg:       '#0A0A0B',   // tool call/result cards (slightly darker)
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const radius = {
  sm: 6,
  md: 10,
  lg: 14,
  xl: 20,
  pill: 999,
} as const;

export const typography = {
  // Use system fonts; Expo doesn't bundle custom fonts without setup.
  // These stacks give JetBrains Mono on Android 12+ (system), Menlo on iOS,
  // and fall back to monospace.
  mono: 'JetBrains Mono, Fira Code, Menlo, Consolas, monospace',
  sans: 'Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
  size: {
    xs: 11,
    sm: 13,
    md: 15,
    lg: 17,
    xl: 20,
    xxl: 24,
  },
  weight: {
    regular: '400' as const,
    medium: '500' as const,
    semibold: '600' as const,
    bold: '700' as const,
  },
} as const;
