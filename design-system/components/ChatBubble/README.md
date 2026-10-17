# ChatBubble

Message bubbles for Copilot and roleplay conversations.

**Source:** `.practice-room-bubble`, `.copilot-assistant-message` and `.chat-bubble-*` in `index.css`. Static rendition.

## Usage
- Incoming bubbles (customer or assistant) have a `#f7faff` fill, an `#e0eafa` hairline and `ink-body` text. Corners are 14/14/14/4, with the flat corner on the speaker's side.
- The outgoing (advisor) bubble is a 135° gradient from `blue-750` to `navy-800` with `white` text, corners 14/14/4/14 and `shadow-bubble`.
- The speaker label is .72rem/700 at 75% opacity.
- The monochrome workspace uses `.chat-bubble-ai` (white card) and `.chat-bubble-user` (`primary` fill).
