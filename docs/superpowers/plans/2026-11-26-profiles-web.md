# Profiles (web) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the web console a Profiles section in Settings to create, edit, reorder and delete profiles and connect each profile's list accounts, and make the console see every series on the server.

**Architecture:** The web stays the managing profile's console: it never sends `X-Soshuhen-Profile` except to act on another profile's own accounts (disconnect). Pure profile logic lives in `src/lib/profiles.ts` with `node --test` tests; the screen is a new `ProfilesPanel` under `features/settings/`, built from `ui/` primitives plus a new `ui/Avatar`. Avatars are twelve original SVG files served from `public/avatars/`, the source of truth the Android plan reuses.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind 4 (tokens in `tailwind.config.ts`), `node --test` for pure modules.

**Spec:** `docs/superpowers/specs/2026-11-25-profiles-design.md` (sections "Web interface" and "Avatars"). Builds on the backend contract from `docs/superpowers/plans/2026-11-25-profiles-backend.md`, merged or on `feat/profiles` (jacksonfdam/soshuhen#289).

## Global Constraints

- Branch from `feat/profiles` while #289 is open, or from `main` once it has merged. Never put web work on `feat/profiles` itself.
- No picker in the web interface. Every request goes without the header, so the web acts as the managing profile; the one exception is `api.disconnect(provider, profileId)`, which sends `X-Soshuhen-Profile` because the backend reads the profile for disconnect from the header.
- Backend contract (verbatim from the backend plan):
  - `GET /api/profiles` returns `[{id, name, avatar, has_pin, is_manager, position}]`.
  - `POST /api/profiles` takes `{name, avatar, pin?}`.
  - `PATCH /api/profiles/{id}` takes `{name?, avatar?, pin?: string|null, position?}`, where `pin: null` clears the PIN.
  - `DELETE /api/profiles/{id}` returns `{ok, series_removed}`, or 409 for the manager.
  - `GET /api/profiles/{id}/connections` returns `[{provider, connected, account_name, uses_oauth}]`.
  - `PUT /api/profiles/{id}/credentials/{provider}` takes `{key}`.
  - `GET /api/auth/{provider}/start?profile_id=N`; the callback redirects to `/settings?connected={provider}&profile={id}`.
  - `GET /api/series?scope=all`; rows gain `held_by: number[]`.
  - `DELETE /api/series` returns `{ok, removed, deleted, skipped}`.
- Name: 1 to 40 characters. PIN: `^\d{4,6}$`. Avatar keys: `avatar-01` … `avatar-12`.
- The four rules in `CLAUDE.md` › The interface hold:
  - every colour or size lives in `tailwind.config.ts`;
  - verify classes by grepping `frontend/dist/` after a build;
  - no feature imports another feature;
  - no number the API cannot serve.
- Avatar SVGs are art assets, not components. Their colours are their own and they are exempt from the token rule. Each file is original work: no character, logo or likeness from any manga, anime or streaming service.
- Copy never calls the PIN security. It is described as keeping someone from opening the wrong profile by accident.
- Verification for every task: `npm test`, `npm run build` (which runs `tsc -b`), and a grep of `frontend/dist/assets/*.css` for every new class.

## Review Focus

1. **Deleting a profile**: the dialog must name the profile and say what goes with it, and a 409 for the manager must never be reachable from the UI. Test in Task 3 (`deleteConsequences`), plus the manager row has no delete button (Task 4 manual check).
2. **PIN editing**: leaving the PIN field empty when editing must keep the existing PIN, not clear it; clearing is its own action. Test in Task 1 (`profilePatch`).
3. **Reordering past either end**: moving the first profile up or the last down must change nothing and send nothing. Test in Task 1 (`reorder`).
4. **Returning from a sign-in for another profile** (`/settings?connected=anilist&profile=7`): the notice must name that profile, and a profile id that no longer exists must not crash the page. Test in Task 3 (`connectedNotice`).
5. **Removing from the console a series only another profile holds**: the notice must say it was skipped, not "Removed 0". Test in Task 5 (`removalNotice`).

---

### Task 1: Profile logic and API client

**Files:**
- Create: `frontend/src/lib/profiles.ts`, `frontend/src/lib/profiles.test.ts`
- Modify: `frontend/src/lib/api.ts` (types and methods below; `request` gains a way to send a profile header)

**Interfaces:**
- Produces in `lib/profiles.ts`:
  - `export const AVATAR_KEYS: readonly string[]` (`avatar-01` … `avatar-12`)
  - `export function avatarUrl(key: string): string` returns `/avatars/${key}.svg`, and `/avatars/avatar-01.svg` for an unknown key.
  - `export function validPin(pin: string): boolean`
  - `export function validName(name: string): boolean` (trimmed, 1 to 40 characters)
  - `export interface ProfileDraft { name: string; avatar: string; pin: string; clearPin: boolean }`
  - `export function profilePatch(before: Profile, draft: ProfileDraft): ProfilePatch | null` returns only the changed fields, with `pin` set to the new PIN when one was typed, `null` when `clearPin`, and absent otherwise. Returns `null` when nothing changed.
  - `export function reorder(profiles: Profile[], id: number, direction: -1 | 1): { id: number; position: number }[]` returns the PATCHes needed (both swapped profiles), or `[]` at either end.
  - `export function profileHeaders(profileId?: number): Record<string, string>` always includes `'Content-Type': 'application/json'`, and adds `'X-Soshuhen-Profile': String(profileId)` only when given.
- Produces in `lib/api.ts`:
  - `export interface Profile { id: number; name: string; avatar: string; has_pin: boolean; is_manager: boolean; position: number }`
  - `export interface ProfilePatch { name?: string; avatar?: string; pin?: string | null; position?: number }`
  - `export interface ProfileConnection { provider: string; connected: boolean; account_name: string | null; uses_oauth: boolean }`
  - `api.profiles()`, `api.createProfile(body: { name: string; avatar: string; pin?: string })`, `api.updateProfile(id, patch: ProfilePatch)`, `api.deleteProfile(id) -> { ok: boolean; series_removed: number }`, `api.profileConnections(id)`, `api.storeProfileCredential(id, provider, key)`
  - `api.authStart(provider: string, profileId?: number)` appends `?profile_id=` when given.
  - `api.disconnect(provider: string, profileId?: number)` and `api.sync(provider: string, profileId?: number)` send `profileHeaders(profileId)`. Both endpoints act for the request's profile, and the web sends no header otherwise, so without it they would act on the manager.
  - `api.series(state?: string, scope: 'own' | 'all' = 'all')`. The console asks for every series.
  - `api.removeSeries` result type becomes `{ ok: boolean; removed: number; deleted: number; skipped: number[] }`.
  - `Series` gains `held_by: number[]`.

- [ ] **Step 1: Write the failing tests in `lib/profiles.test.ts`** (node:test, the style of `readAloud.test.ts`)

```ts
test('a pin is four to six digits', () => {
  for (const ok of ['1234', '123456']) assert.equal(validPin(ok), true)
  for (const bad of ['', '123', '1234567', '12a4']) assert.equal(validPin(bad), false)
})

test('an empty pin field keeps the pin; clearing is explicit', () => {
  const before = { id: 2, name: 'Ana', avatar: 'avatar-02', has_pin: true, is_manager: false, position: 1 }
  assert.equal(profilePatch(before, { name: 'Ana', avatar: 'avatar-02', pin: '', clearPin: false }), null)
  assert.deepEqual(profilePatch(before, { name: 'Ana', avatar: 'avatar-02', pin: '', clearPin: true }), { pin: null })
  assert.deepEqual(profilePatch(before, { name: 'Bia', avatar: 'avatar-05', pin: '4321', clearPin: false }),
    { name: 'Bia', avatar: 'avatar-05', pin: '4321' })
})

test('moving past either end changes nothing', () => {
  const list = [p(1, 0), p(2, 1), p(3, 2)]
  assert.deepEqual(reorder(list, 1, -1), [])
  assert.deepEqual(reorder(list, 3, 1), [])
  assert.deepEqual(reorder(list, 2, -1), [{ id: 2, position: 0 }, { id: 1, position: 1 }])
})

test('an unknown avatar key falls back to the first', () => {
  assert.equal(avatarUrl('avatar-07'), '/avatars/avatar-07.svg')
  assert.equal(avatarUrl('nope'), '/avatars/avatar-01.svg')
})

test('the profile header is sent only when a profile is named', () => {
  assert.deepEqual(profileHeaders(), { 'Content-Type': 'application/json' })
  assert.deepEqual(profileHeaders(7), { 'Content-Type': 'application/json', 'X-Soshuhen-Profile': '7' })
})

test('a name is trimmed and 1 to 40 characters', () => {
  assert.equal(validName('  '), false)
  assert.equal(validName('x'.repeat(41)), false)
  assert.equal(validName(' Ana '), true)
})
```

- [ ] **Step 2: Run and see them fail.** `npm test` should fail with `Cannot find module './profiles.ts'`.
- [ ] **Step 3: Implement `lib/profiles.ts` and the `api.ts` additions.** `reorder` swaps the `position` of the moved profile with its neighbour in the list as sorted by `position, id`.
- [ ] **Step 4: Run `npm test` and `npm run build`.** Both should pass.
- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/profiles.ts frontend/src/lib/profiles.test.ts frontend/src/lib/api.ts
git commit -m "feat(web): profile logic and API client"
```

---

### Task 2: Avatars

**Files:**
- Create: `frontend/public/avatars/avatar-01.svg` … `avatar-12.svg`, and `frontend/src/ui/Avatar.tsx`
- Modify: `frontend/src/ui/index.ts` (export it), `frontend/tailwind.config.ts` (sizes)

**Interfaces:**
- Consumes: `avatarUrl` (Task 1).
- Produces: `export function Avatar({ avatar, name, size = 'md' }: { avatar: string; name: string; size?: 'sm' | 'md' | 'lg' })`. It renders an `<img>` with `alt={name}`, round, in `avatar-sm`, `avatar-md` or `avatar-lg` sizes.
- New spacing tokens in `tailwind.config.ts`: `'avatar-sm': '2rem'`, `'avatar-md': '3rem'`, `'avatar-lg': '5rem'`.

- [ ] **Step 1: Draw the twelve SVGs.**
  - Each is a 96×96 `viewBox` square, a flat full-bleed background colour, and one simple original character face or creature (round mascots, animals, a robot, a ghost and so on).
  - Each is distinct at 32 px and under 4 KB.
  - No text in the art, and nothing traced from or resembling existing works.
- [ ] **Step 2: Write `ui/Avatar.tsx`, add the tokens and export it.**
- [ ] **Step 3: Run `npm run build`,** then `grep -o 'avatar-sm\|avatar-md\|avatar-lg' dist/assets/*.css | sort -u`. Expected: all three classes. Also `ls dist/avatars | wc -l` should give `12`.
- [ ] **Step 4: Commit**

```bash
git add frontend/public/avatars frontend/src/ui/Avatar.tsx frontend/src/ui/index.ts frontend/tailwind.config.ts
git commit -m "feat(web): original profile avatars"
```

---

### Task 3: Profiles panel: list, create, edit, reorder, delete

**Files:**
- Create: `frontend/src/features/settings/ProfilesPanel.tsx`, `frontend/src/features/settings/ProfileEditor.tsx`, `frontend/src/features/settings/profileCopy.ts`, `frontend/src/features/settings/profileCopy.test.ts`
- Modify: `frontend/src/features/settings/SettingsPage.tsx` (a new section above "List Providers & Authentication")

**Interfaces:**
- Consumes: the `api.*` profile methods and the `lib/profiles.ts` helpers (Task 1), and `Avatar` (Task 2). It also uses `ConfirmDialog`, `Button`, `Card` and `EmptyState`/`ErrorState` from `ui/`, and `useAsyncData` from `lib/`.
- Produces in `profileCopy.ts` (pure, tested):
  - `export function deleteConsequences(profile: Profile): string[]` returns exactly:
    - `` `${name}'s list accounts are disconnected from this server` ``
    - `` `${name}'s reading positions, bookmarks and history are deleted` ``
    - `` `Series only ${name} follows are removed from the server; series someone else follows stay` ``
  - `export function connectedNotice(params: URLSearchParams, profiles: Profile[]): string | null`:
    - `'AniList connected for Ana'` when `connected=anilist&profile=<Ana's id>`;
    - `'AniList connected'` when the profile is unknown or is the manager;
    - `null` without `connected`.
    - Provider labels come from a map: `mal: 'MyAnimeList'`, `anilist: 'AniList'`, `mangabaka: 'MangaBaka'`.
  - `export function pinCaption(profile: Profile): string` returns `'PIN set'` or `'No PIN'`.
- Screen behaviour:
  - **Section header.** Icon `lock`, title "Profiles", subtitle "Who reads on this server. A PIN keeps someone from opening the wrong profile by accident; it is not a password."
  - **Rows.** Rows come from `api.profiles()` in `position` order. Each row shows the avatar (md), the name, `pinCaption`, a "Manages this server" tag on the manager, and up/down buttons calling `reorder` and then `updateProfile` for each returned patch. The up button is disabled on the first row and the down button on the last.
  - **Edit and Delete.** Edit opens `ProfileEditor`. Delete opens `ConfirmDialog` with `deleteConsequences`, title `` `Delete ${name}?` `` and `confirmLabel="Delete profile"`. The manager row renders no Delete button.
  - **Editor.** `ProfileEditor` is shared by "Add profile" and Edit. It has:
    - a name field;
    - an avatar grid of all 12 as radio buttons;
    - a PIN field, `inputMode="numeric"`, `maxLength=6`, labelled "PIN (4 to 6 digits, optional)";
    - when editing a profile that has a PIN, a "Remove PIN" checkbox.

    Save is disabled until `validName` and (an empty PIN or `validPin`) hold. On create it calls `createProfile`; on edit it calls `updateProfile` with `profilePatch`, skipping the call when that returns `null`.
  - **After a mutation.** Reload the list. Show the shared notice bar after delete: `` `Deleted ${name}. ${series_removed} series no one else follows were removed.` ``

- [ ] **Step 1: Write the failing tests in `profileCopy.test.ts`** for the three exact `deleteConsequences` lines, the three `connectedNotice` cases above plus `profile=999`, and `pinCaption`.
- [ ] **Step 2: Run `npm test`.** Expected: FAIL (module missing).
- [ ] **Step 3: Implement `profileCopy.ts`, `ProfileEditor.tsx` and `ProfilesPanel.tsx`, and mount the section.** `SettingsPage` passes `connectedNotice(new URLSearchParams(location.search), profiles)` to the existing notice on load.
- [ ] **Step 4: Run `npm test` and `npm run build`,** then grep `dist/assets/*.css` for every class used for the first time in these files. Expected: each one present.
- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/settings/ProfilesPanel.tsx frontend/src/features/settings/ProfileEditor.tsx frontend/src/features/settings/profileCopy.ts frontend/src/features/settings/profileCopy.test.ts frontend/src/features/settings/SettingsPage.tsx
git commit -m "feat(web): manage profiles in settings"
```

---

### Task 4: Each profile's list accounts

**Files:**
- Create: `frontend/src/features/settings/ProfileAccounts.tsx`
- Modify: `frontend/src/features/settings/ProfilesPanel.tsx` (an "Accounts" disclosure per non-manager row)

**Interfaces:**
- Consumes: `api.profileConnections`, `api.authStart(provider, profileId)`, `api.disconnect(provider, profileId)`, `api.sync(provider, profileId)`, `api.storeProfileCredential` (Task 1).
- Produces: `export function ProfileAccounts({ profile }: { profile: Profile })`.
- Behaviour:
  - **Where it shows.** Only on non-manager rows. The manager's accounts stay in the existing "List Providers & Authentication" section, and its row says so in one line: "Your accounts are under List Providers below."
  - **OAuth providers.** For each connection with `uses_oauth`:
    - if connected, show the account name and a Disconnect button;
    - otherwise show a Connect button, which sets `window.location.href` from `authStart(provider, profile.id)`.

    The button copy, from `signInLabel`, says whose account is being signed in.
  - **Key providers.** For each connection without `uses_oauth` (MangaBaka), show a password-type input and Save, calling `storeProfileCredential`. It shows "Key saved" when connected. The key is never echoed back, because the API never returns it.
  - **Sync.** A "Sync now" button per connected provider calls `api.sync(provider, profile.id)`.
  - **Copy, tested.** In `profileCopy.ts` (Task 3's file), add `export function signInLabel(name: string, provider: string): string`. It returns `'Sign in as Ana on AniList'` for `('Ana', 'anilist')`, using the same provider-label map as `connectedNotice`.

- [ ] **Step 1: Add the failing test for `signInLabel`** to `profileCopy.test.ts`.
- [ ] **Step 2: Run `npm test`.** Expected: FAIL.
- [ ] **Step 3: Implement `signInLabel` and build `ProfileAccounts`.**
- [ ] **Step 4: Run `npm test` and `npm run build`,** and grep dist for the new classes.
- [ ] **Step 5: Manual check against a live backend.**
  - Run the branch API: `POSTGRES_HOST=localhost POSTGRES_PORT=5434 .venv/bin/uvicorn app.api.main:app --port 8000` from `backend/`, with a database migrated to head.
  - In `frontend/`, run `npm run dev` and open `/settings`.
  - Create a profile, edit its name and avatar, set and then remove its PIN, reorder it, open its Accounts and save a MangaBaka key ("Key saved" appears), then delete it.
  - Confirm the manager row has no Delete button.
- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/settings/ProfileAccounts.tsx frontend/src/features/settings/ProfilesPanel.tsx frontend/src/features/settings/profileCopy.ts frontend/src/features/settings/profileCopy.test.ts
git commit -m "feat(web): connect each profile's list accounts"
```

---

### Task 5: The console sees every series

**Files:**
- Create: `frontend/src/features/library/removalNotice.ts`, `frontend/src/features/library/removalNotice.test.ts`
- Modify: `frontend/src/features/library/LibraryPage.tsx` (the removal notice), `frontend/src/features/library/useLibrary.ts` and `frontend/src/app/CommandPalette.tsx` (`api.series()` now defaults to `scope=all`, so nothing changes at the call sites; confirm that), and the series card in `features/library/` (holder chip)

**Interfaces:**
- Consumes: `Series.held_by`, the `removeSeries` result type and `api.profiles` (Task 1), and `Avatar` (Task 2).
- Produces: `export function removalNotice(result: { removed: number; deleted: number; skipped: number[] }): string`. The tested strings:
  - `{removed: 2, deleted: 1, skipped: []}` gives `'Removed 2 series from your library. A list sync will not bring them back.'`
  - `{removed: 1, deleted: 0, skipped: []}` gives `'Removed 1 series from your library. Someone else still follows it, so it stays on the server for them.'`
  - `{removed: 0, deleted: 0, skipped: [5]}` gives `'Nothing removed: 1 series is only on someone else\'s lists. Remove it from their profile instead.'`
  - Mixed results join both sentences: the removed sentence first, then `'1 more is only on someone else\'s lists and was left alone.'`
- **Holder chip.** A series whose `held_by` is non-empty and does not include the manager's id shows a small chip with the holders' avatars (sm) and names, so the owner can tell a series that is not theirs. The library fetches `api.profiles()` once through `useAsyncData`. If that request fails, it renders no chips rather than an error.

- [ ] **Step 1: Write the failing tests** for the four `removalNotice` cases.
- [ ] **Step 2: Run `npm test`.** Expected: FAIL.
- [ ] **Step 3: Implement `removalNotice`, use it in `LibraryPage.removeSelected`, and add the chip.**
- [ ] **Step 4: Run `npm test` and `npm run build`,** grep dist for the new classes, and repeat the manual check from Task 4.
  - With two profiles, give the kid a list entry the owner does not have (insert one in the database or sync a real account). The library should show that series with the kid's chip.
  - Removing it should show the "only on someone else's lists" notice and leave the series in place.
- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/library frontend/src/app/CommandPalette.tsx
git commit -m "feat(web): show every series in the console and explain removals"
```

---

### Task 6: Docs and the rebuilt image

**Files:**
- Modify: `docs/features.md` (a short Profiles note under "### Settings" and one line under "### Library" about holder chips), `docs/configuration.md` (Profiles: replace the API-only instructions for creating a profile and connecting its accounts with the Settings steps, keeping the API lines for scripts; fix the `?scope=all` sentence so it is true now)

- [ ] **Step 1: Write the docs.** Every sentence must match what Tasks 1 to 5 built.
- [ ] **Step 2: Rebuild and check the served bundle, not the build log.**
  - From the repo root: `docker compose build web && docker compose up -d --force-recreate web`.
  - Then `docker compose exec web sh -c 'ls /srv/avatars | wc -l'` should give `12` (`frontend/Dockerfile` copies `dist` to `/srv`).
  - `docker compose ps` should show `web` up.
- [ ] **Step 3: Commit**

```bash
git add docs/features.md docs/configuration.md
git commit -m "docs(web): profiles in settings and the console library"
```
