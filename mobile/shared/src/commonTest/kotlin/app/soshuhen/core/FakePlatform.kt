package app.soshuhen.core

class FakePlatform(
    var picked: String? = "content://tree/Manga",
    override val needsNotificationPermission: Boolean = true,
    var unrestricted: Boolean = false,
    var notificationsOn: Boolean = true,
) : Platform {
    var notificationSettingsOpened = 0

    override fun areNotificationsEnabled() = notificationsOn

    override fun openNotificationSettings() {
        notificationSettingsOpened++
    }

    var notificationRequests = 0
    var batterySettingsOpened = 0

    override suspend fun pickFolder(): String? = picked

    override suspend fun requestNotifications(): Boolean {
        notificationRequests++
        return false
    }

    var space: VolumeSpace? = VolumeSpace(free = 21_000_000_000, total = 64_000_000_000)

    override fun freeSpace(treeUri: String): VolumeSpace? = space

    override fun isBatteryUnrestricted() = unrestricted

    override fun openBatterySettings() {
        batterySettingsOpened++
    }
}
