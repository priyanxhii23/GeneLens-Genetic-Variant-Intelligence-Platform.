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
      },
      fontFamily: {
        display: ['"Fraunces"', "Georgia", "serif"],
        sans: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgb(var(--accent) / 0.25), 0 8px 40px -12px rgb(var(--accent) / 0.45)",
        soft: "0 1px 2px rgb(15 23 42 / 0.04), 0 8px 24px -12px rgb(15 23 42 / 0.12)",
      },
    },
  },
  // Classes built dynamically from data (class/tone names) must be safelisted.
  safelist: [
    { pattern: /^(bg|border|text|fill|via)-(plp|vus|blb|conf|other|good|warn|bad|accent|accent2|violet|faint)(\/(10|15|20|40|50|60))?$/ },
  ],
  plugins: [],
};
