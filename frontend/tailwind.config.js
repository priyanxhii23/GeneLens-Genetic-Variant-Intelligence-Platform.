/** Design tokens live as CSS variables in src/index.css (light + dark). */
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        bg: v("bg"), surface: v("surface"), raised: v("raised"), line: v("line"),
        ink: v("ink"), muted: v("muted"), faint: v("faint"),
        accent: v("accent"), accent2: v("accent2"), violet: v("violet"),
        plp: v("plp"), vus: v("vus"), blb: v("blb"), conf: v("conf"), other: v("other"),
        good: v("good"), warn: v("warn"), bad: v("bad"),
        gold: v("gold"), pink: v("pink"),
      },
      fontFamily: {
        display: ['"DM Serif Display"', '"Iowan Old Style"', "Georgia", "serif"],
        sans: ['"Manrope"', '"Segoe UI"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "Consolas", "ui-monospace", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgb(var(--accent) / 0.25), 0 8px 40px -12px rgb(var(--accent) / 0.45)",
        "glow-sm": "0 0 0 1px rgb(var(--accent) / 0.35), 0 0 18px -6px rgb(var(--accent) / 0.55)",
        "glow-gold": "0 0 0 1px rgb(var(--gold) / 0.55), 0 0 16px -6px rgb(var(--gold) / 0.6)",
        "glow-pink": "0 0 0 1px rgb(var(--pink) / 0.55), 0 0 16px -6px rgb(var(--pink) / 0.6)",
        lift: "0 1px 0 rgb(255 255 255 / 0.04) inset, 0 12px 32px -18px rgb(2 6 23 / 0.55)",
        soft: "0 1px 2px rgb(15 23 42 / 0.04), 0 8px 24px -12px rgb(15 23 42 / 0.12)",
      },
    },
  },
  // Classes built dynamically from data (class/tone names) must be safelisted.
  safelist: [
    { pattern: /^(bg|border|text|fill|via|ring|shadow)-(plp|vus|blb|conf|other|good|warn|bad|accent|accent2|violet|faint|gold|pink)(\/(5|10|15|20|30|40|50|60))?$/ },
  ],
  plugins: [],
};
