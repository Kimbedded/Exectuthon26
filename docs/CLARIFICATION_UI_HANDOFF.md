# Meaning clarification and dashboard update

Prepared against GitHub main `1f2c653` (after Satyam's `46e7ef1`). This is a source update, not a deployment or a live-model accuracy result. Kim's gateway retries, audio pipeline, dictionary, archive, and firmware files are retained.

## Requested behavior

| Input | Behavior before translation |
| --- | --- |
| Lets have dinner later, can you make it? | Ask: attend, or prepare/cook it? |
| Lets have dinner later, can you make it at 8? | Use attendance; translate directly. |
| Lets have dinner later, can you make it without salt? | Use preparation/cooking; translate directly. |
| Check the ground. | Ask: electrical grounding, or physical ground? |
| Check the ground rail. | Use electrical grounding; translate directly. |
| Check on the ground beneath your feet. | Use physical ground; translate directly. |

These routing cases use reviewed English evidence rules. They demonstrate the intended interaction; passing them is not evidence that Qwen independently understands all ambiguity. Other sentences still use the existing general model resolver. Generic dinner/later/tonight clues alone deliberately leave “make it” unresolved. Current-source constraints outrank contradictory older context. Conflicting evidence requires a choice.

## Meaning choices and likelihood

- `/context/resolve` returns the existing question, two `options`, `option_contexts`, and an optional `likelihood` object.
- `likelihood.method == "model_vote_share"` means actual sampled choices were counted. `shares` align with the original option order. `valid_samples` and `requested_samples` describe the sample count; `calibrated` is false.
- The default is two samples in each option order (four calls) for unresolved, specific choices only. `IDK_CONTEXT_VOTE_SAMPLES=1..4` sets samples per order. This adds model work and must be timed on the board. Clear reviewed examples skip this ranking work.
- Invalid responses are not votes. With fewer than two usable votes or an upstream failure, display “Likelihood not measured,” with no numbers. A useful question remains usable when estimates fail.
- A 100% vote share can still be wrong. Agreement never suppresses a required speaker clarification. No labeled calibration dataset or corpus-derived meaning probabilities have been added.
- `translation_confidence` stays null. Model agreement is not calibrated translation accuracy. Existing green-LED firmware and its confidence gate are preserved; this update does not manufacture confidence to turn the green LED on. Alternative `probability` is a legacy model-preference field, not accuracy.
- A user choice is passed as `context_selection`. The translator must not rerank and overwrite that choice. Resolve first, translate second; no prewritten sentence translation is used by the live service.

## Dashboard

Light background, violet primary action, readable conversation and translation panels, English labels, explicit loading/empty/error states, responsive layout, keyboard 1/2 choices, stable choice elements during polling, reduced-motion support, and existing dictionary/Save/Review controls. No search bar, font CDN, or new runtime package is needed.

Conversation style is now an optional preference. It no longer blocks the first analysis with a Casual/Professional question. Broad style alone still cannot resolve a word meaning.

“Change meaning” reopens the current frozen result's choices. It clears that result and blocks saving until retranslation finishes. Snapshot IDs and generation checks prevent an old choice/result replacing a new one. Resolved user choices clear the red ambiguity state. Word recall and physical knob actions remain wired through the existing handlers.

New static assets must be served from the same active directory:

- `hardware/live_ui/dashboard.html`
- `hardware/live_ui/dashboard.css`
- `hardware/live_ui/dashboard.js`
- `hardware/live_ui/clarification_view.js`

Also update `dashboard_server.py`, the backend context/catalog/translation/ranking modules, and the new `backend/phrase_context.py`. Updating only HTML is insufficient.

## Verify on Satyam's Mac

From the repository root, using the existing environment:

```bash
~/Desktop/idk-button-backend/.venv/bin/python -m unittest discover -s backend/tests
~/Desktop/idk-button-backend/.venv/bin/python -m unittest discover -s hardware/tests
```

For an interactive preview without Arduino, FastAPI, or a model:

```bash
python3.13 hardware/live_ui/preview_clarification.py
```

Open `http://127.0.0.1:8010`. Stop any older preview on that port first with Control+C. The banner explicitly identifies sample translations. Preview saving is disabled; these examples do not enter the user's database. No estimates are fabricated for the preview. `--port 8011` can use another port.

## Deploy and verify on Kim's Mac

Pull the shared commit normally. Update the actual active runtime copy if it is outside the Git checkout, including all new assets and modules. Restart FastAPI and the dashboard using the existing Python, ADB serial, model endpoint, and firmware configuration. Keep a single backend worker for the shared model lock.

Try all six sentences with real spoken audio, then inspect both the transcript and actual Korean translation. For ambiguous cases, choose each meaning in a separate run and confirm the translated meaning follows the selected option. Check live vote sample counts and latency; do not label them accuracy.

Also test: changing the meaning after a completed result, new speech during a pending question, an old snapshot choice, a blank recording, New conversation, wordbook recall, knob selection/click/hold, LEDs, playback, Save, and Review. Existing `tools/check_translation_context.py` can print a failing snapshot for diagnosis.

## Validation performed here

115 backend/hardware unit tests passed with mocked inference and local temporary data. A DOM harness exercised the real HTTP preview handlers for all six examples, changed meanings, checked measured/unavailable vote rendering, stable focus, safe text rendering, and Save/loading/non-speech/reset states. Syntax and whitespace checks passed.

The browser renderer was unavailable, so responsive layout has not received a screenshot-based visual check here. Real microphone quality, NPU latency, sampled vote behavior, and translation correctness still require Kim's running board. Preview Korean sentences are sample data, not model outputs or an accuracy evaluation.
