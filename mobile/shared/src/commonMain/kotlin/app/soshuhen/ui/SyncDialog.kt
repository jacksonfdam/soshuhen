package app.soshuhen.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import app.soshuhen.core.SyncFlow
import app.soshuhen.core.SyncUi
import app.soshuhen.core.progressText
import app.soshuhen.core.question
import app.soshuhen.core.reasons
import app.soshuhen.core.summary
import app.soshuhen.core.synced
import app.soshuhen.ui.theme.Tokens

/**
 * The sync's one dialog. "Keep on server" is the filled button and what the
 * system dismisses to: the server's copies go only when plainly told to.
 */
@Composable
fun SyncDialog(state: SyncUi, flow: SyncFlow) {
    val (title, body) = when (state) {
        SyncUi.Idle -> return
        is SyncUi.Running -> "Syncing" to progressText(state.progress)
        is SyncUi.Ask -> "Everything is on this device" to question(state.report) +
            state.report.revised.takeIf { it.isNotEmpty() }?.let { "\n\n${it.size} removed volumes have a newer revision on J-Novel Club." }.orEmpty()
        is SyncUi.Synced -> "Everything is on this device" to synced(state.report)
        is SyncUi.Unverified -> "Not everything is on this device" to
            (listOf(summary(state.report)) + reasons(state.report)).joinToString("\n")
        SyncUi.Removing -> "Removing from server…" to "The server checks each file before deleting it."
        is SyncUi.Done -> "Removed from server" to
            "${state.queued} files will be deleted from the server. They stay readable here."
        is SyncUi.Failed -> "Sync stopped" to state.message
    }
    val busy = state is SyncUi.Running || state == SyncUi.Removing
    AlertDialog(
        onDismissRequest = { if (!busy) flow.keep() },
        containerColor = Tokens.surfaceContainer,
        shape = RoundedCornerShape(Tokens.radius.xl),
        title = { Text(title, style = MaterialTheme.typography.headlineSmall, color = Tokens.onSurface) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(Tokens.space.sm)) {
                Text(body, style = MaterialTheme.typography.bodyMedium, color = Tokens.onSurfaceVariant)
            }
        },
        confirmButton = {
            when (state) {
                is SyncUi.Ask -> WebButton("Keep on server", flow::keep, variant = ButtonVariant.Primary)
                is SyncUi.Synced, is SyncUi.Unverified, is SyncUi.Done, is SyncUi.Failed ->
                    WebButton("OK", flow::keep, variant = ButtonVariant.Primary)
                else -> {}
            }
        },
        dismissButton = {
            if (state is SyncUi.Ask) WebButton("Delete from server", flow::deleteFromServer, variant = ButtonVariant.Danger)
        },
    )
}
