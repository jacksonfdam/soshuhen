import { useCallback, useState, type ReactNode } from 'react'

import { api, messageOf, type Profile, type ProfilePatch } from '../../lib/api'
import { reorder } from '../../lib/profiles'
import { useAsyncData } from '../../lib/useAsyncData'
import { Avatar, Badge, Button, ConfirmDialog, ErrorState, IconButton, NoticeBar, Skeleton } from '../../ui'
import { ProfileEditor } from './ProfileEditor'
import { connectedNotice, deleteConsequences, pinCaption } from './profileCopy'

type Editing = { mode: 'closed' } | { mode: 'new' } | { mode: 'edit'; profile: Profile }

/** Who reads on this server: add, edit, order and delete profiles. */
export function ProfilesPanel({
  renderAccounts,
}: {
  /** Each non-manager row's list accounts, mounted by the settings page. */
  renderAccounts?: (profile: Profile) => ReactNode
}) {
  const load = useCallback(() => api.profiles(), [])
  const { data, error, reload } = useAsyncData(load)
  const [editing, setEditing] = useState<Editing>({ mode: 'closed' })
  const [deleting, setDeleting] = useState<Profile | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'info' | 'error'; text: string } | null>(null)

  const run = async (action: () => Promise<string | void>) => {
    setBusy(true)
    try {
      const done = await action()
      setNotice(done ? { tone: 'info', text: done } : null)
      reload()
      return true
    } catch (failure) {
      setNotice({ tone: 'error', text: messageOf(failure) })
      return false
    } finally {
      setBusy(false)
    }
  }

  if (!data && error) {
    return <ErrorState title="Couldn't load the profiles" detail={error} onRetry={reload} />
  }
  if (!data) return <Skeleton className="h-32 w-full" />

  const profiles = [...data].sort((a, b) => a.position - b.position || a.id - b.id)
  // Back from a sign-in started for someone: say whose account it was, until
  // something newer replaces the notice.
  const connected = connectedNotice(new URLSearchParams(window.location.search), profiles)

  const move = (profile: Profile, direction: -1 | 1) =>
    run(async () => {
      for (const change of reorder(profiles, profile.id, direction)) {
        await api.updateProfile(change.id, { position: change.position })
      }
    })

  const create = (body: { name: string; avatar: string; pin?: string }) =>
    run(async () => {
      await api.createProfile(body)
      return `Added ${body.name}.`
    }).then((ok) => ok && setEditing({ mode: 'closed' }))

  const update = (profile: Profile, patch: ProfilePatch) =>
    run(async () => {
      await api.updateProfile(profile.id, patch)
    }).then((ok) => ok && setEditing({ mode: 'closed' }))

  const remove = (profile: Profile) =>
    run(async () => {
      const result = await api.deleteProfile(profile.id)
      return `Deleted ${profile.name}. ${result.series_removed} series no one else follows were removed.`
    }).then(() => setDeleting(null))

  return (
    <div className="flex flex-col gap-space-md">
      {notice ? (
        <NoticeBar tone={notice.tone} text={notice.text} />
      ) : (
        connected && <NoticeBar text={connected} />
      )}
      {error && <NoticeBar tone="error" text={`Couldn't refresh the profiles: ${error}`} onRetry={reload} />}

      <ul className="flex flex-col gap-space-sm">
        {profiles.map((profile, index) => (
          <li key={profile.id} className="flex flex-col gap-space-sm rounded-lg bg-surface-container-low p-space-md">
            <div className="flex flex-wrap items-center gap-space-md">
              <Avatar avatar={profile.avatar} name={profile.name} size="md" />
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-title-md text-on-surface">{profile.name}</span>
                <span className="text-body-sm text-on-surface-variant">{pinCaption(profile)}</span>
              </div>
              {profile.is_manager && <Badge tone="primary">Manages this server</Badge>}
              <div className="flex items-center gap-space-xs">
                <IconButton
                  icon="chevron"
                  label={`Move ${profile.name} up`}
                  className="rotate-180"
                  disabled={busy || index === 0}
                  onClick={() => move(profile, -1)}
                />
                <IconButton
                  icon="chevron"
                  label={`Move ${profile.name} down`}
                  disabled={busy || index === profiles.length - 1}
                  onClick={() => move(profile, 1)}
                />
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => setEditing({ mode: 'edit', profile })}>
                  Edit
                </Button>
                {/* The manager cannot be deleted, so there is nothing to offer. */}
                {!profile.is_manager && (
                  <Button size="sm" variant="danger" disabled={busy} onClick={() => setDeleting(profile)}>
                    Delete
                  </Button>
                )}
              </div>
            </div>
            {editing.mode === 'edit' && editing.profile.id === profile.id && (
              <ProfileEditor
                profile={profile}
                busy={busy}
                onCreate={create}
                onUpdate={(patch) => update(profile, patch)}
                onCancel={() => setEditing({ mode: 'closed' })}
              />
            )}
            {profile.is_manager ? (
              <p className="text-body-sm text-on-surface-variant">
                Your accounts are under List Providers below.
              </p>
            ) : (
              renderAccounts?.(profile)
            )}
          </li>
        ))}
      </ul>

      {editing.mode === 'new' ? (
        <ProfileEditor
          busy={busy}
          onCreate={create}
          onUpdate={() => undefined}
          onCancel={() => setEditing({ mode: 'closed' })}
        />
      ) : (
        <div>
          <Button icon="add" disabled={busy} onClick={() => setEditing({ mode: 'new' })}>
            Add profile
          </Button>
        </div>
      )}

      {deleting && (
        <ConfirmDialog
          title={`Delete ${deleting.name}?`}
          consequences={deleteConsequences(deleting)}
          confirmLabel="Delete profile"
          busy={busy}
          onConfirm={() => remove(deleting)}
          onCancel={() => setDeleting(null)}
        />
      )}
    </div>
  )
}
