package app.soshuhen.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import app.soshuhen.ui.theme.Tokens
import app.soshuhen.ui.theme.mono

// The web's shared primitives from frontend/src/ui/, one composable each, so
// every screen draws a card, a pill or a button the way the web does.

/** The five tones the web's Badge, StatusPill and ProgressBar take. */
enum class Tone(val color: Color, val container: Color, val onContainer: Color) {
    Primary(Tokens.primary, Tokens.primaryContainer, Tokens.onPrimaryContainer),
    Secondary(Tokens.secondary, Tokens.secondaryContainer, Tokens.onSecondaryContainer),
    Tertiary(Tokens.tertiary, Tokens.tertiaryContainer, Tokens.onTertiaryContainer),
    Warning(Tokens.warning, Tokens.warningContainer, Tokens.onWarningContainer),
    Error(Tokens.error, Tokens.errorContainer, Tokens.onErrorContainer),
}

/** The web's Icon.tsx paths, drawn on the same 24-unit box; Book is the one recorded exception. */
enum class WebIcon(val path: String) {
    Sync("M12 4V1L8 5l4 4V6a6 6 0 1 1-6 6H4a8 8 0 1 0 8-8z"),
    Check("M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"),
    Search("M15.5 14h-.8l-.3-.3a6.5 6.5 0 1 0-.7.7l.3.3v.8l5 5 1.5-1.5zm-6 0a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9z"),
    // Deviation: the web's book is a bare outlined rectangle, which on a phone
    // reads as a missing-glyph box ("tofu") and was reported as broken on a
    // tablet. Material's book, filled with its ribbon, says book at 14 dp.
    Book("M18 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 4h5v8l-2.5-1.5L6 12V4z"),
    Download("M12 16 7 11l1.4-1.4L11 12.2V4h2v8.2l2.6-2.6L17 11zM5 18h14v2H5z"),
    Settings("M12 15.5A3.5 3.5 0 1 1 15.5 12 3.5 3.5 0 0 1 12 15.5zm7.4-2.3.1-1.2-.1-1.2 2-1.5-2-3.4-2.3 1a7.6 7.6 0 0 0-2-1.2l-.4-2.4h-4l-.4 2.4a7.6 7.6 0 0 0-2 1.2l-2.3-1-2 3.4 2 1.5-.1 1.2.1 1.2-2 1.5 2 3.4 2.3-1a7.6 7.6 0 0 0 2 1.2l.4 2.4h4l.4-2.4a7.6 7.6 0 0 0 2-1.2l2.3 1 2-3.4z"),
    Sparkle("M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4z"),
    Warning("M1 21h22L12 2zm12-3h-2v-2h2zm0-4h-2v-4h2z"),
    Chevron("M16.59 8.59 12 13.17 7.41 8.59 6 10l6 6 6-6z"),
    Link("M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"),
    Server("M4 4h16v4H4V4zm0 6h16v4H4v-4zm0 6h16v4H4v-4zm2-10.5h2v1.5H6V5.5zm0 6h2v1.5H6V11.5zm0 6h2v1.5H6v-1.5z"),
    Folder("M10 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-8l-2-2z"),
    Bookmark("M17 3H7a2 2 0 0 0-2 2v16l7-3 7 3V5a2 2 0 0 0-2-2z"),
    Bell("M12 22a2 2 0 0 0 2-2h-4a2 2 0 0 0 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4a1.5 1.5 0 0 0-3 0v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1z"),
    Bolt("M11 21v-7H7l6-11v7h4z"),
}

private const val VIEWPORT = 24f

@Composable
fun WebGlyph(icon: WebIcon, tint: Color, size: Dp = Tokens.icon.md, modifier: Modifier = Modifier) {
    val vector = remember(icon) {
        ImageVector.Builder(icon.name, Tokens.icon.xl, Tokens.icon.xl, VIEWPORT, VIEWPORT)
            .addPath(PathParser().parsePathString(icon.path).toNodes(), fill = SolidColor(Color.Black))
            .build()
    }
    Icon(vector, contentDescription = null, tint = tint, modifier = modifier.size(size))
}

/** Card.tsx: rounded-xl surface-container, p-space-lg, shadow-card when elevated. */
@Composable
fun WebCard(
    modifier: Modifier = Modifier,
    elevated: Boolean = true,
    color: Color = Tokens.surfaceContainer,
    shape: RoundedCornerShape = RoundedCornerShape(Tokens.radius.xl),
    padding: Dp = Tokens.space.xl,
    spacing: Dp = Tokens.space.lg,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(
        modifier
            .shadow(if (elevated) Tokens.cardElevation else Tokens.smallElevation, shape, clip = false)
            .background(color, shape)
            .padding(padding),
        verticalArrangement = Arrangement.spacedBy(spacing),
        content = content,
    )
}

