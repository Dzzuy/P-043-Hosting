# TopHeader

Sticky 72px application header with the brand lockup on the left and pill nav tabs.

**Source:** `frontend/src/components/layout/Header.jsx`, plus the `.top-header` and `.nav-tab-item` rules (advisor overrides) in `index.css`. Static rendition.

## Usage
- Ground: a 90° gradient from `header-blue` through `#0c2442` to `navy-950`, solid from 50% to the right edge.
- Brand: the 44px VinFast logo, the `brand-title` (1.05rem/700, white) and a `brand-subtitle` in `header-subtext`.
- Tabs: inactive tabs use `header-text`. The active tab is white with `#09214a` text, a blue glow and a 3px gradient underline.
- Below 700px the brand title shrinks to .84rem and the logout label hides.
