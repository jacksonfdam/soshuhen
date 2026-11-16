package app.soshuhen.core

import app.soshuhen.api.OffloadResult
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

@OptIn(ExperimentalCoroutinesApi::class)
class SyncFlowTest {
    private val verified = SyncReport(2, listOf(Held(BookRef(BookKind.Chapter, 1), "\"e\"", 2_147_483_648)), emptyList(), emptyList())
    private val blocked = SyncReport(1, emptyList(), listOf(Missing(BookRef(BookKind.Chapter, 1), MissingReason.NotCopied)), emptyList())

    private fun TestScope.flow(report: SyncReport, sent: MutableList<SyncReport> = mutableListOf()) =
        SyncFlow(
            run = { _ -> report },
            offload = { r -> sent += r; OffloadResult(queued = r.held.size) },
            scope = this,
        )

    @Test fun a_verified_run_asks_the_question() = runTest(StandardTestDispatcher()) {
        val f = flow(verified)
        f.start()
        advanceUntilIdle()
        val asking = assertIs<SyncUi.Ask>(f.state.value)
        assertEquals(
            "All 1 chapters of 2 series are on this device. Free 2 GB on the server?",
            question(asking.report),
        )
    }

    @Test fun an_unverified_run_only_reports() = runTest(StandardTestDispatcher()) {
        val f = flow(blocked)
        f.start()
        advanceUntilIdle()
        val shown = assertIs<SyncUi.Unverified>(f.state.value)
        assertEquals("0 of 1 on device · 1 could not be copied", summary(shown.report))
    }

    @Test fun keep_sends_nothing() = runTest(StandardTestDispatcher()) {
        val sent = mutableListOf<SyncReport>()
        val f = flow(verified, sent)
        f.start(); advanceUntilIdle()
        f.keep()
        assertEquals(SyncUi.Idle, f.state.value)
        assertEquals(emptyList(), sent)
    }

    @Test fun delete_offloads_the_report() = runTest(StandardTestDispatcher()) {
        val sent = mutableListOf<SyncReport>()
        val f = flow(verified, sent)
        f.start(); advanceUntilIdle()
        f.deleteFromServer(); advanceUntilIdle()
        assertEquals(listOf(verified), sent)
        assertEquals(SyncUi.Done(1), f.state.value)
    }
}
