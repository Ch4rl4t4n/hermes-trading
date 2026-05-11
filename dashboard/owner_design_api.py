"""Owner-only Design System CMS API (Phase 4.5). Registered from dashboard.app."""

from __future__ import annotations

import io
import json
import logging
import os
import re
import time
import zipfile
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from flask import g, jsonify, request
from sqlalchemy import text

from core.owner_access import user_is_owner

try:  # optional, mirrors dashboard.app pattern
    import anthropic  # type: ignore
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore

ANTHROPIC_MODEL = os.getenv("HERMES_OWNER_DESIGN_MODEL", "claude-sonnet-4-20250514")
_AI_RATE_LIMIT_SEC = 6  # min interval per owner-id
_AI_LAST_CALL: dict[int, float] = {}

# ZIP / bundle import safety limits
_BUNDLE_ZIP_MAX_BYTES = 32 * 1024 * 1024  # 32 MB compressed (Claude prototypes often ~5-15 MB)
_BUNDLE_UNCOMPRESSED_MAX = 96 * 1024 * 1024  # 96 MB total uncompressed (Claude HTML w/ base64 assets)
_BUNDLE_MAX_ENTRIES = 400
_BUNDLE_FILE_TEXT_MAX = 4 * 1024 * 1024  # 4 MB per file inspected (HTML may inline images base64)
_CSS_VAR_RE = re.compile(r"--([A-Za-z0-9_-]+)\s*:\s*([^;{}\n]+?)\s*(?=;|\})")

_DESIGN_TOKEN_HINT_KEYS = (
    "globalcssvars",
    "global_css_vars",
    "tokens",
    "designtokens",
    "design_tokens",
    "theme",
    "colors",
    "color",
    "palette",
    "vars",
    "variables",
)

_HTML_STYLE_BLOCK_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_BUNDLE_SKIP_PATH_PARTS = (
    "node_modules/",
    ".git/",
    "dist/",
    "build/",
    ".next/",
    ".cache/",
    ".turbo/",
    ".vite/",
    "__pycache__/",
)
_BUNDLE_TEXT_EXTS = (".json", ".css", ".html", ".htm", ".tsx", ".jsx", ".ts", ".js", ".mjs", ".cjs", ".scss", ".less")

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

_MAX_SCHEMA_BYTES = 480_000


def _hermes_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _template_path() -> Path:
    return _hermes_root() / "frontend" / "src" / "design-system" / "schema.template.json"


def load_template_schema() -> dict[str, Any]:
    p = _template_path()
    try:
        raw = p.read_text(encoding="utf-8")
        return json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("design template load failed: %s", exc)
        return {"version": 0, "globalCssVars": {}, "components": {}, "mobilePWAOverrides": {}}


def _looks_like_token_value(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    s = v.strip().lower()
    if not s:
        return False
    if s.startswith("oklch(") or s.startswith("oklab(") or s.startswith("rgb(") or s.startswith("rgba(") or s.startswith("hsl(") or s.startswith("hsla(") or s.startswith("var("):
        return True
    if re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})", s):
        return True
    if re.fullmatch(r"-?\d+(\.\d+)?(px|rem|em|%|s|ms|deg|fr)?", s):
        return True
    return False


def _normalize_token_key(k: str) -> str:
    """Make sure key is a single CSS custom property starting with '--'."""
    s = str(k).strip()
    if s.startswith("--"):
        return s
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", s).strip("-")
    if not s:
        return ""
    return f"--{s}"


def _flatten_token_object(obj: Any, prefix: str = "") -> list[tuple[str, str]]:
    """
    Walk a nested JSON object and produce (--cssvar, value) pairs from leaves
    that look like design tokens (color/sizes/durations).
    """
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        # Style-Dictionary style { value, type } leaf
        if "value" in obj and not any(isinstance(v, (dict, list)) for v in obj.values()):
            v = obj.get("value")
            if _looks_like_token_value(v):
                key = _normalize_token_key(prefix or "token")
                if key:
                    out.append((key, str(v).strip()))
            return out
        for k, v in obj.items():
            child_prefix = f"{prefix}-{k}" if prefix else str(k)
            out.extend(_flatten_token_object(v, child_prefix))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_flatten_token_object(v, f"{prefix}-{i}" if prefix else str(i)))
    else:
        if _looks_like_token_value(obj) and prefix:
            key = _normalize_token_key(prefix)
            if key:
                out.append((key, str(obj).strip()))
    return out


