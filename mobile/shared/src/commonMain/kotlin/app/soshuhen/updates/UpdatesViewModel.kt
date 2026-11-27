package app.soshuhen.updates

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.soshuhen.core.BookKind
import app.soshuhen.core.LocalStore
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.datetime.LocalDate
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime
import kotlin.time.Clock
import kotlin.time.Instant

/**
 * A series' chapters copied on one day, as one row: a first import brings a
 * whole backlog at once, and the notification already says it in one line.
 */
data class UpdateGroup(
    val seriesId: Long,
    val seriesTitle: String,
    val numbers: List<Double>,
    val latestAt: Instant,
    val day: String,
    val volumes: List<Double> = emptyList(),
)

class UpdatesViewModel(
    store: LocalStore,
    // Injected: "Today" depends on the clock and the zone, and a test has to
    // pin both.
    private val clock: () -> Instant = { Clock.System.now() },
    private val zone: TimeZone = TimeZone.currentSystemDefault(),
) : ViewModel() {
    // The log covers the device. A series someone else marked and this
    // profile did not is their news; one nobody marks (an older install's) stays.
    val rows: StateFlow<List<UpdateGroup>> = combine(store.importLog(), store.markedIds(), store.anyoneMarkedIds()) {
        log, mine, anyone -> log.filter { it.seriesId in mine || it.seriesId !in anyone }
    }
        .map { log ->
            val today = clock().toLocalDateTime(zone).date
            // The log arrives newest first and groupBy keeps first appearances in
            // order, so days and the series within them stay newest first.
            log.groupBy { label(Instant.fromEpochMilliseconds(it.importedAt).toLocalDateTime(zone).date, today) to it.seriesId }
                .map { (key, chapters) ->
                    val newest = chapters.first()
                    val (volumes, rest) = chapters.partition { it.kind == BookKind.Volume.key }
                    UpdateGroup(
                        newest.seriesId, newest.seriesTitle, rest.map { it.number },
                        Instant.fromEpochMilliseconds(newest.importedAt), key.first, volumes.map { it.number },
                    )
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
