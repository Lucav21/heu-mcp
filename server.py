#!/usr/bin/env python3
"""HEU Legal API MCP Server - v0.1.0

MCP Server per integrare HEU Legal con Claude AI.
Gestisce documenti nativi HEU e PDF per firma elettronica via conversazione.

API docs: https://api.heulegal.com/v1
License: MIT
"""

import json
import os
import re
import traceback
from pathlib import Path

import httpx

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

API_KEY = os.getenv("HEU_API_KEY", "")
BASE_URL = os.getenv("HEU_BASE_URL", "https://api.heulegal.com/v1").rstrip("/")
DOWNLOAD_DIR = Path(os.getenv("HEU_DOWNLOAD_DIR", "/tmp"))

DEFAULT_TIMEOUT = 30.0
DOWNLOAD_TIMEOUT = 120.0

app = Server("heu")


def _headers():
    return {
        "x-api-key": API_KEY,
        "Accept": "application/json",
    }


def _request(method: str, path: str, **kwargs):
    """Esegue una richiesta HTTP all'API HEU e ritorna (status, body_or_text, headers).

    Per risposte JSON ritorna il body parsato; per binari ritorna i bytes grezzi."""
    url = f"{BASE_URL}{path}"
    headers = kwargs.pop("headers", {})
    headers = {**_headers(), **headers}
    timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT)
    with httpx.Client(timeout=timeout) as client:
        resp = client.request(method, url, headers=headers, **kwargs)
        ct = resp.headers.get("content-type", "")
        if "application/json" in ct:
            try:
                body = resp.json()
            except Exception:
                body = resp.text
        elif "application/pdf" in ct or resp.headers.get("content-disposition"):
            body = resp.content
        else:
            try:
                body = resp.json()
            except Exception:
                body = resp.text
        return resp.status_code, body, dict(resp.headers)


def _ok(payload) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, indent=2, ensure_ascii=False, default=str))]


def _err(status: int, body, hint: str | None = None) -> list[TextContent]:
    msg = {"error": True, "status": status, "body": body}
    if hint:
        msg["hint"] = hint
    return [TextContent(type="text", text=json.dumps(msg, indent=2, ensure_ascii=False, default=str))]


def _check_config() -> str | None:
    if not API_KEY:
        return "HEU_API_KEY non configurata. Imposta la variabile d'ambiente con la tua API key (Profile > API Keys nella UI HEU, richiede subscription Enterprise)."
    return None


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return name or "document"


