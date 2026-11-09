# FERNIMOON STUDIO — Football Mode

Football Mode is a separate production path. It does not replace the existing documentary workflow.

## Locked editorial profile

- Language: English.
- Narrator: male, low-register voice; confident, powerful sports-broadcast delivery.
- Scope: global major competitions. The active competition catalogue is resolved from API-Football at runtime and filtered through the maintained major-competition registry.
- Default output: 40-second, 9:16 Short; supported durations remain 35–45 seconds.
- Visual rule: no persistent FERNIMOON STUDIO watermark or channel text across scenes.
- Stock-media rule: Pixabay clips are illustrative B-roll only. They must never be described as the actual match, goal, or official highlights.

## Architecture

1. Orchestration / CLI selects documentary or football; pipeline.py dispatches to the matching production path.
2. Football data adapter calls API-Football v3, resolves active major competitions, retrieves live or date-scoped fixtures, and normalizes scores, teams, match state and competition metadata.
3. Editorial generation sends the verified match-data pack to Gemini and validates the resulting English narration against the existing scene and word-count schema.
4. Visual acquisition uses the existing Pixabay downloader to select relevant, licensed football stock footage. It is explicitly treated as illustrative, not match footage. User-owned or separately licensed match clips can be added later as a distinct media adapter.
5. Voice uses a dedicated FOOTBALL_ELEVENLABS_VOICE_ID; football voice settings favor a more energetic delivery. The selected voice itself must be a male low-register voice in the ElevenLabs account.
6. Render and QA reuse the existing FFmpeg renderer, timestamped captions, audio alignment, H.264/AAC output validation and artifact packaging.

## GitHub Actions secrets

Add these repository secrets before running Football Mode:

- FOOTBALL_API_KEY — API-Football key.
- FOOTBALL_ELEVENLABS_VOICE_ID — voice ID for the selected male, deep voice.
- Existing GEMINI_API_KEY, PIXABAY_API_KEY, and ELEVENLABS_API_KEY remain required.

The documentary workflow continues to use ELEVENLABS_VOICE_ID.

## Run locally

Set FERNIMOON_MODE=football, FOOTBALL_API_KEY, and FOOTBALL_ELEVENLABS_VOICE_ID, then run:

python -m fernimoon --mode football --topic "Global football roundup"

For a specific match date:

python -m fernimoon --mode football --date 2026-11-08 --topic "Premier League roundup"

For live matches, include "live" in the topic:

python -m fernimoon --mode football --topic "Live global football scores"

## Coverage and editorial limits

API-Football documents coverage per competition and season. A competition may not provide all events, lineups, player statistics or live scores, and provider updates can lag the live event. The script generator therefore may only state facts present in the retrieved payload. If no major fixtures are returned for the requested date, the pipeline stops rather than inventing a roundup.

This first implementation covers global major-competition fixture/live-score roundups. Match events, standings, player profiles, transfer-news verification, richer tactical analysis and authorized match-highlight ingestion are planned as separate adapters and workflows.
