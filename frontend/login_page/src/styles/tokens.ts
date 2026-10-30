import type { GlobalThemeOverrides } from 'naive-ui'

// Единственный источник цветов, отступов, радиусов, теней и шрифтов (I2, I3, I5, I6).
// Из него берутся и CSS-переменные (плагин design-tokens в vite.config.ts кладёт их в <head>
// index.html), и themeOverrides Naive UI: он считает оттенки из hex и CSS-переменные не принимает.
// Цвета меняются только здесь; в .vue и global.css — var(--…), жёстких цветов там нет.

export interface Palette {
  bg: string
  surface: string
  line: string
  text: string
  textSecondary: string
  button: string
  onButton: string
  accent: string
  accentSoft: string
  todo: string
  inProgress: string
  done: string
  blocked: string
  shadow: string
}

// I2 «графит и изумруд», статусы — I3
export const palettes = {
  light: {
    bg: '#f6f8f7',
    surface: '#ffffff',
    line: '#e1e7e3',
    text: '#111614',
    textSecondary: '#5d6a63',
    button: '#111614',
    onButton: '#ffffff',
    accent: '#0f9d63',
    accentSoft: '#e8f6ef',
    todo: '#6b7890',
    inProgress: '#0f9d63',
    done: '#4b7fd1',
    blocked: '#d65151',
    shadow: '0 8px 24px rgba(17, 22, 20, 0.12)'
  },
  dark: {
    bg: '#0c0f0e',
    surface: '#151a18',
    line: '#242b28',
    text: '#e8eeeb',
    textSecondary: '#93a199',
    button: '#3ecf8e',
    onButton: '#06120c',
    accent: '#3ecf8e',
    accentSoft: '#11241b',
    todo: '#8e9bb2',
    inProgress: '#3ecf8e',
    done: '#6f9cf0',
    blocked: '#ef6f6f',
    shadow: '0 8px 24px rgba(0, 0, 0, 0.5)'
  }
} satisfies Record<string, Palette>

export type ThemeName = keyof typeof palettes

// Шкала 4 px, радиусы, шрифты, плотность (I6: строка задачи ~40–44 px) — общие для обеих тем
export const space = { 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 8: 32, 10: 40, 12: 48 } as const
export const radius = { sm: 4, md: 8, lg: 12, full: 9999 } as const
export const fonts = {
  sans: "'Onest Variable', system-ui, sans-serif",
  mono: "'JetBrains Mono Variable', ui-monospace, monospace"
} as const
// I5: текст 450, названия задач и кнопки 600, заголовки 700
export const weights = { text: 450, strong: 600, heading: 700 } as const
export const rowHeight = 42

type Rgb = [number, number, number]