@app.list_tools()
async def list_tools():
    placeholders_kv_schema = {
        "type": "object",
        "description": "Mappa key->value dei placeholder da sostituire nel template (chiave = nome placeholder)",
        "additionalProperties": {"type": "string"},
    }

    pdf_signer_schema = {
        "type": "object",
        "properties": {
            "source_id": {"type": "string", "description": "ID del signer nel template sorgente"},
            "email": {"type": "string", "format": "email", "description": "Email del firmatario"},
            "full_name": {"type": "string", "description": "Nome completo del firmatario"},
        },
        "required": ["source_id", "email", "full_name"],
    }

    pdf_placeholder_schema = {
        "type": "object",
        "properties": {
            "source_id": {"type": "string", "description": "UUID del placeholder nel template"},
            "is_checked": {"type": ["boolean", "null"], "description": "Per checkbox: spuntato o no"},
            "text_value": {"type": ["string", "null"], "description": "Valore testuale da inserire"},
        },
        "required": ["source_id"],
    }

    return [
        Tool(
            name="get_heu_health",
            description="Health check API HEU. Ritorna { message: 'ok', status: 200 } se operativa.",
            inputSchema={"type": "object", "properties": {}},
        ),
        # ---------- DOCUMENTS (native HEU) ----------
        Tool(
            name="list_heu_documents",
            description="Lista documenti/template nativi HEU con filtri opzionali.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["document", "template"], "description": "Filtra per tipo"},
                    "sort": {"type": "string", "enum": ["asc", "desc"], "description": "Ordinamento per data"},
                    "created_from": {"type": "string", "description": "Data inizio (ISO 8601, es. 2025-01-01T00:00:00Z)"},
                    "created_to": {"type": "string", "description": "Data fine (ISO 8601)"},
                    "have_editors_signed": {"type": "boolean", "description": "Filtra per: tutti gli editor hanno firmato"},
                },
            },
        ),
        Tool(
            name="get_heu_document",
            description="Dettaglio di un documento o template HEU per ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "ID del documento (UUID per document/template HEU)"},
                },
                "required": ["document_id"],
            },
        ),
        Tool(
            name="list_heu_document_placeholders",
            description="Lista i placeholder di un documento/template HEU (chiavi sostituibili nel testo).",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "ID del documento HEU"},
                },
                "required": ["document_id"],
            },
        ),
        Tool(
            name="create_heu_document",
            description=(
                "Crea e condivide un nuovo documento HEU partendo da un template esistente. "
                "Invia email ai destinatari. IMPORTANTE: chiedere conferma all'utente prima di eseguire."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source_document_id": {"type": "string", "description": "ID del template sorgente"},
                    "document_name": {"type": "string", "description": "Nome del nuovo documento"},
                    "document_type": {"type": "string", "enum": ["document", "template"], "description": "Default: document"},
                    "email_subject": {"type": "string", "description": "Oggetto email di condivisione"},
                    "email_text": {"type": "string", "description": "Corpo email di condivisione"},
                    "email_to": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista email destinatari (oppure stringa singola)",
                    },
                    "placeholders": placeholders_kv_schema,
                },
                "required": ["source_document_id", "email_subject", "email_text", "email_to"],
            },
        ),
        Tool(
            name="prompt_heu_document_signature",
            description=(
                "Invia un sollecito di firma per un documento HEU. "
                "Limite: 1 prompt ogni 24h per documento (altrimenti 429). "
                "IMPORTANTE: chiedere conferma all'utente prima di eseguire."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "ID del documento HEU"},
                },
                "required": ["document_id"],
            },
        ),
        Tool(
            name="download_heu_document_pdf",
            description=(
                "Scarica il PDF di un documento HEU e lo salva localmente. Ritorna il path del file. "
                "Layout opzionale (codici a 3 cifre della UI HEU)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "ID del documento HEU"},
                    "layout": {
                        "type": "string",
                        "enum": [
                            "100", "200", "201", "202", "203", "204",
                            "210", "211", "212", "213", "214",
                            "220", "221", "222", "223", "224",
                            "230", "231", "232", "233", "234",
                        ],
                        "description": "Codice layout (opzionale)",
                    },
                    "has_index": {"type": "boolean", "description": "Includi indice (opzionale)"},
                    "has_footer": {"type": "boolean", "description": "Includi footer (opzionale)"},
                    "output_path": {"type": "string", "description": "Path output personalizzato (opzionale, default: HEU_DOWNLOAD_DIR/heu_<id>.pdf)"},
                },
                "required": ["document_id"],
            },
        ),
        # ---------- PDFs (uploaded) ----------
        Tool(
            name="list_pdf_documents",
            description="Lista PDF documenti/template caricati su HEU.",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["document", "template"], "description": "Tipo (richiesto)"},
                    "sort": {"type": "string", "enum": ["asc", "desc"], "description": "Ordinamento"},
                },
                "required": ["type"],
            },
        ),
        Tool(
            name="get_pdf_document",
            description="Dettaglio di un PDF documento/template HEU per ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "ID del PDF"},
                },
                "required": ["document_id"],
            },
        ),
        Tool(
            name="list_pdf_document_signers",
            description="Lista i firmatari di un PDF.",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "ID del PDF"},
                },
                "required": ["document_id"],
            },
        ),
        Tool(
            name="list_pdf_document_signer_placeholders",
            description="Lista i placeholder/campi di firma di un signer specifico su un PDF.",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "ID del PDF"},
                    "signer_id": {"type": "string", "description": "ID del firmatario"},
                },
                "required": ["document_id", "signer_id"],
            },
        ),
        Tool(
            name="list_pdf_document_placeholders",
            description="Lista tutti i placeholder/campi di firma di un PDF.",
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "ID del PDF"},
                },
                "required": ["document_id"],
            },
        ),
        Tool(
            name="create_pdf_document",
            description=(
                "Crea e condivide un nuovo PDF firmabile partendo da un template PDF esistente. "
                "Richiede signers e (opzionalmente) i valori dei placeholder. "
                "Con signature_type='fea' serve avere credito FEA sufficiente. "
                "IMPORTANTE: chiedere conferma all'utente prima di eseguire."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source_document_id": {"type": "string", "description": "ID del template PDF sorgente"},
                    "document_name": {"type": "string", "description": "Nome del nuovo documento"},
                    "signature_type": {"type": "string", "enum": ["fes", "fea"], "description": "Tipo firma. Default: fes"},
                    "email_subject": {"type": "string", "description": "Oggetto email di condivisione"},
                    "email_body": {"type": "string", "description": "Corpo email di condivisione"},
                    "signers": {
                        "type": "array",
                        "items": pdf_signer_schema,
                        "description": "Lista firmatari (richiesto)",
                    },
                    "placeholders": {
                        "type": "array",
                        "items": pdf_placeholder_schema,
                        "description": "Valori dei placeholder (opzionale)",
                    },
                },
                "required": ["source_document_id", "email_subject", "email_body", "signers"],
            },
        ),
        Tool(
            name="prompt_pdf_document_signature",
            description=(
                "Invia un sollecito di firma per un PDF. "
                "IMPORTANTE: chiedere conferma all'utente prima di eseguire."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string", "description": "ID del PDF"},
                },
                "required": ["document_id"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    cfg_err = _check_config()
    if cfg_err and name != "get_heu_health":
        return [TextContent(type="text", text=cfg_err)]

    try:
        if name == "get_heu_health":
            if not API_KEY:
                return [TextContent(type="text", text="HEU_API_KEY non configurata.")]
            status, body, _ = _request("GET", "/health")
            return _ok(body) if status == 200 else _err(status, body)

        # ---------- DOCUMENTS ----------
        if name == "list_heu_documents":
            params = {}
            for k in ("type", "sort", "created_from", "created_to"):
                if k in arguments and arguments[k] is not None:
                    params[k] = arguments[k]
            if "have_editors_signed" in arguments and arguments["have_editors_signed"] is not None:
                params["have_editors_signed"] = "true" if arguments["have_editors_signed"] else "false"
            status, body, _ = _request("GET", "/documents", params=params)
            return _ok(body) if status == 200 else _err(status, body)

        if name == "get_heu_document":
            doc_id = arguments["document_id"]
            status, body, _ = _request("GET", f"/documents/{doc_id}")
            return _ok(body) if status == 200 else _err(status, body)

        if name == "list_heu_document_placeholders":
            doc_id = arguments["document_id"]
            status, body, _ = _request("GET", f"/documents/{doc_id}/placeholders")
            return _ok(body) if status == 200 else _err(status, body)

        if name == "create_heu_document":
            to_addr = arguments["email_to"]
            if isinstance(to_addr, list) and len(to_addr) == 1:
                to_addr = to_addr[0]
            payload = {
                "source_document_id": arguments["source_document_id"],
                "email": {
                    "subject": arguments["email_subject"],
                    "text": arguments["email_text"],
                    "to_addresses": to_addr,
                },
            }
            if "document_name" in arguments:
                payload["document_name"] = arguments["document_name"]
            if "document_type" in arguments:
                payload["document_type"] = arguments["document_type"]
            if "placeholders" in arguments and arguments["placeholders"]:
                payload["placeholders"] = arguments["placeholders"]
            status, body, _ = _request("POST", "/documents", json=payload)
            return _ok(body) if status in (200, 201) else _err(status, body)

        if name == "prompt_heu_document_signature":
            doc_id = arguments["document_id"]
            status, body, headers = _request("POST", f"/documents/{doc_id}/signatures/prompts")
            if status in (200, 201):
                return _ok(body)
            hint = None
            if status == 429:
                retry = headers.get("retry-after")
                hint = f"Sollecito già inviato di recente. Riprova tra {retry}s." if retry else "Sollecito già inviato di recente. Limite 1/24h."
            return _err(status, body, hint=hint)

        if name == "download_heu_document_pdf":
            doc_id = arguments["document_id"]
            payload = {}
            for k in ("layout", "has_index", "has_footer"):
                if k in arguments and arguments[k] is not None:
                    payload[k] = arguments[k]
            kwargs = {"timeout": DOWNLOAD_TIMEOUT}
            if payload:
                kwargs["json"] = payload
            status, body, headers = _request("POST", f"/documents/{doc_id}/download", **kwargs)
            if status != 200:
                return _err(status, body)
            if not isinstance(body, (bytes, bytearray)):
                return _err(status, body, hint="Atteso PDF binario, ricevuto altro contenuto.")
            output_path = arguments.get("output_path")
            if output_path:
                out = Path(output_path)
            else:
                DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
                out = DOWNLOAD_DIR / f"heu_{_safe_filename(doc_id)}.pdf"
            out.write_bytes(body)
            return _ok({
                "saved_to": str(out.resolve()),
                "size_bytes": len(body),
                "content_disposition": headers.get("content-disposition"),
            })

        # ---------- PDFs ----------
        if name == "list_pdf_documents":
            params = {"type": arguments["type"]}
            if "sort" in arguments and arguments["sort"]:
                params["sort"] = arguments["sort"]
            status, body, _ = _request("GET", "/pdfs", params=params)
            return _ok(body) if status == 200 else _err(status, body)

        if name == "get_pdf_document":
            doc_id = arguments["document_id"]
            status, body, _ = _request("GET", f"/pdfs/{doc_id}")
            return _ok(body) if status == 200 else _err(status, body)

        if name == "list_pdf_document_signers":
            doc_id = arguments["document_id"]
            status, body, _ = _request("GET", f"/pdfs/{doc_id}/signers")
            return _ok(body) if status == 200 else _err(status, body)

        if name == "list_pdf_document_signer_placeholders":
            doc_id = arguments["document_id"]
            signer_id = arguments["signer_id"]
            status, body, _ = _request("GET", f"/pdfs/{doc_id}/signers/{signer_id}/placeholders")
            return _ok(body) if status == 200 else _err(status, body)

        if name == "list_pdf_document_placeholders":
            doc_id = arguments["document_id"]
            status, body, _ = _request("GET", f"/pdfs/{doc_id}/placeholders")
            return _ok(body) if status == 200 else _err(status, body)

        if name == "create_pdf_document":
            payload = {
                "source_document_id": arguments["source_document_id"],
                "email": {
                    "subject": arguments["email_subject"],
                    "body": arguments["email_body"],
                },
                "signers": arguments["signers"],
            }
            if "document_name" in arguments:
                payload["document_name"] = arguments["document_name"]
            if "signature_type" in arguments:
                payload["signature_type"] = arguments["signature_type"]
            if "placeholders" in arguments and arguments["placeholders"]:
                payload["placeholders"] = arguments["placeholders"]
            status, body, _ = _request("POST", "/pdfs", json=payload)
            if status in (200, 201):
                return _ok(body)
            hint = None
            if status == 422:
                hint = "Crediti FEA insufficienti per il numero di firmatari."
            return _err(status, body, hint=hint)

        if name == "prompt_pdf_document_signature":
            doc_id = arguments["document_id"]
            status, body, _ = _request("POST", f"/pdfs/{doc_id}/signatures/prompts")
            return _ok(body) if status in (200, 201) else _err(status, body)

        return [TextContent(type="text", text=f"Tool sconosciuto: {name}")]

    except httpx.HTTPError as e:
        return [TextContent(type="text", text=f"Errore HTTP: {str(e)}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Errore: {str(e)}\n{traceback.format_exc()}")]


async def _run():
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


def main():
    import asyncio
    asyncio.run(_run())


if __name__ == "__main__":
    main()
