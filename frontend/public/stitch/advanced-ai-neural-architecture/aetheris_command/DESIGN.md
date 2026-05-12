---
name: Aetheris Command
colors:
  surface: '#0f131f'
  surface-dim: '#0f131f'
  surface-bright: '#353946'
  surface-container-lowest: '#0a0e1a'
  surface-container-low: '#171b28'
  surface-container: '#1b1f2c'
  surface-container-high: '#262a37'
  surface-container-highest: '#313442'
  on-surface: '#dfe2f3'
  on-surface-variant: '#bac9cc'
  inverse-surface: '#dfe2f3'
  inverse-on-surface: '#2c303d'
  outline: '#849396'
  outline-variant: '#3b494c'
  surface-tint: '#00daf3'
  primary: '#c3f5ff'
  on-primary: '#00363d'
  primary-container: '#00e5ff'
  on-primary-container: '#00626e'
  inverse-primary: '#006875'
  secondary: '#ebb2ff'
  on-secondary: '#520071'
  secondary-container: '#721199'
  on-secondary-container: '#e299ff'
  tertiary: '#9affe8'
  on-tertiary: '#00382f'
  tertiary-container: '#51e7cb'
  on-tertiary-container: '#006556'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#9cf0ff'
  primary-fixed-dim: '#00daf3'
  on-primary-fixed: '#001f24'
  on-primary-fixed-variant: '#004f58'
  secondary-fixed: '#f8d8ff'
  secondary-fixed-dim: '#ebb2ff'
  on-secondary-fixed: '#320047'
  on-secondary-fixed-variant: '#721199'
  tertiary-fixed: '#68fadd'
  tertiary-fixed-dim: '#44ddc1'
  on-tertiary-fixed: '#00201a'
  on-tertiary-fixed-variant: '#005145'
  background: '#0f131f'
  on-background: '#dfe2f3'
  surface-variant: '#313442'
typography:
  display-lg:
    fontFamily: Space Grotesk
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Space Grotesk
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '500'
    lineHeight: 32px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-mono:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
  headline-lg-mobile:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  gutter: 20px
  margin-desktop: 40px
---

## Brand & Style

This design system is engineered for high-stakes decision-making and advanced analytical monitoring. It evokes the feeling of a futuristic AI command center—sophisticated, hyper-intelligent, and computationally powerful. The aesthetic leans heavily into **Glassmorphism** and **Skeuomorphic depth**, utilizing layered semi-transparent surfaces to represent the multidimensional nature of data processing.

The target audience consists of elite operators and data scientists who require a focused, low-strain environment that highlights critical anomalies through luminous accents. The UI should feel like a physical "cockpit" of light, where depth is used to prioritize information and thin, glowing borders define the architectural structure of the dashboard.

## Colors

The palette is anchored in a foundation of **Deep Navy (#0A0E1A)** and **Charcoal**, creating a "void" background that minimizes light pollution and maximizes contrast for data visualizations. 

- **Primary (Neon Electric Blue):** Used for active states, primary data streams, and interactive elements. It provides the "pulse" of the system.
- **Secondary (Deep Violet):** Used for high-level AI processing indicators and background light-refracting gradients to add depth.
- **Tertiary (Subtle Teal):** Used for secondary status indicators and decorative technical accents.
- **Surface Colors:** Utilize semi-transparent dark washes with 40-60% opacity to allow background gradients to bleed through, creating the glass effect.

## Typography

This design system uses a triple-font approach to balance technical precision with modern aesthetics. 

- **Space Grotesk** is used for major headlines and display numbers, offering a futuristic, geometric feel that remains highly legible.
- **Inter** provides a neutral, utilitarian foundation for body text and descriptive content, ensuring long-form data is readable.
- **JetBrains Mono** is reserved for technical metadata, timestamps, and status codes, reinforcing the "command center" narrative through a developer-centric monospace style.

All headings should use slightly tightened letter spacing, while mono labels should be tracked out for better clarity in high-density areas.

## Layout & Spacing

The layout utilizes a **12-column fixed grid** on desktop to maintain the structural integrity of complex data visualizations. For ultra-wide displays, the dashboard can extend into a fluid mode with max-width constraints on individual widgets.

- **Desktop:** 12 columns, 20px gutters, 40px outer margins.
- **Tablet:** 8 columns, 16px gutters, 24px outer margins.
- **Mobile:** 4 columns, 12px gutters, 16px outer margins.

Spacing follows a 4px base unit. High-density data areas should utilize 8px (sm) padding to pack information efficiently, while major structural sections should use 32px (xl) to allow the "glass" panels to breathe against the deep navy background.

## Elevation & Depth

Hierarchy is achieved through **optical layering** rather than traditional drop shadows. 

1. **Base Layer:** The Deep Navy background with soft, blurred violet/blue gradients moving slowly in the background.
2. **Surface Layer:** Semi-transparent panels (`rgba(22, 27, 34, 0.6)`) with a `backdrop-filter: blur(12px)`.
3. **Stroke Layer:** 1px borders using linear gradients from transparent to `primary-color` (30% opacity) to define edges.
4. **Interactive Layer:** Elements that are hovered or active gain an "inner glow" and a subtle outer box-shadow with a 15px blur using the primary accent color at low opacity.

This system creates a "holographic" stack where information feels projected rather than printed.

## Shapes

The design system employs a **Soft (1)** roundedness profile to maintain a professional, architectural feel. 

- Small components (buttons, tags): 4px (0.25rem).
- Large containers (cards, panels): 8px (0.5rem).
- Active indicators: 0px (sharp) or vertical bars to emphasize technical precision.

The subtle rounding prevents the UI from feeling "aggressive" while maintaining the sleek, straight lines associated with high-end tech interfaces.

## Components

### Buttons & Controls
Buttons are glass-morphic. Primary buttons use a solid electric blue fill with a subtle outer glow. Ghost buttons use a 1px border with a high-contrast hover state that fills the button with a low-opacity gradient.

### Glass Cards
Cards are the primary container. They must feature a thin top-left to bottom-right gradient border. The background should be slightly more opaque than the general layout surface to pull attention forward.

### Data Visualizations
Charts should use "neon" line styles—thin strokes with a soft glow (drop-shadow blur). Use the neon electric blue for the primary data series and subtle teal for comparisons. Grid lines within charts should be barely visible (10% opacity).

### Form Inputs
Input fields are "underlined" or "bracketed" style to minimize visual clutter. On focus, the bottom border glows intensely in primary blue, and a subtle light-refraction effect appears within the field.

### Status Chips
Status indicators use a "dot + label" format. The dot should have a pulsating glow animation if the status is "Active" or "Critical," mimicking a hardware LED.