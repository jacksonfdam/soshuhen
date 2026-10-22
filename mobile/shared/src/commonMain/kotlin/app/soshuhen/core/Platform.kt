package app.soshuhen.core

/** What only the running phone can do: system pickers, permissions and battery settings. */
interface Platform {
    /** The tree URI of a folder the user picked, with read and write kept across restarts; null when they backed out. */
    suspend fun pickFolder(): String?

    /** Whether notifications may be posted once the user has answered. */
    suspend fun requestNotifications(): Boolean

    /** Android 13 and later ask for notifications at runtime, and only until they are granted. */
    val needsNotificationPermission: Boolean

    fun isBatteryUnrestricted(): Boolean

    fun openBatterySettings()

    /** Whether Android lets this app post at all, whatever was answered at setup. */
    fun areNotificationsEnabled(): Boolean

    /** This app's page in Android's notification settings, the one place they are turned back on. */
    fun openNotificationSettings()
}
