package io.github.godaniya.astronomicalclockswallpaper

import android.graphics.Bitmap
import android.graphics.Canvas
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.time.Instant
import java.time.LocalTime
import java.time.ZoneOffset

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 36])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class WallpaperTabletRenderTest {
    @Test
    fun renderLayersAcrossSurfaces() {
        val renderer = DialRenderer()
        val calculator = AstronomyEngineCalculator()
        val instant = Instant.parse("2026-06-21T12:00:00Z")
        val geometry = calculator.dialGeometry(time = instant, location = PRAGUE_LOCATION)
        val state = clockState(LocalTime.of(12, 0))
        val allLayers = DialLayers(isZodiacRingEnabled = true, isSunEnabled = true, isMoonEnabled = true)
        val noLayers = DialLayers(isZodiacRingEnabled = false, isSunEnabled = false, isMoonEnabled = false)

        for (surface in TabletSurfaces.ALL) {
            val viewport = DialViewport.full(width = surface.width, height = surface.height)
            val style =
                DialRenderStyle(
                    palette = DialStyle.DARK_PALETTE,
                    display = DialDisplaySettings(),
                    viewport = viewport,
                )

            val allOnBitmap = Bitmap.createBitmap(surface.width, surface.height, Bitmap.Config.ARGB_8888)
            renderer.renderDisplay(
                canvas = Canvas(allOnBitmap),
                state = state,
                geometry = geometry,
                layers = allLayers,
                style = style,
            )

            val allOffBitmap = Bitmap.createBitmap(surface.width, surface.height, Bitmap.Config.ARGB_8888)
            renderer.renderDisplay(
                canvas = Canvas(allOffBitmap),
                state = state,
                geometry = geometry,
                layers = noLayers,
                style = style,
            )

            try {
                assertFalse(
                    "Layers enabled vs disabled must produce different pixels on ${surface.name}",
                    allOnBitmap.sameAs(allOffBitmap),
                )
                assertZeroRimClipping(bitmap = allOnBitmap, surface = surface)
            } finally {
                allOnBitmap.recycle()
                allOffBitmap.recycle()
            }
        }
    }

    private fun assertZeroRimClipping(bitmap: Bitmap, surface: TabletSurface) {
        val bg = DialStyle.DARK_PALETTE.background
        // Corners must always remain unpainted background
        assertEquals(bg, bitmap.getPixel(0, 0))
        assertEquals(bg, bitmap.getPixel(surface.width - 1, 0))
        assertEquals(bg, bitmap.getPixel(0, surface.height - 1))
        assertEquals(bg, bitmap.getPixel(surface.width - 1, surface.height - 1))

        // On widescreen (landscape), left/right outer edges are letterbox margins and must be background
        if (surface.width > surface.height) {
            assertEquals("Left margin must be background", bg, bitmap.getPixel(0, surface.height / 2))
            assertEquals(
                "Right margin must be background",
                bg,
                bitmap.getPixel(surface.width - 1, surface.height / 2),
            )
        }
        // On tall screen (portrait), top/bottom outer edges are pillarbox margins and must be background
        if (surface.height > surface.width) {
            assertEquals("Top margin must be background", bg, bitmap.getPixel(surface.width / 2, 0))
            assertEquals(
                "Bottom margin must be background",
                bg,
                bitmap.getPixel(surface.width / 2, surface.height - 1),
            )
        }
    }

    private companion object {
        val PRAGUE_LOCATION =
            ObservingLocation(
                latitude = 50.0875,
                longitude = 14.4213,
                zoneId = ZoneOffset.ofHours(1),
                source = ObservingLocation.Source.MANUAL,
            )
    }
}
