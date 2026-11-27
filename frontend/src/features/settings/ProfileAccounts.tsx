import { useCallback, useState } from 'react'

import { api, messageOf, type Profile, type ProfileConnection } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { Button, NoticeBar, Skeleton } from '../../ui'
import { providerLabel, signInLabel } from './profileCopy'

/** One profile's list accounts: sign in, disconnect, a key, a sync. */
export function ProfileAccounts({ profile }: { profile: Profile }) {
  const load = useCallback(() => api.profileConnections(profile.id), [profile.id])
  const { data, error, reload } = useAsyncData(load)
  const [open, setOpen] = useState(false)
  const [keys, setKeys] = useState<Record<string, string>>({})
  const [notice, setNotice] = useState<{ tone: 'info' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const run = async (action: () => Promise<string>) => {
    setBusy(true)
    try {
      setNotice({ tone: 'info', text: await action() })
      reload()
    } catch (failure) {
      setNotice({ tone: 'error', text: messageOf(failure) })
    } finally {
      setBusy(false)
    }
  }

  const connect = (provider: string) =>
    run(async () => {
      const { url } = await api.authStart(provider, profile.id)
      window.location.href = url
      return `Opening ${providerLabel(provider)}…`
    })

  const row = (connection: ProfileConnection) => {
    const label = providerLabel(connection.provider)
    return (
      <li key={connection.provider} className="flex flex-wrap items-center gap-space-sm">
        <span className="w-32 text-label-md text-on-surface">{label}</span>
        {connection.uses_oauth ? (
          connection.connected ? (
            <>
              <span className="text-body-sm text-on-surface-variant">
                {connection.account_name ?? 'Connected'}
              </span>
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    await api.disconnect(connection.provider, profile.id)
                    return `${label} disconnected for ${profile.name}.`
                  })
                }
              >
                Disconnect
              </Button>
            </>
          ) : (
            <Button size="sm" disabled={busy} onClick={() => connect(connection.provider)}>
              {signInLabel(profile.name, connection.provider)}
            </Button>
          )
        ) : (
          <form
            className="flex flex-wrap items-center gap-space-sm"
            onSubmit={(event) => {
              event.preventDefault()
              const key = keys[connection.provider]?.trim()
              if (!key) return
              run(async () => {
                await api.storeProfileCredential(profile.id, connection.provider, key)
                setKeys({ ...keys, [connection.provider]: '' })
                return `${label} key saved for ${profile.name}.`
              })
            }}
          >
            {/* The key is never shown back: the API does not return it. */}
            <input
              type="password"
              autoComplete="off"
              aria-label={`${label} key for ${profile.name}`}
              placeholder={connection.connected ? 'Key saved' : 'API key'}
              value={keys[connection.provider] ?? ''}
              onChange={(event) => setKeys({ ...keys, [connection.provider]: event.target.value })}
              className="rounded-lg bg-surface-container-lowest px-space-md py-space-xs font-mono text-label-md text-on-surface shadow-inner focus:outline-hidden focus:ring-2 focus:ring-primary"
            />
            <Button size="sm" type="submit" disabled={busy || !keys[connection.provider]?.trim()}>
              Save
            </Button>
          </form>
        )}
        {connection.connected && (
          <Button
            size="sm"
            variant="ghost"
            icon="sync"
            disabled={busy}
            onClick={() =>
              run(async () => {
                await api.sync(connection.provider, profile.id)
                return `${label} sync queued for ${profile.name}.`
              })
            }
          >
            Sync now
          </Button>
        )}
      </li>
    )
  }

  return (
    <div className="flex flex-col gap-space-sm">
      <div>
        <Button size="sm" variant="ghost" icon="link" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? 'Hide accounts' : 'Accounts'}
        </Button>
      </div>
      {open && (
        <div className="flex flex-col gap-space-sm rounded-lg bg-surface-container p-space-md">
          {notice && <NoticeBar tone={notice.tone} text={notice.text} />}
          {error && <NoticeBar tone="error" text={`Couldn't load accounts: ${error}`} onRetry={reload} />}
          {data ? <ul className="flex flex-col gap-space-sm">{data.map(row)}</ul> : !error && <Skeleton className="h-16 w-full" />}
        </div>
      )}
    </div>
  )
}
