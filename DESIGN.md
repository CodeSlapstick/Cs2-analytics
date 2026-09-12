---
name: CS2 SCOUTING
description: Round-by-round demo review for a CS2 team, entered through a tactical briefing board.
colors:
  briefing-charcoal: "#0B0E14"
  slate-plate: "#1E232D"
  field-well: "#151A23"
  steel-rule: "#2E3647"
  steel-rule-hi: "#46516A"
  action-orange: "#FF6B00"
  action-orange-hover: "#FF7A1A"
  action-orange-busy: "#C9580A"
  bracket-orange-hi: "#FFB27A"
  reticle-cyan: "#00E5FF"
  signal-white: "#F2F5F9"
  soft-steel-text: "#C8CFDA"
  muted-steel-text: "#9AA4B5"
  alert-red: "#FF4D5E"
  alert-red-ink: "#FFDCE0"
typography:
  display:
    fontFamily: "Chakra Petch, Anuphan, system-ui, sans-serif"
    fontSize: "clamp(38px, 3.7vw, 62px)"
    fontWeight: 700
    lineHeight: 1.04
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Chakra Petch, Anuphan, system-ui, sans-serif"
    fontSize: "29px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.005em"
  title:
    fontFamily: "Chakra Petch, Anuphan, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 700
    lineHeight: 1.1
    fontFeature: "tnum"
  brand:
    fontFamily: "Chakra Petch, Anuphan, system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.1em"
  action:
    fontFamily: "Chakra Petch, Anuphan, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.06em"
  label:
    fontFamily: "Chakra Petch, Anuphan, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.03em"
  body-lead:
    fontFamily: "Anuphan, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.6
  body:
    fontFamily: "Anuphan, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
  input:
    fontFamily: "Anuphan, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 500
    lineHeight: 1
  caption:
    fontFamily: "Anuphan, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
rounded:
  check: "3px"
  control: "4px"
  plate: "6px"
spacing:
  xs: "8px"
  sm: "10px"
  md: "20px"
  lg: "28px"
  plate: "36px"
  panel: "clamp(28px, 4vw, 56px)"
components:
  button-primary:
    backgroundColor: "{colors.action-orange}"
    textColor: "{colors.briefing-charcoal}"
    typography: "{typography.action}"
    rounded: "{rounded.control}"
    height: "56px"
  button-primary-hover:
    backgroundColor: "{colors.action-orange-hover}"
    textColor: "{colors.briefing-charcoal}"
  button-primary-busy:
    backgroundColor: "{colors.action-orange-busy}"
    textColor: "{colors.briefing-charcoal}"
  text-field:
    backgroundColor: "{colors.field-well}"
    textColor: "{colors.signal-white}"
    typography: "{typography.input}"
    rounded: "{rounded.control}"
    height: "54px"
    padding: "0 6px 0 14px"
  form-plate:
    backgroundColor: "{colors.slate-plate}"
    textColor: "{colors.signal-white}"
    rounded: "{rounded.plate}"
    padding: "36px 36px 28px"
    width: "min(448px, 100%)"
  stat-chip:
    backgroundColor: "{colors.slate-plate}"
    textColor: "{colors.signal-white}"
    typography: "{typography.title}"
    rounded: "{rounded.control}"
    padding: "10px 14px 11px"
  text-link:
    textColor: "{colors.reticle-cyan}"
    typography: "{typography.label}"
  text-link-quiet:
    textColor: "{colors.muted-steel-text}"
  checkbox-checked:
    backgroundColor: "{colors.action-orange}"
    rounded: "{rounded.check}"
    size: "20px"
---

# Design System: CS2 SCOUTING

## Overview

**Creative North Star: "The Tactical Briefing Board"**

Before the team reviews a round, they are already looking at the map. The system is a dark operations board: a near-black charcoal ground, a faint plotting grid that fades out from the map rather than papering the whole panel, the real de_mirage radar drawn as a cyan wireframe with range rings and a slow sweep, and a slate plate framed by orange corner brackets where the work happens. It is dense but calm; everything that can be touched glows cyan when it has focus, and exactly one thing per view is orange and solid: the action.

