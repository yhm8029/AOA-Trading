# Coding and research rules

- This is a LOCAL retrospective research viewer, not an exchange client or prediction engine.
- Never commit, upload, or log private input CSV/ZIP/trade records or personal notes to public services.
- Never generate synthetic candles in the real application. Synthetic tests must say SYNTHETIC.
- Keep BitMEX execution prices separate from Binance spot OHLCV and volume.
- Preserve original event type, source file, source row and group order identity.
- Group quantity/VWAP are not instantaneous first-fill facts. Interleaved before/after snapshots must not be forced to reconcile.
- Keep first/last endpoints together; don't double-count.
- No inferred Long/Short from price. Unverified mapping or classifications remain unknown.
- Missing/invalid/conflicting candles stay missing. Aggregate only complete UTC-aligned 1m groups.
- Display-only timezone conversion; no timestamp shifting.
- No post_* fields or future episode_max_qty as live signals. Imported labels can be retrospective only.
- Do not call CLOSE with a nonzero residual a full close. CUT/FLIP are research hypotheses.
- Keep localhost host/origin validation, write token, CSP and no arbitrary path or URL APIs.
- UI uses textContent for imported text; never innerHTML.
- General runtime must remain Python stdlib + pinned official local chart bundle.
- Before shipping: Python unittest, Node test, real Chromium smoke test and package checks. Report what actually ran; do not invent test results.
- Read docs/DATA_CONTRACTS.md before changing import or financial classifications.
