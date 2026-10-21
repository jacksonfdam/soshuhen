package app.soshuhen.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.core.LocalStore
import app.soshuhen.ui.theme.Tokens

/**
 * Why the last background copy stopped. It is the only way a worker nobody is
 * watching can say something went wrong, since a failure raises no notification.
 */
@Composable
fun ProblemBanner(store: LocalStore, modifier: Modifier = Modifier) {
    val problem by remember(store) { store.problem() }.collectAsStateWithLifecycle(null)
    problem?.let { message ->
        Text(
            message,
            color = Tokens.onWarning,
            modifier = modifier.fillMaxWidth()
                .background(Tokens.warning, RoundedCornerShape(Tokens.radius.sm))
                .padding(Tokens.space.md),
        )
    }
}
