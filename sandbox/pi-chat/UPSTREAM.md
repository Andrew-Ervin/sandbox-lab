Source: https://github.com/iqbalabiyoga/pi-vscode-chat
Commit: 7254553b9b8fcb8701920693c56c3af2be9b317e
License: MIT (included)
Local patches: sanitize Markdown, remove remote webview images, disable unmanaged install/auth wizards, configure the executable externally as ori-lab; default to the secondary sidebar; report edit/terminal/Pi activity for idle shutdown; embed fixed packaged webview assets under a script nonce. The dictation/transcription client and bridge are patched by scripts/patch_pi_dictation.py (LAB_DICTATION). The upstream UI is retained.
Build: scripts/build_pi_chat.mjs
