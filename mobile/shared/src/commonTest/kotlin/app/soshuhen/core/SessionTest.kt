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
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

@OptIn(ExperimentalCoroutinesApi::class)
// runCurrent, not advanceUntilIdle: the session collects in backgroundScope,
// which advanceUntilIdle does not run in kotlinx-coroutines-test 1.11.
class SessionTest {
    private val client = soshuhenHttpClient(MockEngine { respondOk() })

    private fun session(store: ServerStore, answers: Map<String, Identity>, wifi: Pair<String, Int>?, scope: kotlinx.coroutines.CoroutineScope): Session {
        val probe: suspend (ServerAddress) -> Identity? = { answers[it.host] }
        return Session(store, ServerLocator(probe, ServerScanner(probe)), FakeNetworkInfo(wifi), client, scope)
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
}
