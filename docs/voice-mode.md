# Practice Room Voice Mode

Practice Room keeps the same text composer and session in both modes, with one hold-to-talk microphone control. Hold the microphone (or hold Space/Enter while focused) to speak for up to 90 seconds. Use the **Tự động gửi** switch to the right of the microphone: on sends a nonempty transcript on release; off places it in the composer for review and editing before pressing **Gửi**. The switch supports Space/Enter and wraps with the microphone on narrow screens. The choice is saved in localStorage when available and applies in both modes. The default in both modes is **Tự động gửi khi thả tay**.

The round phone button toggles conversation mode without restarting the session. Conversation mode also plays new customer replies automatically, regardless of the send setting. Text input remains available in both modes. The microphone turns green while recording; empty recognized speech shows a hint without sending or replacing the current draft. Voice controls are disabled when the session ends or stops for advisor misconduct.

Both modes use the existing `/practice/{session_id}/message` path for the LangGraph customer, checkpoint, transcript, and evaluation. Customer messages have a speaker button for manual playback. Voice mode also plays each new customer reply automatically. The public scenario summary exposes only `voice_gender`, inferred from the existing customer title, to select the matching Vietnamese WaveNet male (`vi-VN-Wavenet-B`) or female (`vi-VN-Wavenet-A`) voice consistently for the session. An unrecognized title leaves the voice unset and playback reports a clear error instead of guessing. Browser autoplay restrictions may require clicking the speaker button.

## Backend configuration

Set these only on the backend (Render secret environment settings in a hosted deployment, or an untracked local `.env` for Docker):

```text
GROQ_API_KEY=<Groq API key>
GOOGLE_TTS_SERVICE_ACCOUNT_JSON=<single-line service-account JSON secret>
VOICE_STT_USD_PER_HOUR=0.04
VOICE_TTS_USD_PER_MILLION_CHARACTERS=16
```

Enable Google Cloud Text-to-Speech and billing in the Google project. Grant the backend identity only the access needed to synthesize speech. The Google client also accepts Application Default Credentials; for an external host, workload identity federation avoids a long-lived service-account key where available. If using the JSON secret on Render, keep the full value in Render only. Do not put either provider credential in Vercel, frontend code, Git, or logs. Both providers are optional for Text Mode, but both must be configured for the complete voice experience. The app returns an explicit service error if one is missing.

The browser sends compressed audio through the existing same-origin `/api` proxy. It is capped at 4 MB, below the documented Vercel function payload limit. The backend rejects unsupported types and larger uploads, then sends a non-streaming transcription request to Groq Whisper Large V3 Turbo with `language=vi`. It does not save recordings. A recognized transcript is persisted only when submitted: manually after review or automatically after release, according to the selected send setting. The TTS endpoint only synthesizes a customer message ID already present in an advisor-owned session; it never accepts arbitrary text from the browser.

The `practice_voice_usage` SQL table records each successful STT or TTS call with its session ID, provider, billable seconds or characters, and estimated USD. It does not contain audio, transcript text, or credentials. The manager review modal shows per-session usage and estimated cost through the manager-only `/manager/reviews/{session_id}/voice/usage` endpoint. Advisors cannot access these figures. Groq's documented minimum billed STT length is 10 seconds. The estimates use configurable list rates and do not account for free quotas, taxes, or future price changes; verify provider invoices for actual charges. SQL tables are created lazily, as with the existing Practice tables. There is no schema migration system yet.

## Failure and retry behavior

- Only microphone access denied/unavailable (`NotAllowedError` or `NotFoundError` from getUserMedia) and backend `voice_not_configured`/`voice_failed` show the **Không dùng được giọng nói** dialog. Missing browser recording support, empty transcripts, short/silent audio, and other recorder failures show an inline retry hint and leave the draft and turn unchanged.
- A failed transcription shows a retry message. The manual send setting leaves recognized text editable before sending. The automatic setting sends recognized text on release; empty recognized speech is counted as an STT call but does not advance the role-play.
- Browser playback failures, including autoplay denial and interrupted playback, only show **Nhấn nút loa để nghe lại.** inline and log console.debug; they never open a dialog or change mode. Backend TTS configuration/provider failures use the voice dialog. The saved customer reply remains available for replay.
- A `message_not_sent` failure keeps/restores the composer draft and offers **Gửi lại** for the same text. Drafts clear only after successful sending or confirmation that the advisor message was saved.
- Finish failures refresh the saved session and attempt: ended rooms disable input/recording, saved results reopen, and missing evaluations keep **Thử chấm điểm lại** available.
- If customer reply generation fails after an advisor message is saved, the Practice Room displays **Thử lại phản hồi**. Retry generates only the missing customer reply; it does not resend or reanalyze the advisor message. In voice mode, a successful retry also plays the new customer reply. Sending another message or finishing is blocked until the pending reply is resolved.
- Customer audio is cached only in the current browser view for replay, then released when leaving the room. Recording audio is not written to the database.

The recording hook has one output boundary: an audio `Blob` and duration passed to the transcription action. A future browser Silero VAD can produce a compatible blob and call that same action while retaining the Push-to-Talk control. VAD is not installed in this phase.

Provider references: [Groq speech to text](https://console.groq.com/docs/speech-to-text), [Google Cloud TTS setup](https://docs.cloud.google.com/text-to-speech/docs/get-started), [Vietnamese WaveNet voices](https://docs.cloud.google.com/text-to-speech/docs/list-voices-and-types), [Google TTS pricing](https://cloud.google.com/text-to-speech/pricing), [Vercel upload limit](https://vercel.com/docs/errors/function_payload_too_large), [future browser VAD hook](https://docs.vad.ricky0123.com/user-guide/react/).
