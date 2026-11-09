# FERNIMOON STUDIO — Football Mode

Football Mode is a separate production path. It does not replace the existing documentary workflow.

## Locked editorial profile

- Language: English.
- Narrator: male, low-register voice; confident, powerful sports-broadcast delivery.
- Scope: global major competitions. The active competition catalogue is resolved from API-Football at runtime and filtered through the maintained major-competition registry.
- Output: 9:16 Full HD; supported duration presets are 30, 45, 60, 75 and 90 seconds.
- Visual rule: no persistent FERNIMOON STUDIO watermark or channel text across scenes.
- Stock-media rule: Pixabay clips are illustrative B-roll only. They must never be described as the actual match, goal, or official highlights.

## Architecture

1. Orchestration / CLI selects documentary or football; pipeline.py dispatches to the matching production path.
2. Football data adapter calls API-Football v3, resolves active major competitions, retrieves live or date-scoped fixtures, and can enrich selected fixtures with events or team statistics when competition coverage flags allow it.
3. Football News adapter reads allowlisted HTTPS RSS/Atom feeds from global publishers, normalizes headlines, excerpts, publication dates and URLs, filters by topic/category, deduplicates links and adds cautious headline-similarity metadata.
4. Research orchestrator merges news and match data into a fact index. Every generated narration scene must cite one or more exact fact IDs from that index; unsupported claims fail local validation.
5. Editorial generation sends the evidence pack to Gemini and applies format-specific instructions before validating the English narration against the duration-aware scene and word-count schema.
6. Visual acquisition uses the existing Pixabay downloader to select relevant, licensed football stock footage. It is explicitly treated as illustrative, not match footage. User-owned or separately licensed match clips can be added later as a distinct media adapter.
7. Voice uses a dedicated FOOTBALL_ELEVENLABS_VOICE_ID; football voice settings favor a more energetic delivery. The selected voice itself must be a male low-register voice in the ElevenLabs account.
8. Render and QA reuse the existing FFmpeg renderer, timestamped captions, audio alignment, H.264/AAC output validation and artifact packaging.

## GitHub Actions secrets

Add these repository secrets before running Football Mode:

- FOOTBALL_API_KEY — API-Football key.
- FOOTBALL_ELEVENLABS_VOICE_ID — voice ID for the selected male, deep voice.
- Existing GEMINI_API_KEY, PIXABAY_API_KEY, and ELEVENLABS_API_KEY remain required.

The documentary workflow continues to use ELEVENLABS_VOICE_ID.

Optional GitHub repository variables:
- FOOTBALL_NEWS_FEEDS — semicolon-separated HTTPS RSS/Atom feed URLs. Defaults: BBC Sport Football, The Guardian Football, ESPN Soccer and Sky Sports Football.
- FOOTBALL_NEWS_ALLOWED_DOMAINS — semicolon-separated additional publisher hostnames to allow. Default publisher domains are already allowlisted. Never add a domain unless it is a source you trust.

## Run locally

Set FERNIMOON_MODE=football, FOOTBALL_API_KEY, and FOOTBALL_ELEVENLABS_VOICE_ID, then run:

python -m fernimoon --mode football --topic "Global football roundup"

For a Manchester United global-news story:

python -m fernimoon --mode football --topic "Manchester United" --duration 60 --format auto

For a transfer watch:

python -m fernimoon --mode football --topic "Manchester United" --duration 45 --format transfer_watch

For a specific match date:

python -m fernimoon --mode football --date 2026-11-08 --topic "Premier League roundup" --duration 60 --format global_roundup

For live matches, include "live" in the topic:

python -m fernimoon --mode football --topic "Live global football scores" --duration 30

## Coverage and editorial limits

API-Football documents coverage per competition and season. A competition may not provide all events, lineups, player statistics or live scores, and provider updates can lag the live event. The script generator therefore may only state facts present in the retrieved payload. If no major fixtures are returned for the requested date, the pipeline stops rather than inventing a roundup.

This first implementation covers global major-competition fixture/live-score roundups. Match events, standings, player profiles, transfer-news verification, richer tactical analysis and authorized match-highlight ingestion are planned as separate adapters and workflows.

## Editorial formats and next architecture layers

The long-term Football Mode uses one shared data and render core with separate editorial recipes:

