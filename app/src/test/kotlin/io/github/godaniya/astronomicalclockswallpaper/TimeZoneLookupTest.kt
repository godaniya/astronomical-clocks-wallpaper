package io.github.godaniya.astronomicalclockswallpaper

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.ZoneId

/** Tests offline coordinate-to-timezone nearest-anchor lookup and canonical zone lists. */
class TimeZoneLookupTest {
    @Test
    fun referenceLocationsResolveZones() {
        assertZone(latitude = 50.0875, longitude = 14.4206, expectedZone = "Europe/Prague")
        assertZone(latitude = -33.8688, longitude = 151.2093, expectedZone = "Australia/Sydney")
        assertZone(latitude = 35.6762, longitude = 139.6503, expectedZone = "Asia/Tokyo")
        assertZone(latitude = 40.7128, longitude = -74.0060, expectedZone = "America/New_York")
        assertZone(latitude = 34.0522, longitude = -118.2437, expectedZone = "America/Los_Angeles")
        assertZone(latitude = 51.5074, longitude = -0.1278, expectedZone = "Europe/London")
        assertZone(latitude = 78.2232, longitude = 15.6267, expectedZone = "Arctic/Longyearbyen")
        assertZone(latitude = -54.8019, longitude = -68.3030, expectedZone = "America/Argentina/Ushuaia")
        assertZone(latitude = 31.2304, longitude = 121.4737, expectedZone = "Asia/Shanghai")
        assertZone(latitude = 22.5726, longitude = 88.3639, expectedZone = "Asia/Kolkata")
    }

    @Test
    fun disputedPlacesResolveAnchor() {
        // Taipei
        assertZone(latitude = 25.0330, longitude = 121.5654, expectedZone = "Asia/Taipei")
        // Crimea / Simferopol
        assertZone(latitude = 44.9521, longitude = 34.1025, expectedZone = "Europe/Simferopol")
        // Jerusalem
        assertZone(latitude = 31.7683, longitude = 35.2137, expectedZone = "Asia/Jerusalem")
        // Cyprus / Nicosia
        assertZone(latitude = 35.1856, longitude = 33.3823, expectedZone = "Asia/Nicosia")
        // Western Sahara / El Aaiún
        assertZone(latitude = 27.1253, longitude = -13.1625, expectedZone = "Africa/El_Aaiun")
        // Kashmir / Srinagar (nearest tzdb anchor point is Kabul; user can override via picker)
        assertZone(latitude = 34.0837, longitude = 74.7973, expectedZone = "Asia/Kabul")
    }

    @Test
    fun antimeridianNormalizes() {
        assertZone(latitude = -17.7134, longitude = 178.0650, expectedZone = "Pacific/Fiji")
        assertZone(latitude = -21.1789, longitude = -175.1982, expectedZone = "Pacific/Tongatapu")
        // Points just east and west of antimeridian near Fiji resolve to Pacific/Fiji
        assertZone(latitude = -18.0, longitude = 179.9, expectedZone = "Pacific/Fiji")
        assertZone(latitude = -18.0, longitude = -179.9, expectedZone = "Pacific/Fiji")
    }

    @Test
    fun availableZoneIdsAreSorted() {
        val zones = TimeZoneLookup.AVAILABLE_ZONE_IDS
        assertTrue("Zone list must contain standard IANA anchors", zones.size > 300)
        assertEquals("Zone list must be sorted alphabetically", zones.sorted(), zones)
        assertEquals("Zone list must contain no duplicates", zones.distinct(), zones)
        for (zone in zones) {
            val parsed = ZoneId.of(zone)
            assertNotNull(parsed)
        }
    }

    private fun assertZone(latitude: Double, longitude: Double, expectedZone: String) {
        val resolved = TimeZoneLookup.lookup(latitude = latitude, longitude = longitude)
        assertEquals(ZoneId.of(expectedZone), resolved)
    }
}