function toRgb(hex: string): Rgb {
  const n = parseInt(hex.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

// Смесь двух цветов: доля t от `to`, остальное от `from`
function mix(from: string, to: string, t: number): string {
  const a = toRgb(from)
  const b = toRgb(to)
  const channel = (i: number) => Math.round(a[i]! * (1 - t) + b[i]! * t)
  return '#' + [0, 1, 2].map((i) => channel(i).toString(16).padStart(2, '0')).join('')
}

const WHITE = '#ffffff'
const BLACK = '#000000'

// Наведение и нажатие — правило, а не отдельные цвета: светлее на 18 %, темнее на 14 %
const hover = (c: string) => mix(c, WHITE, 0.18)
const pressed = (c: string) => mix(c, BLACK, 0.14)

// Всё, что выводится из палитры (мягкие фоны статусов, наведение, цвет текста на акценте)
export function derive(p: Palette) {
  return {
    surfaceHover: mix(p.surface, p.text, 0.04),
    buttonHover: hover(p.button),
    buttonPressed: pressed(p.button),
    accentHover: hover(p.accent),
    accentPressed: pressed(p.accent),
    // белый на #0f9d63 — 3,4:1; текст палитры на акценте проходит AA в обеих темах
    onAccent: p.button === p.accent ? p.onButton : p.text,
    todoSoft: mix(p.surface, p.todo, 0.12),
    inProgressSoft: mix(p.surface, p.inProgress, 0.12),
    doneSoft: mix(p.surface, p.done, 0.12),
    blockedSoft: mix(p.surface, p.blocked, 0.12)
  }
}

const kebab = (s: string) => s.replace(/[A-Z]/g, (c) => '-' + c.toLowerCase())

function paletteVars(p: Palette): string {
  const all: Record<string, string> = { ...p, ...derive(p) }
  delete all.shadow
  const name = (k: string) =>
    (/^(todo|inProgress|done|blocked)/.test(k) ? 'status-' : '') + kebab(k)
  const lines = Object.entries(all).map(([k, v]) => `  --color-${name(k)}: ${v};`)
  lines.push(`  --shadow-overlay: ${p.shadow};`)
  return lines.join('\n')
}

function sharedVars(): string {
  const lines = [
    ...Object.entries(space).map(([k, v]) => `  --space-${k}: ${v}px;`),
    ...Object.entries(radius).map(([k, v]) => `  --radius-${k}: ${v}px;`),
    ...Object.entries(fonts).map(([k, v]) => `  --font-${k}: ${v};`),
    ...Object.entries(weights).map(([k, v]) => `  --weight-${k}: ${v};`),
    `  --row-height: ${rowHeight}px;`,
    '  --transition: 0.2s ease;'
  ]
  return lines.join('\n')
}

// CSS для <head>: светлая палитра в :root, тёмная — под [data-theme='dark'] (включает 3.2.5)
export function tokensCss(): string {
  return [
    `:root {\n  color-scheme: light;\n${sharedVars()}\n${paletteVars(palettes.light)}\n}`,
    `:root[data-theme='dark'] {\n  color-scheme: dark;\n${paletteVars(palettes.dark)}\n}`
  ].join('\n')
}

export function themeOverrides(p: Palette): GlobalThemeOverrides {
  const d = derive(p)
  return {
    common: {
      fontFamily: fonts.sans,
      fontFamilyMono: fonts.mono,
      fontWeight: String(weights.text),
      fontWeightStrong: String(weights.strong),
      borderRadius: `${radius.md}px`,
      borderRadiusSmall: `${radius.sm}px`,
      bodyColor: p.bg,
      cardColor: p.surface,
      modalColor: p.surface,
      popoverColor: p.surface,
      tableColor: p.surface,
      inputColor: p.surface,
      actionColor: d.surfaceHover,
      hoverColor: d.surfaceHover,
      borderColor: p.line,
      dividerColor: p.line,
      textColorBase: p.text,
      textColor1: p.text,
      textColor2: p.text,
      textColor3: p.textSecondary,
      placeholderColor: p.textSecondary,
      iconColor: p.textSecondary,
      primaryColor: p.button,
      primaryColorHover: d.buttonHover,
      primaryColorPressed: d.buttonPressed,
      primaryColorSuppl: d.buttonHover,
      // success и warning — акцент («время идёт»): оттенка предупреждения в I2 и I3 нет
      successColor: p.accent,
      successColorHover: d.accentHover,
      successColorPressed: d.accentPressed,
      successColorSuppl: d.accentHover,
      warningColor: p.accent,
      warningColorHover: d.accentHover,
      warningColorPressed: d.accentPressed,
      warningColorSuppl: d.accentHover,
      errorColor: p.blocked,
      errorColorHover: hover(p.blocked),
      errorColorPressed: pressed(p.blocked),
      errorColorSuppl: hover(p.blocked),
      infoColor: p.todo,
      infoColorHover: hover(p.todo),
      infoColorPressed: pressed(p.todo),
      infoColorSuppl: hover(p.todo),
      boxShadow1: p.shadow,
      boxShadow2: p.shadow,
      boxShadow3: p.shadow
    },
    Button: {
      fontWeight: String(weights.strong),
      textColorPrimary: p.onButton,
      textColorHoverPrimary: p.onButton,
      textColorPressedPrimary: p.onButton,
      textColorFocusPrimary: p.onButton,
      textColorDisabledPrimary: p.onButton,
      textColorSuccess: d.onAccent,
      textColorHoverSuccess: d.onAccent,
      textColorPressedSuccess: d.onAccent,
      textColorFocusSuccess: d.onAccent,
      textColorDisabledSuccess: d.onAccent,
      textColorWarning: d.onAccent,
      textColorHoverWarning: d.onAccent,
      textColorPressedWarning: d.onAccent,
      textColorFocusWarning: d.onAccent,
      textColorDisabledWarning: d.onAccent
    },
    Card: {
      borderRadius: `${radius.lg}px`,
      borderColor: p.line
    },
    Dialog: {
      borderRadius: `${radius.lg}px`
    },
    Layout: {
      color: p.bg,
      headerColor: p.surface,
      headerBorderColor: p.line,
      textColor: p.text
    },
    Drawer: {
      color: p.surface,
      headerBorderBottom: `1px solid ${p.line}`
    }
  }
}
