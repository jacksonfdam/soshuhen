package app.soshuhen.profiles

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.text.style.TextAlign
import app.soshuhen.api.Profile
import app.soshuhen.ui.Avatar
import app.soshuhen.ui.WebGlyph
import app.soshuhen.ui.WebIcon
import app.soshuhen.ui.theme.Tokens

private const val DIMMED = 0.4f

/** Who is reading. A PIN keeps someone out of the wrong profile by a wrong tap; it is not a lock. */
@Composable
fun ProfilePickerScreen(model: ProfilesViewModel) {
    val state by model.state.collectAsState()
    Box(Modifier.fillMaxSize().padding(Tokens.space.lg), contentAlignment = Alignment.Center) {
        val pinFor = state.pinFor
        if (pinFor != null) {
            PinPad(pinFor, state.pinError, state.busy, model::submitPin, model::cancelPin)
            return@Box
        }
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(Tokens.space.lg)) {
            Text("Who's reading?", style = MaterialTheme.typography.headlineSmall, color = Tokens.onSurface)
            LazyVerticalGrid(
                columns = GridCells.Adaptive(Tokens.box.avatarLg + Tokens.space.lg),
                horizontalArrangement = Arrangement.spacedBy(Tokens.space.lg),
                verticalArrangement = Arrangement.spacedBy(Tokens.space.lg),
            ) {
                items(state.profiles, key = { it.id }) { profile -> Tile(profile, state.atHome, model::choose) }
            }
        }
    }
}

@Composable
private fun Tile(profile: Profile, atHome: Boolean, onChoose: (Profile) -> Unit) {
    // Away from home a PIN cannot be checked, so the profile is shown but shut.
    val shut = profile.hasPin && !atHome
    Column(
        Modifier.alpha(if (shut) DIMMED else 1f).clickable(enabled = !shut) { onChoose(profile) },
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Tokens.space.xs),
    ) {
        Avatar(profile.avatar, profile.name, Tokens.box.avatarLg)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Tokens.space.xs)) {
            if (profile.hasPin) WebGlyph(WebIcon.Lock, Tokens.outline, Tokens.icon.sm)
            Text(profile.name, style = MaterialTheme.typography.titleSmall, color = Tokens.onSurface)
        }
        if (shut) {
            Text(
                "Needs the server to check the PIN",
                style = MaterialTheme.typography.bodySmall,
                color = Tokens.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
        }
    }
}
