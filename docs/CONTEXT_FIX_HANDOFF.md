# Translation context repair

Based on main **880eabc**, retaining Kim’s model-gateway retry fixes. This patch fixes input handling and decision handling; it does not establish the model's translation accuracy. It preserves the newer chat reset, live transcript, wordbook, audio, hardware, and dictionary UI code.

## Problems reproduced

- Sentence mode preferred the live transcript frozen at button press over newer preceding sentences in the completed ASR snapshot. A snapshot saying `This electrical circuit has intermittent voltage. Check the ground.` could therefore send earlier construction/soil text as its context.
- A failed context analysis was relabeled as resolved using only the chat category, such as `Professional`. Translation then continued without a supported word sense.
- That category was also placed inside the conversation sent to the context resolver, allowing a category label to be mistaken for spoken evidence.
- A mixed model response containing both a topic and clarification choices had its choices silently deleted, making an inconsistent decision appear resolved. Conversely, a valid self-contained greeting could be rejected because its supporting quote was in the source rather than previous conversation.
- Single-letter units such as `5 V.` were treated as personal initials, merging a voltage-limit sentence into the next translation target. The Python and browser parsers had the same issue.
- Conflicting electrical and physical cues still forced an electrical `ground` hint when using the translation endpoint directly.

## Resulting behavior

The completed snapshot's own preceding sentences now take priority, with at most four before the source. When it contains only the source, the frozen sentence ledger still supplies earlier context. Time mode keeps its existing frozen-window behavior. No live update after the button press is used to change a pending request.

The resolver sees actual conversation separately from the persistent Casual/Professional preference. Valid specific clarification questions still work. If analysis cannot produce a supported decision, the dashboard clears translation options, keeps saving blocked, and asks the user to say another sentence before analyzing again. It does not present the broad chat category as a resolved meaning.

Consistent resolved/clarification model branches are validated as returned. Valid evidence in a self-contained source remains accepted. Contradictory branches are rejected rather than coerced into a topic.

All translation variants receive the same explicit policy: use the selected sense first when supplied, otherwise use nearby relevant context; preserve negation, numbers, units, actors and conditions; translate only the source. Contradictory `ground` cues no longer generate a forced electrical hint. This is prompt/input handling, not a guarantee that Qwen will obey every instruction.

## Apply and deploy on Kim's Mac

1. Save or commit current local work, then pull the team's current main normally. Do not reset or discard work to apply this patch.
2. Apply the provided guarded updater from the checkout. It first runs `git apply --check`, backs up affected files, and stops if the patch cannot apply cleanly. It makes no commit, push, server restart, firmware change or model change.
3. Review the diff and run the existing backend/hardware checks in the established Python environment.
4. Update the code actually used by the running processes. If the dashboard still runs from a separate runtime directory, merge the small changes to `dashboard_server.py`, `transcript_stream.py` and `transcript_view.js` there. The active backend needs the changes in `context_resolution.py` and `translate_sentence.py`. Preserve any newer local edits.
5. Restart the existing FastAPI and dashboard using the same model endpoint, Python environment and ADB configuration.

The updater also adds `tools/check_translation_context.py`. From the checkout, capture the failed live example with:

```bash
python tools/check_translation_context.py
```

This default command only reads `/api/state`; it does not run AI or alter the conversation. Its output includes the captured transcript, selected context, context decision and actual translation.

To isolate translation/context inference from the microphone:

```bash
python tools/check_translation_context.py --pairs
```

This makes real local API/model calls for electrical, construction and insufficient-context versions of `Check the ground.`. A fluent Korean speaker must check the actual output for the first two cases. The third should ask a clarification question and skip translation. These are diagnostic examples, not a general translation benchmark. Then repeat the scenarios with real speech and verify transcript, selected context, translated meaning, no-speech behavior, word options and Save/Review.

## Validation completed here

93 backend/hardware unit checks passed using mocked model responses and temporary SQLite databases. Added coverage includes the stale electrical/construction context, five-sentence limit, negation and voltage boundaries, unresolved-context blocking, category/evidence separation, a valid self-contained greeting, mixed decision rejection and conflicting term hints. A JavaScript check covered the same voltage boundary and retained title abbreviation handling.

No live Qwen or Arduino is attached to this environment. Actual translated meaning and live microphone behavior still require verification on Kim's setup. If inputs and selected meanings are correct but the model still mistranslates, capture the failing case before further prompt/model changes.
