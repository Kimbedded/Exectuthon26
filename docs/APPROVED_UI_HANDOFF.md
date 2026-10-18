# Approved Qualcomm / Snapdragon / Arduino dashboard

This applies the design Satyam approved in the interactive preview. The exact preview CSS forms the base of `dashboard.css`, with its blue header strip, Arduino VENTUNO Q label, Qualcomm/Snapdragon colour references, typography, spacing, two-panel layout, red clarification accents, and teal word details. The live page adds working device controls and diagnostics in closed disclosure sections.

The primary Conversation and Wordbook tabs now show the live conversation and actual saved SQLite data. Existing Save/Review, model-vote labels, context choices, keyboard choices, physical knob actions, stream updates and no-speech guards remain connected to their existing handlers. No backend interpretation or database module changes are included in this styling update.

Icons are a local subset of the already-installed Lucide library; its ISC license is included in `hardware/live_ui/LICENSE-Lucide.txt`. No font, icon, or styling CDN is needed while using the app offline.

## Apply and preview on Satyam's Mac

The guarded installer expects the previous meaning-choices update to be installed. It checks every patch first, backs up changed files, and refuses conflicting edits before writing. Reapplying it is a no-op. It does not commit, push, or restart anything.

Stop the running preview with Control+C, apply the updater, then restart:

```bash
cd ~/Desktop/Exectuthon26
python3.13 ~/Downloads/apply-approved-ui.py
python3.13 hardware/live_ui/preview_clarification.py --port 8011
```

Open `http://127.0.0.1:8011`. The same six sample phrases are in the example dropdown. The banner identifies sample data, and preview saving remains disabled. Sample word meanings let the preview demonstrate the approved dictionary layout without a database. The live page uses the full dictionary API.

## Deploy on Kim's Mac after the team commit

Pull the shared commit normally. Update the actual running copy if it lives outside the repository. Copy all updated UI files, the new icon module and license, and `dashboard_server.py`. Restart the dashboard; an old running Python process will not know the new icon asset route even if the HTML has refreshed. Preserve the existing Python environment, ASR, model endpoint, ADB serial, firmware and database.

The header identifies technology and colour inspiration; it does not change the board platform or model runtime. Typography, styling, and sample text do not improve or validate model accuracy. Test actual speech and translation quality on the board.

## Verification

The UI integration checks exercise the six real preview HTTP flows, both meaning choices, reopening a meaning, real Save endpoint wiring, Wordbook navigation, dictionary selection, measured/unavailable vote states, safe text rendering, loading, non-speech and chat reset. The approved base CSS is compared directly to the preview's CSS. No screenshot-based visual verification or real board validation is claimed.
