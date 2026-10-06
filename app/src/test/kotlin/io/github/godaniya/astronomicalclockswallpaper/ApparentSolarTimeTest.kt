package io.github.godaniya.astronomicalclockswallpaper

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.time.ZoneId
import kotlin.math.atan2

/**
 * Validates the relationship between the zoned civil hand and local apparent solar time (#57).
 *
 * Checks:
 * 1. At independent local apparent noon instants, the Sun marker's bearing is XII (0.0°) within
 *    astronomical tolerances, while the civil hand reflects the site's civil time and documented offset.
 * 2. Northern and southern sites, under both DST and non-DST conditions, are verified.
 * 3. Dial shading (day, twilight, night regions) and zodiac sidereal rotation are strictly zone-independent.
 */
class ApparentSolarTimeTest {
    private val calculator = AstronomyEngineCalculator()

    @Test
    fun apparentNoonSunBearingAtXii() {
        for (fixture in apparentSolarTimeFixtures) {
            assertDstMatchesZoneRules(fixture)
            val location =
                ObservingLocation(
                    latitude = fixture.latitudeDeg,
                    longitude = fixture.longitudeDeg,
                    source = ObservingLocation.Source.MANUAL,
                    zoneId = fixture.zoneId,
                )
            val geometry = calculator.dialGeometry(fixture.instant, location)
            val projection = OrlojProjection(geometry)
            val sunPoint = projection.sunPoint
            assertNotNull("Sun marker must be present in geometry for ${fixture.siteName}", sunPoint)

            // Bearing measured clockwise from negative y-axis (XII / top vertical axis)
            val sunBearingDeg =
                Math.toDegrees(atan2(y = sunPoint!!.x, x = -sunPoint.y)).mod(FULL_TURN_DEGREES)
            val deviationFromXii =
                if (sunBearingDeg > HALF_TURN_DEGREES) {
                    FULL_TURN_DEGREES - sunBearingDeg
                } else {
                    sunBearingDeg
                }
            assertTrue(
                "Sun bearing at local apparent noon must point to XII (0.0°) within tolerance for ${fixture.siteName}",
                deviationFromXii < SOLAR_NOON_TOLERANCE_DEG,
            )

            // Verify civil time and hand angle
            val localTime = fixture.instant.atZone(location.zoneId).toLocalTime()
            assertEquals("Civil time must match fixture for ${fixture.siteName}", fixture.expectedCivilTime, localTime)

            val handAngle = clockState(localTime).hourAngle.toDouble()
            assertEquals(
                "Civil hand angle must match expected angle for ${fixture.siteName}",
                fixture.expectedHandAngleDeg,
                handAngle,
                CIVIL_HAND_TOLERANCE_DEG,
            )

            // Angular offset between civil hand and Sun marker
            val angularOffset = (handAngle - sunBearingDeg).mod(FULL_TURN_DEGREES)
            val utcOffsetHours =
                location.zoneId.rules
                    .getOffset(fixture.instant)
                    .totalSeconds /
                    SECONDS_PER_HOUR
            val longitudeOffsetHours = fixture.longitudeDeg / DEGREES_PER_HOUR
            val equationOfTimeHours = fixture.expectedEquationOfTimeMinutes / MINUTES_PER_HOUR
            val expectedOffset = (utcOffsetHours - longitudeOffsetHours - equationOfTimeHours) * DEGREES_PER_HOUR
            val offsetDifference = (angularOffset - expectedOffset).mod(FULL_TURN_DEGREES)
            val offsetDeviation =
                if (offsetDifference > HALF_TURN_DEGREES) {
                    FULL_TURN_DEGREES - offsetDifference
                } else {
                    offsetDifference
                }
            assertTrue(
                "Civil hand to Sun marker offset must match documented offset for ${fixture.siteName}",
                offsetDeviation < SOLAR_NOON_TOLERANCE_DEG,
            )
        }
    }

    @Test
    fun shadingAndZodiacIgnoreZone() {
        // Varying the civil timezone for an observing site alters the civil hand angle
        // while leaving plate shading (day, twilight, night contours) and the zodiac ring's
        // sidereal orientation completely identical.
        val instant = Instant.parse("2026-06-21T11:04:07Z")
        val latitude = 50.0875
        val longitude = 14.4214
        val zones =
            listOf(
                ZoneId.of("Europe/Prague"),
                ZoneId.of("UTC"),
                ZoneId.of("America/New_York"),
                ZoneId.of("Asia/Tokyo"),
                ZoneId.of("Pacific/Honolulu"),
            )
        val geometries =
            zones.map { zone ->
                val location =
                    ObservingLocation(
                        latitude = latitude,
                        longitude = longitude,
                        source = ObservingLocation.Source.MANUAL,
                        zoneId = zone,
                    )
                calculator.dialGeometry(instant, location)
            }
        val projections = geometries.map { OrlojProjection(it) }

        val firstGeo = geometries.first()
        for (geo in geometries.drop(1)) {
            assertEquals(firstGeo.localSiderealAngleDeg, geo.localSiderealAngleDeg, 0.0)
            assertEquals(firstGeo.trueObliquityDeg, geo.trueObliquityDeg, 0.0)
            assertEquals(firstGeo.sunLongitudeDeg, geo.sunLongitudeDeg)
            assertEquals(firstGeo.moonLongitudeDeg, geo.moonLongitudeDeg)
            assertEquals(firstGeo.moonPhaseLongitudeDeg, geo.moonPhaseLongitudeDeg)
        }

        val firstProj = projections.first()
        for (proj in projections.drop(1)) {
            assertEquals(firstProj.altitudeRegion(0.0), proj.altitudeRegion(0.0))
            assertEquals(firstProj.altitudeRegion(-18.0), proj.altitudeRegion(-18.0))
            assertEquals(firstProj.zodiacCircle, proj.zodiacCircle)
            assertEquals(firstProj.sunPoint, proj.sunPoint)
        }

        // Civil hand angles must differ according to each timezone
        val handAngles = mutableSetOf<Float>()
        for (zone in zones) {
            val time = instant.atZone(zone).toLocalTime()
            handAngles.add(clockState(time).hourAngle)
        }
        assertEquals(
            "Distinct timezones must yield distinct civil hand angles",
            zones.size,
            handAngles.size,
        )
    }

    private fun assertDstMatchesZoneRules(fixture: ApparentSolarTimeFixture) {
        assertEquals(
            "DST flag must match the zone rules for ${fixture.siteName}",
            fixture.isDst,
            fixture.zoneId.rules.isDaylightSavings(fixture.instant),
        )
    }

    private companion object {
        const val FULL_TURN_DEGREES = 360.0
        const val HALF_TURN_DEGREES = 180.0
        const val DEGREES_PER_HOUR = 15.0
        const val SECONDS_PER_HOUR = 3600.0
        const val MINUTES_PER_HOUR = 60.0

        // Allows ephemeris/frame differences at independently sourced JPL Horizons solar transits.
        const val SOLAR_NOON_TOLERANCE_DEG = 0.02

        // Civil hand angle precision from LocalTime seconds
        const val CIVIL_HAND_TOLERANCE_DEG = 0.005
    }
}
