package app.soshuhen.core

import app.soshuhen.api.Series
import app.soshuhen.api.SeriesChapter
import app.soshuhen.api.SeriesDetail
import app.soshuhen.db.SoshuhenDatabase
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.time.Instant

class DeviceLibraryTest {
    private lateinit var db: SoshuhenDatabase
    private lateinit var store: LocalStore
    private lateinit var folder: FakeChapterFolder
    private lateinit var library: DeviceLibrary
    private val series = Series(id = 7, title = "S", slug = "s")

    @BeforeTest fun setUp() {
        db = testDatabase()
        store = LocalStore(db)
        folder = FakeChapterFolder()
        library = DeviceLibrary(store, folder)
    }

    @AfterTest fun tearDown() = db.close()

    private suspend fun onDevice(id: Long, number: Double) {
        val name = "c$id.cbz"
        store.indexChapter(DeviceChapter(id, 7, number, name, folder.put("s", name), null, 3, Instant.fromEpochMilliseconds(1)))
    }

    private suspend fun indexed() = store.allDeviceChapterIds().first()

    @Test fun markingRemembersTheSeries() = runTest {
        library.mark(series)
        assertTrue(store.isMarked(7).first())
    }

    @Test fun unmarkKeepsFilesByDefault() = runTest {
        library.mark(series)
        onDevice(1, 1.0)
        onDevice(2, 2.0)
        library.unmark(7, deleteFiles = false)
        assertFalse(store.isMarked(7).first())
        assertEquals(2, folder.files.size)
        assertEquals(setOf(1L, 2L), indexed())
    }

    @Test fun unmarkWithDeleteRemovesFilesAndIndex() = runTest {
        library.mark(series)
        onDevice(1, 1.0)
        onDevice(2, 2.0)
        library.unmark(7, deleteFiles = true)
        assertTrue(folder.files.isEmpty())
        assertTrue(indexed().isEmpty())
        assertFalse(store.isMarked(7).first())
    }

    @Test fun deleteReadKeepsUnread() = runTest {
        onDevice(1, 1.0)
        onDevice(2, 2.5)
        onDevice(3, 3.0)
        val detail = SeriesDetail(series.copy(progress = 2), listOf(SeriesChapter(3, 3.0, state = "downloaded", filePath = "/x")))
        library.deleteRead(detail)
        assertEquals(setOf(3L), indexed())
        assertEquals(1, folder.files.size)
    }

    @Test fun aFileAlreadyGoneIsStillForgotten() = runTest {
        onDevice(1, 1.0)
        folder.files.clear()
        library.deleteChapter(1)
        assertTrue(indexed().isEmpty())
    }

    @Test fun anUnavailableFolderKeepsTheIndex() = runTest {
        onDevice(1, 1.0)
        folder.failDeleteWith = FolderUnavailable()
        assertFailsWith<FolderUnavailable> { library.deleteChapter(1) }
        assertEquals(setOf(1L), indexed())
    }
}
