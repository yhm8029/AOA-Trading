# Third-party components

## Lightweight Charts™ 5.0.9

TradingView Lightweight Charts™
Copyright (c) 2025 TradingView, Inc.
https://www.tradingview.com/

Licensed under Apache License 2.0. The unmodified standalone build, LICENSE and upstream NOTICE are downloaded from the fixed npm package and retained under `vendor/` by `scripts/prepare_vendor.py`. The npm tarball's SHA-512 integrity value is verified; per-file SHA-256 values are recorded. The original NOTICE and LICENSE in the distribution remain authoritative. The application UI includes a visible TradingView link and chart attribution.

This is an independent viewer, not TradingView.com and not endorsed by TradingView. Their library license does not grant access to TradingView's hosted chart data or account APIs.

## Public market data and imported source records

Public market data is requested from Binance only on an explicit user action. Source trade records are supplied locally by the user. These records are not committed and are not covered by the application's MIT license. No ownership of these records is asserted.

## Development-only tools

Playwright and GitHub Actions are used to run tests. Browser screenshots in CI use clearly synthetic fixtures, not the user's AOA history. They are not analytical evidence about the trader.
