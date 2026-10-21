package app.soshuhen.server

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull

class ServerAddressTest {
    @Test fun bareIp() =
        assertEquals(ServerAddress("http", "192.168.1.20", 8080), parseServerAddress("192.168.1.20"))

    @Test fun ipWithPort() = assertEquals(8090, parseServerAddress("192.168.1.20:8090")!!.port)

    @Test fun fullUrlWithTrailingSlash() =
        assertEquals("http://192.168.1.20:8080", parseServerAddress("http://192.168.1.20:8080/")!!.baseUrl)

    @Test fun surroundingSpaces() {
        assertNotNull(parseServerAddress("  192.168.1.20  "))
    }

    @Test fun https() =
        assertEquals(ServerAddress("https", "host", 8443), parseServerAddress("https://host:8443"))

    @Test fun httpsDefaultsTo443() = assertEquals(443, parseServerAddress("https://host")!!.port)

    @Test fun garbage() {
        listOf("", "   ", "abc def", "http://", "192.168.1.20:99999", "192.168.1.20:0", "ftp://x", "http://h/api", "h:port")
            .forEach { assertNull(parseServerAddress(it), "accepted '$it'") }
    }
}
