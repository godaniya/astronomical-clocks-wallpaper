package io.github.godaniya.astronomicalclockswallpaper

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.RectF
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 36])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class MoonRendererTest {
    private val renderer = MoonRenderer()

    @Test
    fun newMoonProducesNoPath() {
        assertNull("0° new moon must have null path", renderer.buildPhasePath(0.0))
        assertNull("360° new moon must have null path", renderer.buildPhasePath(360.0))
        assertNull("near new moon (0.1°) must have null path", renderer.buildPhasePath(0.1))
        assertNull("near new moon (359.9°) must have null path", renderer.buildPhasePath(359.9))
    }

    @Test
    fun fullMoonProducesFullDisc() {
        val full = renderer.buildPhasePath(180.0)
        assertNotNull("180° full moon must produce a path", full)
        val bounds = RectF()
        full?.computeBounds(bounds, true)
        assertEquals(-MoonRenderer.MOON_RADIUS, bounds.left, TOLERANCE)
        assertEquals(-MoonRenderer.MOON_RADIUS, bounds.top, TOLERANCE)
        assertEquals(MoonRenderer.MOON_RADIUS, bounds.right, TOLERANCE)
        assertEquals(MoonRenderer.MOON_RADIUS, bounds.bottom, TOLERANCE)
    }

    @Test
    fun firstQuarterIlluminatesRight() {
        val firstQuarter = renderer.buildPhasePath(90.0)
        assertNotNull("90° first quarter must produce a path", firstQuarter)
        val bounds = RectF()
        firstQuarter?.computeBounds(bounds, true)
        // Bounded strictly in the right hemisphere x >= 0
        assertEquals(0f, bounds.left, TOLERANCE)
        assertEquals(MoonRenderer.MOON_RADIUS, bounds.right, TOLERANCE)
        assertEquals(-MoonRenderer.MOON_RADIUS, bounds.top, TOLERANCE)
        assertEquals(MoonRenderer.MOON_RADIUS, bounds.bottom, TOLERANCE)
    }

    @Test
    fun lastQuarterIlluminatesLeft() {
        val lastQuarter = renderer.buildPhasePath(270.0)
        assertNotNull("270° last quarter must produce a path", lastQuarter)
        val bounds = RectF()
        lastQuarter?.computeBounds(bounds, true)
        // Bounded strictly in the left hemisphere x <= 0
        assertEquals(-MoonRenderer.MOON_RADIUS, bounds.left, TOLERANCE)
        assertEquals(0f, bounds.right, TOLERANCE)
        assertEquals(-MoonRenderer.MOON_RADIUS, bounds.top, TOLERANCE)
        assertEquals(MoonRenderer.MOON_RADIUS, bounds.bottom, TOLERANCE)
    }

    @Test
    fun intermediatePhasesStayInDisc() {
        val crescent = renderer.buildPhasePath(45.0)
        assertNotNull(crescent)
        val crescentBounds = RectF()
        crescent?.computeBounds(crescentBounds, true)
        val maxRadius = MoonRenderer.MOON_RADIUS + TOLERANCE
        assertTrue("crescent must be in right hemisphere", crescentBounds.left >= -TOLERANCE)
        assertTrue("crescent right must not exceed radius", crescentBounds.right <= maxRadius)

        val gibbous = renderer.buildPhasePath(135.0)
        assertNotNull(gibbous)
        val gibbousBounds = RectF()
        gibbous?.computeBounds(gibbousBounds, true)
        assertTrue("gibbous left must be negative", gibbousBounds.left < 0f)
        assertTrue("gibbous right must reach outer limb", gibbousBounds.right <= maxRadius)
    }

    @Test
    fun drawHandlesNullAndHemispheres() {
        val bitmap = Bitmap.createBitmap(100, 100, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)

        // Null moon point
        val nullGeometry = DialGeometry(localSiderealAngleDeg = 0.0, trueObliquityDeg = 23.44, latitudeDeg = 50.0)
        renderer.draw(canvas, OrlojProjection(nullGeometry))

        // Northern hemisphere
        val northGeometry =
            DialGeometry(
                localSiderealAngleDeg = 0.0,
                trueObliquityDeg = 23.44,
                latitudeDeg = 50.0,
                moonLongitudeDeg = 45.0,
                moonPhaseLongitudeDeg = 90.0,
            )
        renderer.draw(canvas, OrlojProjection(northGeometry))

        // Southern hemisphere
        val southGeometry =
            DialGeometry(
                localSiderealAngleDeg = 0.0,
                trueObliquityDeg = 23.44,
                latitudeDeg = -33.87,
                moonLongitudeDeg = 45.0,
                moonPhaseLongitudeDeg = 90.0,
            )
        renderer.draw(canvas, OrlojProjection(southGeometry))
    }

    private companion object {
        const val TOLERANCE = 0.001f
    }
}
