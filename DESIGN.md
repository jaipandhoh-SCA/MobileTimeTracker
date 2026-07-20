# Design System — All Inclusive ADU Portal

## Theme: Dark Modern Futuristic

### Surface Layers (elevation system)
| Token | Value | Usage |
|-------|-------|-------|
| `surface-base` | `#0B0F14` | Deepest page background |
| `surface-raised` | `#131820` | Card backgrounds (12% lighter) |
| `surface-overlay` | `#1A2230` | Dropdowns, modals, nested cards |
| `surface-hover` | `#1F2A3A` | Hover state on raised surfaces |
| `surface-active` | `#253344` | Active/pressed states |

### Borders & Edges
| Token | Value | Usage |
|-------|-------|-------|
| `edge` | `#1E2A38` | Default card/divider borders |
| `edge-strong` | `#2A3A4E` | Emphasized borders, inputs |
| `edge-glow` | `#2D6A4F33` | Green glow accents on key cards |

### Text Hierarchy
| Token | Value | Contrast | Usage |
|-------|-------|----------|-------|
| `txt-primary` | `#F1F5F9` | 15.4:1 | Headlines, key content |
| `txt-secondary` | `#94A3B8` | 7.2:1 | Body text, descriptions |
| `txt-muted` | `#64748B` | 4.6:1 | Labels, timestamps |
| `txt-faint` | `#475569` | 3.1:1 | Disabled, placeholders |

### Primary — Forest Green (bright for dark mode)
| Token | Value | Usage |
|-------|-------|-------|
| `primary` | `#34D399` | Buttons, links, active states |
| `primary-hover` | `#2BB584` | Button hover |
| `primary-light` | `#0F2A1F` | Dark-tinted bg for green contexts |
| `primary-ring` | `rgba(52,211,153,0.25)` | Focus rings |
| `primary-muted` | `#2D6A4F` | Subdued fills |

### Accent — Warm Amber
| Token | Value | Usage |
|-------|-------|-------|
| `accent` | `#F59E0B` | Revenue numbers, highlights |
| `accent-light` | `#1F1A0F` | Dark amber tint bg |

### Semantic (dark mode variants)
| Token | Light BG | Text | Usage |
|-------|----------|------|-------|
| `success` | `#052E16` | `#4ADE80` | Positive states |
| `warning` | `#1C1A05` | `#FBBF24` | Caution states |
| `danger` | `#1F0A0A` | `#F87171` | Destructive actions |

### Shadows
| Token | Value | Usage |
|-------|-------|-------|
| `shadow-card` | `0 4px 24px -4px rgba(0,0,0,0.5), inset border` | Card elevation |
| `shadow-glow-sm` | `0 0 15px -3px rgba(52,211,153,0.15)` | Subtle green glow |
| `shadow-glow-md` | `0 0 25px -5px rgba(52,211,153,0.2)` | Emphasized glow |

## Typography

| Role | Family | Weight | Source |
|------|--------|--------|--------|
| Display (numbers, section titles) | Fraunces | 600-700 | Google Fonts |
| Body (everything else) | Inter | 400-600 | Google Fonts |

## Spacing & Radius

- Card border-radius: `1rem` (16px)
- Button border-radius: `0.75rem` (12px)
- Section gap: `1.5rem` (24px)
- Card border: `1px solid edge`

## Motion

All transitions: `150ms ease`. Chart animations: `800ms easeOutQuart`.
Respect `prefers-reduced-motion: reduce`.

## Key Principles

1. **Layer separation**: Each surface layer is 12-15% brighter than the one below
2. **Border over shadow**: Borders define edges; shadows add depth/glow
3. **Bright accent on dark**: Primary is #34D399 (bright mint) not the muted forest — it pops
4. **Cool neutrals**: Blue-tinted grays (slate family) not warm browns
5. **Glow for emphasis**: Green glow shadow on important interactive elements
