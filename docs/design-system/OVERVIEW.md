# AgentGate Design System

## Design Philosophy

AgentGate's interface is built for clarity and trust. Users need to quickly understand payment decisions, approve or deny requests, and configure policies without confusion. The design follows these principles:

1. **Decisions are never color-only** — every status (allow, deny, approval) is paired with an icon and a text label.
2. **Loading, error, and empty states are first-class** — every API-driven page handles all response states consistently.
3. **Accessibility is baseline** — WCAG AA contrast (4.5:1), keyboard navigation, focus-visible indicators, and reduced-motion support.
4. **Consistent feedback** — hover, focus, and active states follow the same visual pattern across all interactive elements.

## Color Tokens

All colors are defined in `frontend/src/tokens.css` as CSS custom properties. Every color in the app derives from these tokens.

### Surfaces & Text (Light Theme)

| Token | Value | Usage |
|---|---|---|
| `--color-bg` | `#f6f7f9` | Page background |
| `--color-surface` | `#ffffff` | Cards, modals, tables |
| `--color-surface-2` | `#f9fafb` | Subtle surface elevation |
| `--color-border` | `#d4d8de` | Standard borders |
| `--color-border-subtle` | `#e6e8ec` | Dividers, subtle separators |
| `--color-text` | `#1b1f24` | Primary text |
| `--color-text-muted` | `#545b66` | Secondary text, labels |

### Brand

| Token | Value | Usage |
|---|---|---|
| `--color-primary` | `#1f4fd1` | Primary buttons, links, active states |
| `--color-primary-hover` | `#183fa8` | Primary button hover |
| `--color-primary-bg` | `#e8eefc` | Primary tint backgrounds |
| `--color-on-primary` | `#ffffff` | Text on primary buttons |
| `--color-focus` | `#1f4fd1` | Focus ring color |
| `--color-info-bg` | `#e8eefc` | Info callout backgrounds |

### Decision States

Always paired with an icon and label — never color alone.

| Token | Value | Usage |
|---|---|---|
| `--color-allow` | `#146c3a` | Allowed decision text/icon |
| `--color-allow-bg` | `#e3f4ea` | Allowed decision background |
| `--color-deny` | `#b42318` | Denied decision text/icon |
| `--color-deny-bg` | `#fdecea` | Denied decision background |
| `--color-approval` | `#8a4b00` | Needs-approval text/icon |
| `--color-approval-bg` | `#fff3dc` | Needs-approval background |
| `--color-neutral` | `#545b66` | Neutral/pending text |
| `--color-neutral-bg` | `#eef0f3` | Neutral/pending background |

### Inverse Surfaces

Used for code windows, CTA bands, and toasts. Stay dark in every theme.

| Token | Value |
|---|---|
| `--color-inverse-bg` | `#1b1f24` |
| `--color-inverse-text` | `#ffffff` |
| `--color-inverse-muted` | `#d4d8de` |
| `--color-inverse-border` | `#545b66` |

## Typography

| Token | Size | Usage |
|---|---|---|
| `--text-xs` | 0.75rem (12px) | Labels, timestamps, metadata |
| `--text-sm` | 0.875rem (14px) | Body text, table cells |
| `--text-base` | 1rem (16px) | Default body text |
| `--text-lg` | 1.25rem (20px) | Section headings |
| `--text-xl` | 1.75rem (28px) | Page headings |
| `--text-2xl` | 2.25rem (36px) | Hero headings |

**Font families:**
- Sans-serif: `'Inter Variable', system-ui, 'Segoe UI', Roboto, sans-serif`
- Monospace: `ui-monospace, 'Cascadia Code', Consolas, monospace`

**Font sizes** are controlled via `data-font-size` attribute on `<html>`: small (87.5%), default (100%), large (112.5%), x-large (125%).

## Spacing & Layout

| Token | Value | Usage |
|---|---|---|
| `--space-1` | 4px | Tight padding, icon gaps |
| `--space-2` | 8px | Small padding, inline gaps |
| `--space-3` | 12px | Medium padding |
| `--space-4` | 16px | Standard padding, margins |
| `--space-5` | 20px | Section spacing |
| `--space-6` | 24px | Card padding |
| `--space-8` | 32px | Large section gaps |
| `--space-12` | 48px | Hero spacing |

