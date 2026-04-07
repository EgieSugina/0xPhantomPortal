# Design System Document: Tactical Noir

## 1. Overview & Creative North Star: "The Terminal Authority"
The North Star for this design system is **"The Terminal Authority."** We are moving away from the generic, bright SaaS aesthetic toward a high-fidelity, "Dev-Ops" editorial experience. It is designed to feel like a high-end command center—secure, technical, and hyper-efficient.

The interface breaks the "template" look through **Tonal Layering** and **Intentional Asymmetry**. We prioritize high-contrast action points against a void-like depth. This isn't just a dark mode; it is a curated environment where information emerges from the shadows only when necessary, using vibrant accents to signal state and priority.

---

## 2. Colors: Depth and Luminance
The palette is rooted in a deep, near-black purple (`#0d0d16`) that provides more sophistication than a pure hex black. 

### The "No-Line" Rule
**Explicit Instruction:** Do not use 1px solid borders to section off the UI. Structural definition must be achieved through background shifts. 
- A card should not be "outlined"; it should be a `surface-container-low` block sitting on a `surface` background. 
- Use the **Surface Hierarchy** to nest depth:
    - **Base:** `surface` (#0d0d16)
    - **Sectioning:** `surface-container` (#191924)
    - **Interactive Elements:** `surface-container-high` (#1f1e2b)

### The "Glass & Gradient" Rule
To elevate the "hacker" aesthetic, use Glassmorphism for floating overlays (e.g., Modals or Popovers). Apply `surface-bright` with a 60% opacity and a `backdrop-blur` of 20px. 
For main CTAs, do not use flat fills. Apply a subtle linear gradient from `primary` (#aca3ff) to `primary_dim` (#6f5fea) at a 135-degree angle to give buttons a "glowing" hardware feel.

---

## 3. Typography: Tech-Editorial Hybrid
We use a dual-font strategy to balance technical precision with modern readability.

*   **Display & Headlines (Space Grotesk):** This is our "mechanical" voice. The wide apertures and geometric construction feel like a modernized terminal. Use `display-lg` for impactful entry points and `headline-sm` for section headers.
*   **Body & Labels (Manrope):** A clean, workhorse sans-serif. It provides high legibility for dense technical data. Use `body-md` for standard descriptions and `label-sm` for metadata or "hacker-style" tags.

**Hierarchy Note:** Always maintain a significant scale jump between headlines and body text to create an "editorial" feel. If a headline is `headline-lg`, the supporting text should skip two levels down to `body-md`.

---

## 4. Elevation & Depth: Tonal Stacking
Standard shadows are forbidden. We use the **Layering Principle** to convey hierarchy.

*   **Tonal Layering:** Depth is achieved by "stacking" surface tiers. Place a `surface-container-lowest` (#000000) card inside a `surface-container` (#191924) wrapper to create a "recessed" look, or `surface-container-highest` to create a "lifted" look.
*   **Ambient Shadows:** If an element must float, use a shadow with a 40px blur, 0% spread, and 8% opacity using the `primary` color token. This creates a "glow" rather than a shadow.
*   **Ghost Borders:** For accessibility in complex forms, use the `outline_variant` token at **15% opacity**. This provides a "suggestion" of a container without breaking the seamless aesthetic.

---

## 5. Components

### Buttons & Actions
*   **Primary Action:** Use the `secondary` (#00fd93) token for "Positive/Go" actions (e.g., Connect, Start). High-contrast black text (`on_secondary_fixed`) is mandatory. Use `rounded-sm` (0.125rem) for a sharp, technical look.
*   **System Action:** Use `primary` (#aca3ff) for configuration and neutral logic. 
*   **Danger Action:** Use `error` (#ff6e84) with a subtle outer glow of the same color at 10% opacity.

### Tactical Cards
*   **Rules:** No borders. No dividers. 
*   **Styling:** Use `surface-container-low` for the card body. Header text should use `title-sm` in `primary` color. 
*   **Spacing:** Use generous internal padding (`1.5rem`) to allow the "dev-ops" data to breathe.

### Input Fields & Terminal Prompts
*   **Style:** Recessed appearance using `surface-container-lowest`. 
*   **Focus State:** Instead of a thick border, use a 1px `secondary` (#00fd93) "Ghost Border" and a subtle glow.
*   **Typography:** All input text should be `label-md` to mimic terminal entry.

### Chips & Status Indicators
*   **Status Dots:** Use `secondary` for "Online," `error` for "Offline," and `primary` for "Standby." 
*   **Nesting:** Place chips inside `surface-container-highest` containers to ensure they pop against the deep background.

---

## 6. Do's and Don'ts

### Do:
*   **Do** use `secondary` (#00fd93) sparingly. It is a "power" color meant for final actions.
*   **Do** leverage asymmetry. Align headers to the left and actions to the far right with significant negative space between them.
*   **Do** use `surface_container_highest` for hover states on list items to create a "light-up" effect.

### Don't:
*   **Don't** use pure white (`#ffffff`) for text. Use `on_surface` (#ece9f7) to reduce eye strain and maintain the "noir" atmosphere.
*   **Don't** use standard 1px dividers. If you need to separate content, use a 16px or 24px vertical gap or a subtle shift in surface color.
*   **Don't** use large border-radii. Keep to `sm` (2px) or `none` (0px) for most containers to maintain the "technical/hardware" feel. Only use `full` for status pips or circular icon buttons.

---

## 7. Signature Pattern: The "Data Pulse"
When a process is active (e.g., "Port Forwarding"), do not use a standard loading spinner. Instead, apply a slow pulse animation to the `secondary` (#00fd93) accent color of the associated card. This reinforces the "technical/live" nature of the system.