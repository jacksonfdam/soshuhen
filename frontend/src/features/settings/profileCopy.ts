import type { Profile } from '../../lib/api.ts'

const PROVIDER_LABEL: Record<string, string> = {
  mal: 'MyAnimeList',
  anilist: 'AniList',
  mangabaka: 'MangaBaka',
}

export function providerLabel(provider: string): string {
  return PROVIDER_LABEL[provider] ?? provider
}

/** What deleting a profile does, one effect per line, for the confirm dialog. */
export function deleteConsequences(profile: Profile): string[] {
  const name = profile.name
  return [
    `${name}'s list accounts are disconnected from this server`,
    `${name}'s reading positions, bookmarks and history are deleted`,
    `Series only ${name} follows are removed from the server; series someone else follows stay`,
  ]
}

/** The notice after an OAuth round trip lands back on /settings.

    The callback says which profile the sign-in was for. Naming the manager
    adds nothing, and a profile deleted meanwhile is simply not named. */
export function connectedNotice(params: URLSearchParams, profiles: Profile[]): string | null {
  const provider = params.get('connected')
  if (!provider) return null
  const label = `${providerLabel(provider)} connected`
  const id = Number(params.get('profile'))
  const profile = profiles.find((candidate) => candidate.id === id)
  return profile && !profile.is_manager ? `${label} for ${profile.name}` : label
}

export function pinCaption(profile: Profile): string {
  return profile.has_pin ? 'PIN set' : 'No PIN'
}

/** The connect button for someone else's account. The sign-in happens in this
    browser, so it says plainly whose account the provider should be shown. */
export function signInLabel(name: string, provider: string): string {
  return `Sign in as ${name} on ${providerLabel(provider)}`
}
