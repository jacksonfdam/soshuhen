package app.soshuhen.updates

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.soshuhen.core.LocalStore
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import kotlin.time.Clock
import kotlin.time.Instant

/** One copied chapter, with the heading of the day it arrived on. */
data class ImportLogRow(
    val chapterId: Long,
    val seriesId: Long,
    val seriesTitle: String,
    val number: Double,
    val importedAt: Instant,
    val day: String,
)

class UpdatesViewModel(
    store: LocalStore,
    // Injected: "Today" depends on the clock and the zone, and a test has to
    // pin both.
    private val clock: () -> Instant = { Clock.System.now() },
    private val zone: TimeZone = TimeZone.currentSystemDefault(),
) : ViewModel() {
    val rows: StateFlow<List<ImportLogRow>> = store.importLog()
        .map { log ->
            val today = clock().toLocalDateTime(zone).date
            log.map {
                val at = Instant.fromEpochMilliseconds(it.importedAt)
                ImportLogRow(it.chapterId, it.seriesId, it.seriesTitle, it.number, at, label(at.toLocalDateTime(zone).date, today))
            }
        }
        .stateIn(viewModelScope, SharingStarted.Eagerly, emptyList())

    private fun label(day: LocalDate, today: LocalDate): String = when (day.toEpochDays()) {
        today.toEpochDays() -> "Today"
        today.toEpochDays() - 1 -> "Yesterday"
        else -> "${day.day} ${MONTHS[day.month.ordinal]} ${day.year}"
    }

    private companion object {
        val MONTHS = listOf("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    }
}
