# Input

Labelled text input and select for forms, plus the advisor search field.

**Source:** `.form-group`, `.form-label`, `.form-input`, `.form-select` and `.knowledge-search input` in `index.css`. Static rendition.

## Usage
- Wrap the field in `.form-group` (6px gap) with a `.form-label` (`small` type, 600, `secondary`).
- Inputs are 42px tall with 14px horizontal padding, `radius-md` and a `border` hairline.
- Focus state: the border turns `primary` with a 3px `rgba(0,0,0,.06)` ring. Disabled inputs fill `hover` with `muted` text.
- Search inputs on advisor pages are 44px tall with 12px corners. Their focus border is `#2583ed` with a blue ring.
