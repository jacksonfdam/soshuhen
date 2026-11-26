import { useId, useState } from 'react'

import type { Profile } from '../../lib/api'
import { AVATAR_KEYS, profilePatch, validName, validPin, type ProfileDraft } from '../../lib/profiles'
import { Avatar, Button } from '../../ui'

const INPUT =
  'w-full rounded-lg bg-surface-container-lowest px-space-md py-space-sm text-body-md text-on-surface shadow-inner focus:outline-hidden focus:ring-2 focus:ring-primary'

/** Adds a profile, or edits one when `profile` is given. */
export function ProfileEditor({
  profile,
  busy,
  onCreate,
  onUpdate,
  onCancel,
}: {
  profile?: Profile
  busy: boolean
  onCreate: (body: { name: string; avatar: string; pin?: string }) => void
  onUpdate: (patch: NonNullable<ReturnType<typeof profilePatch>>) => void
  onCancel: () => void
}) {
  const ids = useId()
  const [draft, setDraft] = useState<ProfileDraft>({
    name: profile?.name ?? '',
    avatar: profile?.avatar ?? AVATAR_KEYS[0],
    pin: '',
    clearPin: false,
  })
  const pinOk = draft.pin === '' || validPin(draft.pin)
  const canSave = validName(draft.name) && pinOk && !busy

  const save = () => {
    if (!canSave) return
    if (!profile) {
      onCreate({ name: draft.name.trim(), avatar: draft.avatar, ...(draft.pin ? { pin: draft.pin } : {}) })
      return
    }
    const patch = profilePatch(profile, draft)
    // Nothing changed is a finished edit, not a request worth sending.
    if (patch) onUpdate(patch)
    else onCancel()
  }

  return (
    <form
      className="flex flex-col gap-space-md rounded-lg bg-surface-container-low p-space-md"
      onSubmit={(event) => {
        event.preventDefault()
        save()
      }}
    >
      <label className="flex flex-col gap-space-xs" htmlFor={`${ids}-name`}>
        <span className="text-label-md text-on-surface">Name</span>
        <input
          id={`${ids}-name`}
          className={INPUT}
          value={draft.name}
          maxLength={40}
          autoFocus
          onChange={(event) => setDraft({ ...draft, name: event.target.value })}
        />
      </label>

      <fieldset className="flex flex-col gap-space-xs">
        <legend className="mb-space-xs text-label-md text-on-surface">Avatar</legend>
        <div className="grid grid-cols-6 gap-space-sm">
          {AVATAR_KEYS.map((key) => (
            <label
              key={key}
              className={`w-fit cursor-pointer justify-self-center rounded-full p-0.5 ${draft.avatar === key ? 'ring-2 ring-primary' : 'ring-1 ring-transparent hover:ring-outline'}`}
            >
              <input
                type="radio"
                name={`${ids}-avatar`}
                value={key}
                checked={draft.avatar === key}
                onChange={() => setDraft({ ...draft, avatar: key })}
                className="sr-only"
              />
              <Avatar avatar={key} name={key} size="md" />
            </label>
          ))}
        </div>
      </fieldset>

      <label className="flex flex-col gap-space-xs" htmlFor={`${ids}-pin`}>
        <span className="text-label-md text-on-surface">PIN (4 to 6 digits, optional)</span>
        <span className="text-body-sm text-on-surface-variant">
          {profile?.has_pin
            ? 'Leave empty to keep the current PIN. It keeps someone from opening this profile by accident; it is not a password.'
            : 'It keeps someone from opening this profile by accident; it is not a password.'}
        </span>
        <input
          id={`${ids}-pin`}
          className={`${INPUT} font-mono`}
          type="password"
          inputMode="numeric"
          autoComplete="off"
          maxLength={6}
          value={draft.pin}
          disabled={draft.clearPin}
          onChange={(event) => setDraft({ ...draft, pin: event.target.value.replace(/\D/g, '') })}
        />
        {!pinOk && <span className="text-body-sm text-error">A PIN is 4 to 6 digits.</span>}
      </label>

      {profile?.has_pin && (
        <label className="flex items-center gap-space-sm text-body-sm text-on-surface">
          <input
            type="checkbox"
            checked={draft.clearPin}
            onChange={(event) => setDraft({ ...draft, clearPin: event.target.checked, pin: '' })}
          />
          Remove PIN
        </label>
      )}

      <div className="flex justify-end gap-space-sm">
        <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={!canSave}>
          {profile ? 'Save' : 'Add profile'}
        </Button>
      </div>
    </form>
  )
}
