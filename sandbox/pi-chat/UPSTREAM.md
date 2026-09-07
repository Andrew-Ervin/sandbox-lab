Source: https://github.com/iqbalabiyoga/pi-vscode-chat
Commit: 7254553b9b8fcb8701920693c56c3af2be9b317e
License: MIT (included)
Local patches: sanitize Markdown, remove remote webview images, disable unmanaged install/auth wizards, configure the executable externally as ori-lab; default to the secondary sidebar; report edit/terminal/Pi activity for idle shutdown. The upstream UI is retained.
Build: scripts/build_pi_chat.mjs

The local `scripts/patch_pi_dictation.py` patch adds opt-in five-minute microphone dictation, using `sandbox/pi-dictation` and the authenticated transcription gateway.