The world is recorded from its first shipped surface, `/login` (`frontend/src/LoginPage.tsx`, the `.login-shell` block of `frontend/src/styles.css`). Tokens are scoped on `.login-shell` as `--l-*` custom properties, not on `:root`. Imagery is only ever real: the radar raster is derived from the game's own file (`frontend/src/assets/brief-mirage-lines.png`, provenance embedded) and the numbers on the board come live from `/api/health`, hidden when unavailable. Thai UI with Counter-Strike terms in English.

**Open decision (drift, not repaired).** The rest of the app (`MatchPage.tsx`, `RoundView.tsx`, the `:root` block at the top of `styles.css`) still runs the older incumbent system: navy `--bg #0b1220`, card `#111a2c`, line `#1f2b44`, accent/T orange `#ff8a1e`, CT blue `#4f8cff`, `system-ui` at 14px, 12px card radius. The user has not approved rolling the briefing-board world out app-wide. Until they do, this document describes the login world as the system of record for new briefing-board surfaces; the incumbent pages are not to be restyled by inference.

**Key Characteristics:**
- Charcoal ground, slate plate, steel hairlines; depth by tone first, then by glow.
- Orange means "act"; cyan means "interactive / in focus"; red means "something is wrong".
- Chakra Petch speaks (display, labels, action); Anuphan explains (body, inputs).
- Orange corner brackets are the reusable signature: on the plate, in the logo, and around the action on hover/focus.
- Drawn line icons at one stroke weight (1.75 on a 24 grid, 20px).
- Only real proof: real radar, real counts, nothing invented.

## Colors

A cold, low-light palette of charcoal and steel with two signal colors that never swap roles.

### Primary
- **Action Orange** (action-orange): the solid fill of the single primary action per view, the checked checkbox, the text caret, the slogan's second line, the plate's corner brackets. Text on it is Briefing Charcoal.
- **Action Orange Hover** (action-orange-hover) and **Action Orange Busy** (action-orange-busy): the action's hover/focus fill and its disabled-while-working fill.
- **Bracket Orange Hi** (bracket-orange-hi): the corner reticle that closes in around the action on hover/focus, and its 1px ring in that state.

### Secondary
- **Reticle Cyan** (reticle-cyan): focus and interactivity. The global focus-visible outline (2px, 3px offset), the focused field's border and glow, the focused field's leading icon, text links, the inline help note's tint, and at low alpha the radar wireframe, grid, range rings and sweep.

### Tertiary
- **Alert Red** (alert-red) with **Alert Red Ink** (alert-red-ink): the error state. Red border on invalid fields, a red-tinted alert block (12% fill, 60% border) whose text is the pale ink, never red body text on charcoal.

### Neutral
- **Briefing Charcoal** (briefing-charcoal): page ground, and the ink on orange.
- **Slate Plate** (slate-plate): the form plate and (at 78% alpha) stat chips.
- **Field Well** (field-well): recessed input and checkbox wells, darker than the plate they sit on.
- **Steel Rule** (steel-rule): every 1px border and the panel divider; **Steel Rule Hi** (steel-rule-hi) for the unchecked checkbox's 1.5px stroke.
- **Signal White** (signal-white): headings, input text, numerals.
- **Soft Steel Text** (soft-steel-text): lead copy, labels, checkbox label, notes.
- **Muted Steel Text** (muted-steel-text): secondary lines, captions, idle icons, footers.

### Named Rules
**The Two Signals Rule.** Orange is for acting, cyan is for focus and interactivity. A cyan button or an orange focus ring breaks the grammar.

**The One Solid Orange Rule.** At most one solid orange fill per view: the primary action. Brackets, caret, and a single accented slogan line are the only other orange.

**The Real Wireframe Rule.** Cyan line imagery is drawn from real game geometry (the radar), at low alpha, behind content. It is never decorative wallpaper.

## Typography

