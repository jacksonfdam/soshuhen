# Three voices when a chapter is read aloud

> **Status: not built.** The experiment this design was gated on did not pass (see "Result" below),
> and on 18 November 2026 the user chose to stop and keep the one-voice reading. This document is
> kept as the record of what was tried and why it was not built, so the same route is not taken
> again without new evidence.

## Why

The comic reader reads a chapter aloud in one voice (`2026-11-17-reader-narration-design.md`). After
hearing it on a real chapter, the user asked for narration that tells the characters apart and
changes voice with them.

Text recognition cannot say who is speaking, so three trials looked for something local that can:

- **Two general vision models** already installed on the machine could not. Each split one
  character into two people, and neither recognised anyone on the next page.
- **A model built for comics** (Magi v3, University of Oxford) could, in part. On a manga page it
  grouped all six drawings of the lead character as one person, and across four consecutive pages
  it kept him as one person in 20 of 21 drawings.
- It does **not** keep side characters apart across pages, and a speaker who is never drawn cannot
  be tied to anyone.

What that supports honestly is three voices, not one per character: **the main character, everyone
else, and the narrator**. The user chose to build that, on their own machine.

## Goals

- When a chapter is read aloud, dialogue of the **main character** is in one voice, dialogue of
  **anyone else** in a second, and the narrator's announcements and narration boxes in a third.
- **Sound effects and credits are not read**, which also removes a known defect of the one-voice
  reading.
- **Narration never waits for voices.** Read aloud starts at once in one voice, exactly as today.
  Pages are prepared in the background, a little ahead of where the listener is, and narration uses
  three voices on every page that is ready when it is reached.
- **A chapter is prepared once.** What was worked out is kept, so listening again, or coming back
  tomorrow, has three voices from the first page.
- **A chapter can be prepared ahead of listening**, from the chapter list.
- **No page leaves the installation**, as before.
- **Optional and off by default.** Without the new service nothing changes, including for an
  installation that runs the one-voice narrator.

## Non-goals

- A voice per character. The evidence supports three roles.
- Matching a voice to a character's gender or age. The model does not say either.
- Identifying a speaker who is not drawn.
- Chapters that are streamed rather than downloaded. They stay in one voice; only an archive on disk
  is prepared.
- Preparing chapters nobody has asked for. Nothing is prepared at download time.
- A GPU, the Android client, languages other than English.

## Anti-goals

- **A page or its text sent to a third party**, by default or by fallback.
- **Narration that stalls on the voices.** A page that is not ready, or a service that is down, is
  read in one voice.
- **Background work that takes the machine away from the user, or never ends.** It runs one page at
  a time, with a ceiling on processors and memory, in a lane of its own that no other job waits
  behind, and only ever on the one chapter most recently asked for.
- **Model weights in the repository or in an image.** Their terms allow personal and non-commercial
  use; redistribution is the authors' to grant. The user fetches them.
- **Pretending to more than is known.** The reader does not show or announce character names, and
  the documentation says how often a voice is wrong.

## What the trials do and do not show

All of it comes from a handful of pages judged by eye, and this section is the whole of it.

- **Who a line is given to was checked for correctness on one page**, a black-and-white manga page
  of 16 letterings read alone: 8 right, 1 unclear, 4 given to nobody, 3 wrong. All three wrong ones
  were speakers outside the panel, given to the character in view.
- **How many lines get any speaker** was counted on four pages: 11 of 16, 8 of 11, 4 of 8, and on
  colour strip pieces 6 of 7.
- **The same character across pages** was checked on four consecutive manga pages by one method
  (below): the lead in 20 of 21 drawings; two drawings of someone else wrongly merged into him;
  side characters not kept together.
- **On colour strips**, within one page, two characters who look alike were merged into one.
  Nothing about following a character across strip pages has been tried.
- **The model also reports** which lettering is dialogue rather than a sound effect, and which
  bubbles have a tail. The first was seen to be right on the few strip pieces looked at. The second
  has not been looked at.

