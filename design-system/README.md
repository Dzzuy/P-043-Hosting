VinFast Sales Coach is the interface language of the VinFast AI Sales Coach: a training and copilot platform for VinFast EV sales advisors and their managers. It has two layers that share one set of components:

- **Monochrome workspace.** Ink on warm off-white, used for manager tools and the shared primitives. It is the base the codebase calls the "Automotive monochrome design system".
- **Advisor blue.** A navy header, cool white grounds and a single electric blue. It carries the login screen's night-drive photography into every advisor screen: Home, Practice, Copilot and Knowledge.

## Content fundamentals

- **Language.** All UI copy is Vietnamese, with full diacritics. Never strip accents ("Luyện tập", not "Luyen tap").
- **Address.** Speak to the advisor as *bạn*. Customer-facing sample lines use the showroom register *anh/chị* and *em* ("Dạ, em gửi anh bảng chi tiết nhé").
- **Casing.** Use sentence case for titles, buttons and tabs: "Bắt đầu luyện tập", "Thư viện kiến thức". Use uppercase only for the hero `eyebrow` (letter-spacing .23em) and the voice-stage label.
- **Buttons.** Start with a verb and keep them short: "Thử lại", "Kết thúc", "Xem lịch sử". The loading label is always "Đang xử lý...".
- **Empty and error copy.** Say what is missing, then what to do. Defaults: "Không có dữ liệu" / "Hiện tại chưa có thông tin nào được hiển thị." and "Đã có sự cố xảy ra" / "Không thể tải dữ liệu vào lúc này. Vui lòng thử lại sau."
- **Sources.** Copilot answers cite documents. Mark them with the grounded badge ("Có nguồn trích dẫn") and never present an uncited claim as policy.
- **No emoji in UI chrome.** NoticeDialog uses the glyphs `i`, `✓` and `!` inside a tinted disc.

## Visual foundations

### Colour
- **Monochrome surfaces.** Page `bg-app`, cards `surface`, text `primary`. Secondary text is `secondary`, helper text `muted`. Hairlines are `border`; dividers inside cards are `border-light`.
- **Advisor surfaces.** Page `advisor-bg`. Cards are `surface` with a `blue-border` hairline. Inset panels use `blue-wash`, and card headers fade from `blue-wash-strong` to white at 110°.
- **Advisor ink.** Headings `ink-navy`, body `ink-body`, meta lines `ink-slate-strong`. `ink-slate` (4.4:1) is what the source uses for subtitles. It misses AA for small text, so prefer `ink-slate-strong` in new work.
- **Accent.** One blue, `blue-600`, for the send button, active toggles and icons on `blue-tint` tiles. Links use `blue-650`, outline-button text `blue-text`, and hover fills `blue-hover`.
- **Navy fills.** `navy-900` for selected chips, model badges and the Start button. `navy-850` for primary buttons inside advisor cards. The header runs from `header-blue` to `navy-950`.
- **Violet.** `violet-600` on `violet-tint` marks the roleplay entry only.
- **Status.** `success`, `warning`, `danger` and `blue-500` (info) are tones for icons and the NoticeDialog. Always pair them with a word. `warning` (3.6:1) and `blue-500` (3.65:1) are not text colours on white.
- **Muted marks.** `muted-light` is for placeholders and disabled marks only.

### Type
- **Family.** One family, the system UI stack in `sans`, with `mono` for IDs and technical values. The product ships no font files.
- **Sizes.** The scale is rem-based on 16px. `body` is 14.4px (.9rem), `small` 13.12px (.82rem) and `caption` 12px. Below `micro` (10.88px) nothing is readable.
- **Headings.** Headings tighten their tracking: `hero-title` −0.04em, `section-title` −0.035em, `card-title` −0.02em. Weights run heavy: 700–800 for titles, 600 for buttons and labels.
- **Hero.** `hero-title` sits on the photograph in white, with `eyebrow` above it.

