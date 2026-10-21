package app.soshuhen.onboarding

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.server.FoundServer
import app.soshuhen.ui.theme.Tokens

@Composable
fun OnboardingScreen(model: OnboardingViewModel) {
    val state by model.state.collectAsStateWithLifecycle()
    var address by rememberSaveable { mutableStateOf("") }
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(Tokens.space.xl),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Column(Modifier.widthIn(max = Tokens.contentMaxWidth), verticalArrangement = Arrangement.spacedBy(Tokens.space.lg)) {
            Text("Find your Soshuhen server", style = MaterialTheme.typography.headlineMedium)
            val found = when (val s = state) {
                is OnboardingState.Scanning -> s.found
                is OnboardingState.Done -> s.found
                else -> emptyList()
            }
            if (state is OnboardingState.Scanning) {
                Text("Looking on this network…", color = MaterialTheme.colorScheme.onSurfaceVariant)
                LinearProgressIndicator(Modifier.fillMaxWidth())
            }
            found.forEach { ServerRow(it) { model.choose(it) } }
            if (state is OnboardingState.Done && found.isEmpty()) {
                Text("No server found on this network.", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (state is OnboardingState.Done) {
                TextButton(onClick = model::rescan) { Text("Scan again") }
            }
            Text("Or type its address", style = MaterialTheme.typography.titleMedium)
            OutlinedTextField(
                value = address,
                onValueChange = { address = it },
                label = { Text("Server address") },
                placeholder = { Text("192.168.1.20:8080") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Go),
                keyboardActions = KeyboardActions(onGo = { model.submitAddress(address) }),
                isError = state is OnboardingState.Failed,
                supportingText = (state as? OnboardingState.Failed)?.let { { Text(it.message) } },
                modifier = Modifier.fillMaxWidth(),
            )
            Button(
                onClick = { model.submitAddress(address) },
                enabled = state !is OnboardingState.Checking,
            ) { Text(if (state is OnboardingState.Checking) "Connecting…" else "Connect") }
        }
    }
}

@Composable
private fun ServerRow(server: FoundServer, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Row(Modifier.padding(Tokens.space.lg), horizontalArrangement = Arrangement.spacedBy(Tokens.space.md)) {
            Column {
                Text(server.identity.name, style = MaterialTheme.typography.titleMedium)
                Text(
                    "${server.address.host}:${server.address.port} · ${server.identity.version}",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}