So "the main character's voice is right most of the time" and "about one line in five is wrong" are
what one page suggests, not a measurement, and the first task below exists to replace them with
one.

## Approaches

**What tells characters apart.** Decided with the user over three trials.

- *The comic-specific model, local (chosen).* The only local option that grouped a character's
  drawings correctly. Slow, and limited as described above.
- *A general vision model, local.* Tried twice; unreliable in the way that matters most (one person
  read as two).
- *A vision model over an API.* Likely to do better, including speakers who are not drawn. Sends
  every page out. Declined again.
- *Alternating voices with no identity.* Cheap, wrong whenever a character speaks twice running.

**When the work is done.** Decided with the user: **start at once, voices join in.**

No chapter has been prepared end to end. One model pass was timed at 12 to 30 seconds on this
machine's processor, and counting the passes four real chapters need gives an estimate of 7 to 75
minutes a chapter: a paged chapter is one pass a page, a long strip page is many.

- *In the background while listening, kept afterwards (chosen).*
- *A "prepare" action first, then listen.* Three voices from the first page, after that wait.
- *Per page while the reader waits, nothing kept.* A minute of silence per page. Rejected.

*What the chosen one means in practice, which the user should know before approving:* preparing is
about as fast as listening. On a paged chapter the work should stay ahead of a listener. On a
chapter of long strip pages it may not, and a first listen can stay in one voice for most of the
chapter; the three voices are then there the second time. *My call:* for that reason the second
option is built too, as a small **Prepare voices** action on a chapter in the chapter list. It is
the same request the reader makes by itself, made early.

**Who does the work.** *My call:* a job in the existing queue, in a new lane with its own worker.

- *A queue job (chosen).* The queue already gives leases, retries, de-duplication and a record of
  what ran. A lane of its own keeps a job that runs for an hour from holding a slot that list
  syncs and downloads need, which is the reason the two existing lanes were split.
- *The api, in a background task.* No queue change, but the work would die with every api restart
  and nothing would say what happened to it.
- *The speaker service keeping its own list of work.* It would need the database or the library,
  and it is kept sealed precisely so that it has neither.

## Not yet proven: the first task

**The first task of the plan is an experiment, and nothing else is built until it passes.** It
settles four things on one manga chapter and one colour strip chapter from the library, judged by
eye on at least forty drawings of characters and forty lines of dialogue in each.

1. **Colour strips.** Whether a character can be followed across strip pages at all.
2. **The method for following a character.** Two candidates:
   - *Side by side:* neighbouring pages in one image. Tried on manga. Two passes a page, and each
     page at half its detail, which is probably why side characters fell apart. It only links a
     page to its neighbour, so pages must be prepared in reading order from the first page.
   - *A reference sheet:* one pass a page, with small crops of the characters seen so far set
     beside the page. Not tried. Pages can be prepared in any order.
3. **Who a line is given to**, under the method chosen, on both kinds of chapter.
4. **Narration boxes.** Whether "no speaker and no tail" picks them out from speech by someone
   unseen.

It passes when, on a chapter:

- at least 85 in 100 drawings of the main character are labelled as the main character,
- no more than 10 in 100 drawings of anyone else are, and
- no more than 25 in 100 lines of dialogue are given to the wrong role (main for other, or other
  for main).

What follows from the result, each of which goes to the user before more is built:

- **Neither method passes on the strip chapter:** stop. The user decides whether a feature for
  paged manga alone is worth building.
- **Only side by side passes:** preparing always starts at a chapter's first page and goes in
  order, so "voices join in" holds only for a listener who starts at the beginning, and a chapter
  costs twice the passes estimated above.
- **Point 4 fails:** every line with no known speaker is read in the "others" voice, and the
  narrator's voice is kept for announcements.

The counts are written into this document.

### Result: it did not pass, and nothing below was built

Run on 18 November 2026, sealed, on eight consecutive pages of a black-and-white manga chapter and
the first thirty pages of a colour strip chapter, with both methods. Judged by eye; every figure is
a count of what was looked at.

