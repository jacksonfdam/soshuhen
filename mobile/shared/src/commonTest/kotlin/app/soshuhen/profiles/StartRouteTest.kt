package app.soshuhen.profiles

import app.soshuhen.api.Profile
import kotlin.test.Test
import kotlin.test.assertEquals

class StartRouteTest {
    private val me = Profile(1, "Me", "avatar-01", hasPin = false, isManager = true, position = 0)
    private val ana = Profile(7, "Ana", "avatar-12", hasPin = true, isManager = false, position = 1)

    @Test fun oneProfileOpensStraightIn() =
        assertEquals(StartRoute.Open(0), startRoute(listOf(me), atHome = true, saved = null, chosen = false, switching = false))

    @Test fun twoProfilesAtHomeAskOnEveryColdStart() =
        assertEquals(StartRoute.Picker, startRoute(listOf(me, ana), atHome = true, saved = 7, chosen = false, switching = false))

    @Test fun onceChosenThisLaunchTheProfileOpens() =
        assertEquals(StartRoute.Open(7), startRoute(listOf(me, ana), atHome = true, saved = 7, chosen = true, switching = false))

    @Test fun awayFromHomeOpensTheLastProfile() =
        assertEquals(StartRoute.Open(7), startRoute(listOf(me, ana), atHome = false, saved = 7, chosen = false, switching = false))

    @Test fun aDeletedProfileGoesBackToThePicker() =
        assertEquals(StartRoute.Picker, startRoute(listOf(me, ana), atHome = true, saved = 9, chosen = true, switching = false))

    @Test fun beforeTheListLoadsTheLastProfileOpens() =
        assertEquals(StartRoute.Open(7), startRoute(null, atHome = true, saved = 7, chosen = false, switching = false))

    @Test fun switchingAlwaysShowsThePicker() =
        assertEquals(StartRoute.Picker, startRoute(listOf(me, ana), atHome = false, saved = 7, chosen = true, switching = true))
}
