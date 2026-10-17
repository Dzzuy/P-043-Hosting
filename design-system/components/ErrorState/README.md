# ErrorState

Inline failure message with an optional retry action.

**Source:** `frontend/src/components/common/ErrorState.jsx`. Static rendition.

## Props
`title` (default "Đã có sự cố xảy ra"), `message` (default "Không thể tải dữ liệu vào lúc này. Vui lòng thử lại sau."), `onRetry` (shows an outline "Thử lại" button with a refresh icon).

## Usage
- Same box as EmptyState, padded 40px × 24px. The icon is 20px in a 36px `#f4f4f2` disc.
- Keep it monochrome. Reserve `danger` for destructive actions, not load failures.