**Display Font:** Chakra Petch 600/700 (falling back to Anuphan, then system-ui), self-hosted via @fontsource
**Body Font:** Anuphan 400/500/600 (falling back to system-ui), self-hosted via @fontsource

**Character:** Chakra Petch's squared, instrument-panel letterforms carry the tactical voice for short strings; Anuphan is a calm, open Thai-and-Latin text face for everything that has to be read. Both carry Thai, so no string falls through to a system face.

### Hierarchy
- **Display** (700, clamp 38–62px, 1.04, -0.01em, balanced wrap): the briefing slogan only. Collapses to clamp(28px, 6.4vw, 40px) below 1024px.
- **Headline** (700, 29px, 1.2): the plate's heading.
- **Title** (700, 22px, 1.1, tabular numerals): stat-chip numbers (16px below 1024px).
- **Brand** (700, 19px, 0.1em tracking): the wordmark beside the logo.
- **Action** (700, 18px, 0.06em tracking): the primary button label.
- **Label** (600, 15px, 0.03em tracking): field labels.
- **Body Lead** (400, 18px, 1.6, max 34ch): the briefing's supporting line.
- **Body** (400, 16px, 1.55): default text.
- **Input** (500, 17px): typed values.
- **Caption** (13–14.5px): chip labels, notes, hints, footers.

### Named Rules
**The Speaks / Explains Rule.** Chakra Petch for anything short and commanding (display, headings, labels, action, numerals); Anuphan for anything a person reads or types. Never set a paragraph in Chakra Petch.

**The Tabular Numbers Rule.** Live counts use tabular numerals and Thai locale grouping.

## Layout

A split briefing board at ≥1024px: a briefing panel (`minmax(0, 1.25fr)`, about 56%) and a form side (`minmax(440px, 1fr)`) with the plate centred in it. Panel padding is fluid (clamp 28–56px); the briefing stacks brand, copy and caption with `space-between`. The plate is at most 448px wide, internal gap 20px, padding 36/36/28.

On short laptops (≥1024px wide, ≤720px tall) the plate tightens (gap 16px, padding 28/32/22, fields 50px, action 52px) so the whole plate stays in one screen. Below 1024px the briefing collapses to a short band above the form: lead and caption hidden, chips in one non-wrapping row, radar pushed off the right edge at 360px. Below 480px only the two count chips remain.

Spacing rhythm: 8 / 10 between tightly coupled items, 20 between plate rows, 28 between blocks.

## Elevation & Depth

Depth is tonal first: charcoal ground, darker field wells, lighter slate plate, with 1px steel borders defining edges. Two soft radial washes add atmosphere: 8% cyan behind the radar, 9% orange behind the plate. Shadows are soft and ambient, never offset slabs; glow is reserved for state.

### Shadow Vocabulary
- **Plate lift** (`box-shadow: 0 28px 64px -24px rgba(0,0,0,.75), 0 2px 6px rgba(0,0,0,.35)`): the form plate only.
- **Action rest** (`box-shadow: 0 0 0 1px #FF6B00, 0 10px 26px -14px rgba(255,107,0,.8)`): the primary action at rest.
- **Action engaged** (`box-shadow: 0 0 0 1px #FFB27A, 0 0 28px -4px rgba(255,107,0,.75), 0 14px 32px -12px rgba(255,107,0,.9)`): action hover and focus-visible.
- **Reticle focus** (`box-shadow: 0 0 0 3px rgba(0,229,255,.16), 0 0 22px -6px rgba(0,229,255,.55)`): a focused field.
- **Alert focus** (`box-shadow: 0 0 0 3px rgba(255,77,94,.18)`): a focused invalid field.

### Named Rules
**The Glow Is State Rule.** Glow appears only in response to focus or hover. Nothing glows at rest except the action's faint orange underglow.

## Shapes