**Layout:**
- Sidebar width: `248px`
- Content max-width: `1200px`
- Border radius: `8px` (standard), `12px` (large)
- Minimum tap target: `44px`

## Shadows

| Token | Usage |
|---|---|
| `--shadow-sm` | Subtle elevation (cards, rows) |
| `--shadow-md` | Standard elevation (dropdowns, popovers) |
| `--shadow-lg` | High elevation (modals, toasts) |

## Responsive Behavior

- **Desktop (>1024px)**: Full sidebar layout with navigation.
- **Tablet (768–1024px)**: Collapsible sidebar, stacked cards.
- **Mobile (<768px)**: Single-column layout, bottom navigation or hamburger menu.

All dashboard pages use CSS Grid and Flexbox for responsive layouts. Tables scroll horizontally on narrow viewports.

## Components & Variants

### Buttons (`frontend/src/ui/`)

- **Primary**: `--color-primary` background, `--color-on-primary` text. Hover: `--color-primary-hover`.
- **Secondary**: Outlined with `--color-primary` border. Transparent background.
- **Danger**: `--color-deny` background. Used for destructive actions (deny, revoke, delete).
- **Ghost**: No background, text-only. Used for secondary actions in dense contexts.

All buttons have `disabled` state styling and `isSubmitting` support on forms.

### Badges (`Badge.tsx`)

Color-coded status indicators. Variants: allow, deny, approval, neutral. Always paired with text labels.

### Cards (`StatCard.tsx`)

Elevated containers with `--shadow-sm`. Used for metrics, summary data, and dashboard widgets.

### Modals (`Modal.tsx`)

Overlay with `--scrim` backdrop. Used for confirmations, forms, and detail views.

### Toasts (`ToastProvider.tsx`)

Non-blocking notifications. Use for success confirmations, error messages, and async operation feedback.

### Tables

Striped rows with `--color-surface-2` alternation. Hover state on rows. Fixed header with sticky positioning.

## Forms & Validation

- **Field errors**: Inline error messages below the field in `--color-deny`. Field border turns `--color-deny`.
- **Submit buttons**: `disabled={isSubmitting}` during async operations.
- **Success feedback**: Toast notification after successful submission.
- **Validation**: Client-side validation before submit, server-side validation on every request.

## Loading, Error, Empty & Success States

Every API-driven page uses `useApiResource` hook (`frontend/src/api/useApiResource.ts`) which provides:

- **Loading**: Skeleton or spinner while data is fetching.
- **Error**: `ApiError` component with error message and retry button.
- **Empty**: `EmptyState` component with contextual message and action.
- **Success**: Rendered data.

## Accessibility Standards

- **Contrast**: All text/background pairs meet WCAG AA (4.5:1 minimum).
- **Focus**: `3px` focus ring using `--color-focus`. Visible on all interactive elements via `:focus-visible`.
- **Reduced motion**: `@media (prefers-reduced-motion: reduce)` disables transitions and animations.
- **Keyboard**: All interactive elements are keyboard-accessible. Tab order follows visual order.
- **Screen readers**: Semantic HTML, ARIA labels where needed, status changes announced via live regions.

## Interaction Patterns

- **Hover feedback**: Card elevation change, border color transition, icon color transition.
- **Focus-visible**: Equivalent visual feedback to hover states.
- **Tap-to-reveal**: On touch devices, tap reveals content that would otherwise be hover-only.
- **Transitions**: `160ms` duration with `cubic-bezier(0.2, 0, 0, 1)` easing.

## Dark & Light Themes

Theme is controlled via `data-theme` attribute on `<html>`:
- `data-theme="light"` (default): Light surfaces, dark text.
- `data-theme="dark"`: Dark surfaces, light text. Inverse surfaces stay dark in both themes.

Theme preferences are stored in `localStorage` and respect `prefers-color-scheme`.

## Design Conventions for Future Screens

1. Use CSS custom properties from `tokens.css` — never hardcode colors.
2. Use `useApiResource` for all API-driven data — never raw `fetch` or `useEffect`.
3. Handle loading, error, and empty states on every page.
4. Pair decision colors with icons and labels — never color alone.
5. Use `--space-*` tokens for all spacing — never arbitrary pixel values.
6. Ensure `:focus-visible` matches `:hover` styles on interactive elements.
7. Respect `prefers-reduced-motion` for all animations.
8. Keep decision messages free of budgets, caps, or spent amounts — those belong in the dashboard and audit views.
