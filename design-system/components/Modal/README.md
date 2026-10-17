# Modal

Centered dialog with a title bar, close button and scrollable body.

**Source:** `frontend/src/components/common/Modal.jsx`. Static rendition.

## Props
| prop | type | default |
| --- | --- | --- |
| `isOpen` | boolean | |
| `onClose` | () => void | Called on Escape, backdrop click and the close button. |
| `title` | ReactNode | |
| `children` | ReactNode | |
| `maxWidth` | number | `640` |

## Usage
- Backdrop: `rgba(0,0,0,.65)` with a 4px blur. The panel is `surface` with `radius-card`, `shadow-modal` and at most 90vh tall.
- Header: 18px × 24px padding with a `border` divider. The title is 1.1rem/700. The close icon is 18px in `muted` and labelled "Đóng".
- Body scroll locks while the modal is open. Use NoticeDialog for confirmations instead.
