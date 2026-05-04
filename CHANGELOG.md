# Changelog

Tutte le modifiche significative a questo progetto vengono documentate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/),
e questo progetto aderisce a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4] - 2026-05-04

### Fixed
- Corretto il case del namespace MCP Registry: `io.github.Lucav21/heu-mcp` (case-match con l'username GitHub canonical, richiesto dal registry).

## [0.1.3] - 2026-05-04

### Changed
- Aggiornato namespace MCP Registry e URL del repository al nuovo username GitHub `Lucav21`.

## [0.1.2] - 2026-05-04

### Added
- Marker `mcp-name` nel README per la verifica di ownership richiesta dal MCP Registry ufficiale.

## [0.1.1] - 2026-05-04

### Fixed
- Corretti gli URL del progetto (homepage, repository, issues) che puntavano a un username GitHub errato.

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
