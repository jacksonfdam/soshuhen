# Android Client, Part 2: App Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An installable Android app that finds the Soshuhen server on the home network (or takes a
typed address), then shows the library and series detail online, in the web library's layout,
responsive across phone and tablet, with its own icon and splash.

**Architecture:** A Gradle project in `mobile/` with two modules. `shared` is a Kotlin
Multiplatform library holding every screen, view model, API call and rule in `commonMain`, with
Android implementations of platform services in `androidMain` and a `jvm()` target that exists so
`commonTest` runs as fast host tests. `androidApp` is the Android application: activity, manifest,
icon, splash and network security config. Nothing offline yet. Part 3 adds the mark/unmark toggle,
the "On device" tab, the Updates tab, the folder picker and battery step in first run, the offline
library snapshot, imports, the reader, the progress queue, notifications and release signing.

**Tech Stack:** Kotlin 2.4.21, Compose Multiplatform 1.12.2, CMP Material 3 1.12.0-alpha03 with
`material3-adaptive-navigation-suite` 1.12.0-alpha03 and `material3.adaptive` 1.3.0, navigation-compose
2.10.0-rc01, lifecycle-viewmodel-compose 2.11.0, Ktor client 3.6.0, kotlinx-serialization 1.12.0,
kotlinx-coroutines 1.11.0, DataStore 1.2.1, Koin 4.2.2, Coil 3.6.3, `core-splashscreen` 1.2.0, AGP
9.4.1, Gradle 9.7.0.

**Spec:** `docs/superpowers/specs/2026-10-20-android-client-design.md`. Part 1
(`docs/superpowers/plans/2026-10-21-android-client-server.md`) is done: `/api/identity`,
`/api/chapters/{id}/archive`, `/api/series/{id}/cover` and `read_at` exist on this branch.

## Global Constraints

