import { useCallback, useState } from 'react'

import { api, messageOf } from '../../lib/api'
import { useAsyncData } from '../../lib/useAsyncData'
import { Button } from '../../ui'
import { SourceCard } from './SourceCard'

const LEVEL_LABEL: Record<string, string> = {
  PREMIUM_MEMBER: 'Premium',
  MEMBER: 'Member',
  USER: 'Free account',
}

function formatExpiry(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

// The password typed here goes to one request and nowhere else: the server
// keeps only the token it buys. When that lapses, this card asks again.
export function JNovelClubCard() {
  const load = useCallback(() => api.jncSession(), [])
  const { data: session, error, reload } = useAsyncData(load)
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  const signIn = async () => {
    setBusy(true)
    setFailure(null)
    try {
      await api.jncSignIn(login, password)
      setPassword('')
      reload()
    } catch (caught) {
      setFailure(messageOf(caught))
    } finally {
      setBusy(false)
    }
  }

  const syncLibrary = async () => {
    setBusy(true)
    setFailure(null)
    try {
      await api.jncLibrarySync()
    } catch (caught) {
      setFailure(messageOf(caught))
    } finally {
      setBusy(false)
    }
  }

  const signOut = async () => {
    setBusy(true)
    try {
      await api.jncSignOut()
      reload()
    } catch (caught) {
      setFailure(messageOf(caught))
    } finally {
      setBusy(false)
    }
  }

  const signedIn = session && session.via !== 'none'
  const level = session?.level ? (LEVEL_LABEL[session.level] ?? session.level) : null
  const statusLabel = !session
    ? error ?? 'Checking…'
    : session.via === 'env'
      ? 'Signed in from .env'
      : session.via === 'settings'
        ? [level, session.expires_at && `expires ${formatExpiry(session.expires_at)}`]
            .filter(Boolean)
            .join(' · ')
        : 'Not signed in'

  return (
    <SourceCard
      icon="book"
      title="J-Novel Club"
      subtitle="Premium parts of licensed light novels"
      tone={signedIn ? 'ok' : 'neutral'}
      statusLabel={statusLabel}
    >
      {session && session.via !== 'none' && (
        <div className="flex flex-wrap gap-space-xs">
          <Button variant="surface" onClick={syncLibrary} disabled={busy}>
            Sync library now
          </Button>
          {session.via === 'settings' && (
            <Button variant="surface" onClick={signOut} disabled={busy}>
              Sign out
            </Button>
          )}
        </div>
      )}
      {session?.via === 'none' && (
        <form
          className="flex flex-col gap-space-xs"
          onSubmit={(event) => {
            event.preventDefault()
            void signIn()
          }}
        >
          <input
            type="email"
            autoComplete="username"
            placeholder="email"
            value={login}
            onChange={(event) => setLogin(event.target.value)}
            className="w-full rounded-lg bg-surface-container-lowest px-space-md py-space-sm font-mono text-label-md text-tertiary shadow-inner focus:outline-hidden focus:ring-2 focus:ring-primary"
          />
          <input
            type="password"
            autoComplete="current-password"
            placeholder="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="w-full rounded-lg bg-surface-container-lowest px-space-md py-space-sm font-mono text-label-md text-tertiary shadow-inner focus:outline-hidden focus:ring-2 focus:ring-primary"
          />
          <Button type="submit" disabled={busy || !login || !password}>
            Sign in
          </Button>
          <p className="text-body-sm text-on-surface-variant">
            Only the sign-in token is kept, for up to 14 days; the password is never stored. Or set
            <code className="mx-1 font-mono text-primary">JNC_LOGIN</code>
            and
            <code className="mx-1 font-mono text-primary">JNC_PASSWORD</code>
            in .env to stay signed in.
          </p>
        </form>
      )}
      {failure && <p className="font-mono text-label-sm text-error">{failure}</p>}
    </SourceCard>
  )
}
