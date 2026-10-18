// Shield (the firewall) with a check (the decision). Colors come from tokens.css,
// so the mark follows the palette. public/favicon.svg is a static copy of this mark.

export default function Logo() {
  return (
    <span className="logo">
      <svg className="logo-mark" viewBox="0 0 32 32" aria-hidden="true">
        <path
          d="M16 2 28 6.5V15c0 7.5-5.2 12.8-12 15C9.2 27.8 4 22.5 4 15V6.5Z"
          fill="var(--color-primary)"
        />
        <path
          d="M16 5.2 25.2 8.7V15c0 5.8-3.9 10.1-9.2 12"
          fill="none"
          stroke="var(--color-on-primary)"
          strokeOpacity="0.35"
          strokeWidth="1.2"
        />
        <path
          d="m10.5 16.2 3.8 3.8 7.2-7.6"
          fill="none"
          stroke="var(--color-on-primary)"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="logo-text">
        Agent<span className="logo-accent">Gate</span>
      </span>
    </span>
  )
}
