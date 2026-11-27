package app.soshuhen.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.Dp
import app.soshuhen.resources.Res
import app.soshuhen.resources.avatar_01
import app.soshuhen.resources.avatar_02
import app.soshuhen.resources.avatar_03
import app.soshuhen.resources.avatar_04
import app.soshuhen.resources.avatar_05
import app.soshuhen.resources.avatar_06
import app.soshuhen.resources.avatar_07
import app.soshuhen.resources.avatar_08
import app.soshuhen.resources.avatar_09
import app.soshuhen.resources.avatar_10
import app.soshuhen.resources.avatar_11
import app.soshuhen.resources.avatar_12
import org.jetbrains.compose.resources.DrawableResource
import org.jetbrains.compose.resources.painterResource

// Rasterised from frontend/public/avatars/*.svg, the art's one source; the
// server stores the key, and the web and the app draw the same face for it.
private val AVATARS: Map<String, DrawableResource> = mapOf(
    "avatar-01" to Res.drawable.avatar_01,
    "avatar-02" to Res.drawable.avatar_02,
    "avatar-03" to Res.drawable.avatar_03,
    "avatar-04" to Res.drawable.avatar_04,
    "avatar-05" to Res.drawable.avatar_05,
    "avatar-06" to Res.drawable.avatar_06,
    "avatar-07" to Res.drawable.avatar_07,
    "avatar-08" to Res.drawable.avatar_08,
    "avatar-09" to Res.drawable.avatar_09,
    "avatar-10" to Res.drawable.avatar_10,
    "avatar-11" to Res.drawable.avatar_11,
    "avatar-12" to Res.drawable.avatar_12,
)

@Composable
fun Avatar(avatar: String, name: String, size: Dp, modifier: Modifier = Modifier) {
    Image(
        painter = painterResource(AVATARS[avatar] ?: Res.drawable.avatar_01),
        contentDescription = name,
        modifier = modifier.size(size).clip(CircleShape),
    )
}
