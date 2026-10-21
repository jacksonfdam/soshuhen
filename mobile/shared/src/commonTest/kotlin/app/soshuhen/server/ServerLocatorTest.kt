package app.soshuhen.server

import app.soshuhen.api.Identity
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull

class ServerLocatorTest {
    private val saved = SavedServer(ServerAddress("http", "10.0.0.20", 8080), "id-1")
    private var scanned = false

    private fun locator(answers: Map<String, Identity>): ServerLocator {
        val probe: suspend (ServerAddress) -> Identity? = { answers[it.host] }
        val scanner = ServerScanner { scanned = true; probe(it) }
        return ServerLocator(probe, scanner)
    }

    @Test fun savedAddressStillAnswers() = runTest {
        assertEquals(saved.address, locator(mapOf("10.0.0.20" to identity())).locate(saved, listOf("10.0.0.31")))
        assertFalse(scanned)
    }

    @Test fun movedServerIsFoundByInstanceId() = runTest {
        val found = locator(mapOf("10.0.0.31" to identity())).locate(saved, listOf("10.0.0.20", "10.0.0.31"))
        assertEquals("10.0.0.31", found?.host)
    }

    @Test fun aDifferentInstallationIsNotTakenForOurs() = runTest {
        val others = mapOf("10.0.0.20" to identity(id = "other"), "10.0.0.31" to identity(id = "other"))
        assertNull(locator(others).locate(saved, listOf("10.0.0.20", "10.0.0.31")))
    }

    @Test fun offWifiNoScan() = runTest {
        assertNull(locator(emptyMap()).locate(saved, null))
        assertFalse(scanned)
    }
}
