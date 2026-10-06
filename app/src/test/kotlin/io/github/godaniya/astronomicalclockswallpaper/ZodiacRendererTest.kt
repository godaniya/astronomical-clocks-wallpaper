package io.github.godaniya.astronomicalclockswallpaper

import android.graphics.Bitmap
import android.graphics.Canvas
import android.util.Log
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.shadows.ShadowLog

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 36])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ZodiacRendererTest {
    private val prague = DialGeometry(localSiderealAngleDeg = 0.0, trueObliquityDeg = 23.44, latitudeDeg = 50.08)
    private val renderer = ZodiacRenderer()

    @Test
    fun normalDrawProducesNoWarnings() {
        val bitmap = Bitmap.createBitmap(800, 800, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val projection = OrlojProjection(prague)

        ShadowLog.clear()
        renderer.draw(canvas, projection)
        val logs = ShadowLog.getLogsForTag("ZodiacRenderer")
        assertTrue("Normal render must not emit logs, but was: $logs", logs.isEmpty())
    }

    @Test
    fun degenerateCoordinatesBounded() {
        val bitmap = Bitmap.createBitmap(800, 800, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val degenerateProjection =
            object : OrlojProjection(prague) {
                override fun eclipticPoint(longitudeDeg: Double): DialPoint =
                    if (longitudeDeg == 0.0) DialPoint(x = 0.0, y = 0.0) else super.eclipticPoint(longitudeDeg)
            }
        val normalProjection = OrlojProjection(prague)

        ShadowLog.clear()
        repeat(3) { renderer.draw(canvas, degenerateProjection) }
        val warnings = ShadowLog.getLogsForTag("ZodiacRenderer").filter { it.type == Log.WARN }
        assertEquals(1, warnings.size)
        assertTrue(warnings[0].msg.contains("skipping divider: degenerate coordinate"))
        assertTrue(warnings[0].msg.contains("sign 0: distance=0.0"))

        // One completed healthy frame ends the episode and logs recovery.
        renderer.draw(canvas, normalProjection)
        val recoveries = ShadowLog.getLogsForTag("ZodiacRenderer").filter { it.type == Log.INFO }
        assertEquals(1, recoveries.size)
        assertTrue(recoveries[0].msg.contains("recovered after 3 consecutive failures"))

        // A subsequent degenerate frame logs again as a new episode.
        renderer.draw(canvas, degenerateProjection)
        val subsequentWarnings = ShadowLog.getLogsForTag("ZodiacRenderer").filter { it.type == Log.WARN }
        assertEquals(2, subsequentWarnings.size)
    }

    @Test
    fun nonFiniteEndpointsBounded() {
        val bitmap = Bitmap.createBitmap(800, 800, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val nonFiniteCircleProjection =
            object : OrlojProjection(prague) {
                override val zodiacCircle: DialCircle
                    get() = DialCircle(center = DialPoint(x = Double.NaN, y = 0.0), radius = 1.0)
            }
        val normalProjection = OrlojProjection(prague)

        ShadowLog.clear()
        repeat(3) { renderer.draw(canvas, nonFiniteCircleProjection) }
        val endpointWarnings = ShadowLog.getLogsForTag("ZodiacRenderer").filter { it.type == Log.WARN }
        assertEquals(1, endpointWarnings.size)
        assertTrue(endpointWarnings[0].msg.contains("skipping divider: non-finite endpoint"))

        // Recovery check after healthy frame
        renderer.draw(canvas, normalProjection)
        val recoveries = ShadowLog.getLogsForTag("ZodiacRenderer").filter { it.type == Log.INFO }
        assertEquals(1, recoveries.size)
        assertTrue(recoveries[0].msg.contains("recovered after 3 consecutive failures"))
    }
}
