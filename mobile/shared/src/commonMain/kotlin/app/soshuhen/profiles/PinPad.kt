package app.soshuhen.profiles

import androidx.compose.animation.core.Animatable
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import app.soshuhen.api.Profile
import app.soshuhen.ui.Avatar
import app.soshuhen.ui.ButtonVariant
import app.soshuhen.ui.WebButton
import app.soshuhen.ui.theme.Tokens

private const val MIN_PIN = 4
private const val MAX_PIN = 6

/**
 * Six dots and a digit grid. Submits on its own at six digits, or on OK from
 * four. A wrong PIN shakes and clears: it says "try again", not "go away".
 */
@Composable
fun PinPad(
    profile: Profile,
    error: Boolean,
    busy: Boolean,
    onSubmit: (String) -> Unit,
    onCancel: () -> Unit,
) {
    var pin by remember(profile.id) { mutableStateOf("") }
    val shake = remember { Animatable(0f) }
    LaunchedEffect(error) {
        if (error) {
            pin = ""
            // A shake measured in the spacing scale, settling back to rest.
            for (x in listOf(1f, -1f, 0.66f, -0.66f, 0f)) shake.animateTo(x)
        }
    }
    fun type(digit: Char) {
        if (busy || pin.length >= MAX_PIN) return
        pin += digit
        if (pin.length == MAX_PIN) onSubmit(pin)
    }
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(Tokens.space.lg)) {
        Avatar(profile.avatar, profile.name, Tokens.box.avatarLg)
        Text("Enter ${profile.name}'s PIN", style = MaterialTheme.typography.titleMedium, color = Tokens.onSurface)
        Row(
            Modifier.offset(x = Tokens.space.md * shake.value).semantics { contentDescription = "${pin.length} digits entered" },
            horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm),
        ) {
            repeat(MAX_PIN) { i ->
                Box(
                    Modifier.size(Tokens.box.pinDot).clip(CircleShape)
                        .background(if (i < pin.length) Tokens.primary else Tokens.surfaceContainerHighest),
                )
            }
        }
        if (error) Text("That PIN didn't match. Try again.", style = MaterialTheme.typography.bodySmall, color = Tokens.error)
        val rows = listOf("123", "456", "789")
        Column(verticalArrangement = Arrangement.spacedBy(Tokens.space.sm)) {
            rows.forEach { digits ->
                Row(horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm)) { digits.forEach { Key(it.toString()) { type(it) } } }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm)) {
                Key("⌫") { if (!busy) pin = pin.dropLast(1) }
                Key("0") { type('0') }
                Key("OK", enabled = pin.length >= MIN_PIN && !busy) { onSubmit(pin) }
            }
        }
        WebButton("Back to profiles", onCancel, variant = ButtonVariant.Ghost)
    }
}

@Composable
private fun Key(label: String, enabled: Boolean = true, onClick: () -> Unit) {
    Box(
        Modifier.size(Tokens.box.pinKey).clip(CircleShape)
            .background(Tokens.surfaceContainerHigh)
            .clickable(enabled = enabled, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.titleLarge,
            color = if (enabled) Tokens.onSurface else Tokens.outline,
        )
    }
}
