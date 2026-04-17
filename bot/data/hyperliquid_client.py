from __future__ import annotations

import httpx

INFO_URL = "https://api.hyperliquid.xyz/info"


class HyperliquidClient:
    def __init__(self, timeout: float = 10.0) -> None:
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HyperliquidClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def meta_and_asset_ctxs(self) -> tuple[list[dict], list[dict]]:
        """Return (universe, asset_contexts) for all perpetuals.

        universe[i] pairs with asset_contexts[i]. Each asset context contains
        dayNtlVlm, openInterest (in coins), funding, markPx, premium, etc.
        """
        r = self._client.post(INFO_URL, json={"type": "metaAndAssetCtxs"})
        r.raise_for_status()
        meta, ctxs = r.json()
        return meta["universe"], ctxs
