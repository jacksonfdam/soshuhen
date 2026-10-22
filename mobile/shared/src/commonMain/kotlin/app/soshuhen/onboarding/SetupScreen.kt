package app.soshuhen.onboarding

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.ui.theme.Tokens

@Composable
fun SetupScreen(model: SetupViewModel) {
    val step by model.step.collectAsStateWithLifecycle()
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(Tokens.space.xl),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Column(Modifier.widthIn(max = Tokens.contentMaxWidth), verticalArrangement = Arrangement.spacedBy(Tokens.space.lg)) {
            Text("Set up this phone", style = MaterialTheme.typography.headlineMedium)
            when (step) {
                SetupStep.Folder -> StepCard(
                    title = "Where should chapters be kept?",
                    why = "Chapters you keep on this device are copied into a folder you choose, " +
                        "inside a Soshuhen folder of their own. They stay there, readable by any app, " +
                        "until you delete them.",
                ) {
                    Button(onClick = model::pickFolder) { Text("Pick a folder") }
                }
                SetupStep.Notifications -> StepCard(
                    title = "Tell you about new chapters?",
                    why = "When a copy brings new chapters, one notification says which series they are for.",
                ) {
                    Button(onClick = model::allowNotifications) { Text("Allow") }
                    TextButton(onClick = model::notNow) { Text("Not now") }
                }
                SetupStep.Battery -> StepCard(
                    title = "Let it copy in the background",
                    why = "Samsung and other phones put apps you have not opened lately to sleep, " +
                        "and a sleeping app copies nothing. Allowing unrestricted battery use keeps " +
                        "the hourly copy running.",
                ) {
                    Button(onClick = model::openBatterySettings) { Text("Open battery settings") }
                    TextButton(onClick = model::skipBattery) { Text("Skip") }
                }
                null -> Unit
            }
        }
    }
}

@Composable
private fun StepCard(title: String, why: String, actions: @Composable () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(Tokens.space.lg), verticalArrangement = Arrangement.spacedBy(Tokens.space.md)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            Text(why, color = Tokens.onSurfaceVariant)
            Row(horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm), verticalAlignment = Alignment.CenterVertically) {
                actions()
            }
        }
    }
}