### Spacing and layout
- **Pages.** Monochrome pages: content max 1360px, 24px gutter (16px under 768px). Advisor pages: max 1560px, gutter `clamp(24px, 5vw, 86px)`, 14–26px top padding.
- **Vertical rhythm.** Home sections are 26px apart (`space-6-5`), grids 12–14px, card padding 20–24px.
- **Breakpoints.** 1350px (header wraps), 1100px (practice grid goes to one column), 1024px (Copilot sidebar stacks), 768px and 700px (mobile header).

### Radii, borders and shadows
- **Monochrome radii.** Pills (`radius-pill`) for buttons, chips, badges, tabs and the composer. `radius-lg` for cards, `radius-md` for inputs.
- **Advisor radii.** Rectangular buttons use `radius-btn` (9px). Cards use 13–16px (`radius-card` for chat and modal), and the hero 17px.
- **Borders before shadows.** Every card has a 1px hairline. Shadows are low and tinted navy on advisor screens (`shadow-advisor-card`, `shadow-advisor-tile`) and neutral on monochrome ones (`shadow-subtle`, `shadow-card`).

### Interaction and motion
- **Easing.** Transitions use `all 0.2s cubic-bezier(0.16, 1, 0.3, 1)`.
- **Hover.** Buttons and quick cards lift 1–2px on hover. Primary buttons return to rest and darken to `black` when pressed.
- **Focus.** Inputs show a 3px ring: `rgba(0,0,0,.06)` on monochrome screens and `rgba(32,126,242,.12)` with a `blue-focus` border on advisor screens. Focusable cards use `outline: 3px solid rgba(32,126,242,.4)` with a 2px offset. Those rings are translucent and fall under 3:1. In new work, use a solid `blue-600` ring.
- **Loading.** Skeletons shimmer over 1.6s, and the spinner turns once every 0.8s.
- **Reduced motion.** `prefers-reduced-motion` turns off dialog and voice-bubble animation.

### Imagery
- **Photography.** One image, `Imagery/login-suv-fog.png`: a VinFast SUV in night fog. It sits behind the login showcase and the home hero on `navy-hero`, covered by a left-to-right navy gradient (`rgba(4,12,24,.95)` to transparent at 78%) so white type stays legible.
- **Vehicles.** Vehicle thumbnails are product shots, `object-fit: cover` with 8px corners.
- **Other content.** No illustrations or people.

## Iconography

- **Inline icons.** The UI draws Lucide-style outline icons: 24px grid, 2px stroke, round caps and joins, `stroke="currentColor"`. They come from `lucide-react` and the hand-copied set in `components/common/Icons.jsx`.
- **Sizes.** Icons render at 15–19px inside buttons and rows, and at 26–33px in icon tiles.
- **Feature icons.** The `Icons` group holds the product's standalone SVGs: 28 topic icons (car, battery, policy, fee...) and four feature marks: `danh-gia-ky-nang`, `luyen-tap-tinh-huong`, `tra-cuu-co-nguon` and `roleplay-icon`.
- **Colouring icons.** Use them as CSS masks over `currentColor` so they take the surrounding colour (`blue-600` on `blue-tint`).
- **Emoji.** Never use emoji as icons.

## Logos

- **Brand logo.** Use `Logos/vinfast-official-logo.png`, the chrome V emblem over the VINFAST wordmark, as provided. Show it on dark grounds only (header, login showcase) at 44–56px. Don't recolour or redraw it.
- **Role marks.** `advisor-logo`, `manager-logo` and `copilot-logo` are blue role marks for the login role cards and the Copilot mark. Copilot uses its mark as a mask, filled with `currentColor`.
- **Favicon.** `favicon.svg` is the app favicon: the chrome V on a dark disc.

## Not synced

- **Fonts.** None are shipped. The product uses the system stack.
- **Tokens.** Dark mode was not extracted: the codebase has only one `[data-theme="dark"]` rule, on NoticeDialog. One-off gradients and `rgba()` overlays stay literal in `bundle.css`.
- **Components.** The 14 components are static renditions styled by `bundle.css`; no React bundle was built. View-level screens (`CopilotWorkspace`, `PracticeRoom`, `ManagerReviewView`...) were not carded. The 62 inline icons in `components/common/Icons.jsx` are not split out as files.