/** Badge.tsx: a solid *-container pill. */
@Composable
fun Badge(text: String, tone: Tone) {
    Text(
        text,
        style = MaterialTheme.typography.labelSmall.mono(),
        color = tone.onContainer,
        maxLines = 1,
        modifier = Modifier.background(tone.container, CircleShape)
            .padding(horizontal = Tokens.space.xs, vertical = Tokens.space.xxs),
    )
}

/** StatusPill.tsx and ChapterStateBadge: a 12% tint with a dot. */
@Composable
fun StatePill(text: String, tone: Tone, modifier: Modifier = Modifier) {
    Row(
        modifier.background(tone.color.copy(alpha = Tokens.tintAlpha), CircleShape)
            .padding(horizontal = Tokens.space.sm, vertical = Tokens.space.xxs),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Tokens.space.xsPlus),
    ) {
        Box(Modifier.size(Tokens.box.dot).background(tone.color, CircleShape))
        Text(text, style = MaterialTheme.typography.labelSmall.mono(), color = tone.color, maxLines = 1)
    }
}

/** The rounded surface-container-high tag the web uses for a country or a genre. */
@Composable
fun Tag(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.labelSmall.mono(),
        color = Tokens.onSurfaceVariant,
        maxLines = 1,
        modifier = Modifier.background(Tokens.surfaceContainerHigh, RoundedCornerShape(Tokens.radius.base))
            .padding(horizontal = Tokens.space.sm, vertical = Tokens.space.xxs),
    )
}

enum class NoticeTone { Info, Error }

/** NoticeBar.tsx: a one-line outcome above a screen's content. */
@Composable
fun NoticeBar(text: String, tone: NoticeTone = NoticeTone.Info, modifier: Modifier = Modifier, action: (@Composable () -> Unit)? = null) {
    val (background, color) = when (tone) {
        NoticeTone.Info -> Tokens.surfaceContainer to Tokens.onSurfaceVariant
        NoticeTone.Error -> Tokens.errorContainer.copy(alpha = Tokens.noticeAlpha) to Tokens.error
    }
    Row(
        modifier.fillMaxWidth().background(background, RoundedCornerShape(Tokens.radius.xl))
            .padding(horizontal = Tokens.space.lg, vertical = Tokens.space.sm),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm),
    ) {
        Text(text, style = MaterialTheme.typography.bodySmall, color = color, modifier = Modifier.weight(1f))
        action?.invoke()
    }
}

enum class ButtonVariant { Primary, Surface, Ghost, Danger }

/** Button.tsx: rounded-lg, text-label-md, md is px-space-md py-space-sm and sm is px-space-sm py-space-xs. */
@Composable
fun WebButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    variant: ButtonVariant = ButtonVariant.Surface,
    small: Boolean = false,
    icon: WebIcon? = null,
    enabled: Boolean = true,
) {
    val (background, color) = when (variant) {
        ButtonVariant.Primary -> Tokens.primary to Tokens.onPrimary
        ButtonVariant.Surface -> Tokens.surfaceContainerHigh to Tokens.onSurface
        ButtonVariant.Ghost -> Color.Transparent to Tokens.onSurfaceVariant
        ButtonVariant.Danger -> Tokens.error.copy(alpha = Tokens.tintAlpha) to Tokens.error
    }
    val shape = RoundedCornerShape(Tokens.radius.lg)
    Row(
        modifier
            .alpha(if (enabled) 1f else Tokens.disabledAlpha)
            .clip(shape)
            .background(background, shape)
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick)
            .padding(
                horizontal = if (small) Tokens.space.sm else Tokens.space.lg,
                vertical = if (small) Tokens.space.xs else Tokens.space.sm,
            ),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Tokens.space.xs),
    ) {
        icon?.let { WebGlyph(it, color) }
        Text(text, style = MaterialTheme.typography.labelMedium, color = color, maxLines = 1)
    }
}

