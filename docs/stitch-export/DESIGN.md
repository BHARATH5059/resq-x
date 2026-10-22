---
name: Tactical Emergency Operations
colors:
  surface: '#0b1326'
  surface-dim: '#0b1326'
  surface-bright: '#31394d'
  surface-container-lowest: '#060e20'
  surface-container-low: '#131b2e'
  surface-container: '#171f33'
  surface-container-high: '#222a3d'
  surface-container-highest: '#2d3449'
  on-surface: '#dae2fd'
  on-surface-variant: '#bec8d2'
  inverse-surface: '#dae2fd'
  inverse-on-surface: '#283044'
  outline: '#88929b'
  outline-variant: '#3e4850'
  surface-tint: '#89ceff'
  primary: '#89ceff'
  on-primary: '#00344d'
  primary-container: '#0ea5e9'
  on-primary-container: '#003751'
  inverse-primary: '#006591'
  secondary: '#ffb95f'
  on-secondary: '#472a00'
  secondary-container: '#ee9800'
  on-secondary-container: '#5b3800'
  tertiary: '#ffb3ad'
  on-tertiary: '#68000a'
  tertiary-container: '#ff6c66'
  on-tertiary-container: '#6e000c'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#c9e6ff'
  primary-fixed-dim: '#89ceff'
  on-primary-fixed: '#001e2f'
  on-primary-fixed-variant: '#004c6e'
  secondary-fixed: '#ffddb8'
  secondary-fixed-dim: '#ffb95f'
  on-secondary-fixed: '#2a1700'
  on-secondary-fixed-variant: '#653e00'
  tertiary-fixed: '#ffdad7'
  tertiary-fixed-dim: '#ffb3ad'
  on-tertiary-fixed: '#410004'
  on-tertiary-fixed-variant: '#930013'
  background: '#0b1326'
  on-background: '#dae2fd'
  surface-variant: '#2d3449'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Inter
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
  headline-sm:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 20px
  body-lg:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 22px
  body-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-lg:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 18px
    letterSpacing: 0.04em
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.06em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.08em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 0.75rem
  margin: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style
The brand personality is authoritative, mission-critical, analytical, and uncompromisingly precise. Designed for incident commanders, civil defense strategists, and emergency dispatch coordinators operating under intense temporal and situational pressure, the interface eliminates cognitive clutter to deliver immediate situational awareness. 

The aesthetic is High-Contrast Tactical HUD mixed with Modern Utilitarianism:
- High data density calibrated for continuous multi-display command environments.
- Monochromatic, atmospheric slate foundations paired with sharp, signal-grade status indicators.
- Technical, micro-paneled structural modules conveying precision engineering and real-time situational readiness.
- Low visual fatigue under sustained low-light conditions, prioritizing glanceability, spatial indexing, and tactical clarity over decoration.

## Colors
The color architecture enforces operational rigor through strict semantic discipline:

- **Primary Canvas & Structural Neutrals:**
  - Base Ground: `#0B111E` (deep, light-absorbing navy canvas).
  - Surface Tier 1 (Module/Panel Background): `#0F172A` (deep slate).
  - Surface Tier 2 (Elevated HUD/Dock): `#1E293B` (tactical slate).
  - Boundary Outlines: `#334155` (crisp technical borders) and `#1E293B` (recessed divider lines).
  - Text Primary: `#F8FAFC` (pure readability).
  - Text Secondary/Muted: `#94A3B8` (metadata, field labels).

- **Operational Telemetry & Tactical Accents:**
  - **Cyan/Electric Blue (`#0EA5E9`):** Primary command inputs, selected state toggles, real-time telemetry cursors, and active vector controls.
  - **Amber / Cautionary Yellow (`#F59E0B`):** Level-2 breach alerts, advisory statuses, dynamic sensor warnings, and pending actions.
  - **Crimson Red (`#EF4444`):** Catastrophic levee failures, immediate evacuation zones, high-risk operational alarms, and critical system alerts.
  - **Emerald Green (`#10B981`):** Nominal telemetry, secured zones, optimal water throughput, and operational stability.

Accent saturation is strictly restricted to status beacons, interactive handles, map vectors, and telemetry alerts. Neutral surfaces must never compete with live status signals.

## Typography
Typography is split into dual operational roles:

1. **Interface Hierarchy & Qualitative Directives (Inter):** Clean, neutral, high-legibility geometric sans-serif for contextual headers, panel labels, situation reports, and workflow steps. Emphasizes instant legibility under split-second scanning.
2. **Telemetry, Timestamps, & Spatial Indices (JetBrains Mono):** Reserved for technical instrumentation, coordinates (lat/long), water level readings, timecode deltas, serial identifiers, and micro badge notifications. All monospaced typography must default to tabular figures (`tnum`) to eliminate spatial shifting during continuous live updates.

Key typography instructions:
- Use uppercase styling for all `label-sm` and `label-md` tokens to maintain military/civil operations hierarchy.
- Numeric counters and sensor gauges must enforce uniform horizontal alignment across vertical feeds.

## Layout & Spacing
The layout employs an ultra-compact, high-density telemetry grid structured around operational focus areas:

