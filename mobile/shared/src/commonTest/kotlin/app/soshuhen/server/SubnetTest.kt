package app.soshuhen.server

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse

class SubnetTest {
    @Test fun slash24() {
        val hosts = subnetHosts("192.168.1.20", 24)
        assertEquals(253, hosts.size)
        assertFalse("192.168.1.20" in hosts)
        assertFalse("192.168.1.0" in hosts)
        assertFalse("192.168.1.255" in hosts)
    }

    @Test fun widerPrefixIsNarrowedTo24() {
        val hosts = subnetHosts("10.0.5.9", 16)
        assertEquals(253, hosts.size)
        assertEquals("10.0.5.1", hosts.first())
    }

    @Test fun slash30() = assertEquals(listOf("10.0.0.2"), subnetHosts("10.0.0.1", 30))
}
