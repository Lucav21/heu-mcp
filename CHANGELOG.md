# Changelog

Tutte le modifiche significative a questo progetto vengono documentate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/),
e questo progetto aderisce a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-04

### Added
- Prima release pubblica.
- 14 tool MCP che coprono interamente l'API HEU Legal v1:
  - Documenti nativi: list, get, list placeholders, create, prompt signature, download PDF.
  - PDF caricati: list, get, list signers, list signer placeholders, list placeholders, create, prompt signature.
  - Health check.
- Variabili d'ambiente: `HEU_API_KEY`, `HEU_BASE_URL`, `HEU_DOWNLOAD_DIR`.
- Compatibilità Python 3.10+.
- Documentazione README con esempi di configurazione per Claude Desktop e Claude Code.
