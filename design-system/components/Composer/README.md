# Composer

Pill-shaped message input with a round send button, used by Copilot and the practice room.

**Source:** `.copilot-composer-form`, `.copilot-send-button` and `.practice-room-composer-form` in `index.css`. Static rendition.

## Usage
- The container is a pill with a `blue-border-strong` border and a `#f8fbff` fill. On `:focus-within` the border turns `blue-focus` and a 3px blue ring appears.
- The send button is a 38px circle in `blue-600` (hover `blue-700`, disabled `blue-disabled`).
- The practice room adds 40px round controls for dictation and voice mode. The recording state is green (`#d9f5e8` / `#138954`).
- The consumer supplies the value, the submit handler and the disabled state while a reply streams.
