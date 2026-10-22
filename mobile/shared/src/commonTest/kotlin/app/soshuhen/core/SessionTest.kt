package app.soshuhen.core

import app.soshuhen.api.Identity
import app.soshuhen.api.soshuhenHttpClient
import app.soshuhen.server.SavedServer
import app.soshuhen.server.ServerAddress
import app.soshuhen.server.ServerLocator
import app.soshuhen.server.ServerScanner
import app.soshuhen.server.identity
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respondOk
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
// runCurrent, not advanceUntilIdle: the session collects in backgroundScope,
// which advanceUntilIdle does not run in kotlinx-coroutines-test 1.11.
class SessionTest {
    private val client = soshuhenHttpClient(MockEngine { respondOk() })

    private fun session(
        store: ServerStore,
        answers: Map<String, Identity>,
        wifi: Pair<String, Int>?,
        scope: kotlinx.coroutines.CoroutineScope,
        network: FakeNetworkInfo = FakeNetworkInfo(wifi),
        onProbe: () -> Unit = {},
    ): Session {
        val probe: suspend (ServerAddress) -> Identity? = { onProbe(); answers[it.host] }
        return Session(store, ServerLocator(probe, ServerScanner(probe)), network, client, scope)
    }

    @Test fun apiIsNullUntilAServerIsSaved() = runTest {
        val store = FakeServerStore()
        val s = session(store, emptyMap(), "10.0.0.1" to 24, backgroundScope)
        runCurrent()
        assertNull(s.api.value)
        store.save(SavedServer(ServerAddress("http", "10.0.0.20", 8080), "id-1"))
        runCurrent()
        assertEquals("http://10.0.0.20:8080", s.api.value?.baseUrl)
    }

    @Test fun apiFollowsTheServerWhenItMoves() = runTest {
        val store = FakeServerStore(SavedServer(ServerAddress("http", "10.0.0.20", 8080), "id-1"))
        val s = session(store, mapOf("10.0.0.31" to identity(id = "id-1")), "10.0.0.1" to 24, backgroundScope)
        s.refreshLocation()
        runCurrent()
        assertEquals("http://10.0.0.31:8080", s.api.value?.baseUrl)
        assertEquals("10.0.0.31", store.saved.value?.address?.host)
    }

    @Test fun anUnreachableServerKeepsItsAddress() = runTest {
        val store = FakeServerStore(SavedServer(ServerAddress("http", "10.0.0.20", 8080), "id-1"))
        val s = session(store, emptyMap(), null, backgroundScope)
        s.refreshLocation()
        runCurrent()
        assertEquals("http://10.0.0.20:8080", s.api.value?.baseUrl)
    }

    @Test fun atHomeIsTrueOnlyWhenTheInstanceAnswers() = runTest {
        val saved = SavedServer(ServerAddress("http", "10.0.0.20", 8080), "id-1")
        val home = session(FakeServerStore(saved), mapOf("10.0.0.20" to identity(id = "id-1")), "10.0.0.1" to 24, backgroundScope)
        val away = session(FakeServerStore(saved), emptyMap(), null, backgroundScope)
        assertFalse(home.atHome.value)
        runCurrent()
        assertTrue(home.atHome.value)
        assertFalse(away.atHome.value)
    }

    @Test fun aNetworkChangeRelocates() = runTest {
        val saved = SavedServer(ServerAddress("http", "10.0.0.20", 8080), "id-1")
        val network = FakeNetworkInfo("10.0.0.1" to 24)
        var probes = 0
        session(FakeServerStore(saved), mapOf("10.0.0.20" to identity(id = "id-1")), null, backgroundScope, network) { probes++ }
        runCurrent()
        val first = probes
        network.changeEvents.emit(Unit)
        runCurrent()
        assertTrue(probes > first)
    }

    @Test fun aChangeMidScanCancelsTheStaleScan() = runTest {
        val saved = SavedServer(ServerAddress("http", "10.0.0.20", 8080), "id-1")
        val network = FakeNetworkInfo("10.0.0.1" to 24)
        var calls = 0
        var firstCancelled = false
        val probe: suspend (ServerAddress) -> Identity? = {
            if (calls++ == 0) {
                try { awaitCancellation() } catch (e: CancellationException) { firstCancelled = true; throw e }
            } else null
        }
        val s = Session(FakeServerStore(saved), ServerLocator(probe, ServerScanner(probe)), network, client, backgroundScope)
        runCurrent()
        assertFalse(firstCancelled)
        // The phone left home while the first check was still running.
        network.wifi = null
        network.changeEvents.emit(Unit)
        runCurrent()
        assertTrue(firstCancelled)
        assertFalse(s.atHome.value)
    }

    @Test fun startupProbesOnce() = runTest {
        val saved = SavedServer(ServerAddress("http", "10.0.0.20", 8080), "id-1")
        var probes = 0
        session(FakeServerStore(saved), mapOf("10.0.0.20" to identity(id = "id-1")), null, backgroundScope) { probes++ }
        runCurrent()
        assertEquals(1, probes)
    }
}
