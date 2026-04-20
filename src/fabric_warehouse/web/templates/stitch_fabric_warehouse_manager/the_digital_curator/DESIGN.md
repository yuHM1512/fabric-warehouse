# Design System Document: The Digital Curator

## 1. Overview & Creative North Star
This design system is built upon the philosophy of **"The Digital Curator."** In the context of Fabric Warehouse Management, we are moving away from the cluttered, industrial aesthetic of legacy ERPs. Instead, we treat textile inventory as a collection of high-end artifacts. 

The Creative North Star is **Academic Editorial**: the UI should feel like a premium digital monograph. We achieve this through "intentional breathing room," sophisticated tonal shifts instead of rigid lines, and a dramatic typographic scale that establishes a clear, authoritative hierarchy. By utilizing glassmorphism and a monochromatic base, we create a calm environment where the textures and colors of the fabrics themselves become the primary visual interest.

---

## 2. Colors & Tonal Layering

### The "No-Line" Rule
**Explicit Instruction:** Use of 1px solid borders for sectioning or containment is strictly prohibited. Boundaries must be defined through **Tonal Layering**. If two areas need separation, they must be distinguished by a shift in background tokens (e.g., a `surface-container-low` element sitting on a `surface` background).

### Surface Hierarchy & Nesting
Treat the interface as a physical stack of premium paper or frosted glass. Use the hierarchy below to create depth:
*   **Base Layer (`surface` / #f8f9fa):** The "canvas" of the application.
*   **Secondary Sections (`surface-container-low` / #f3f4f5):** For large layout blocks or sidebar backgrounds.
*   **Content Containers (`surface-container-lowest` / #ffffff):** For primary data cards and high-priority content.
*   **Tertiary Accents (`surface-container-high` / #e7e8e9):** For subtle grouping within white cards.

### The Signature "Soul" Gradient
To inject professional polish into an otherwise monochromatic environment, use the **Primary 135 Gradient**:
*   **Value:** `linear-gradient(135deg, #0040a1 0%, #0056d2 100%)`
*   **Usage:** Reserved for primary CTAs, hero headers, and progress indicators. It provides a "liquid" contrast against the flat, matte surfaces of the warehouse data.

---

## 3. Typography
The typography scale is designed to feel like a high-end publication. We pair the geometric authority of **Manrope** with the utilitarian precision of **Inter**.

*   **Display & Headlines (Manrope):** 
    *   **Display-LG (56px):** Used for total inventory valuations or warehouse titles.
    *   **Headline-MD (28px):** Used for section headers and fabric category titles. 
    *   *Direction:* Use tight tracking (-2%) for headlines to give them a "custom-set" editorial feel.
*   **Body & Labels (Inter):** 
    *   **Body-LG (16px, 1.6 line-height):** All descriptive text and fabric specifications. The 1.6 line-height is mandatory to ensure the "Academic" readability of long-form data.
    *   **Label-MD (12px, Bold):** Used for metadata, SKU numbers, and status indicators.

---

## 4. Elevation & Depth

### Cloud Shadow
Traditional "Material" shadows are too heavy for this aesthetic. When a floating element (like a modal or a fabric detail pop-over) is required, use the **Cloud Shadow**:
*   **Value:** `0px 20px 40px rgba(25, 28, 29, 0.05)`
*   **Context:** This shadow should feel like ambient light hitting a surface, not a harsh drop shadow.

### Glassmorphism
For floating navigation bars or contextual overlays, use semi-transparent surfaces to maintain the warehouse's spatial awareness:
*   **Effect:** `surface-container-lowest` at 80% opacity with a `24px` backdrop-blur. 
*   **Goal:** This allows the "colors" of the fabric rolls in the background to bleed through softly, softening the interface.

### The "Ghost Border" Fallback
If accessibility requirements (WCAG) demand a border for a specific interactive element, use the **Ghost Border**:
*   **Value:** `outline-variant` (#c3c6d4) at **15% opacity**. 
*   **Rule:** Never use 100% opaque borders.

---

## 5. Components

### Buttons
*   **Primary:** Uses the 135-degree Signature Gradient. Pill-shaped (`rounded-full`). No shadow. On hover, increase the gradient brightness slightly.
*   **Secondary (Ghost Pill):** No background, no border. On hover, apply `surface-container-high`.
*   **Tertiary:** `on-surface-variant` text with a subtle underline that appears only on hover.

### Input Fields
*   **Style:** Background set to `surface-container-low`. No borders.
*   **Corners:** `md` (0.75rem).
*   **State:** On focus, the background shifts to `surface-container-lowest` and a subtle 2px bottom-bar of `primary` appears.

### Fabric Inventory Cards
*   **Structure:** No dividers. Use `1.5rem (xl)` padding to separate fabric name from the SKU.
*   **Visuals:** Use high-resolution swatches. The swatch should have a `lg` (1rem) corner radius.
*   **Nesting:** Place the white card (`surface-container-lowest`) on a `surface` background to create natural lift.

### Lists & Data Tables
*   **No Dividers:** Separate rows using a background toggle of `surface` and `surface-container-low`.
*   **Vertical Space:** Increase row height to `72px` to emphasize the editorial "Curator" feel.

---

## 6. Do's and Don'ts

### Do:
*   **Embrace Asymmetry:** Align high-level stats to the left and primary actions to the far right with significant whitespace between them.
*   **Use Subtle Shifts:** If a section feels "lost," try changing the background color by just one tier (e.g., from `surface` to `surface-container-low`) before reaching for a shadow.
*   **Curate Information:** Only show the most vital fabric specs (Weight, Composition, Yardage) by default. Hide secondary data in glassmorphic drawers.

### Don't:
*   **Don't use 1px lines:** Even for tables. Use whitespace and tonal shifts instead.
*   **Don't use pure black:** Use `on-surface` (#191c1d) for text to maintain the "ink on premium paper" look.
*   **Don't crowd the edges:** Ensure a minimum of `2rem` (32px) padding on all main containers. The "Editorial" look fails if the content feels "trapped."