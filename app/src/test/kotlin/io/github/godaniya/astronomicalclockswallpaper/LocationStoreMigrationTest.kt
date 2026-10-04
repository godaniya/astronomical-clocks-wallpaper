package io.github.godaniya.astronomicalclockswallpaper

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowLog
import java.time.ZoneId

/** Exercises one-time device-zone capture for legacy coordinates and incomplete version-one records. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 36])
class LocationStoreMigrationTest {
    @Test
    fun legacyCapturesZoneOnce() {
        saveLegacy()
        var deviceZone = ZoneId.of("Europe/Prague")
        var zoneReads = 0
        val store =
            LocationStore(RuntimeEnvironment.getApplication()) {
                zoneReads++
                deviceZone
            }
        val expected =
            ObservingLocation(
                latitude = 50.0,
                longitude = 14.0,
                source = ObservingLocation.Source.MANUAL,
                zoneId = deviceZone,
            )
        // Purity check: load() reads legacy coordinates without mutating SharedPreferences.
        assertEquals(expected, store.load())
        assertEquals(setOf("latitude", "longitude", "source"), preferences().all.keys)

        // Explicit migration: migrateAndRepair() persists the versioned record once.
        store.migrateAndRepair()
        assertEquals(expected, store.load())
        assertEquals(setOf("location"), preferences().all.keys)
        deviceZone = ZoneId.of("Asia/Tokyo")
        assertEquals(expected, store.load())
        assertEquals(expected, LocationStore(RuntimeEnvironment.getApplication()) { deviceZone }.load())
        assertEquals(2, zoneReads)
    }

    @Test
    fun legacyKeepsCoordinateBounds() {
        preferences()
            .edit()
            .putString("latitude", "-90.0")
            .putString("longitude", "180.0")
            .putString("source", "CURRENT_COARSE")
            .apply()
        val zone = ZoneId.of("UTC")
        val store = LocationStore(RuntimeEnvironment.getApplication()) { zone }
        val expected =
            ObservingLocation(
                latitude = -90.0,
                longitude = 180.0,
                source = ObservingLocation.Source.CURRENT_COARSE,
                zoneId = zone,
            )
        assertEquals(expected, store.load())
        assertEquals(setOf("latitude", "longitude", "source"), preferences().all.keys)
        store.migrateAndRepair()
        assertEquals(expected, store.load())
        assertEquals(setOf("location"), preferences().all.keys)
    }

    @Test
    fun malformedLegacyIsPreserved() {
        val store = LocationStore(RuntimeEnvironment.getApplication()) { error("must not read device zone") }
        val malformed =
            listOf(
                "latitude" to "not a number",
                "latitude" to "NaN",
                "latitude" to "91.0",
                "longitude" to "Infinity",
                "longitude" to "-181.0",
                "source" to "UNKNOWN",
            )
        for ((key, value) in malformed) {
            saveLegacy()
            preferences().edit().putString(key, value).apply()
            assertUntouched(store)
        }
        assertTrue(ShadowLog.getLogsForTag("LocationStore").all { it.msg.contains("malformed") })
    }

    @Test
    fun invalidLegacyFieldsPreserved() {
        val store = LocationStore(RuntimeEnvironment.getApplication()) { error("must not read device zone") }
        for (key in listOf("latitude", "longitude", "source")) {
            saveLegacy()
            preferences().edit().remove(key).apply()
            assertUntouched(store)
            saveLegacy()
            preferences().edit().putBoolean(key, true).apply()
            assertUntouched(store)
        }
    }

    @Test
    fun invalidZonesRepairedOnce() {
        val invalidZones = listOf(null, "", "No/Such_Zone", JSONObject.NULL, 42, false)
        for (invalidZone in invalidZones) {
            ShadowLog.clear()
            val record = JSONObject(VALID_RECORD).put("zoneId", invalidZone).put("retainedField", "keep")
            preferences().edit().putString("location", record.toString()).apply()
            var zoneReads = 0
            val store =
                LocationStore(RuntimeEnvironment.getApplication()) {
                    zoneReads++
                    ZoneId.of("Australia/Sydney")
                }
            val expected =
                ObservingLocation(
                    latitude = 50.0,
                    longitude = 14.0,
                    source = ObservingLocation.Source.MANUAL,
                    zoneId = ZoneId.of("Australia/Sydney"),
                )
            // Purity check: load() uses fallback in-memory without persisting or logging repair.
            assertEquals(expected, store.load())
            assertEquals(1, zoneReads)
            assertTrue(ShadowLog.getLogsForTag("LocationStore").isEmpty())
            val rawBeforeRepair = preferences().getString("location", null)
            val jsonBeforeRepair = JSONObject(requireNotNull(rawBeforeRepair))
            assertEquals(invalidZone?.toString().orEmpty(), jsonBeforeRepair.optString("zoneId"))

            // Explicit repair: migrateAndRepair() updates SharedPreferences once and logs the repair.
            store.migrateAndRepair()
            assertEquals(expected, store.load())
            assertEquals(2, zoneReads)
            val repaired = JSONObject(requireNotNull(preferences().getString("location", null)))
            assertEquals("Australia/Sydney", repaired.getString("zoneId"))
            assertEquals("keep", repaired.getString("retainedField"))
            assertEquals(1, ShadowLog.getLogsForTag("LocationStore").size)
            assertTrue(ShadowLog.getLogsForTag("LocationStore").all { it.msg.contains("repaired") })

            // Subsequent load() and migrateAndRepair() do not re-read device zone or re-repair.
            assertEquals(expected, store.load())
            store.migrateAndRepair()
            assertEquals(expected, store.load())
            assertEquals(2, zoneReads)
        }
    }

    @Test
    fun currentRecordOverridesLegacy() {
        saveLegacy()
        val record = JSONObject(VALID_RECORD).put("latitude", -30.0).put("zoneId", "Pacific/Auckland")
        preferences().edit().putString("location", record.toString()).apply()
        val before = preferences().all
        val store = LocationStore(RuntimeEnvironment.getApplication()) { error("must not read device zone") }
        assertNotNull(store.load())
        assertEquals(-30.0, requireNotNull(store.load()).latitude, 0.0)
        assertEquals(ZoneId.of("Pacific/Auckland"), requireNotNull(store.load()).zoneId)
        assertEquals(before, preferences().all)
    }

    private fun saveLegacy() {
        preferences()
            .edit()
            .clear()
            .putString("latitude", "50.0")
            .putString("longitude", "14.0")
            .putString("source", "MANUAL")
            .apply()
    }

    private fun assertUntouched(store: LocationStore) {
        val before = preferences().all
        assertNull(store.load())
        assertEquals(before, preferences().all)
        store.migrateAndRepair()
        assertEquals(before, preferences().all)
    }

    private fun preferences(): SharedPreferences =
        RuntimeEnvironment.getApplication().getSharedPreferences("observing_location", Context.MODE_PRIVATE)

    private companion object {
        const val VALID_RECORD = """{"version":1,"latitude":50.0,"longitude":14.0,"source":"MANUAL"}"""
    }
}
