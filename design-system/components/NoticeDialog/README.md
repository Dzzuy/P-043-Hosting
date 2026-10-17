# NoticeDialog

Accessible alert dialog with a tone (`info`, `success`, `warning`, `error`), a message and one or more actions.

**Source:** `frontend/src/components/common/NoticeDialog.jsx` and `NoticeDialog.css`. Static rendition.

## Props
| prop | type | notes |
| --- | --- | --- |
| `notice` | `{ title, message?, tone?, dismissible?, actions: [{ id, label, kind: 'primary' \| 'secondary' }] }` or `null` | `null` hides the dialog. |
| `onAction` | `(id) => void` | |
| `onClose` | `() => void` | Called only when `dismissible` is set. |

## Usage
- Tone sets `--notice-tone`: info `blue-500`, success `success`, warning `warning`, error `danger`. The icon disc is the tone at 12%.
- The dialog traps focus, focuses the primary action and restores focus on close.
- The primary action fills `blue-500` with white .86rem/600 text, which is only 3.65:1. For a fix, use `blue-600` or larger text.
- Under `[data-theme="dark"]` the panel uses `dark-card`/`dark-border`. This is the only dark-mode rule in the codebase.