**Colour strip, reference sheet** (the better method there), 64 drawings and 25 lines judged:

| Measure | Needed | Got |
|---|---|---|
| Drawings of the main character labelled as him | at least 85 in 100 | 15 of 18 (83) |
| Drawings of anyone else labelled as him | at most 10 in 100 | 10 of 46 (22) |
| Lines given to the wrong role | at most 25 in 100 | 9 of 25 (36) |

The chapter's first thirty pages hold 25 lines of dialogue and narration, short of the forty asked
for. Of 19 sound effects and credits, 14 were correctly left out and 5 were taken for dialogue.

**Colour strip, side by side:** the main character was labelled in 7 of 80 drawings, all in the
first six pages, and the thirty pages produced 50 separate identities. It does not follow anyone.

**Manga, both methods:** fine for the first four pages and then lost. From the fifth page on, where
a new scene begins and the lead appears in most panels, the reference sheet labelled none of his
drawings as him across four pages, and side by side none across the last three. About 20 of his
roughly 38 drawings were recognised with the reference sheet. The earlier trial's "20 of 21" was
those first four pages.

**Narration boxes** (point 4): all 7 real narration boxes on the strip were labelled narration, and
so were 8 things that are not (speech in bubbles without a tail, and sound effects). Seven right in
fifteen.

By the rule set above, the work stopped here. The sections that follow describe what would have
been built and are kept as the record of the design, not as a plan.

## How it works

```
reader ── POST …/chapters/{id}/voices {page} ──> api ── note where the listener is, enqueue
                                                             │
   worker-voices <───────────────────────────────────────────┘
        │  until the chapter is done, or another chapter is asked for:
        │    next page not yet prepared, a little ahead of the listener
        │    page bytes from the archive, cast so far ──> speakers
        │    store one row and the cast
        ▼
reader ── GET …/pages/{n}/transcript ──> api ── narrator, as today
                                               └ a row for the page? lay it over the transcript
reader ── GET …/chapters/{id}/voices ──> api ── who the main character is, so far
```

### The speakers service

A new top-level folder `speakers/`, shaped like `narrator/`: its own dependencies, tests, image and
compose profile, importing nothing from `backend/` or `narrator/`. It holds PyTorch (processor
build), Transformers pinned to the version the model's code was written against, and a thin HTTP
surface.

- **The model is not in the image.** Its weights live in a directory the user fills once with a
  documented command and the service mounts read-only. On start the service checks the weight
  file's SHA-256 and the model revision against values pinned in its source, and refuses to start
  on a mismatch. The model's own Python files come from that same directory and are run by
  Transformers; they were read for the trial and reach for nothing but the libraries they import.
- **Sealed like the narrator, and more.** Internal network with no route out, shared only with the
  worker that calls it; read-only filesystem; no capabilities; not root; limits on memory and on
  processors, the latter set from an environment variable. Hugging Face's libraries are told to
  work offline and send no usage data.
- **It never reads the lettering.** It answers boxes and relations only, so nothing it returns or
  logs contains page text.

Contract:

```
POST /v1/pages          multipart: the page image, and the cast so far, which may be empty
200  {
       "engine": "magiv3 @ <revision>",
       "width": 800, "height": 1138,
       "characters": [ { "box": [x, y, w, h], "identity": 3 } ],
       "texts":      [ { "box": [x, y, w, h], "speaker": 0 | null,   // index into characters
                         "dialogue": true, "tail": true } ],
       "cast":       "<opaque>"                                      // the cast, updated
     }
413 / 422               as the narrator answers them
GET /healthz
```

`identity` is a number that means the same character for the whole chapter. **The cast** is how
that is kept without the service remembering anything: an opaque value the caller stores and hands
back with the next page. What is in it (reference crops, or the previous page) belongs to whichever
method the first task chooses. A page taller than two and a half times its width is cut into
page-shaped pieces inside the service, as the trial did.