Gently squared: 4px on controls, chips, notes, error blocks and the action; 6px on the plate; 3px on the checkbox; circles only for the radar. The recurring silhouette is the **corner bracket**: 20px L-shaped 2px orange strokes that sit exactly on the plate's corners, repeated in the logo (brackets around a cyan reticle) and as a 14px reticle that closes in on the action. All icons are drawn inline SVG on a 24 grid, 1.75 stroke, round caps and joins.

## Components

### Buttons
Solid, weighty, one per view.
- **Shape:** gently squared (4px), 56px tall, full width of the plate.
- **Primary:** Action Orange fill, charcoal Chakra Petch 700 label with a trailing arrow icon, 10px gap.
- **Hover / Focus:** fill lifts to the hover orange, the engaged glow switches on, and four pale-orange corner ticks travel from 9px outside to 5px outside the button (0.35s, cubic-bezier(.16, 1, .3, 1)). Focus-visible gets the same treatment in place of an outline. Active nudges down 1px.
- **Busy:** busy-orange fill, no glow, progress cursor, a charcoal spinner and a present-tense label ("กำลังตรวจสอบ…").
- **Icon toggle (password reveal):** 40px square, transparent, muted icon; hover brightens to Signal White over a 4% white wash.

### Cards / Containers
- **Form plate:** Slate Plate, 1px Steel Rule border, 6px corners, plate-lift shadow, orange corner brackets. One per view.
- **Stat chip:** 78% Slate Plate over the briefing, 1px steel border, 4px corners, a tabular numeral over a muted caption, min 132px wide.

### Inputs / Fields
- **Style:** 54px Field Well box, 1px steel border, 4px corners, leading 20px line icon in muted steel, Chakra Petch label above (8px gap). Autofill is painted back to the well color.
- **Focus:** border turns cyan, the reticle-focus glow appears, and the leading icon turns cyan. The inner input shows no second outline.
- **Error:** border turns Alert Red; the message sits in a red-tinted alert block with a drawn warning icon, announced with `role="alert"` and wired by `aria-describedby`.
- **Checkbox:** custom 20px well, 1.5px steel-hi stroke, 3px corners; checked fills orange with a charcoal tick that scales in.

### Navigation
- **Links:** Anuphan 600 15px in Reticle Cyan, underline on hover (3px offset). The quiet variant is 14px 500 muted steel and brightens to white on hover or when expanded.
- **Inline note:** disclosed help appears as a 6% cyan-tinted block with a 28% cyan border, 4px corners, fading down 4px in.

### Briefing Radar (signature)
The real de_mirage radar as a cyan wireframe raster at 80% opacity, masked to a circle and faded toward the text side, overlaid with eight range rings and a crosshair at 14–16% cyan, and a conic sweep rotating every 7s linear. Under `prefers-reduced-motion` the sweep is removed and all entrance animations and transitions are off.

## Do's and Don'ts

### Do:
- **Do** keep orange for the one primary action and cyan for focus and interactivity (The Two Signals Rule).
- **Do** give every interactive element the cyan focus-visible outline (2px, 3px offset) or a cyan glow equivalent.
- **Do** frame the single primary plate with the 20px orange corner brackets; reuse the bracket language rather than inventing new ornaments.
- **Do** draw icons inline at 20px on a 24 grid with a 1.75 stroke.
- **Do** use only real imagery and real numbers; hide a figure when its source is unavailable.
- **Do** keep field and action heights at 54px and 56px (50px and 52px on short laptops).
- **Do** keep the briefing-board tokens scoped to their surface (`--l-*` on `.login-shell`) until the user approves an app-wide rollout.

### Don't:
- **Don't** fall back to the category default of a centred card floating on a gradient with a stock hero.
- **Don't** put more than one solid orange fill in a view.
- **Don't** set body copy or input text in Chakra Petch.
- **Don't** use hard offset shadows; depth here is tonal plus soft ambient shadow and state glow.
- **Don't** add eyebrow or kicker labels above headings. The incumbent app's `.eyebrow` class is a pre-existing defect, not part of this system.
- **Don't** restyle the match or round pages into this world, or mix its tokens with the incumbent `:root` palette, without the user's decision.
