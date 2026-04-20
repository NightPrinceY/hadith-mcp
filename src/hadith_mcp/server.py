"""FastMCP server: tools over ``hadith.db``."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import anyio
import numpy as np
from dotenv import load_dotenv
from fastmcp import Context, FastMCP
from fastmcp.server.lifespan import lifespan
from mcp.types import Icon
from openai import OpenAI
from starlette.requests import Request
from starlette.responses import Response

from hadith_mcp.embeddings_index import EmbeddingIndex
from hadith_mcp.grounding import GROUNDING_RULES
from hadith_mcp.grounding_state import GroundingState
from hadith_mcp.middleware_logging import ToolCallLoggingMiddleware
from hadith_mcp.openai_fallback import should_fallback_to_keyword
from hadith_mcp.query_cache import SearchResponseCache
from hadith_mcp.rate_limit import RateLimiter
from hadith_mcp.settings import AppConfig, load_app_config
from hadith_mcp.store import HadithStore

logger = logging.getLogger("hadith_mcp.server")

_MAX_HADITH_RANGE = 25
_SEARCH_APP_BASE_URL = os.environ.get("HADITH_SEARCH_APP_URL", "https://search.hadith-mcp.org").strip().rstrip("/")


def _search_client_key(ctx: Context) -> str:
    """Coarse client bucket for search rate limits (HTTP client IP when available)."""
    try:
        from fastmcp.server.dependencies import get_http_request

        req = get_http_request()
        if req.client and req.client.host:
            return f"ip:{req.client.host}"
        return "ip:unknown"
    except Exception:
        pass
    rc = ctx.request_context
    if rc is not None:
        return f"mcp:{id(rc)}"
    return "stdio:default"


def _session_key(ctx: Context) -> str:
    rc = ctx.request_context
    sess = getattr(rc, "session", None) if rc is not None else None
    return hex(id(sess)) if sess is not None else "default"


def _hadith_url(hadith_id: int) -> str:
    return f"{_SEARCH_APP_BASE_URL}/?id={hadith_id}"


def _add_hadith_url(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["url"] = _hadith_url(int(row["id"]))
    return out


def _add_match_url(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["url"] = _hadith_url(int(row["matched_hadith_id"]))
    return out


def _parse_hadith_span(
    hadith_number: int | str | None,
    hadith_number_end: int | None,
    id_in_book: int | None,
) -> tuple[int, int | None]:
    """Return ``(start_in_book, end_in_book_or_none)`` for a single id or inclusive range."""
    if hadith_number is None:
        if id_in_book is None:
            raise ValueError("Provide hadith_number or id_in_book with collection")
        hadith_number = id_in_book
    if isinstance(hadith_number, str):
        s = hadith_number.strip().replace(" ", "")
        if "-" in s:
            a, _, b = s.partition("-")
            return int(a), int(b)
        start = int(s)
        return start, hadith_number_end
    start = int(hadith_number)
    return start, hadith_number_end


@lifespan
async def _lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    cfg: AppConfig = getattr(server, "_hadith_cfg", None) or load_app_config()
    store = HadithStore(cfg.db_path)
    emb_index: EmbeddingIndex | None = None
    try:
        emb_index = await anyio.to_thread.run_sync(EmbeddingIndex.load, cfg.db_path)
        logger.info(
            "loaded embedding index rows=%s dim=%s",
            emb_index.mat.shape[0],
            emb_index.mat.shape[1],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding index unavailable: %s", exc)
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    openai_client = OpenAI(api_key=api_key) if api_key else None
    if openai_client and emb_index is None:
        logger.warning("OPENAI_API_KEY set but embedding index missing; semantic search disabled.")
    if emb_index is not None and openai_client is None:
        logger.warning("Embedding index present but OPENAI_API_KEY missing; semantic search disabled.")
    rate_limiter = RateLimiter(cfg.rate_limit_search_per_minute)
    search_cache = (
        SearchResponseCache(cfg.search_cache_max_entries)
        if cfg.search_cache_max_entries > 0
        else None
    )
    logger.info(
        "search: query_model=%s rate_limit_rpm=%s cache_max=%s",
        cfg.query_embedding_model,
        cfg.rate_limit_search_per_minute,
        cfg.search_cache_max_entries,
    )
    grounding = GroundingState()
    try:
        yield {
            "store": store,
            "config": cfg,
            "embeddings": emb_index,
            "openai": openai_client,
            "grounding": grounding,
            "search_rate_limiter": rate_limiter,
            "search_cache": search_cache,
        }
    finally:
        store.close()
        logger.info("closed database connection")


def build_server(*, config_yaml: Path | None = None) -> FastMCP:
    cfg = load_app_config(config_yaml=config_yaml)
    mcp = FastMCP(
        "hadith-mcp",
        instructions=(
            "Hadith corpus in SQLite. Call fetch_grounding_rules first when citing hadith. "
            "Never quote hadith from memory: use fetch_hadith or search_hadith. "
            "Cite with collection slug/name and id_in_book (hadith number in book). "
            "When tool responses include a hadith 'url' field, include that link in user-facing citations for quick verification. "
            "search_hadith defaults to semantic (embeddings); use mode='keyword' for substring search. "
            "Semantic search falls back to keyword on rate limits, quota/billing errors, or model/index mismatch. "
            "Cross-references are algorithmic, not scholarly isnad proof."
        ),
        icons=[Icon(src="https://hadith-mcp.org/logo.png")],
        lifespan=_lifespan,
    )
    mcp._hadith_cfg = cfg  # type: ignore[attr-defined]
    mcp.add_middleware(ToolCallLoggingMiddleware())

    async def _semantic_search(
        ctx: Context,
        query: str,
        limit: int,
        coll_filter: str | None,
    ) -> dict[str, Any]:
        cfg: AppConfig = ctx.lifespan_context["config"]
        store: HadithStore = ctx.lifespan_context["store"]
        idx = ctx.lifespan_context.get("embeddings")
        client = ctx.lifespan_context.get("openai")
        if idx is None or client is None:
            return {"ok": False, "reason": "semantic_unavailable", "results": [], "fallback": False}

        rl = ctx.lifespan_context.get("search_rate_limiter")
        if rl is not None and not rl.allow(_search_client_key(ctx)):
            return {"ok": False, "reason": "rate_limited", "results": [], "fallback": True}

        cache = ctx.lifespan_context.get("search_cache")
        cache_key = (query.strip().lower(), limit, coll_filter or "", cfg.query_embedding_model)
        if cache is not None:
            hit = cache.get(cache_key)
            if hit is not None:
                return {"ok": True, "results": hit, "cache_hit": True, "fallback": False}

        coll_id: int | None = None
        if coll_filter:
            slug = store.resolve_collection_slug(coll_filter) or coll_filter.strip()
            coll_id = store.get_collection_id(slug)

        model = cfg.query_embedding_model

        def _embed() -> np.ndarray:
            r = client.embeddings.create(model=model, input=query)
            return np.asarray(r.data[0].embedding, dtype=np.float32)

        try:
            qv = await anyio.to_thread.run_sync(_embed)
        except Exception as exc:  # noqa: BLE001
            if should_fallback_to_keyword(exc):
                logger.warning("semantic search falling back to keyword (OpenAI): %s", exc)
                return {
                    "ok": False,
                    "reason": "openai_error",
                    "fallback": True,
                    "openai_message": str(exc),
                    "results": [],
                }
            raise

        if int(qv.shape[0]) != int(idx.mat.shape[1]):
            logger.warning(
                "query embedding dim %s != index dim %s (model=%s); use a query model that matches hadith.db",
                qv.shape[0],
                idx.mat.shape[1],
                model,
            )
            return {
                "ok": False,
                "reason": "dimension_mismatch",
                "fallback": True,
                "results": [],
            }

        top = idx.topk(qv, limit, collection_id=coll_id)
        ids = [i for i, _ in top]
        scores = {i: s for i, s in top}
        rows = store.fetch_hadiths_by_ids(ids)
        results: list[dict[str, Any]] = []
        for r in rows:
            hid = int(r["id"])
            results.append(
                {
                    "hadith_id": hid,
                    "similarity": float(scores[hid]),
                    "collection_slug": r["collection_slug"],
                    "id_in_book": r["id_in_book"],
                    "english_excerpt": (r.get("english") or "")[:280],
                    "url": _hadith_url(hid),
                }
            )
        if cache is not None:
            cache.set(cache_key, results)
        return {"ok": True, "results": results, "cache_hit": False, "fallback": False}

    def _keyword_search(
        ctx: Context,
        query: str,
        limit: int,
        coll_filter: str | None,
    ) -> dict[str, Any]:
        store: HadithStore = ctx.lifespan_context["store"]
        kw_slug: str | None = None
        if coll_filter:
            kw_slug = store.resolve_collection_slug(coll_filter) or coll_filter.strip()
        rows = store.search_hadith(query, limit=limit, collection_slug=kw_slug)
        results = [
            {
                "hadith_id": int(r["id"]),
                "similarity": None,
                "collection_slug": r["collection_slug"],
                "id_in_book": r["id_in_book"],
                "english_excerpt": r.get("english_excerpt"),
                "url": _hadith_url(int(r["id"])),
            }
            for r in rows
        ]
        return {"ok": True, "results": results}

    @mcp.tool()
    def list_collections(ctx: Context) -> list[dict[str, Any]]:
        """List all collections (slug, English/Arabic names, hadith counts)."""
        store: HadithStore = ctx.lifespan_context["store"]
        return store.list_collections()

    @mcp.tool()
    def fetch_hadith(
        ctx: Context,
        hadith_id: int | None = None,
        collection: str | None = None,
        collection_slug: str | None = None,
        hadith_number: int | str | None = None,
        hadith_number_end: int | None = None,
        id_in_book: int | None = None,
        include_cross_references: bool = False,
    ) -> dict[str, Any]:
        """Fetch hadith text by global ``hadith_id`` or by ``collection`` + ``hadith_number`` (or ``id_in_book``).

        ``hadith_number`` may be an int, or a string range like ``\"1-5\"`` (inclusive). Ranges are
        capped (see ``hadiths`` list length). Set ``include_cross_references`` to attach algorithmic
        matches per returned hadith.
        """
        store: HadithStore = ctx.lifespan_context["store"]
        coll_raw = (collection or collection_slug or "").strip() or None

        def _attach_cross(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
            out: dict[str, list[dict[str, Any]]] = {}
            for r in rows:
                hid = int(r["id"])
                out[str(hid)] = [_add_match_url(m) for m in store.fetch_cross_references(hid, limit=40)]
            return out

        if hadith_id is not None and coll_raw is not None:
            return {
                "error": "Use either hadith_id alone, or collection + hadith_number — not both",
                "hadith": None,
                "hadiths": None,
                "cross_references": None,
            }
        if hadith_id is not None:
            row = store.fetch_hadith(hadith_id=hadith_id)
            if row is None:
                return {"error": "not_found", "hadith": None, "hadiths": None, "cross_references": None}
            row_out = _add_hadith_url(row)
            crs = _attach_cross([row_out]) if include_cross_references else None
            return {"error": None, "hadith": row_out, "hadiths": None, "cross_references": crs}

        if not coll_raw:
            return {
                "error": "Provide hadith_id, or collection + hadith_number / id_in_book",
                "hadith": None,
                "hadiths": None,
                "cross_references": None,
            }

        slug = store.resolve_collection_slug(coll_raw) or coll_raw
        try:
            start, end = _parse_hadith_span(hadith_number, hadith_number_end, id_in_book)
        except (TypeError, ValueError) as e:
            return {
                "error": f"invalid_hadith_number: {e}",
                "hadith": None,
                "hadiths": None,
                "cross_references": None,
            }

        if end is None:
            row = store.fetch_hadith(collection_slug=slug, id_in_book=start)
            if row is None:
                return {"error": "not_found", "hadith": None, "hadiths": None, "cross_references": None}
            row_out = _add_hadith_url(row)
            crs = _attach_cross([row_out]) if include_cross_references else None
            return {"error": None, "hadith": row_out, "hadiths": None, "cross_references": crs}

        span = abs(end - start) + 1
        if span > _MAX_HADITH_RANGE:
            return {
                "error": f"range too large (max {_MAX_HADITH_RANGE} hadiths)",
                "hadith": None,
                "hadiths": None,
                "cross_references": None,
            }
        rows = store.fetch_hadiths_in_range(slug, start, end)
        if not rows:
            return {"error": "not_found", "hadith": None, "hadiths": [], "cross_references": None}
        rows_out = [_add_hadith_url(r) for r in rows]
        crs = _attach_cross(rows_out) if include_cross_references else None
        return {"error": None, "hadith": None, "hadiths": rows_out, "cross_references": crs}

    @mcp.tool()
    async def search_hadith(
        ctx: Context,
        query: str,
        limit: int = 20,
        collection: str | None = None,
        collection_slug: str | None = None,
        mode: str = "semantic",
    ) -> dict[str, Any]:
        """Search hadiths: ``mode='semantic'`` (default) uses embeddings; ``keyword`` uses SQL LIKE; ``both`` runs both."""
        limit = max(1, min(int(limit), 100))
        coll_f = (collection or collection_slug or "").strip() or None
        mode_l = mode.strip().lower()
        if mode_l not in {"semantic", "keyword", "both"}:
            return {
                "mode": mode_l,
                "error": "mode must be semantic, keyword, or both",
                "results": [],
            }

        if mode_l == "keyword":
            kw = _keyword_search(ctx, query, limit, coll_f)
            return {"mode": "keyword", "results": kw["results"], "note": None}

        if mode_l == "semantic":
            sem = await _semantic_search(ctx, query, limit, coll_f)
            if sem["ok"]:
                note = "cached_response" if sem.get("cache_hit") else None
                return {"mode": "semantic", "results": sem["results"], "note": note}
            kw = _keyword_search(ctx, query, limit, coll_f)
            reason = sem.get("reason")
            if reason == "semantic_unavailable":
                msg = "Semantic search unavailable (missing index or OPENAI_API_KEY); used keyword search."
            elif reason == "rate_limited":
                msg = "Search rate limit exceeded; used keyword search."
            elif reason == "dimension_mismatch":
                msg = (
                    "Query embedding size does not match database vectors; "
                    "fix embedding.query_model / HADITH_MCP_QUERY_EMBEDDING_MODEL to match hadith.db. "
                    "Used keyword search."
                )
            elif reason == "openai_error":
                msg = f"OpenAI embedding failed; used keyword search. ({sem.get('openai_message', '')})"
            else:
                msg = "Semantic search failed; used keyword search."
            return {"mode": "keyword_fallback", "results": kw["results"], "note": msg}

        sem = await _semantic_search(ctx, query, limit, coll_f)
        kw = _keyword_search(ctx, query, limit, coll_f)
        note = None
        if not sem["ok"]:
            note = (
                f"Semantic leg incomplete ({sem.get('reason', 'unknown')}); "
                "keyword leg still returned."
            )
        return {
            "mode": "both",
            "semantic": sem,
            "keyword": kw,
            "note": note,
        }

    @mcp.tool()
    def fetch_cross_references(
        ctx: Context,
        hadith_id: int | None = None,
        collection: str | None = None,
        collection_slug: str | None = None,
        hadith_number: int | None = None,
        id_in_book: int | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Cross-collection similarity matches for a hadith (by ``hadith_id`` or ``collection`` + number)."""
        store: HadithStore = ctx.lifespan_context["store"]
        hid = hadith_id
        if hid is None:
            coll_raw = (collection or collection_slug or "").strip() or None
            inn = hadith_number if hadith_number is not None else id_in_book
            if not coll_raw or inn is None:
                return {
                    "error": "Provide hadith_id, or collection + hadith_number / id_in_book",
                    "hadith_id": None,
                    "matches": [],
                }
            slug = store.resolve_collection_slug(coll_raw) or coll_raw
            hid = store.resolve_hadith_id(slug, int(inn))
            if hid is None:
                return {"error": "not_found", "hadith_id": None, "matches": []}
        matches = [_add_match_url(m) for m in store.fetch_cross_references(hid, limit=limit)]
        return {"error": None, "hadith_id": hid, "matches": matches}

    @mcp.tool()
    def fetch_grounding_rules(
        ctx: Context,
        nonce: str | None = None,
        force_full: bool = False,
    ) -> dict[str, Any]:
        """Citation and limitation guidance. Re-calls without ``force_full`` return a short repeat message."""
        grounding: GroundingState = ctx.lifespan_context["grounding"]
        return grounding.fetch(
            _session_key(ctx),
            nonce=nonce,
            force_full=force_full,
            full_text=GROUNDING_RULES,
        )

    _ICON_PATH = Path(__file__).parent / "assets" / "icon.png"
    _icon_bytes: bytes | None = None
    if _ICON_PATH.is_file():
        _icon_bytes = _ICON_PATH.read_bytes()
        logger.info("loaded icon asset (%d bytes)", len(_icon_bytes))

    @mcp.custom_route("/icon.png", methods=["GET", "HEAD"])
    async def serve_icon(request: Request) -> Response:
        if _icon_bytes is None:
            return Response(status_code=404)
        return Response(
            content=_icon_bytes,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=604800, immutable"},
        )

    return mcp


load_dotenv()
mcp = build_server()
