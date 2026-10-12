// Tailwind compilado en el servidor (ops/install-site.sh) en vez del CDN: sin dependencias externas al cargar.
// Los colores apuntan a los tokens CSS de index.html, que cambian solos con el tema claro/oscuro.
module.exports = {
  content: ["./index.html"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)", surface: "var(--surface)", ink: "var(--ink)", muted: "var(--muted)", line: "var(--line)",
        accent: "var(--accent)", "accent-soft": "var(--accent-soft)", chip: "var(--chip)",
        bull: "var(--bull)", "bull-soft": "var(--bull-soft)", bear: "var(--bear)", "bear-soft": "var(--bear-soft)",
        cond: "var(--cond)", "cond-soft": "var(--cond-soft)", code: "var(--code-bg)", "code-ink": "var(--code-fg)",
      },
      fontFamily: {
        display: ["Archivo", "Arial Narrow", "Helvetica Neue", "Arial", "sans-serif"],
        sans: ['"IBM Plex Sans"', "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
};