- **Desktop Framework:** A continuous multi-pane workspace driven by an edge-to-edge 12-column grid. Left and right control docks remain locked at fixed functional widths (320px–380px) to house simulation controls and incoming feed logs, while the central canvas hosts the dynamic spatial map or cross-section topography.
- **Micro-Gutter System:** Consistent `0.75rem` (12px) gutters lock modules in a structured, modular HUD matrix without excessive gaps, maximizing spatial utility.
- **Responsive Adaptation:**
  - **Desktop (1440px+):** Tri-pane layout with persistent real-time map, dynamic flood velocity telemetry, and command panel.
  - **Tablet (768px - 1439px):** Map occupies full canvas; control panels collapse into slide-out technical sheets or docked drawer tabs.
  - **Mobile (<768px):** Single vertical telemetry stack; critical status badges and hazard tickers persist in top-fixed safe areas with bottom-docked quick-action triggers.

## Elevation & Depth
Depth in this design system is structural and tactile, relying on precise tonal layering and razor-sharp border delineation rather than ambient decorative blur:

- **Ground Layer:** `#0B111E` forms the base infinite canvas.
- **Structural Paneling:** `#0F172A` surfaces outlined with a 1px solid `#334155` border define telemetry modules, map controls, and sub-panels.
- **Elevated Modals & Floating Overlays:** `#1E293B` backgrounds framed with 1px `#475569` borders and an intense, directional drop shadow: `0 4px 20px -2px rgba(2, 6, 23, 0.85)`.
- **Status Glow (Emergency Telemetry Only):** Functional back-lighting applied strictly to active state badges and emergency status indicators. Critical alert states use a localized, tight luminescence: `0 0 12px rgba(239, 68, 68, 0.45)`. Controlled states use cyan luminescent edges: `0 0 10px rgba(14, 165, 233, 0.35)`.

## Shapes
A disciplined, low-radius shape profile (`roundedness: 1`, 0.25rem / 4px base) delivers an engineered, technical appearance suited for mission-critical software. 

- **Containers & Modules:** Base radius of 4px (`rounded-sm`). Sharp enough to appear technical, structured, and modular.
- **Badges & Micro Chips:** 2px to 4px maximum corner radius. Avoid pill shapes or full circular roundness to maintain a clinical, instrument-grade silhouette.
- **Buttons & Control Knobs:** Crisp 4px borders with segmented interior dividers, reinforcing the feel of physical tactical consoles.

## Components

### Buttons & Tactical Triggers
- **Primary Action (Command Execute):** Background `#0EA5E9`, text `#0B111E` (bold weight for maximum contrast), 1px solid `#38BDF8`. Hover switches to `#38BDF8` with a restrained blue glow.
- **Destructive/Emergency Action (Breach/Evacuate):** Background `#EF4444`, text `#FFFFFF`, 1px solid `#F87171`. Active/Triggered state blinks with a discrete CSS pulse.
- **Secondary/Utility:** Background `#1E293B`, text `#F8FAFC`, 1px solid `#334155`. Hover shifts border to `#64748B`.
- **Dimensions:** Compact 32px height for micro-actions; 38px for primary global triggers.

### Status Indicators & HUD Badges
- **Structure:** 18px–22px height, uppercase `label-sm` monospace text, accompanied by a 6px status light beacon on the left edge.
- **Nominal / Safe:** Border `1px solid rgba(16, 185, 129, 0.4)`, background `rgba(16, 185, 129, 0.1)`, text `#10B981`.
- **Caution / Warning:** Border `1px solid rgba(245, 158, 11, 0.4)`, background `rgba(245, 158, 11, 0.1)`, text `#F59E0B`.
- **Critical / Failure:** Border `1px solid rgba(239, 68, 68, 0.5)`, background `rgba(239, 68, 68, 0.15)`, text `#EF4444`. Light beacon has a subtle 1Hz ping animation.

### Telemetry & HUD Cards
- Panel wrappers use `#0F172A` with 1px `#334155` borders.
- Header bars feature technical metadata sub-strips: 24px height, `#1E293B` background, displaying panel coordinates or sector identifiers in `label-sm` muted text.
- Inner grid gutters are sealed to maintain high data density.

### Form Inputs & Adjusters
- **Input Fields:** `#0B111E` background, 1px solid `#334155` border, text `#F8FAFC`. Focus ring is a clean 1px solid `#0EA5E9` without soft outer blur.
- **Monospace Value Steppers:** Numerical inputs display large tabular figures alongside +/- micro-stepper buttons nested directly into the field boundary.

### Checkboxes & Segmented Radios
- **Checkboxes:** 14px square boxes, `#0B111E` base, 1px `#334155` border. Checked state fills with `#0EA5E9` and displays a crisp white check vector.
- **Segmented Radio Bars:** Horizontal command group with mutual exclusivity. Unselected segments: `#0F172A`, text `#94A3B8`. Selected segment: `#1E293B` with a prominent `#0EA5E9` 2px top active line.

### Specialized Incident Modules
- **Water Level Ticker:** Monospace telemetry readout with live drift arrows (▲ / ▼), color-graded according to risk thresholds.
- **Levee Stress Matrix:** Segmented gauge composed of 10 individual 2px ticks transitioning dynamically across Emerald, Amber, and Crimson.