# Button

Pill-shaped action button with five variants: `primary`, `white`, `outlineDark`, `outline` and `ghost`.

**Source:** `frontend/src/components/common/Button.jsx` with the `.btn-*` rules in `index.css`. Static rendition: the preview is plain markup styled by `bundle.css`.

## Props
| prop | type | default | notes |
| --- | --- | --- | --- |
| `variant` | `'primary' \| 'white' \| 'outlineDark' \| 'outline' \| 'ghost'` | `'primary'` | Unknown values fall back to primary. |
| `loading` | boolean | `false` | Disables the button and swaps the label for a 14px spinner and "Đang xử lý...". |
| `disabled` | boolean | `false` | Renders at 50% opacity with `not-allowed`. |
| `icon` | ReactNode | `null` | Placed before the label, gap 6–8px. |
| `children` | ReactNode | | The label. |

## Usage
- Use `primary` (`primary` fill, `white` text, `radius-pill`) for the one main action on a surface.
- Use `white` and `outlineDark` only on dark grounds (`dark-card`, the hero photograph).
- Use `outline` for secondary actions and `ghost` for tertiary actions in toolbars.
- Inside advisor (blue) cards the same classes switch to `radius-btn` corners: primary fills `navy-850` (hover `#1552a1`), outline text turns `blue-text`.
- Labels are Vietnamese, sentence case, verb first ("Bắt đầu luyện tập", "Thử lại").