/** Toggle.tsx: a 44 by 24 track, secondary when on, with the label beside it. */
@Composable
fun WebToggle(label: String, checked: Boolean, onChange: (Boolean) -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    Row(
        modifier
            .alpha(if (enabled) 1f else Tokens.disabledAlpha)
            .toggleable(checked, enabled = enabled, role = Role.Switch, onValueChange = onChange),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm),
    ) {
        Box(
            Modifier.size(Tokens.box.toggleWidth, Tokens.box.toggleHeight)
                .background(if (checked) Tokens.secondary else Tokens.surfaceVariant, CircleShape),
            contentAlignment = Alignment.CenterStart,
        ) {
            Box(
                Modifier.offset(x = if (checked) Tokens.box.toggleWidth - Tokens.box.toggleThumb - Tokens.space.xs else Tokens.space.xs)
                    .size(Tokens.box.toggleThumb)
                    .background(if (checked) Tokens.onSecondaryContainer else Tokens.onSurface, CircleShape),
            )
        }
        Text(label, style = MaterialTheme.typography.bodyMedium, color = Tokens.onSurface)
    }
}

/** SettingsPage's SectionHeader: a tinted icon tile, a headline and a line under it. */
@Composable
fun SectionHeader(icon: WebIcon, title: String, subtitle: String, meta: (@Composable () -> Unit)? = null) {
    Row(
        Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Tokens.space.sm),
    ) {
        Box(
            Modifier.size(Tokens.box.sectionTile)
                .background(Tokens.primary.copy(alpha = Tokens.tintAlpha), RoundedCornerShape(Tokens.radius.base)),
            contentAlignment = Alignment.Center,
        ) { WebGlyph(icon, Tokens.primary) }
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.headlineSmall, color = Tokens.onSurface)
            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = Tokens.onSurfaceVariant)
        }
        meta?.invoke()
    }
}

/** EmptyState.tsx: an icon disc, a title and a line, centred on a card. */
@Composable
fun EmptyState(icon: WebIcon, title: String, detail: String, modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxWidth().background(Tokens.surfaceContainer, RoundedCornerShape(Tokens.radius.xl))
            .padding(Tokens.space.xxl),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Tokens.space.sm),
    ) {
        Box(
            Modifier.size(Tokens.box.emptyIcon).background(Tokens.surfaceContainerHigh, CircleShape),
            contentAlignment = Alignment.Center,
        ) { WebGlyph(icon, Tokens.onSurfaceVariant, Tokens.icon.xl) }
        Text(title, style = MaterialTheme.typography.titleMedium, color = Tokens.onSurface, textAlign = TextAlign.Center)
        Text(
            detail,
            style = MaterialTheme.typography.bodySmall,
            color = Tokens.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.widthIn(max = Tokens.box.emptyDetailMax),
        )
    }
}

/** ProgressBar.tsx: h-1, rounded, on surface-container-highest. */
@Composable
fun ProgressBar(value: Float, max: Float, tone: Tone = Tone.Secondary, modifier: Modifier = Modifier) {
    val fraction = if (max > 0f) (value / max).coerceIn(0f, 1f) else 0f
    Box(modifier.fillMaxWidth().height(Tokens.box.bar).clip(CircleShape).background(Tokens.surfaceContainerHighest)) {
        Box(Modifier.fillMaxHeight().fillMaxWidth(fraction).background(tone.color, CircleShape))
    }
}

/** Chip.tsx: a status tab with its count. */
@Composable
fun WebChip(label: String, count: Int?, active: Boolean, onClick: () -> Unit) {
    val shape = RoundedCornerShape(Tokens.radius.xl)
    Row(
        Modifier.clip(shape)
            .background(if (active) Tokens.primary else Color.Transparent, shape)
            .clickable(role = Role.Tab, onClick = onClick)
            .padding(horizontal = Tokens.space.lg, vertical = Tokens.space.sm),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Tokens.space.xs),
    ) {
        Text(label, style = MaterialTheme.typography.titleSmall, color = if (active) Tokens.onPrimary else Tokens.onSurfaceVariant, maxLines = 1)
        count?.let {
            Text(
                it.toString(),
                style = MaterialTheme.typography.labelSmall.mono(),
                color = if (active) Tokens.onPrimary else Tokens.outline,
                modifier = Modifier
                    .background(if (active) Tokens.onPrimary.copy(alpha = Tokens.countAlpha) else Tokens.surfaceContainer, CircleShape)
                    .padding(horizontal = Tokens.space.sm, vertical = Tokens.space.xxs),
            )
        }
    }
}

/** A mono label in the web's text-label-sm, the line most of its small print uses. */
@Composable
fun MonoLabel(text: String, color: Color = Tokens.outline, modifier: Modifier = Modifier, uppercase: Boolean = false) {
    Text(
        if (uppercase) text.uppercase() else text,
        style = MaterialTheme.typography.labelSmall.mono(),
        color = color,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis,
        modifier = modifier,
    )
}

@Composable
fun Divider(modifier: Modifier = Modifier, color: Color = Tokens.divider) =
    Box(modifier.fillMaxWidth().height(Tokens.hairline).background(color))