- minSdk 29, targetSdk 37, compileSdk 37 (the local SDK has `platforms/android-37.0`). applicationId and namespace `app.soshuhen`, shared namespace `app.soshuhen.shared`. **(Builder's call.)**
- Versions are the spec appendix's, pinned in `mobile/gradle/libs.versions.toml`. No other source of a version number.
- Gradle runs on JDK 21: `export JAVA_HOME=$(/usr/libexec/java_home -v 21)` before any `./gradlew` here (the default JDK on this machine is 25). `mobile/local.properties` (gitignored) holds `sdk.dir=/Users/jackson.mafra/Library/Android/sdk`.
- Commands run from `mobile/`. Host tests: `./gradlew :shared:jvmTest`. Build: `./gradlew :androidApp:assembleDebug`. Both must pass before every commit.
- The app talks only to the Soshuhen server, over `http://<ip>:<port>`. No request goes anywhere else, covers included: covers load from `GET /api/series/{id}/cover`, never from `cover_url`.
- Cleartext HTTP is allowed app-wide through `network_security_config.xml` (`base-config cleartextTrafficPermitted="true"`). A `domain-config` cannot match IP ranges.
- `mobile/shared/src/commonMain/kotlin/app/soshuhen/ui/theme/Tokens.kt` is the only place a colour, size, radius or spacing value lives, copied from `frontend/tailwind.config.ts` with the same names. No colour or dp literal in any other file.
- Feature packages (`onboarding`, `library`, `detail`, `settings`) never import from each other. Shared code goes in `api`, `server`, `ui` or `core`.
- Only comic series appear. A series whose `kind == "prose"` is filtered out of every list the app shows. **(Builder's call: the spec keeps prose out of the app entirely for now.)**
- Comments explain why, never what. Commits: English, one focused change each, no assistant attribution.

## Review Focus

1. **First run off the home network** (mobile data, or a Wi-Fi with no Soshuhen on it): the scan ends within its time budget showing "No server found" and the address field, never an endless spinner. Test in Task 4.
2. **Typed addresses in every shape a person types them**: `192.168.1.20`, `192.168.1.20:8080`, `http://192.168.1.20:8080/`, ` 192.168.1.20 ` with spaces, `https://host:8443`, and garbage like `abc def` or `http://` rejected with a message rather than a crash. Test in Task 3.
3. **Something else on the LAN answers `/api/identity`** (a router admin page returning HTML, another app returning unrelated JSON, a 500): not listed as a server. Test in Task 3.
4. **Real payloads with nulls**: `cover_url`, `total_chapters`, `status`, `last_read_at`, `updated_at`, `kind` all null, and unknown extra fields. They parse, and the screen shows the series. Test in Task 2.
5. **The server stops answering after the library loaded** (laptop asleep, phone left the Wi-Fi): a refresh failure keeps the loaded grid and shows a banner; it does not blank the screen. Test in Task 5.

---

### Task 1: Project skeleton, theme, icon and splash, CI

**Files:**
- Create: `mobile/settings.gradle.kts`, `mobile/build.gradle.kts`, `mobile/gradle.properties`, `mobile/gradle/libs.versions.toml`, `mobile/gradlew`, `mobile/gradlew.bat`, `mobile/gradle/wrapper/gradle-wrapper.jar`, `mobile/gradle/wrapper/gradle-wrapper.properties`, `mobile/.gitignore`
- Create: `mobile/shared/build.gradle.kts`, `mobile/shared/src/commonMain/kotlin/app/soshuhen/App.kt`, `.../ui/theme/Tokens.kt`, `.../ui/theme/Theme.kt`
- Create: `mobile/androidApp/build.gradle.kts`, `mobile/androidApp/src/main/AndroidManifest.xml`, `.../kotlin/app/soshuhen/MainActivity.kt`, `.../res/xml/network_security_config.xml`, `.../res/values/themes.xml`, `.../res/drawable/ic_launcher_foreground.xml`, `.../res/drawable/ic_launcher_monochrome.xml`, `.../res/mipmap-anydpi/ic_launcher.xml`, `.../res/values/ic_launcher_background.xml`
- Create: `mobile/art/icon.svg` (the source of the icon), `mobile/README.md`
- Modify: `.github/workflows/ci.yml` (a `mobile` job)
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/ui/theme/TokensTest.kt`

**Interfaces:**
- Produces: `object Tokens` with the web's colour roles as `Color` values (`background`, `onBackground`, `surfaceContainerLow`, `surfaceContainer`, `surfaceContainerHigh`, `surfaceContainerHighest`, `onSurface`, `onSurfaceVariant`, `outline`, `outlineVariant`, `primary`, `onPrimary`, `primaryContainer`, `inversePrimary`, `secondary`, `onSecondary`, `tertiary`, `error`, `warning`, `readerBlack`, `readerGray`, `readerWhite`) plus `Tokens.space` (4, 8, 12, 16, 24 dp), `Tokens.radius` (6, 12, 999 dp) and the cover aspect `Tokens.coverAspect = 2f / 3f`. `@Composable fun SoshuhenTheme(content: @Composable () -> Unit)`: a dark Material 3 `ColorScheme` built from `Tokens` only. `@Composable fun App()`: the root, for now a themed empty `Scaffold`.

- [ ] **Step 1: Generate the wrapper** from the Gradle already in the local cache, so no download is needed:

Run: `~/.gradle/wrapper/dists/gradle-9.7.0-bin/*/gradle-9.7.0/bin/gradle wrapper --gradle-version 9.7.0 --distribution-type bin` inside `mobile/` (with an empty `settings.gradle.kts` present).
Expected: `mobile/gradlew` and `mobile/gradle/wrapper/*` exist.

- [ ] **Step 2: Write the failing test** `TokensTest`:

```kotlin
@Test fun tokensMatchTheWebPalette() {
    assertEquals(Color(0xFF10141A), Tokens.background)
    assertEquals(Color(0xFFD0BCFF), Tokens.primary)
    assertEquals(Color(0xFFA078FF), Tokens.primaryContainer)
    assertEquals(Color(0xFF4EDEA3), Tokens.secondary)
    assertEquals(Color(0xFF6D3BD7), Tokens.inversePrimary)
}
@Test fun themeUsesTheTokens() {
    val scheme = soshuhenColorScheme()
    assertEquals(Tokens.background, scheme.background)
    assertEquals(Tokens.primary, scheme.primary)
    assertEquals(Tokens.surfaceContainer, scheme.surfaceContainer)
}
```

`soshuhenColorScheme(): ColorScheme` is the non-composable builder `SoshuhenTheme` calls.

- [ ] **Step 3: Write the build files** and run the test to see it fail

Root `build.gradle.kts` declares the plugins with `apply false`. `shared` applies `org.jetbrains.kotlin.multiplatform`, `com.android.kotlin.multiplatform.library`, `org.jetbrains.compose`, `org.jetbrains.kotlin.plugin.compose`, `org.jetbrains.kotlin.plugin.serialization`; targets `android { namespace = "app.soshuhen.shared"; compileSdk = 37; minSdk = 29 }` and `jvm()`. `androidApp` applies `com.android.application` and `org.jetbrains.kotlin.plugin.compose` (AGP 9 compiles Kotlin itself) and depends on `project(":shared")`.

Run: `./gradlew :shared:jvmTest`
Expected: FAIL, `Tokens` unresolved.

If AGP 9.4.1 and Kotlin 2.4.21 do not configure together, drop AGP to 9.3.3 and ledger why (spec appendix).

- [ ] **Step 4: Implement `Tokens.kt`, `Theme.kt` and `App.kt`.** Values come from `frontend/tailwind.config.ts`; copy every role listed in Interfaces with its hex value.

- [ ] **Step 5: Run the tests**

Run: `./gradlew :shared:jvmTest`
Expected: PASS, 2 tests.

- [ ] **Step 6: Android shell.** `MainActivity` (a `ComponentActivity`) calls `installSplashScreen()` before `super.onCreate`, then `enableEdgeToEdge()` and `setContent { App() }`. The manifest sets `android:networkSecurityConfig="@xml/network_security_config"`, `android:icon`/`android:roundIcon` to `@mipmap/ic_launcher`, and the activity theme `Theme.Soshuhen.Splash` (parent `Theme.SplashScreen`, `windowSplashScreenBackground` `#10141A`, `windowSplashScreenAnimatedIcon` `@drawable/ic_launcher_foreground`, `postSplashScreenTheme` a no-action-bar theme). These four XML colour values are the one place outside `Tokens.kt` a colour may appear: Android reads them before any Kotlin runs. `INTERNET` and `ACCESS_NETWORK_STATE` permissions.

Icon, option C from the spec: three panels `#A078FF` (top left), `#D0BCFF` (top right), `#6D3BD7` (bottom) and a `#4EDEA3` downward arrow on `#10141A`, drawn inside the adaptive icon's 66 dp safe zone of a 108 dp canvas. `mobile/art/icon.svg` holds the same drawing as the source; the monochrome layer is the same shapes in one colour.

- [ ] **Step 7: Build**

Run: `./gradlew :androidApp:assembleDebug`
Expected: `BUILD SUCCESSFUL`, `androidApp/build/outputs/apk/debug/androidApp-debug.apk` exists.

- [ ] **Step 8: CI and README.** A `mobile` job in `ci.yml`: `ubuntu-latest`, `actions/setup-java@v4` with Temurin 21, `android-actions/setup-android@v3`, then from `mobile/` `./gradlew :shared:jvmTest :androidApp:assembleDebug`. No signing, no artefact upload. `mobile/README.md`: JDK 21, `local.properties`, the two commands, `./gradlew :androidApp:installDebug` to put it on a phone over USB, and the keystore note from the spec's "Building and installing" (release signing itself is part 3). `mobile/.gitignore`: `.gradle/`, `build/`, `local.properties`, `*.keystore`, `keystore.properties`, `.kotlin/`.

- [ ] **Step 9: Commit**

```bash
git add mobile .github/workflows/ci.yml
git commit -m "feat(mobile): start the Android client with its theme, icon and splash"
```

### Task 2: API models and client

**Files:**
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/api/Models.kt`, `.../api/SoshuhenApi.kt`, `.../api/HttpClientFactory.kt`
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/api/SoshuhenApiTest.kt` and `.../api/Fixtures.kt` (fixture JSON as Kotlin string constants, because test resources are not portable across KMP targets)

**Interfaces:**
- Consumes: the server's JSON as the web client types it (`frontend/src/lib/api.ts:5-70`, `:221-233`) and part 1's `/api/identity`.
- Produces:
  - `@Serializable data class Identity(val app: String, val name: String, val version: String, @SerialName("instance_id") val instanceId: String)`
  - `@Serializable data class Series(id: Long, title: String, slug: String, @SerialName("cover_url") coverUrl: String? = null, downloaded: Int = 0, known: Int = 0, @SerialName("total_chapters") totalChapters: Int? = null, kind: String? = null, status: String? = null, progress: Int = 0, @SerialName("last_read_at") lastReadAt: Instant? = null, @SerialName("updated_at") updatedAt: Instant? = null)`
  - `@Serializable data class SeriesChapter(id: Long, number: Double, title: String? = null, state: String, @SerialName("file_path") filePath: String? = null)`
  - `@Serializable data class SeriesDetail(series: Series, chapters: List<SeriesChapter>)`
  - `@Serializable data class Resume(@SerialName("chapter_id") chapterId: Long, page: Int)`
  - `class SoshuhenApi(baseUrl: String, client: HttpClient)` with `suspend fun identity(): Identity`, `suspend fun series(): List<Series>`, `suspend fun seriesDetail(id: Long): SeriesDetail`, `suspend fun resume(seriesId: Long): Resume?` (null on 404), `fun coverUrl(seriesId: Long): String` (`"$baseUrl/api/series/$seriesId/cover"`). Non-2xx throws `ApiException(status: Int)`.
  - `fun soshuhenHttpClient(engine: HttpClientEngine? = null): HttpClient`: Ktor with `ContentNegotiation` + `Json { ignoreUnknownKeys = true; coerceInputValues = true; explicitNulls = false }`, connect timeout 3 s, request timeout 15 s.
  - `Instant` is `kotlin.time.Instant` (stable in Kotlin 2.4); kotlinx-datetime is not needed for this.

- [ ] **Step 1: Write the failing tests** with Ktor `MockEngine`. `Fixtures.kt` holds one `GET /api/series` body with two rows: a full one copied from a real response's field set, and one with every nullable field `null`, `kind: "prose"` and an unknown field `"something_new": 1`. One `GET /api/series/1` body with three chapters.

```kotlin
@Test fun parsesTheLibraryIncludingNulls() = runTest {
    val rows = api(respond(Fixtures.SERIES)).series()
    assertEquals(2, rows.size)
    assertNull(rows[1].coverUrl); assertNull(rows[1].totalChapters); assertNull(rows[1].lastReadAt)
}
@Test fun parsesSeriesDetailChapters() = runTest {
    val detail = api(respond(Fixtures.DETAIL)).seriesDetail(1)
    assertEquals(listOf(1.0, 2.0, 2.5), detail.chapters.map { it.number })
}
@Test fun identityParses() = runTest { assertEquals("soshuhen", api(respond(Fixtures.IDENTITY)).identity().app) }
@Test fun resumeIsNullWhenTheServerHasNone() = runTest { assertNull(api(respond("", NotFound)).resume(1)) }
@Test fun aServerErrorIsAnApiException() = runTest {
    assertEquals(500, assertFailsWith<ApiException> { api(respond("", InternalServerError)).series() }.status)
}
@Test fun coverUrlPointsAtTheServerNotTheCdn() {
    assertEquals("http://10.0.0.5:8080/api/series/7/cover", SoshuhenApi("http://10.0.0.5:8080", client()).coverUrl(7))
}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./gradlew :shared:jvmTest --tests '*SoshuhenApiTest*'`
Expected: FAIL, unresolved references.

- [ ] **Step 3: Implement `Models.kt`, `HttpClientFactory.kt`, `SoshuhenApi.kt`** with the signatures above. The Android engine is OkHttp (`ktor-client-okhttp`) in `androidMain`, CIO in `jvmMain`.

- [ ] **Step 4: Run the tests**

Run: `./gradlew :shared:jvmTest`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/shared
git commit -m "feat(mobile): read the library and series detail from the server"
```

### Task 3: Server address parsing, LAN scan and server locator

**Files:**
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/server/ServerAddress.kt`, `.../server/Subnet.kt`, `.../server/ServerScanner.kt`, `.../server/ServerLocator.kt`
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/server/ServerAddressTest.kt`, `SubnetTest.kt`, `ServerScannerTest.kt`, `ServerLocatorTest.kt`

**Interfaces:**
- Consumes: `SoshuhenApi.identity()`, `soshuhenHttpClient`.
- Produces:
  - `data class ServerAddress(val scheme: String, val host: String, val port: Int) { val baseUrl: String }`. `fun parseServerAddress(input: String): ServerAddress?`: trims, accepts a bare host, `host:port`, or an `http://` / `https://` URL with an optional trailing slash and no path; default port 8080 for http, 443 for https; `null` for anything else.
  - `fun subnetHosts(address: String, prefixLength: Int): List<String>`: every usable IPv4 host in the subnet, excluding network, broadcast and `address` itself. A prefix shorter than 24 is narrowed to the `/24` containing `address`, so a `/16` home network is 253 probes, not 65 000. **(Builder's call.)**
  - `data class FoundServer(val address: ServerAddress, val identity: Identity)`
  - `class ServerScanner(private val probe: suspend (ServerAddress) -> Identity?)` with `fun scan(hosts: List<String>, port: Int = 8080, concurrency: Int = 32, perHostTimeout: Duration = 800.milliseconds): Flow<FoundServer>`. A probe that throws, times out, or returns an identity whose `app != "soshuhen"` yields nothing. The flow completes when every host has answered or timed out.
  - `fun identityProbe(client: HttpClient): suspend (ServerAddress) -> Identity?`: `SoshuhenApi(address.baseUrl, client).identity()`, null on any exception.
  - `class ServerLocator(private val probe: suspend (ServerAddress) -> Identity?, private val scanner: ServerScanner)` with `suspend fun locate(saved: SavedServer, hosts: List<String>?): ServerAddress?`. Tries `saved.address`; returns it when the identity's `instanceId == saved.instanceId`. Otherwise, when `hosts` is not null (the device is on Wi-Fi), scans and returns the first server with that `instanceId`. Otherwise null.
  - `data class SavedServer(val address: ServerAddress, val instanceId: String)`

- [ ] **Step 1: Write the failing tests**

```kotlin
// ServerAddressTest
@Test fun bareIp() = assertEquals(ServerAddress("http", "192.168.1.20", 8080), parseServerAddress("192.168.1.20"))
@Test fun ipWithPort() = assertEquals(8090, parseServerAddress("192.168.1.20:8090")!!.port)
@Test fun fullUrlWithTrailingSlash() = assertEquals("http://192.168.1.20:8080", parseServerAddress("http://192.168.1.20:8080/")!!.baseUrl)
@Test fun surroundingSpaces() = assertNotNull(parseServerAddress("  192.168.1.20  "))
@Test fun https() = assertEquals(ServerAddress("https", "host", 8443), parseServerAddress("https://host:8443"))
@Test fun garbage() { listOf("", "abc def", "http://", "192.168.1.20:99999", "ftp://x", "http://h/api").forEach { assertNull(parseServerAddress(it), it) } }

// SubnetTest
@Test fun slash24() { val hosts = subnetHosts("192.168.1.20", 24); assertEquals(253, hosts.size); assertFalse("192.168.1.20" in hosts); assertFalse("192.168.1.0" in hosts); assertFalse("192.168.1.255" in hosts) }
@Test fun widerPrefixIsNarrowedTo24() = assertEquals(253, subnetHosts("10.0.5.9", 16).size)
@Test fun slash30() = assertEquals(listOf("10.0.0.2"), subnetHosts("10.0.0.1", 30))

// ServerScannerTest — probe is a fake keyed by host
@Test fun findsOnlySoshuhen() = runTest {
    val found = scanner(mapOf("10.0.0.2" to identity("soshuhen"), "10.0.0.3" to identity("router"))).scan(listOf("10.0.0.2", "10.0.0.3", "10.0.0.4")).toList()
    assertEquals(listOf("10.0.0.2"), found.map { it.address.host })
}
@Test fun aThrowingOrSlowHostIsSkipped() = runTest { /* one host throws, one delays 5 s; flow completes with the good one under virtual time */ }
@Test fun nothingFoundCompletesEmpty() = runTest { assertTrue(scanner(emptyMap()).scan(subnetHosts("10.0.0.1", 24)).toList().isEmpty()) }

// ServerLocatorTest
@Test fun savedAddressStillAnswers() = runTest { /* probe answers saved with same instanceId -> saved address */ }
@Test fun movedServerIsFoundByInstanceId() = runTest { /* saved .20 dead; .31 answers same id -> .31 */ }
@Test fun aDifferentInstallationIsNotTakenForOurs() = runTest { /* .20 answers another id, scan finds only other ids -> null */ }
@Test fun offWifiNoScan() = runTest { /* saved dead, hosts = null -> null, scanner never called */ }
```

Plus a `MockEngine` test for `identityProbe`: an HTML body with 200 and a 500 both give `null`.

- [ ] **Step 2: Run them to verify they fail**

Run: `./gradlew :shared:jvmTest --tests 'app.soshuhen.server.*'`
Expected: FAIL, unresolved references.

- [ ] **Step 3: Implement the four files.** The scanner bounds concurrency with a `Semaphore(concurrency)` inside `channelFlow`, each probe wrapped in `withTimeoutOrNull(perHostTimeout)`.

- [ ] **Step 4: Run the tests**

Run: `./gradlew :shared:jvmTest`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/shared
git commit -m "feat(mobile): find the server on the LAN and again after it moves"
```

### Task 4: Saved server, Wi-Fi subnet, and the first-run screen

**Files:**
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/core/ServerStore.kt` (interface), `.../core/NetworkInfo.kt` (interface), `mobile/shared/src/androidMain/kotlin/app/soshuhen/core/DataStoreServerStore.kt`, `.../core/AndroidNetworkInfo.kt`
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/onboarding/OnboardingViewModel.kt`, `.../onboarding/OnboardingScreen.kt`
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/core/Session.kt`
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/onboarding/OnboardingViewModelTest.kt`, `.../core/SessionTest.kt`

**Interfaces:**
- Consumes: Task 3's `ServerScanner`, `ServerLocator`, `SavedServer`, `parseServerAddress`, `subnetHosts`, `identityProbe`.
- Produces:
  - `interface ServerStore { val saved: Flow<SavedServer?>; suspend fun save(server: SavedServer); suspend fun clear() }`. Android: DataStore Preferences, keys `server_scheme`, `server_host`, `server_port`, `instance_id`.
  - `interface NetworkInfo { fun wifiAddress(): Pair<String, Int>? }`: the device's IPv4 address and prefix length on Wi-Fi, null on mobile data or no network. Android: `ConnectivityManager.activeNetwork` → `NetworkCapabilities.hasTransport(TRANSPORT_WIFI)` → `LinkProperties.linkAddresses` first `Inet4Address`.
  - `sealed interface OnboardingState { Scanning(found: List<FoundServer>); Done(found: List<FoundServer>); Checking; Failed(message: String) }` and `class OnboardingViewModel(scanner, probe, network: NetworkInfo, store: ServerStore, scanBudget: Duration = 15.seconds) : ViewModel` with `val state: StateFlow<OnboardingState>`, `fun rescan()`, `fun choose(server: FoundServer)`, `fun submitAddress(input: String)`. The scan starts in `init`. No Wi-Fi: straight to `Done(emptyList())`. The whole scan is cut at `scanBudget`. `submitAddress` with an unparsable input: `Failed("Not an address. Try 192.168.1.20 or 192.168.1.20:8080.")`. A parsable one that is not Soshuhen: `Failed("No Soshuhen server answered at <baseUrl>.")`. Success and `choose` both save and end onboarding.
  - `class Session(store: ServerStore, locator: ServerLocator, network: NetworkInfo)` with `val api: StateFlow<SoshuhenApi?>` (null until a server is saved and located) and `suspend fun refreshLocation()`. This is what Tasks 5 and 6 read the API from.

- [ ] **Step 1: Write the failing tests** with fakes for `ServerStore`, `NetworkInfo` and the probe, `StandardTestDispatcher` and `Dispatchers.setMain`:

```kotlin
@Test fun offWifiSkipsTheScanAndOffersTheField() = runTest { assertEquals(OnboardingState.Done(emptyList()), vm(wifi = null).state.value.afterIdle()) }
@Test fun aScanThatFindsNothingEndsWithinTheBudget() = runTest { /* every probe hangs; after scanBudget of virtual time state is Done(empty) */ }
@Test fun foundServersAreListedAsTheyAnswer() = runTest { /* two hosts answer; Done(found.size == 2) */ }
@Test fun choosingSavesAddressAndInstanceId() = runTest { /* store.saved == SavedServer(addr, "id-1") */ }
@Test fun aTypedAddressThatIsNotSoshuhenFails() = runTest { assertEquals(OnboardingState.Failed("No Soshuhen server answered at http://10.0.0.9:8080."), ...) }
@Test fun garbageInputFailsWithTheExample() = runTest { /* "abc def" -> Failed("Not an address. Try 192.168.1.20 or 192.168.1.20:8080.") */ }

// SessionTest
@Test fun apiIsNullUntilAServerIsSaved() = runTest { ... }
@Test fun apiFollowsTheServerWhenItMoves() = runTest { /* saved .20 dead, scan finds same id at .31 -> api.baseUrl ends with .31:8080, store updated */ }
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./gradlew :shared:jvmTest --tests '*OnboardingViewModelTest*' --tests '*SessionTest*'`
Expected: FAIL, unresolved references.

- [ ] **Step 3: Implement the view model, `Session`, and the Android `ServerStore` and `NetworkInfo`.** `Session.refreshLocation` saves the new address when the locator found the server somewhere else.

- [ ] **Step 4: Implement `OnboardingScreen`**: title "Find your Soshuhen server", the live list of found servers (name, address, version) as tappable rows, a progress indicator while `Scanning`, "No server found on this network." when `Done` is empty, an address field with a "Connect" button, the `Failed` message under the field, and "Scan again". Wire it in `App()`: no saved server shows onboarding; a saved one shows the main shell (Task 5).

- [ ] **Step 5: Run the tests and the build**

Run: `./gradlew :shared:jvmTest :androidApp:assembleDebug`
Expected: PASS, `BUILD SUCCESSFUL`.

- [ ] **Step 6: Commit**

```bash
git add mobile/shared
git commit -m "feat(mobile): pick the server on first run, by scan or by address"
```

### Task 5: Library screen

**Files:**
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/ui/LoadState.kt`, `.../library/LibraryRules.kt`, `.../library/LibraryViewModel.kt`, `.../library/LibraryScreen.kt`, `.../ui/CoverImage.kt`
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/MainShell.kt` (navigation suite + nav graph), `.../di/Modules.kt` (Koin)
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/library/LibraryRulesTest.kt`, `.../library/LibraryViewModelTest.kt`

**Interfaces:**
- Consumes: `Session.api`, `SoshuhenApi.series()`, `SoshuhenApi.coverUrl`.
- Produces:
  - `sealed interface LoadState<out T> { Loading; Loaded(data: T, refreshFailed: String? = null); Failed(message: String) }`, the app's equivalent of the web's `lib/useAsyncData.ts`: a request not yet landed, a failed first load, and a failed refresh over loaded data are three different states.
  - In `LibraryRules.kt`, pure functions mirroring `frontend/src/features/library/useLibrary.ts`:
    - `fun totalChapters(s: Series): Int? = max(s.totalChapters ?: 0, s.known).takeIf { it > 0 }`
    - `fun unread(s: Series): Int = totalChapters(s)?.let { max(0, it - s.progress) } ?: 0`
    - `fun continueReading(all: List<Series>): List<Series>`: `status == "reading"` and (`lastReadAt` or `updatedAt` not null), sorted by recent reading (a series with `lastReadAt` before one without; then `lastReadAt` desc; then `updatedAt` desc), first 3.
    - `val STATUS_ORDER = listOf("reading", "plan_to_read", "completed", "on_hold", "dropped")` and `STATUS_LABEL` = Reading, Plan to read, Completed, On hold, Dropped.
    - `fun visible(all: List<Series>, status: String?, query: String): List<Series>`: comics only (`kind != "prose"`), status filter when not null ("All" is null), case-insensitive title contains.
  - `class LibraryViewModel(session: Session) : ViewModel` with `val state: StateFlow<LoadState<List<Series>>>`, `val status: StateFlow<String?>` (default `"reading"`), `val query: StateFlow<String>`, `fun refresh()`, `fun setStatus(s: String?)`, `fun setQuery(q: String)`.
  - `@Composable fun CoverImage(url: String, title: String, modifier: Modifier)`: Coil `AsyncImage` with a placeholder made of the title's initials on `Tokens.surfaceContainerHigh` when loading fails.
  - `MainShell`: `NavigationSuiteScaffold` with destinations Library and Settings (Updates arrives in part 3); it shows a bottom bar on compact width and a rail on medium and expanded, which is the spec's rule. Navigation routes `library`, `series/{id}`, `settings`.

- [ ] **Step 1: Write the failing tests**

```kotlin
// LibraryRulesTest
@Test fun totalUsesTheHigherOfTotalAndKnown() = assertEquals(141, totalChapters(series(total = 120, known = 141)))
@Test fun noTotalAndNoneKnownIsNull() = assertNull(totalChapters(series(total = null, known = 0)))
@Test fun unreadIsTotalMinusProgress() = assertEquals(3, unread(series(total = 141, progress = 138)))
@Test fun unreadNeverNegative() = assertEquals(0, unread(series(total = 10, progress = 12)))
@Test fun continueReadingTakesThreeReadingSeriesMostRecentFirst() { /* 5 reading, 1 completed; lastReadAt mixed with nulls -> ids in expected order, size 3, no completed */ }
@Test fun aSeriesNeverReadFallsBehindOnesThatWere() { ... }
@Test fun proseIsNeverVisible() = assertTrue(visible(listOf(series(kind = "prose")), null, "").isEmpty())
@Test fun nullKindIsAComic() = assertEquals(1, visible(listOf(series(kind = null)), null, "").size)
@Test fun searchIgnoresCase() = assertEquals(1, visible(listOf(series(title = "Frieren")), null, "frie").size)

// LibraryViewModelTest — fake api through a Session fake
@Test fun firstLoadFailureIsFailed() = runTest { ... }
@Test fun refreshFailureKeepsTheLoadedRows() = runTest {
    // first series() returns 2 rows, second throws
    vm.refresh(); advanceUntilIdle()
    val state = vm.state.value as LoadState.Loaded
    assertEquals(2, state.data.size); assertNotNull(state.refreshFailed)
}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./gradlew :shared:jvmTest --tests 'app.soshuhen.library.*'`
Expected: FAIL, unresolved references.

- [ ] **Step 3: Implement `LoadState`, `LibraryRules`, `LibraryViewModel`.**

- [ ] **Step 4: Run the tests**

Run: `./gradlew :shared:jvmTest`
Expected: PASS.

- [ ] **Step 5: Implement `LibraryScreen`, `CoverImage`, `MainShell`, Koin modules.** Layout, top to bottom, as mockup option A: a search field; "Continue reading" row (horizontal, covers with chapter `progress + 1` and a progress bar `progress / total`); status chips from `STATUS_ORDER` with counts plus "All"; a `LazyVerticalGrid(GridCells.Adaptive(minSize = 112.dp))` of covers with title and an unread badge when `unread > 0`. `112.dp` lives in `Tokens` as `coverMinWidth`. Pull to refresh calls `refresh()`. `refreshFailed` shows as a banner above the grid ("Can't reach the server. Showing what was loaded."). `Failed` shows the message and a Retry button. Tapping a cover navigates to `series/{id}`.

- [ ] **Step 6: Build**

Run: `./gradlew :shared:jvmTest :androidApp:assembleDebug`
Expected: PASS, `BUILD SUCCESSFUL`.

- [ ] **Step 7: Commit**

```bash
git add mobile/shared
git commit -m "feat(mobile): show the library the way the web does"
```

### Task 6: Series detail and Settings

**Files:**
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/detail/DetailRules.kt`, `.../detail/SeriesDetailViewModel.kt`, `.../detail/SeriesDetailScreen.kt`
- Create: `mobile/shared/src/commonMain/kotlin/app/soshuhen/settings/SettingsScreen.kt`, `.../settings/SettingsViewModel.kt`
- Modify: `mobile/shared/src/commonMain/kotlin/app/soshuhen/MainShell.kt` (detail route, list-detail on wide screens, settings)
- Test: `mobile/shared/src/commonTest/kotlin/app/soshuhen/detail/DetailRulesTest.kt`, `.../detail/SeriesDetailViewModelTest.kt`

**Interfaces:**
- Consumes: `SoshuhenApi.seriesDetail`, `SoshuhenApi.resume`, `LoadState`, `CoverImage`, `Session`, `ServerStore.clear()`.
- Produces:
  - `enum class Availability { OnServer, NotDownloaded }` (part 3 adds `OnDevice`).
  - `data class ChapterRow(val id: Long, val number: Double, val title: String?, val read: Boolean, val availability: Availability)`.
  - `fun chapterRows(detail: SeriesDetail): List<ChapterRow>`: newest first; `read = floor(number) <= series.progress`, the same whole-chapter rule the server's `complete` uses; `OnServer` when `state == "downloaded"` and `filePath != null`, else `NotDownloaded`.
  - `fun continueChapter(detail: SeriesDetail, resume: Resume?): ChapterRow?`: the resume chapter when the server gave one and it is in the list, else the lowest-numbered unread `OnServer` chapter, else null.
  - `class SeriesDetailViewModel(seriesId: Long, session: Session) : ViewModel` with `val state: StateFlow<LoadState<DetailUi>>`, `data class DetailUi(val series: Series, val rows: List<ChapterRow>, val continueWith: ChapterRow?)`, `fun refresh()`.
  - `SettingsViewModel(session, store)`: shows the connected server (name, address, version from `identity()`) and `fun forget()` which clears the store and returns to onboarding.

- [ ] **Step 1: Write the failing tests**

```kotlin
@Test fun rowsAreNewestFirst() = assertEquals(listOf(3.0, 2.5, 2.0, 1.0), chapterRows(detail(progress = 0)).map { it.number })
@Test fun readIsByWholeChapter() { val rows = chapterRows(detail(progress = 2)); assertTrue(rows.single { it.number == 2.5 }.read); assertFalse(rows.single { it.number == 3.0 }.read) }
@Test fun downloadedWithAFileIsOnServer() { /* state downloaded + file_path -> OnServer; state downloaded + null path -> NotDownloaded; state known -> NotDownloaded */ }
@Test fun continueUsesTheServersResume() { /* resume chapter_id of 2.0 -> 2.0 */ }
@Test fun continueFallsBackToFirstUnreadOnServer() { /* resume null, progress 1, 2.0 not downloaded, 2.5 on server -> 2.5 */ }
@Test fun resumePointingAtAChapterNotListedFallsBack() { ... }
@Test fun nothingToContinueIsNull() { ... }
@Test fun detailRefreshFailureKeepsLoadedRows() = runTest { ... } // same shape as the library one
```

- [ ] **Step 2: Run them to verify they fail**

Run: `./gradlew :shared:jvmTest --tests 'app.soshuhen.detail.*'`
Expected: FAIL, unresolved references.

- [ ] **Step 3: Implement `DetailRules`, `SeriesDetailViewModel`, `SettingsViewModel`.**

- [ ] **Step 4: Run the tests**

Run: `./gradlew :shared:jvmTest`
Expected: PASS.

- [ ] **Step 5: Implement the screens and the wide layout.** Detail: cover, title, "Read up to chapter N · M on the server" (`N = progress`, `M = downloaded`), a "Continue chapter X" button that is shown but disabled with "Reading arrives in the next update" until part 3's reader exists, then the chapter list with a ✓ for read and "on server" / "not downloaded". On medium and expanded widths `MainShell` uses `ListDetailPaneScaffold` so the library grid and the detail sit side by side (mockup: tablet). Settings: the server card, "Change server" (calls `forget()`), and the app version.

- [ ] **Step 6: Build and try it on a device or emulator** against the running stack (`docker compose ps` shows `web` up on 8080)

Run: `./gradlew :shared:jvmTest :androidApp:installDebug`
Expected: PASS and `Installed on 1 device`. On the device: first run lists the server; the library shows covers from `/api/series/{id}/cover`; a series opens; rotating a tablet or an emulator at 1280×800 shows the rail and list-detail.

- [ ] **Step 7: Document.** A short "Android app" section in `docs/features.md`: what it does today (find the server, browse the library and a series) and that offline reading arrives next. Point to `mobile/README.md` for building.

- [ ] **Step 8: Commit**

```bash
git add mobile/shared docs/features.md
git commit -m "feat(mobile): open a series and see what has been read and downloaded"
```
