# Skeleton

Shimmering placeholder block that holds layout while data loads.

**Source:** `frontend/src/components/common/Skeleton.jsx` (`Skeleton`, `ScenarioCardSkeleton`). Static rendition.

## Props
`width` (default `100%`), `height` (default `16px`), `borderRadius` (default `6px`, i.e. `radius-sm`), `className`, `style`.

## Usage
- A 90° gradient between `#ebebe8` and `#f4f4f2` with a 1.6s shimmer.
- Mirror the real layout: use pills (999px) for badges and circles for avatars. `ScenarioCardSkeleton` is the reference composition.
