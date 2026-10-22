package app.soshuhen.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import app.soshuhen.core.LocalStore

/**
 * Why the last background copy stopped. It is the only way a worker nobody is
 * watching can say something went wrong, since a failure raises no notification.
 */
@Composable
fun ProblemBanner(store: LocalStore, modifier: Modifier = Modifier) {
    val problem by remember(store) { store.problem() }.collectAsStateWithLifecycle(null)
    problem?.let { message -> NoticeBar(message, NoticeTone.Error, modifier) }
}