| Format | Required data | Editorial output |
|---|---|---|
| Global roundup | Fixtures, scores, competition, match state | Biggest stories across the matchday |
| Match preview / recap | Fixture, events, lineups where covered, recent form | One match, one central storyline |
| Tactical analysis | Events, team statistics, lineups and formations | Evidence-led tactical explanation; interpretation clearly separated from facts |
| Player spotlight | Player profile, teams, season statistics, honours | Career arc, current form and defining strengths |
| Transfer / drama | Official club statements plus multiple reputable news reports | Verified timeline, confirmed facts versus reported claims |
| Highlights / key moments | Licensed or user-owned match footage plus verified event timestamps | Short visual recap with source and rights metadata |

The next adapters should be isolated behind provider interfaces:
- Football data: fixtures, events, standings, team/player statistics, player profiles, transfers and injuries. Check the competition's coverage flags before requesting or narrating a field.
- Football news: RSS/official club and competition announcements first, then reputable publishers. Transfer or controversy claims require independent corroboration and publication timestamps.
- Media rights: user-owned clips, direct licenses, or media whose reuse terms explicitly allow the intended use. Do not rip broadcast feeds, paywalled video, YouTube highlights or social clips. Pixabay is only illustrative B-roll in the current implementation.
- Editorial ledger: every factual sentence maps to one or more retrieved records or article sources; uncertainty and opinion are labeled.
- Visual renderer: score cards, match timelines, player/stat cards, tactical boards and scene-specific captions. No always-on channel watermark; if branding is wanted later, use a brief end slate only.

The first code increment deliberately implements the fixture/live-score vertical slice before adding news and highlight ingestion. This avoids presenting unverified transfer rumours or copyrighted match footage as source material.


## Football Intelligence 2.0 — editorial formats

The workflow exposes these formats:

- auto — select the strongest supported angle from news and match evidence.
- global_roundup — up to three consequential stories across competitions.
- breaking_news — newest supported development, with attribution and status.
- transfer_watch — confirmed transfers, attributed reporting, negotiations and rumours kept distinct.
- match_preview — upcoming fixture context.
- match_recap — score and event timeline when the provider covers match events.
- tactical_analysis — team statistics only when the competition coverage flags expose them; analysis is labeled as interpretation.
- player_spotlight — player-related publisher reports and available match evidence.
- club_business — ownership, finance, board and stadium reporting.
- drama — controversy and disputes with neutral attribution.
- academy — youth and academy reporting.
- history_facts — historical football stories only when configured feed excerpts support the subject; a dedicated historical archive adapter remains future work.

Duration presets: 30, 45, 60, 75 and 90 seconds. The script validator scales the narration word budget and scene capacity with the selected duration. For longer videos it allows up to ten scenes.

## News source handling and limits

The first News Engine increment consumes RSS/Atom headlines and publisher-provided excerpts. It does not crawl paywalled article bodies or bypass access controls. A publisher feed can be added through FOOTBALL_NEWS_FEEDS, but its domain must be on the allowlist. Each article retains publisher, publication timestamp, URL and a stable source ID.

Headline similarity across publishers is only a discovery signal. It is not proof that reports are independent or that a claim is true. The editorial prompt and local fact-ID validator require each scene to reference the research pack, but human review remains necessary for sensitive allegations, transfer claims and rapidly changing news. Official club/league statements should take precedence when available.

The current news categories are filters over available feed excerpts, not guaranteed coverage. If a feed does not report on a transfer, player or club, the system must stop or use other supported evidence rather than inventing detail. Match recaps and tactical analysis are gated by API-Football coverage flags. This increment does not yet implement a full player-profile database, injury endpoint, transfer database, independent article full-text research or licensed match-highlight ingestion.

## Production and editorial safeguards

- Every football narration scene carries one or more exact fact_ids from the research pack.
- Scores and event records are attributed to API-Football; publisher reporting is presented as reporting, not as an official confirmation.
- A reported transfer interest is not described as a completed transfer.
- No invented quotes, injuries, lineups, scorers, assists, statistics or dressing-room claims.
- Pixabay footage is illustrative B-roll. It is not represented as official highlights or footage of the specific fixture.
- No persistent channel watermark is rendered across the video.
