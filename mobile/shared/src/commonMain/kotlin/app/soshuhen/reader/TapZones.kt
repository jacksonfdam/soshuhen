package app.soshuhen.reader

enum class TapAction { Previous, Next, Chrome }

/**
 * The web's PagedView zones: a third each side, the middle for the chrome.
 * Only `paged_rtl` flips them; the web's double page reads left to right.
 */
fun tapAction(x: Float, width: Float, mode: String): TapAction {
    // Down a strip a tap anywhere is for the chrome, as the web's StripView:
    // the page is turned by scrolling, not by where the finger lands.
    if (mode == "long_strip" || width <= 0f) return TapAction.Chrome
    val at = x / width
    val left = if (mode == "paged_rtl") TapAction.Next else TapAction.Previous
    val right = if (mode == "paged_rtl") TapAction.Previous else TapAction.Next
    return when {
        at < 1f / 3f -> left
        at > 2f / 3f -> right
        else -> TapAction.Chrome
    }
}