def _extract_tokens_from_json_obj(obj: Any) -> list[tuple[str, str]]:
    """Find token-y subtrees and flatten them. Recognise common Hermes shape too."""
    if isinstance(obj, dict):
        if isinstance(obj.get("globalCssVars"), dict):
            return [
                (_normalize_token_key(k), str(v).strip())
                for k, v in obj["globalCssVars"].items()
                if isinstance(v, str) and _normalize_token_key(k)
            ]
        # Try common subtrees
        for key in obj.keys():
            if key.lower() in _DESIGN_TOKEN_HINT_KEYS:
                pairs = _flatten_token_object(obj[key], key)
                if pairs:
                    return pairs
    return _flatten_token_object(obj)


def _extract_css_vars(text_blob: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in _CSS_VAR_RE.finditer(text_blob):
        key = f"--{m.group(1).strip()}"
        val = m.group(2).strip()
        # cleanup template-literal residue (`${...}`) — keep static values only
        if "${" in val or "{{" in val:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append((key, val))
    return out


def _extract_css_vars_from_html(text_blob: str) -> list[tuple[str, str]]:
    """Pull <style> blocks first, then run css regex on whole HTML (covers inline styles too)."""
    pairs: list[tuple[str, str]] = []
    for block in _HTML_STYLE_BLOCK_RE.findall(text_blob):
        pairs.extend(_extract_css_vars(block))
    pairs.extend(_extract_css_vars(text_blob))
    seen: dict[str, str] = {}
    for k, v in pairs:
        seen.setdefault(k, v)
    return list(seen.items())


def _extract_css_vars_from_jsx(text_blob: str) -> list[tuple[str, str]]:
    """JSX/TSX/JS/TS: run css var regex on whole text (matches `--accent: oklch(...)` strings)."""
    return _extract_css_vars(text_blob)


def validate_design_schema(obj: Any) -> tuple[bool, str]:
    if not isinstance(obj, dict):
        return False, "Schéma musí byť JSON objekt."
    if "version" not in obj:
        return False, "Pole version je povinné."
    gcv = obj.get("globalCssVars")
    if gcv is not None and not isinstance(gcv, dict):
        return False, "globalCssVars musí byť objekt."
    comp = obj.get("components")
    if comp is not None and not isinstance(comp, dict):
        return False, "components musí byť objekt."
    mob = obj.get("mobilePWAOverrides")
    if mob is not None and not isinstance(mob, dict):
        return False, "mobilePWAOverrides musí byť objekt."
    try:
        blob = json.dumps(obj)
    except (TypeError, ValueError):
        return False, "Schéma nie je serializovateľné do JSON."
    if len(blob.encode("utf-8")) > _MAX_SCHEMA_BYTES:
        return False, "Schéma je príliš veľké."
    return True, ""


def register_owner_design_routes(
    app,
    *,
    db: Any,
    login_required: Any,
    _resolve_identity: Any,
) -> None:
    def owner_required(f):
        @wraps(f)
        def decorated(*args: Any, **kwargs: Any):
            _resolve_identity()
            if getattr(g, "auth_kind", None) != "db" or not getattr(g, "db_user", None):
                return jsonify({"error": "Vyžaduje sa prihlásenie."}), 401
            if not user_is_owner(g.db_user):
                return jsonify({"error": "Prístup len pre platform owner."}), 403
            return f(*args, **kwargs)

        return decorated

    def _fetch_active_row(sess: Any) -> Optional[dict[str, Any]]:
        row = sess.execute(
            text(
                """
                SELECT id, created_at, label, schema_json, applied_at, applied_by_user_id
                FROM design_system_versions
                WHERE applied_at IS NOT NULL
                ORDER BY applied_at DESC
                LIMIT 1
                """
            )
        ).mappings().first()
        return dict(row) if row else None

    @app.route("/api/design/active-schema", methods=["GET"])
    def api_design_active_schema_public():
        """Verejný endpoint — len aktívne CSS tokeny pre SPA (bez prihlásenia)."""
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        sess = db.db_session()
        try:
            row = _fetch_active_row(sess)
            if not row:
                tpl = load_template_schema()
                return jsonify(
                    {
                        "active": False,
                        "version": tpl.get("version"),
                        "globalCssVars": tpl.get("globalCssVars") or {},
                        "applied_at": None,
                    }
                )
            sj = row.get("schema_json")
            if isinstance(sj, str):
                try:
                    sj = json.loads(sj)
                except json.JSONDecodeError:
                    sj = {}
            if not isinstance(sj, dict):
                sj = {}
            applied = row.get("applied_at")
            return jsonify(
                {
                    "active": True,
                    "version": sj.get("version"),
                    "globalCssVars": sj.get("globalCssVars") or {},
                    "applied_at": applied.isoformat() if applied is not None and hasattr(applied, "isoformat") else None,
                }
            )
        except Exception:  # noqa: BLE001
            log.exception("active-schema public")
            return jsonify({"error": "Nepodarilo sa načítať schému."}), 500
        finally:
            sess.close()

    @app.route("/api/owner/design/schema-template", methods=["GET"])
    @login_required
    @owner_required
    def api_owner_design_schema_template():
        return jsonify({"schema": load_template_schema()})

    @app.route("/api/owner/design/schema", methods=["GET"])
    @login_required
    @owner_required
    def api_owner_design_schema_current():
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        sess = db.db_session()
        try:
            row = _fetch_active_row(sess)
            if row:
                sj = row["schema_json"]
                if isinstance(sj, str):
                    try:
                        sj = json.loads(sj)
                    except json.JSONDecodeError:
                        sj = {}
                applied = row.get("applied_at")
                return jsonify(
                    {
                        "active_version_id": row["id"],
                        "schema": sj,
                        "label": row.get("label"),
                        "applied_at": applied.isoformat() if applied is not None and hasattr(applied, "isoformat") else None,
                    }
                )
            tpl = load_template_schema()
            return jsonify({"active_version_id": None, "schema": tpl, "label": None, "applied_at": None})
        finally:
            sess.close()

    @app.route("/api/owner/design/history", methods=["GET"])
    @login_required
    @owner_required
    def api_owner_design_history():
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        try:
            lim = min(max(int(request.args.get("limit") or 30), 1), 100)
        except (TypeError, ValueError):
            lim = 30
        sess = db.db_session()
        try:
            rows = sess.execute(
                text(
                    """
                    SELECT id, created_at, label, applied_at, applied_by_user_id
                    FROM design_system_versions
                    ORDER BY id DESC
                    LIMIT :lim
                    """
                ),
                {"lim": lim},
            ).mappings().all()
            out = []
            for r in rows:
                d = dict(r)
                ca = d.get("created_at")
                aa = d.get("applied_at")
                if ca is not None and hasattr(ca, "isoformat"):
                    d["created_at"] = ca.isoformat()
                if aa is not None and hasattr(aa, "isoformat"):
                    d["applied_at"] = aa.isoformat()
                else:
                    d["applied_at"] = None
                out.append(d)
            return jsonify({"versions": out})
        finally:
            sess.close()

    @app.route("/api/owner/design/apply", methods=["POST"])
    @login_required
    @owner_required
    def api_owner_design_apply():
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        body = request.get_json(silent=True) or {}
        schema = body.get("schema")
        label = str(body.get("label") or "").strip()[:240] or None
        ok, err = validate_design_schema(schema)
        if not ok:
            return jsonify({"error": err}), 400
        uid = int(g.db_user.id)
        sess = db.db_session()
        try:
            sess.execute(
                text(
                    """
                    INSERT INTO design_system_versions (label, schema_json, applied_at, applied_by_user_id)
                    VALUES (:label, CAST(:sj AS jsonb), NOW(), :uid)
                    """
                ),
                {"label": label, "sj": json.dumps(schema), "uid": uid},
            )
            sess.commit()
            return jsonify({"ok": True, "message": "Schéma uložená a aktivovaná."})
        except Exception:  # noqa: BLE001
            sess.rollback()
            log.exception("owner design apply")
            return jsonify({"error": "Uloženie zlyhalo."}), 500
        finally:
            sess.close()

    def _ai_throttle(uid: int) -> Optional[str]:
        now = time.time()
        last = _AI_LAST_CALL.get(uid, 0.0)
        if now - last < _AI_RATE_LIMIT_SEC:
            return f"Príliš rýchlo — počkaj {int(_AI_RATE_LIMIT_SEC - (now - last))}s pred ďalším volaním."
        _AI_LAST_CALL[uid] = now
        return None

    def _anthropic_client():
        api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        if not api_key:
            return None, "ANTHROPIC_API_KEY nie je nastavený."
        if anthropic is None:
            return None, "Anthropic SDK nie je nainštalovaný."
        try:
            return anthropic.Anthropic(api_key=api_key), None
        except Exception as exc:  # noqa: BLE001
            return None, f"Anthropic init failed: {exc}"

    def _claude_text(client, *, system: str, user_msg: str, max_tokens: int = 1500) -> tuple[Optional[str], Optional[str]]:
        try:
            msg = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            parts: list[str] = []
            for block in getattr(msg, "content", []) or []:
                if getattr(block, "type", None) == "text":
                    parts.append(str(getattr(block, "text", "") or ""))
            return "".join(parts).strip(), None
        except Exception as exc:  # noqa: BLE001
            log.exception("owner design claude call")
            return None, f"AI volanie zlyhalo: {exc}"

    def _strip_codeblock(raw: str) -> str:
        s = raw.strip()
        if s.startswith("```"):
            s = s.split("```", 2)[-1] if s.count("```") < 2 else s.split("```")[1]
            if s.lower().startswith("json"):
                s = s[4:]
        return s.strip().strip("`").strip()

    @app.route("/api/owner/design/analyze", methods=["POST"])
    @login_required
    @owner_required
    def api_owner_design_analyze():
        body = request.get_json(silent=True) or {}
        schema = body.get("schema")
        if not isinstance(schema, dict):
            return jsonify({"error": "Pole schema (objekt) je povinné."}), 400
        ok, err = validate_design_schema(schema)
        if not ok:
            return jsonify({"error": err}), 400
        msg = _ai_throttle(int(g.db_user.id))
        if msg:
            return jsonify({"error": msg}), 429
        client, cerr = _anthropic_client()
        if client is None:
            return jsonify({"error": cerr}), 503
        system = (
            "Si dizajn-system audítor pre Hermes (dark neon trading SPA). Odpoveď v slovenčine, "
            "max 250 slov, odrážky. Zhodnoť konzistenciu farieb (oklch), kontrast, accessibility, "
            "krytie tokenov a navrhni 3 konkrétne mikro-úpravy globalCssVars. Bez kódu, len text."
        )
        text_out, terr = _claude_text(
            client,
            system=system,
            user_msg=f"Aktuálna design schéma:\n```json\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n```",
            max_tokens=900,
        )
        if text_out is None:
            return jsonify({"error": terr or "AI zlyhalo."}), 502
        return jsonify({"report_md": text_out, "model": ANTHROPIC_MODEL})

    @app.route("/api/owner/design/generate", methods=["POST"])
    @login_required
    @owner_required
    def api_owner_design_generate():
        body = request.get_json(silent=True) or {}
        prompt = str(body.get("prompt") or "").strip()[:2000]
        if not prompt:
            return jsonify({"error": "Prompt je povinný."}), 400
        base_schema = body.get("schema")
        if not isinstance(base_schema, dict):
            base_schema = load_template_schema()
        msg = _ai_throttle(int(g.db_user.id))
        if msg:
            return jsonify({"error": msg}), 429
        client, cerr = _anthropic_client()
        if client is None:
            return jsonify({"error": cerr}), 503
        system = (
            "Si Hermes Design System Generator. Odpoveď VRÁŤ IBA AKO VALID JSON (bez markdownu) "
            "s tvarom: {\"version\": <int>, \"label\": \"...\", \"globalCssVars\": {...}, "
            "\"components\": {}, \"mobilePWAOverrides\": {}}. "
            "globalCssVars musia byť CSS premenné začínajúce '--' a hodnoty v 'oklch(...)' alebo HEX. "
            "Vychádzaj zo zadanej základnej schémy a uprav ju podľa promptu používateľa, zachovaj všetky existujúce "
            "kľúče a pridaj nové len ak je to nutné. Žiadne komentáre, žiadny markdown."
        )
        user_msg = (
            f"Základná schéma:\n```json\n{json.dumps(base_schema, ensure_ascii=False, indent=2)}\n```\n\n"
            f"Požiadavka používateľa: {prompt}"
        )
        raw, terr = _claude_text(client, system=system, user_msg=user_msg, max_tokens=1800)
        if raw is None:
            return jsonify({"error": terr or "AI zlyhalo."}), 502
        cleaned = _strip_codeblock(raw)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            return jsonify({"error": f"AI nevrátilo platný JSON: {exc}", "raw": raw[:1200]}), 500
        ok, err = validate_design_schema(parsed)
        if not ok:
            return jsonify({"error": f"AI výstup neplatný: {err}", "raw": raw[:1200]}), 500
        return jsonify({"schema": parsed, "model": ANTHROPIC_MODEL})

    def _bundle_from_json_text(name: str, content: str) -> tuple[Optional[dict[str, Any]], list[tuple[str, str]], list[str]]:
        warnings_out: list[str] = []
        cleaned = _strip_codeblock(content)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            return None, [], [f"{name}: neplatný JSON ({exc})"]
        # If it is already a full schema, accept as-is
        if isinstance(parsed, dict) and ("globalCssVars" in parsed or "components" in parsed) and "version" in parsed:
            ok, err = validate_design_schema(parsed)
            if ok:
                return parsed, [], warnings_out
            warnings_out.append(f"{name}: schéma má vadnú štruktúru ({err}); pokúšam sa o token extrakciu.")
        pairs = _extract_tokens_from_json_obj(parsed)
        if not pairs:
            warnings_out.append(f"{name}: nenašli sa žiadne token-y vhodného formátu (oklch/hex/rem/…).")
        return None, pairs, warnings_out

    def _bundle_from_css_text(name: str, content: str) -> tuple[list[tuple[str, str]], list[str]]:
        if len(content) > _BUNDLE_FILE_TEXT_MAX:
            return [], [f"{name}: súbor je príliš veľký ({len(content)} B), preskočené."]
        pairs = _extract_css_vars(content)
        if not pairs:
            return [], [f"{name}: žiadne `--var: value;` deklarácie nenájdené."]
        return pairs, []

    def _build_schema_from_pairs(pairs: list[tuple[str, str]], label: str) -> dict[str, Any]:
        seen: dict[str, str] = {}
        for k, v in pairs:
            if not k or not isinstance(v, str):
                continue
            seen[k] = v.strip()
        return {
            "version": 1,
            "label": (label or "imported-bundle")[:240],
            "globalCssVars": seen,
            "components": {},
            "mobilePWAOverrides": {},
        }

    def _process_bundle_zip(filename: str, blob: bytes) -> dict[str, Any]:
        report: dict[str, Any] = {
            "files": [],
            "errors": [],
            "warnings": [],
            "stats": {"total_files": 0, "tokens": 0, "css_files": 0, "json_files": 0, "skipped": 0},
        }
        if len(blob) > _BUNDLE_ZIP_MAX_BYTES:
            report["errors"].append(f"ZIP je väčší než {_BUNDLE_ZIP_MAX_BYTES // (1024 * 1024)} MB.")
            return {"schema": None, "report": report, "success": False}
        try:
            zf = zipfile.ZipFile(io.BytesIO(blob))
        except zipfile.BadZipFile:
            report["errors"].append("Súbor nie je platný ZIP archív.")
            return {"schema": None, "report": report, "success": False}

        # Pre-filter out heavy/irrelevant directories (node_modules, .git, dist, ...)
        all_entries = [info for info in zf.infolist() if not info.is_dir()]
        skipped_paths_count = 0
        infos: list[zipfile.ZipInfo] = []
        for info in all_entries:
            normpath = info.filename.replace("\\", "/").lower()
            if any(part in normpath for part in _BUNDLE_SKIP_PATH_PARTS):
                skipped_paths_count += 1
                continue
            infos.append(info)
        if skipped_paths_count:
            report["warnings"].append(
                f"Preskočených {skipped_paths_count} súborov z node_modules/.git/dist/.next/ a podobných."
            )
        if len(infos) > _BUNDLE_MAX_ENTRIES:
            report["errors"].append(f"ZIP obsahuje viac ako {_BUNDLE_MAX_ENTRIES} relevantných súborov.")
            return {"schema": None, "report": report, "success": False}

        total_uncompressed = sum(info.file_size for info in infos)
        if total_uncompressed > _BUNDLE_UNCOMPRESSED_MAX:
            report["errors"].append(f"Celková rozbalená veľkosť presahuje limit ({_BUNDLE_UNCOMPRESSED_MAX // (1024 * 1024)} MB).")
            return {"schema": None, "report": report, "success": False}

        report["stats"]["total_files"] = len(infos)
        all_pairs: list[tuple[str, str]] = []
        existing_full_schema: Optional[dict[str, Any]] = None

        for info in infos:
            entry: dict[str, Any] = {"name": info.filename, "size": info.file_size}
            # Path traversal guard
            if ".." in info.filename.split("/") or info.filename.startswith("/"):
                entry["status"] = "error"
                entry["reason"] = "podozrivá cesta súboru"
                report["files"].append(entry)
                report["errors"].append(f"{info.filename}: neplatná cesta v ZIP-e.")
                continue
            lower = info.filename.lower()
            try:
                with zf.open(info, "r") as fh:
                    data = fh.read(_BUNDLE_FILE_TEXT_MAX + 1)
            except (KeyError, RuntimeError, zipfile.BadZipFile) as exc:
                entry["status"] = "error"
                entry["reason"] = f"načítanie zlyhalo: {exc}"
                report["files"].append(entry)
                report["errors"].append(f"{info.filename}: nedá sa načítať.")
                continue
            if len(data) > _BUNDLE_FILE_TEXT_MAX:
                entry["status"] = "skipped"
                entry["reason"] = f"súbor presahuje limit {_BUNDLE_FILE_TEXT_MAX // (1024 * 1024)} MB"
                report["warnings"].append(f"{info.filename}: príliš veľký, preskočený.")
                report["stats"]["skipped"] += 1
                report["files"].append(entry)
                continue
            try:
                content = data.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                entry["status"] = "skipped"
                entry["reason"] = "binárny súbor"
                report["stats"]["skipped"] += 1
                report["files"].append(entry)
                continue

            if lower.endswith(".json"):
                schema_obj, pairs, warns = _bundle_from_json_text(info.filename, content)
                report["warnings"].extend(warns)
                report["stats"]["json_files"] += 1
                if schema_obj is not None and existing_full_schema is None:
                    existing_full_schema = schema_obj
                    entry["status"] = "ok"
                    entry["role"] = "full-schema"
                    entry["extracted"] = len((schema_obj.get("globalCssVars") or {}))
                elif pairs:
                    all_pairs.extend(pairs)
                    entry["status"] = "ok"
                    entry["role"] = "tokens-json"
                    entry["extracted"] = len(pairs)
                    report["stats"]["tokens"] += len(pairs)
                else:
                    entry["status"] = "skipped"
                    entry["reason"] = "JSON nemá design tokeny"
                    report["stats"]["skipped"] += 1
            elif lower.endswith((".css", ".scss", ".less")):
                pairs, warns = _bundle_from_css_text(info.filename, content)
                report["warnings"].extend(warns)
                report["stats"]["css_files"] += 1
                if pairs:
                    all_pairs.extend(pairs)
                    entry["status"] = "ok"
                    entry["role"] = "css-vars"
                    entry["extracted"] = len(pairs)
                    report["stats"]["tokens"] += len(pairs)
                else:
                    entry["status"] = "skipped"
                    entry["reason"] = "žiadne CSS premenné"
                    report["stats"]["skipped"] += 1
            elif lower.endswith((".html", ".htm")):
                pairs = _extract_css_vars_from_html(content)
                if pairs:
                    all_pairs.extend(pairs)
                    entry["status"] = "ok"
                    entry["role"] = "html-vars"
                    entry["extracted"] = len(pairs)
                    report["stats"]["tokens"] += len(pairs)
                else:
                    entry["status"] = "skipped"
                    entry["reason"] = "v HTML žiadne --premenné"
                    report["stats"]["skipped"] += 1
            elif lower.endswith((".jsx", ".tsx", ".ts", ".js", ".cjs", ".mjs")):
                if "tailwind" in lower:
                    entry["status"] = "skipped"
                    entry["reason"] = "tailwind config v JS — neparsujem JS"
                    report["warnings"].append(
                        f"{info.filename}: tailwind config v JS sa nečíta — vyexportuj tokeny do JSON/CSS."
                    )
                    report["stats"]["skipped"] += 1
                else:
                    pairs = _extract_css_vars_from_jsx(content)
                    if pairs:
                        all_pairs.extend(pairs)
                        entry["status"] = "ok"
                        entry["role"] = "jsx-vars"
                        entry["extracted"] = len(pairs)
                        report["stats"]["tokens"] += len(pairs)
                    else:
                        entry["status"] = "skipped"
                        entry["reason"] = "v JS/TSX žiadne --premenné"
                        report["stats"]["skipped"] += 1
            elif lower.endswith(".zip"):
                entry["status"] = "skipped"
                entry["reason"] = "vnorený ZIP — rozbaľ ho a nahraj samostatne"
                report["warnings"].append(
                    f"{info.filename}: vnorený ZIP nečítam rekurzívne; rozbaľ ho a pridaj obsah priamo."
                )
                report["stats"]["skipped"] += 1
            elif lower.endswith((".md", ".txt", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff", ".woff2", ".ttf", ".otf")):
                entry["status"] = "skipped"
                entry["reason"] = "nedeskriptívny formát"
                report["stats"]["skipped"] += 1
            else:
                entry["status"] = "skipped"
                entry["reason"] = "neznámy typ súboru"
                report["stats"]["skipped"] += 1
            report["files"].append(entry)

        if existing_full_schema is not None:
            ok, err = validate_design_schema(existing_full_schema)
            if not ok:
                report["errors"].append(f"Existujúca schéma je nevalidná: {err}.")
                return {"schema": None, "report": report, "success": False}
            return {"schema": existing_full_schema, "report": report, "success": True}

        if not all_pairs:
            report["errors"].append("Bundle neobsahuje žiadne použiteľné design tokeny.")
            return {"schema": None, "report": report, "success": False}

        candidate = _build_schema_from_pairs(all_pairs, label=f"imported-zip:{filename}")
        ok, err = validate_design_schema(candidate)
        if not ok:
            report["errors"].append(f"Zostavená schéma je nevalidná: {err}.")
            return {"schema": None, "report": report, "success": False}
        report["stats"]["tokens"] = len(candidate.get("globalCssVars") or {})
        return {"schema": candidate, "report": report, "success": True}

    def _process_bundle_text(name: str, content: str) -> dict[str, Any]:
        report: dict[str, Any] = {
            "files": [{"name": name, "size": len(content)}],
            "errors": [],
            "warnings": [],
            "stats": {"total_files": 1, "tokens": 0, "css_files": 0, "json_files": 0, "skipped": 0},
        }
        lower = name.lower()
        if lower.endswith((".css", ".scss", ".less")):
            pairs, warns = _bundle_from_css_text(name, content)
            report["warnings"].extend(warns)
            report["stats"]["css_files"] = 1
            if not pairs:
                report["errors"].append("V CSS sa nenašli žiadne `--var:` deklarácie.")
                report["files"][0]["status"] = "error"
                return {"schema": None, "report": report, "success": False}
            schema = _build_schema_from_pairs(pairs, label=f"imported-css:{name}")
            ok, err = validate_design_schema(schema)
            if not ok:
                report["errors"].append(err)
                return {"schema": None, "report": report, "success": False}
            report["stats"]["tokens"] = len(schema["globalCssVars"])
            report["files"][0]["status"] = "ok"
            report["files"][0]["role"] = "css-vars"
            report["files"][0]["extracted"] = len(schema["globalCssVars"])
            return {"schema": schema, "report": report, "success": True}

        if lower.endswith((".html", ".htm")):
            pairs = _extract_css_vars_from_html(content)
            if not pairs:
                report["errors"].append("V HTML sa nenašli žiadne `--var:` deklarácie (skús .zip).")
                report["files"][0]["status"] = "error"
                return {"schema": None, "report": report, "success": False}
            schema = _build_schema_from_pairs(pairs, label=f"imported-html:{name}")
            ok, err = validate_design_schema(schema)
            if not ok:
                report["errors"].append(err)
                return {"schema": None, "report": report, "success": False}
            report["files"][0]["status"] = "ok"
            report["files"][0]["role"] = "html-vars"
            report["files"][0]["extracted"] = len(schema["globalCssVars"])
            report["stats"]["tokens"] = report["files"][0]["extracted"]
            return {"schema": schema, "report": report, "success": True}

        if lower.endswith((".jsx", ".tsx", ".ts", ".js", ".cjs", ".mjs")):
            if "tailwind" in lower:
                report["errors"].append("Tailwind config v JS nečítam — vyexportuj tokeny do JSON/CSS.")
                report["files"][0]["status"] = "error"
                return {"schema": None, "report": report, "success": False}
            pairs = _extract_css_vars_from_jsx(content)
            if not pairs:
                report["errors"].append("V JSX/TSX/JS súbore sa nenašli žiadne `--var:` deklarácie. Pošli celý .zip prototyp.")
                report["files"][0]["status"] = "error"
                return {"schema": None, "report": report, "success": False}
            schema = _build_schema_from_pairs(pairs, label=f"imported-jsx:{name}")
            ok, err = validate_design_schema(schema)
            if not ok:
                report["errors"].append(err)
                return {"schema": None, "report": report, "success": False}
            report["files"][0]["status"] = "ok"
            report["files"][0]["role"] = "jsx-vars"
            report["files"][0]["extracted"] = len(schema["globalCssVars"])
            report["stats"]["tokens"] = report["files"][0]["extracted"]
            return {"schema": schema, "report": report, "success": True}

        # default: JSON
        report["stats"]["json_files"] = 1
        schema_obj, pairs, warns = _bundle_from_json_text(name, content)
        report["warnings"].extend(warns)
        if schema_obj is not None:
            ok, err = validate_design_schema(schema_obj)
            if not ok:
                report["errors"].append(err)
                report["files"][0]["status"] = "error"
                return {"schema": None, "report": report, "success": False}
            report["files"][0]["status"] = "ok"
            report["files"][0]["role"] = "full-schema"
            report["files"][0]["extracted"] = len(schema_obj.get("globalCssVars") or {})
            report["stats"]["tokens"] = report["files"][0]["extracted"]
            return {"schema": schema_obj, "report": report, "success": True}
        if pairs:
            schema = _build_schema_from_pairs(pairs, label=f"imported-json:{name}")
            ok, err = validate_design_schema(schema)
            if not ok:
                report["errors"].append(err)
                return {"schema": None, "report": report, "success": False}
            report["files"][0]["status"] = "ok"
            report["files"][0]["role"] = "tokens-json"
            report["files"][0]["extracted"] = len(schema["globalCssVars"])
            report["stats"]["tokens"] = report["files"][0]["extracted"]
            return {"schema": schema, "report": report, "success": True}
        report["errors"].append("V JSON neexistujú design tokeny v rozpoznanej štruktúre.")
        report["files"][0]["status"] = "error"
        return {"schema": None, "report": report, "success": False}

    @app.route("/api/owner/design/import-bundle", methods=["POST"])
    @login_required
    @owner_required
    def api_owner_design_import_bundle():
        """Multipart endpoint: prijíma .json / .css / .zip a vráti report + schémanavhrh."""
        if "file" not in request.files:
            return jsonify({"error": "Pošli súbor pod kľúčom 'file'."}), 400
        f = request.files["file"]
        filename = (f.filename or "bundle").strip()[:200]
        try:
            blob = f.read(_BUNDLE_ZIP_MAX_BYTES + 1)
        except Exception:  # noqa: BLE001
            return jsonify({"error": "Načítanie súboru zlyhalo."}), 400
        if not blob:
            return jsonify({"error": "Prázdny súbor."}), 400
        if len(blob) > _BUNDLE_ZIP_MAX_BYTES:
            return jsonify({"error": f"Súbor presahuje {_BUNDLE_ZIP_MAX_BYTES // (1024 * 1024)} MB."}), 413

        lower = filename.lower()
        text_exts = (".css", ".scss", ".less", ".html", ".htm", ".tsx", ".jsx", ".ts", ".js", ".cjs", ".mjs")
        if lower.endswith(".zip") or blob[:2] == b"PK":
            result = _process_bundle_zip(filename, blob)
        elif lower.endswith(text_exts):
            try:
                content = blob.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                return jsonify({"error": "Súbor nie je textový."}), 400
            result = _process_bundle_text(filename, content)
        elif lower.endswith(".json") or blob[:1] in (b"{", b"["):
            try:
                content = blob.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                return jsonify({"error": "Súbor nie je textový."}), 400
            result = _process_bundle_text(filename if lower.endswith(".json") else f"{filename}.json", content)
        else:
            return jsonify({"error": "Podporujem .json, .css, .scss, .less, .html, .tsx/.jsx/.ts/.js alebo .zip."}), 415

        status = 200 if result.get("success") else 422
        return jsonify(result), status

    @app.route("/api/owner/design/import", methods=["POST"])
    @login_required
    @owner_required
    def api_owner_design_import():
        """Accepts JSON body { content_json: "<string>" } or {schema: {...}} and returns a validated schema."""
        body = request.get_json(silent=True) or {}
        candidate: Any = None
        if isinstance(body.get("schema"), dict):
            candidate = body["schema"]
        else:
            content = str(body.get("content_json") or body.get("content") or "").strip()
            if not content:
                return jsonify({"error": "Pošli buď 'schema' (objekt) alebo 'content_json' (text)."}), 400
            content = _strip_codeblock(content)
            try:
                candidate = json.loads(content)
            except json.JSONDecodeError as exc:
                return jsonify({"error": f"Neplatný JSON: {exc}"}), 400
        # Coerce flat token map into globalCssVars wrapper if useful
        if isinstance(candidate, dict) and "globalCssVars" not in candidate and all(
            isinstance(k, str) and k.startswith("--") and isinstance(v, str)
            for k, v in candidate.items()
        ):
            candidate = {
                "version": 1,
                "label": "imported-tokens",
                "globalCssVars": candidate,
                "components": {},
                "mobilePWAOverrides": {},
            }
        ok, err = validate_design_schema(candidate)
        if not ok:
            return jsonify({"error": err}), 400
        return jsonify({"schema": candidate})

    @app.route("/api/owner/design/revert", methods=["POST"])
    @login_required
    @owner_required
    def api_owner_design_revert():
        if db.SessionLocal is None:
            return jsonify({"error": "database unavailable"}), 503
        body = request.get_json(silent=True) or {}
        try:
            vid = int(body.get("version_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "Neplatné version_id."}), 400
        uid = int(g.db_user.id)
        sess = db.db_session()
        try:
            row = sess.execute(
                text(
                    """
                    SELECT schema_json, label FROM design_system_versions WHERE id = :id
                    """
                ),
                {"id": vid},
            ).mappings().first()
            if not row:
                return jsonify({"error": "Verzia neexistuje."}), 404
            rd = dict(row)
            sj = rd.get("schema_json")
            if isinstance(sj, str):
                try:
                    sj = json.loads(sj)
                except json.JSONDecodeError:
                    sj = {}
            if not isinstance(sj, dict):
                return jsonify({"error": "Poškodená verzia."}), 400
            ok, err = validate_design_schema(sj)
            if not ok:
                return jsonify({"error": err}), 400
            rev_label = f"revert→{vid}"
            sess.execute(
                text(
                    """
                    INSERT INTO design_system_versions (label, schema_json, applied_at, applied_by_user_id)
                    VALUES (:label, CAST(:sj AS jsonb), NOW(), :uid)
                    """
                ),
                {"label": rev_label[:240], "sj": json.dumps(sj), "uid": uid},
            )
            sess.commit()
            return jsonify({"ok": True, "message": "Revert aplikovaný ako nová aktívna verzia."})
        except Exception:  # noqa: BLE001
            sess.rollback()
            log.exception("owner design revert")
            return jsonify({"error": "Revert zlyhal."}), 500
        finally:
            sess.close()
