package app.soshuhen.reader

import kotlin.test.Test
import kotlin.test.assertEquals

class VolumeKeysTest {
    @Test fun downReadsOn() = assertEquals(ReaderKey.Next, volumeKey(down = true, inverted = false))
    @Test fun upGoesBack() = assertEquals(ReaderKey.Previous, volumeKey(down = false, inverted = false))
    @Test fun invertedDownGoesBack() = assertEquals(ReaderKey.Previous, volumeKey(down = true, inverted = true))
    @Test fun invertedUpReadsOn() = assertEquals(ReaderKey.Next, volumeKey(down = false, inverted = true))
}
