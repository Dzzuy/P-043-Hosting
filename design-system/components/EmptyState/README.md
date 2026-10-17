# EmptyState

Centered placeholder for an empty list or view, with an optional icon and action.

**Source:** `frontend/src/components/common/EmptyState.jsx`. Static rendition.

## Props
`icon` (ReactNode), `title` (default "Không có dữ liệu"), `description` (default "Hiện tại chưa có thông tin nào được hiển thị."), `action` (ReactNode, usually an outline Button).

## Usage
- White box with a `border` hairline and a 14px radius, padded 48px × 24px.
- The title is 1.05rem/600 in `primary`. The description is .88rem in `muted`, at most 420px wide.
- Advisor pages use a dashed variant: a 1px dashed `blue-border-strong` border on `#f7faff`.
