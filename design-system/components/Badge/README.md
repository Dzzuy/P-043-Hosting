# Badge

Small pill label for status, category and metadata.

**Source:** `frontend/src/components/common/Badge.jsx` (`default`, `dark`, `highlight`, `success`) plus the advisor badges in `index.css` (model, difficulty, grounded, document status). Static rendition.

## Props
| prop | type | default |
| --- | --- | --- |
| `variant` | `'default' \| 'dark' \| 'highlight' \| 'success'` | `'default'` |
| `children` | ReactNode | |

`success` currently renders the same as `default`. Use `.badge-status` (`success-text` on `success-bg`) for a real success state.

## Usage
- Use `caption` type (12px/600), `radius-pill`, 3px × 8px padding.
- Model names sit in `.badge-model` (`navy-900`); difficulty in `.badge-difficulty` (`blue-tint-chip`).
- Use `.badge-grounded` only on Copilot answers that cite sources.
- Always pair a status colour with a word. Never rely on colour alone.
