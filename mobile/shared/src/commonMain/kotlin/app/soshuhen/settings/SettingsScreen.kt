package app.soshuhen.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.ui.theme.Tokens

@Composable
fun SettingsScreen(model: SettingsViewModel, appVersion: String) {
    val server by model.server.collectAsStateWithLifecycle()
    Column(
        Modifier.padding(Tokens.space.xl).widthIn(max = Tokens.contentMaxWidth),
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
        OutlinedButton(onClick = model::forget) { Text("Change server") }
        Text("Soshuhen for Android $appVersion", color = Tokens.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
    }
}
