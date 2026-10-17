# Chip

Toggleable pill used as a filter or segment selector.

**Source:** `.chip` in `index.css` and `.practice-filter-group button` in the practice catalog. Static rendition.

## Usage
- Monochrome chip: `surface` with a `border` hairline and `secondary` text. Active state fills `primary` with `white` text.
- Advisor filter chip: `.chip-filter`. Selected state fills `navy-900` with a soft navy shadow.
- One chip in a row is active at a time unless the row is labelled as multi-select.
- The consumer supplies the label, the active state and an `onClick`.