### Storage

One migration, `0033`. Neither table knows about reading direction: what the model sees does not
depend on it.

- `page_speakers` — `chapter_id` (cascade), `page`, `body` (jsonb), `engine`, `created_at`; primary
  key on the first two. `body` is the service's answer without the cast: the characters with their
  chapter identities, and the texts with speaker, `dialogue` and `tail`. A page the service could
  not read is stored with `unreadable` set and nothing else, so it is not tried again.
- `chapter_voices` — `chapter_id` (primary key, cascade), `cast` (bytea), `wanted_page`,
  `requested_at`, `updated_at`. One row per chapter that has been asked for.

Roles are not stored. **The main character is whoever has been drawn most in the chapter so far**,
counted from the stored rows when asked. A chapter opened on a page the lead is not on therefore
corrects itself as more pages are prepared, with nothing to rewrite.

Deleting a chapter's rows is how it is prepared again.

### The queue

- A new job type, `chapter_voices`, with payload `{chapter_id}` and that chapter as its
  `dedupe_key`: asking twice queues once. Where the listener is travels in the `chapter_voices`
  row, not in the payload, because a queued job's payload cannot be changed and a second job with
  the same key is refused while the first is pending or leased.
- A third lane, `voices`, holding only that type, and a worker for it: the same image as the other
  two with `LANE=voices`, concurrency one, behind the same compose profile as the speakers service.
  An installation without the profile has no such worker, and the api queues nothing unless the
  speakers service is configured.
- **One job prepares one chapter and holds its lease while it does**, calling `renew_lease()` after
  every page, which is what `docs/jobs.md` asks of a long handler. It does not hand a remainder to
  a successor: the de-duplication that makes asking twice harmless would refuse it.
- **Which page next:** the first unprepared page at or after `wanted_page` plus a small lead, then
  on to the end, then from the start. Read from the row before every page, so a listener who jumps
  is followed at the next page. If the first task chooses side by side, the order is instead the
  chapter's own, from its first page.
- **Only the latest chapter.** Before every page the handler checks whether another chapter has
  been asked for more recently. If one has, it finishes, leaving its rows; it goes on when its
  chapter is asked for again. Skimming five chapters leaves five short starts, not hours of work.
- **Every page is its own transaction**, the row and the cast together, so a worker that dies
  resumes at the next unprepared page when the job is leased again.
- **Failures are told apart.** A page the service answers 413 or 422 for is stored as unreadable
  and the job goes on. A service that cannot be reached fails the job, which the queue retries at
  one, five and twenty-five minutes; nothing is stored for that page, so an outage never leaves a
  chapter marked as prepared in one voice.

### The api

- `Settings.speakers_url`, from `SPEAKERS_URL`, empty by default. Voices are available when both
  it and the narrator are configured.
- `GET /api/reader/narration` gains `"voices": true|false`.
- `POST /api/reader/chapters/{id}/voices` with the page the listener is on: notes it in the
  chapter's row and queues the job. 409 for a chapter with no archive on disk, 503 when voices are
  not available.
- `GET /api/reader/chapters/{id}/voices`: `{"prepared": 12, "total": 23, "working": true,
  "main": 3 | null}`. Never cached.
- `DELETE /api/reader/chapters/{id}/voices`: forgets what was prepared.
- `GET …/pages/{n}/transcript` keeps its shape. The narrator is asked as today. When the page has a
  row, a **pure function** in `backend/app/reader/`, beside the narrator client, lays it over the
  transcript: every block gains `kind` and `speaker` from the model's text box it overlaps most,
  and the answer says `"voices": "ready"`. With no row it says `"pending"` when the chapter has
  been asked for and `"off"` otherwise. A ready answer holds nothing that later pages can change,
  so it keeps the day-long cache; a pending one is sent `no-store`, or the browser would keep the
  one-voice page after its voices were ready.

How a block is labelled:

- overlaps a text the model calls dialogue, with a speaker: `speech`, that identity
- dialogue, no speaker, a tail: `speech`, speaker unknown
- dialogue, no speaker, no tail: `narration` (subject to point 4 of the first task)
- not dialogue: `effect`
- overlaps no text box at all: `speech`, speaker unknown

### The reader

- **Starting.** Turning Read aloud on, when voices are available and the chapter is an archive,
  also posts the page on screen to the voices route, and does so again at each page turn. Nothing
  else about starting changes.
- **Who the main character is.** Asked of the chapter's voices route when a page's script is built.
  A block's role is worked out then, in the reader: `main` when its speaker is that identity,
  `other` for any other speaker or an unknown one, `narrator` for narration.
- **Which voice.** The narration script gives every item a voice: the narrator for page and panel
  announcements and for narration, `main` and `other` for speech. Effects are left out of what is
  said and stay in the transcript panel, marked.
- **Pages that were not ready.** A transcript that came back `pending` is spoken as it is and asked
  for again the next time its page is shown, instead of being kept.
- **The player.** The shared read-aloud player takes a voice per block. The prose reader passes
  none and is unchanged.
- **Three voices from one browser.** The saved read-aloud setting gains two optional voices beside
  the existing one. Left on automatic, the reader picks two other voices of the narrator voice's
  language from what the browser offers; where it offers only one, the same voice is used at a
  lower and a higher pitch. A Voices section in the reader's settings sheet shows the three and
  lets each be chosen.
- **Preparing ahead.** The chapter list shows, for a downloaded chapter, a Prepare voices action
  and how far a prepared chapter has got. It makes the same request the reader does.
- **Nothing is announced about voices.** A listener hears the change, and the transcript panel
  shows each line's role beside it.

### Running it

- Compose: `speakers` and `worker-voices` behind `profiles: ["voices"]`. `SPEAKERS_URL` and the
  processor ceiling in `.env.example`, both commented.
- Turning it on: fetch the weights with the documented command, set `SPEAKERS_URL`, start the
  profile, recreate `api`. It needs the narrator profile as well; the documentation says so.
- `docs/features.md`, `docs/configuration.md`, `docs/architecture.md`, `docs/jobs.md`,
  `docs/data-model.md` and `CLAUDE.md` gain the service, the lane, the job type and the two tables.
  `docs/features.md` says in plain words what a listener should expect, from the first task's
  counts, and `docs/configuration.md` carries the model's terms of use.

### Tests

- `speakers/`: geometry, cutting strips, the cast, and the HTTP surface against a stand-in model.
  The real model is **not** run in CI: its weights are not redistributable and are not in the
  repository. One test, skipped unless a weights directory is given, runs it on a page the test
  draws.
- Backend: laying a row over a transcript, case by case; who the main character is from stored
  counts; the handler against a stand-in service (follows the listener, resumes after a death,
  stops for a newer chapter, stores an unreadable page, fails on an unreachable service and stores
  nothing); the routes; the lane.
- Frontend: voice per item in the script, role from the chapter's main character, the player's
  voice per block, choosing three voices from a list of browser voices, and a pending transcript
  being asked for again.

## Left to the builder

- The method for following a character, and what the cast holds, by the first task's result.
- The lead the worker keeps ahead of the listener, and how progress is reported.
- The memory limit and the default processor ceiling.
- The pitch offsets, and how voices are ranked when choosing automatically.
- Names inside `speakers/`, the exact multipart field names.
- Copy, in the interface's existing voice.

## Done

The first task's counts are in this document and it passed, or the user chose how to go on. With
both profiles running, in the web interface, on a downloaded paged chapter: Read aloud starts
within a second in one voice; within a few pages lines are heard in three voices and sound effects
stop being read; the transcript panel shows each line's role. Opening the same chapter again has
three voices from the first page. Prepare voices on another chapter shows its progress, and that
chapter is then heard in three voices from its first page. With the voices profile stopped, the
reader behaves exactly as it does today. CI passes.
