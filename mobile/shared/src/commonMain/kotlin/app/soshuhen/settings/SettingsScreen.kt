package app.soshuhen.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.LifecycleResumeEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.ui.theme.Tokens

@Composable
fun SettingsScreen(model: SettingsViewModel, appVersion: String) {
    val server by model.server.collectAsStateWithLifecycle()
    val volumeKeys by model.volumeKeys.collectAsStateWithLifecycle()
    val volumeInvert by model.volumeInvert.collectAsStateWithLifecycle()
    val folder by model.folder.collectAsStateWithLifecycle()
    val unrestricted by model.batteryUnrestricted.collectAsStateWithLifecycle()
    LifecycleResumeEffect(model) {
        model.refreshBattery()
        onPauseOrDispose { }
    }
    Column(
        // Scrolls: with the device card a short phone in landscape no longer fits it all.
        Modifier.verticalScroll(rememberScrollState()).padding(Tokens.space.xl).widthIn(max = Tokens.contentMaxWidth),
        verticalArrangement = Arrangement.spacedBy(Tokens.space.lg),
    ) {
        Text("Settings", style = MaterialTheme.typography.headlineMedium)
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(Tokens.space.lg), verticalArrangement = Arrangement.spacedBy(Tokens.space.xs)) {
                Text("Server", style = MaterialTheme.typography.titleMedium)
                val card = server
                if (card != null) {
                    Text(card.identity?.name ?: "Not reachable right now", style = MaterialTheme.typography.bodyLarge)
                    Text(
                        card.baseUrl + (card.identity?.let { " · ${it.version}" } ?: ""),
                        color = Tokens.onSurfaceVariant,
                    )
                }
            }
        }
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(Tokens.space.lg), verticalArrangement = Arrangement.spacedBy(Tokens.space.xs)) {
                Text("On this device", style = MaterialTheme.typography.titleMedium)
                Text(folder ?: "No folder picked", style = MaterialTheme.typography.bodyLarge)
                Text(
                    "Chapters already copied stay where they are. New ones go to the folder picked here.",
                    color = Tokens.onSurfaceVariant,
                    style = MaterialTheme.typography.bodySmall,
                )
                OutlinedButton(onClick = model::changeFolder) { Text("Change folder") }
                Text(
                    if (unrestricted) "Background copies: unrestricted" else "Background copies: Android may put the app to sleep",
                    color = if (unrestricted) Tokens.onSurface else Tokens.warning,
                    modifier = Modifier.padding(top = Tokens.space.sm),
                )
                OutlinedButton(onClick = model::openBatterySettings) { Text("Open battery settings") }
            }
        }
        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(Tokens.space.lg), verticalArrangement = Arrangement.spacedBy(Tokens.space.xs)) {
                Text("Reader", style = MaterialTheme.typography.titleMedium)
                SwitchRow("Volume keys turn pages", volumeKeys, model::setVolumeKeys)
                // Off while the keys do nothing: inverting them would be a choice with no effect.
                SwitchRow("Invert volume keys", volumeInvert, model::setVolumeInvert, enabled = volumeKeys)
            }
        }
        OutlinedButton(onClick = model::forget) { Text("Change server") }
        Text("Soshuhen for Android $appVersion", color = Tokens.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun SwitchRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit, enabled: Boolean = true) {
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, color = if (enabled) Tokens.onSurface else Tokens.onSurfaceVariant, modifier = Modifier.weight(1f))
        Switch(checked = checked, onCheckedChange = onChange, enabled = enabled)
    }
}
