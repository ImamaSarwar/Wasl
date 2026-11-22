# Deliverables, decisions, and bugs already fixed

## Deliverables made in this chat
1. **Revised proposal** `Wasl_Project_Proposal_Revised_v2.docx` (edited from the user's docx by editing the XML). Changes: statuses marked planned/built, Table 13 counts, a preliminary results paragraph, an honest test-split statement, Table 11 S2/S3 wording, a "Known gaps" sentence, an AI declaration about question authorship, a cost assumption note, a risk-table quota note. It needs updating again with final numbers.
2. **Evaluation deck, plain look:** a 13-slide Slides artifact "Wasl AI Evaluation" (https://claude.ai/artifact/ShSVeMtKpv1kYwXEihAQo3). Dark/light navy-green style, Space Grotesk and Inter.
3. **Evaluation deck, template look:** a 14-slide Slides artifact "Wasl AI Evaluation (Template)" (https://claude.ai/artifact/MgQpWGwPs7QwW9npKvJWTt), built on the peach/navy template from Imama's Canva PDF. Illustrations were cut from the PDF and uploaded; the heading font Cheddar is not on Google Fonts, so **Bungee** stands in. Pill text is navy instead of white for readability. The 14th slide (Thank You) comes from the template. Both decks are private until shared from the page's Share menu. The template deck was published but not visually checked; look for table overflow and crowded slides.
4. Slide content (both decks): setup, test sets, metrics, five systems, comparison table, takeaway, held-out, error groups, fixes, latency (cost not reported), targets vs measured, limits.

## Key decisions and why
- **Three-zone threshold** so borderline meaning matches go to the LLM to judge instead of being forced either way.
- **Database-only fallback** so a Gemini failure or a verifier rejection never leaves the user without an answer.
- **Verifier before display:** an unverifiable LLM answer is dropped.
- **Wilson intervals and bootstrap** because groups are small.
- **Cost never assumed:** only from user-supplied prices.
- **Imama's questions kept as held-out** until tuning consumed them; now dev.
- **Prompt-only baseline kept honest:** its strength on meaning search is reported (0.93 vs 0.80), not hidden.

## Bugs found and fixed (do not reintroduce)
- Gemini 503/429 and an overloaded `gemini-3.8-flash`: switched to `gemini-3.5-flash-lite`; evals cached and resumable.
- Verifier too strict: gloss with wrapping quotes, lemma spelling, quoted Arabic, counts of forms. Fixed with `_gloss_norm`, `_canon`, quote allowlist, extra allowed counts.
- My slicing bug `OTHER_SURAH.pattern[:-0]` made every question refuse. Fixed by concatenating the pattern.
- A test assumed an ayn/hamza lemma collision that does not exist in the data; replaced with `ʿaliym` and `aajr` resolution assertions.
- Docx edit: the first row matcher hit multiple rows and a multi-`w:t` run broke replacement. Fixed with exact first-cell matching and operating over all `w:t` elements.
- Old cache entries reported 0 ms and 0 tokens. Flagged `measured=False`.
- Over-refusal root cause was the concept-route hijack (see architecture file).
- `vite` missing: the user ran `npm install`.

## Things the assistant must not do
- Claim the held-out numbers support the proposal targets; they do not.
- Invent prices, costs or statistics.
- Paste or request the API key in chat.
- Commit or push without being asked.
