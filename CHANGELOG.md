# Changelog

## 0.2.0 - 2026-07-13
### Fixed
- ACP stdio server delivered no session updates (called a nonexistent connection method); serve() now also awaits acp.run_agent, which is a coroutine in SDK 0.11.
- Model thought chunks no longer leak into user-visible response text.
### Changed
- Backend processes are spawned once per session and reused across turns; instruction sent once; conversation continuity handled by the backend session. Context.close() releases resources.
- prompt_stream() streams chunks live during generation.
- Backend registry updated to current CLIs (gemini --acp, @agentclientprotocol adapter packages); removed placeholder openai/ollama backends; added preflight check for missing CLIs.
- Requires agent-client-protocol >= 0.11.
### Added
- 11 new pre-registered backends from the ACP Registry: copilot, opencode, goose, qwen, cursor, grok, cline, auggie, kilo, devin, kimi.

## 0.1.1 - 2026-03-07
- Initial public release.
