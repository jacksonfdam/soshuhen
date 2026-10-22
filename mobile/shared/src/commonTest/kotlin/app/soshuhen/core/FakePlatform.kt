package app.soshuhen.core

class FakePlatform(
    var picked: String? = "content://tree/Manga",
    override val needsNotificationPermission: Boolean = true,
    var unrestricted: Boolean = false,
) : Platform {
    var notificationRequests = 0
    var batterySettingsOpened = 0

    override suspend fun pickFolder(): String? = picked

    override suspend fun requestNotifications(): Boolean {
        notificationRequests++
        return false
    }

    override fun isBatteryUnrestricted() = unrestricted

    override fun openBatterySettings() {
        batterySettingsOpened++
    }
}
