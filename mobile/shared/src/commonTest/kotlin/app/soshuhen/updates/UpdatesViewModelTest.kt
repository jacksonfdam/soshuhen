package app.soshuhen.updates

import app.soshuhen.core.LocalStore
import app.soshuhen.core.newChaptersText
import app.soshuhen.core.testDatabase
import app.soshuhen.db.ImportLogEntity
import app.soshuhen.db.SoshuhenDatabase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.datetime.TimeZone
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.time.Instant

@OptIn(ExperimentalCoroutinesApi::class)
class UpdatesViewModelTest {
    private val dispatcher = StandardTestDispatcher()
    private lateinit var db: SoshuhenDatabase
    private lateinit var store: LocalStore
    private val now = Instant.parse("2026-10-22T12:00:00Z")

    @BeforeTest fun setUp() {
        Dispatchers.setMain(dispatcher)
        db = testDatabase(dispatcher)
        store = LocalStore(db)
    }

    @AfterTest fun tearDown() {
        Dispatchers.resetMain()
        db.close()
    }

    private suspend fun log(chapter: Long, title: String, number: Double, at: String, series: Long = 1) =
        store.logImport(ImportLogEntity(chapter, series, title, number, Instant.parse(at).toEpochMilliseconds()))

    @Test fun updatesAreNewestFirstAndGroupedByDay() = runTest(dispatcher) {
        log(1, "Frieren", 139.0, "2026-10-10T08:00:00Z")
        log(2, "Frieren", 140.0, "2026-10-21T23:30:00Z")
        log(3, "Frieren", 141.0, "2026-10-22T10:00:00Z")
        val vm = UpdatesViewModel(store, { now }, TimeZone.UTC)
        advanceUntilIdle()
        assertEquals(listOf(listOf(141.0), listOf(140.0), listOf(139.0)), vm.rows.value.map { it.numbers })
        assertEquals(listOf("Today", "Yesterday", "10 Oct 2026"), vm.rows.value.map { it.day })
    }

    @Test fun aSeriesBacklogOnOneDayIsOneRow() = runTest(dispatcher) {
        // A first import: 39 chapters a few seconds apart, then another series.
        for (n in 1..39) log(n.toLong(), "Rebirth", n.toDouble(), "2026-10-21T20:00:${(n % 60).toString().padStart(2, '0')}Z")
        log(100, "Frieren", 141.0, "2026-10-21T21:00:00Z", series = 2)
        log(101, "Rebirth", 40.0, "2026-10-22T09:00:00Z")
        val vm = UpdatesViewModel(store, { now }, TimeZone.UTC)
        advanceUntilIdle()
        val rows = vm.rows.value
        assertEquals(listOf("Today" to 1L, "Yesterday" to 2L, "Yesterday" to 1L), rows.map { it.day to it.seriesId })
        assertEquals(
            listOf("1 new chapter (40)", "1 new chapter (141)", "39 new chapters (1–39)"),
            rows.map { newChaptersText(it.seriesTitle, it.numbers).second },
        )
        assertEquals(Instant.parse("2026-10-21T20:00:39Z"), rows[2].latestAt)
    }

    @Test fun theDayFollowsTheZoneNotUtc() = runTest(dispatcher) {
        // 23:30 UTC on the 21st is already the 22nd at UTC+2.
        log(1, "Frieren", 140.0, "2026-10-21T23:30:00Z")
        val vm = UpdatesViewModel(store, { now }, TimeZone.of("Europe/Stockholm"))
        advanceUntilIdle()
        assertEquals(listOf("Today"), vm.rows.value.map { it.day })
    }

    @Test fun nothingCopiedYetIsAnEmptyList() = runTest(dispatcher) {
        val vm = UpdatesViewModel(store, { now }, TimeZone.UTC)
        advanceUntilIdle()
        assertEquals(emptyList(), vm.rows.value)
    }
}
