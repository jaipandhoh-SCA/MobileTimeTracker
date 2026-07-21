# Design System — All Inclusive ADU Portal

## Theme: Light Soft UI

### Page Canvas & Cards
| Token | Value | Usage |
|-------|-------|-------|
| `canvas` | `#f3f4f6` | Page background (gray-100) |
| `card` | `#ffffff` | Card backgrounds |
| `card-radius` | `16px` | `rounded-2xl` on all cards |
| `card-shadow` | `0 1px 3px rgba(0,0,0,0.06), 0 8px 24px rgba(0,0,0,0.04)` | Soft diffuse elevation — NO borders, NO glows, NO gradients |

### Text Hierarchy
| Token | Value | Usage |
|-------|-------|-------|
| `txt-primary` | `#0f172a` | Headlines, hero numbers (slate-900) |
| `txt-secondary` | `#475569` | Body text, descriptions (slate-600) |
| `txt-muted` | `#94a3b8` | Labels, timestamps, breadcrumb parents (slate-400) |

### Accent Discipline
| Color | Value | Usage |
|-------|-------|-------|
| Near-black | `#0f172a` | Default chart/line color, primary text |
| Magenta | `#D6246E` | ONLY brand accent: Meta Ads sparkline, hover states, notification badge |
| Green | `#10b981` | Positive deltas, "No spend" badges |
| Red | `#ef4444` | Negative deltas |
| **No other colors anywhere.** |||

### Badges & Pills
- Background: `#f1f5f9` (slate-100)
- Border-radius: `20px` (fully rounded)
- Text size: `11px`
- Text color: muted by default; green for semantic "No spend", etc.

### Dividers
| Token | Value | Usage |
|-------|-------|-------|
| `hairline` | `#eef2f6` | Card-internal dividers between sections |

### Typography
| Role | Family | Weight | Size |
|------|--------|--------|------|
| Hero numbers | System font stack (`font-sans`) | 600 | 26-30px |
| Card labels | System font stack | 400-500 | 12-14px |
| Body | System font stack | 400 | 14px |

System font stack: `ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`

**No Fraunces. No Google Fonts dependency.**

### Spacing & Radius
- Card border-radius: `16px` (`rounded-2xl`)
- Badge border-radius: `20px` (`rounded-full` or `rounded-[20px]`)
- Button border-radius: `12px` (`rounded-xl`)
- Section gap: `16-24px`
- Card padding: `20-24px`

### Shadows
| Token | Value | Usage |
|-------|-------|-------|
| `card` | `0 1px 3px rgba(0,0,0,0.06), 0 8px 24px rgba(0,0,0,0.04)` | All cards |
| No glow shadows. No colored shadows. |||

### Motion
- All transitions: `150ms ease`
- Chart/sparkline entrance: `800ms easeOutQuart`
- Respect `prefers-reduced-motion: reduce`

### Focus States
- Outline: `2px solid #0f172a`
- Outline offset: `2px`
- No glow shadow on focus

## Layout Structure (Mobile-First)

### Top Bar
- Breadcrumb: muted parent ("Dashboard") + dark current page ("Overview")
- Sync-status pill: white bg, rounded, green dot + service names + time ago

### Summary Card
- Full-width white card
- Left: "Overall ROI" label, hero number (e.g. 3.4x), green delta below
- Right: label-over-value pairs (Revenue, Ad spend, Leads, Conversion)
- Divided by hairline `#eef2f6`

### Channel Cards Grid
- Mobile: single column stack
- Tablet (>=768px): 2-across grid
- Desktop (>=1024px): 3-across grid
- Each card: header (icon + name + badge) -> hero metric + sub-label -> sparkline -> hairline -> footer stats

### Channel Card Sparkline Colors
| Channel | Line Color | Fill |
|---------|-----------|------|
| Organic / No-spend | `#10b981` (green) | 8% opacity green |
| Meta Ads | `#D6246E` (magenta) | 8% opacity magenta |
| Google Ads / CRM | `#0f172a` (near-black) | 8% opacity black |
| Calls | `#94a3b8` (slate) | 8% opacity slate |

### States
- Empty/zero: "No data yet" in muted text — never a blank box
- Not connected: "Not connected" state for channels without live integration
- Supervisor-only visibility for channel cards (existing logic preserved)

## Key Principles

1. **No dark theme remnants**: Every surface is light. No near-black backgrounds, no glow shadows, no scan-line textures.
2. **Elevation via shadow only**: Cards float above canvas with soft shadows, no borders.
3. **Accent discipline**: Near-black default, magenta is the ONE brand color, green/red are semantic only.
4. **System fonts only**: No external font dependencies. Fast, native feel.
5. **Whitespace over decoration**: Let spacing and shadow do the work. No gradients, no textures.
