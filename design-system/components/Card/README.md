# Card

The surface container. There are three families: white (monochrome), quick (advisor) and dark.

**Source:** `.card-white`, `.card-dark` and `.home-quick-card` in `index.css`. Static rendition.

## Usage
- `.card-white`: `surface`, a `border` hairline, `radius-lg`, 24px padding, `shadow-subtle`. On hover, add `.card-white-hover` (`border-hover`, `shadow-card`).
- `.card-quick`: the advisor entry tile. White fading to `#edf5ff` at 145°, 15px radius, and a 60px `icon-tile` in `blue-tint`. The roleplay variant swaps to `violet-tint`/`violet-600`. Hover lifts by 2px.
- `.card-dark`: `dark-card`, `radius-xl`, 32px padding. Use it for banners only.
- Advisor list cards (`.card-advisor`) use a `#e3edf8` hairline, 13px radius and `shadow-advisor-tile`.
- Don't add coloured left borders. The knowledge document card's 4px gradient stripe is the only exception.
