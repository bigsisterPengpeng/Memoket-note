/** App mark: a page of notes + a fact diamond. Same master as the dmg icon (desktop/build/icon.png). */
export default function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg className="app-logo" width={size} height={size} viewBox="0 0 64 64" aria-label="MEMOKET NOTE">
      <rect x="4" y="4" width="56" height="56" rx="14" fill="var(--accent)" />
      <rect x="16" y="20" width="30" height="4" rx="2" fill="#fff" opacity=".95" />
      <rect x="16" y="29" width="22" height="4" rx="2" fill="#fff" opacity=".95" />
      <rect x="16" y="38" width="14" height="4" rx="2" fill="#fff" opacity=".95" />
      <path d="M44 34 L52 42 L44 50 L36 42 Z" fill="#fff" />
      <path d="M44 38 L48 42 L44 46 L40 42 Z" fill="var(--accent)" />
    </svg>
  )
}
