const glyphs = {
  activity: "∿",
  bot: "◈",
  boxes: "▦",
  check: "✓",
  clipboard: "☑",
  clock: "◷",
  coins: "◉",
  compare: "⇄",
  database: "▤",
  external: "↗",
  file: "≡",
  gauge: "◔",
  layers: "▧",
  play: "▶",
  refresh: "↻",
  send: "↑",
  shield: "◇",
  sparkles: "✦",
  warning: "!",
  x: "×",
} as const;

export type IconName = keyof typeof glyphs;

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <span className={`cp-icon cp-icon-${name}`} style={{ width: size, height: size, fontSize: size * 0.82 }}>
      {glyphs[name]}
    </span>
  );
}
