package io.github.godaniya.astronomicalclockswallpaper

import android.content.pm.ApplicationInfo
import android.graphics.Canvas
import android.os.Looper
import android.service.wallpaper.WallpaperService
import android.view.SurfaceView
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowLog
import org.robolectric.shadows.ShadowLooper
import java.time.Clock
import java.time.Duration
import java.time.Instant
import java.time.LocalTime
import java.time.ZoneOffset

/**
 * Verifies dial rendering, proportional scaling, zero clipping, and dynamic surface
 * recreation for tablet and foldable aspect ratios and resolutions (#86).
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 36])
class WallpaperLayoutTabletTest {
    @Test
    @Config(qualifiers = "sw1600dp-w2560dp-h1600dp-land-mdpi")
    fun landscapeTabletDialFits() {
        assertDialFitsWithinDimensions(width = TABLET_LAND_WIDTH, height = TABLET_LAND_HEIGHT)
    }

    @Test
    @Config(qualifiers = "sw1600dp-w1600dp-h2560dp-port-mdpi")
    fun portraitTabletDialFits() {
        assertDialFitsWithinDimensions(width = TABLET_PORT_WIDTH, height = TABLET_PORT_HEIGHT)
    }

    @Test
    @Config(qualifiers = "sw1768dp-w2208dp-h1768dp-mdpi")
    fun foldableUnfoldedDialFits() {
        assertDialFitsWithinDimensions(width = FOLDABLE_UNFOLDED_WIDTH, height = FOLDABLE_UNFOLDED_HEIGHT)
    }

    @Test
    fun dynamicFoldTransition() {
        RuntimeEnvironment.setQualifiers("sw1080dp-w1080dp-h2400dp-port-mdpi")
        val controller = Robolectric.buildService(AstronomicalClocksWallpaperService::class.java).create()
        val service = controller.get()
        service.applicationInfo.flags = service.applicationInfo.flags or ApplicationInfo.FLAG_DEBUGGABLE

        LocationStore(service) { ZoneOffset.UTC }.save(PRAGUE_LOCATION)

        val holder =
            ReadyFrameHolder(
                delegate = SurfaceView(service).holder,
                width = maxOf(a = FOLDABLE_UNFOLDED_WIDTH, b = FOLDABLE_FOLDED_WIDTH),
                height = maxOf(a = FOLDABLE_UNFOLDED_HEIGHT, b = FOLDABLE_FOLDED_HEIGHT),
            )
        val looper = shadowOf(Looper.getMainLooper())
        var lastViewport: DialViewport? = null
        var lastGeometry: DialGeometry? = null
        var frameCount = 0

        val engine =
            service.createEngine(
                draw = { _, _, geometry, _, _, _, usable ->
                    frameCount++
                    lastViewport = usable
                    lastGeometry = geometry
                },
                holder = holder,
                clock = Clock.fixed(Instant.parse("2026-03-21T12:00:00Z"), ZoneOffset.UTC),
            )

        try {
            assertFoldedPhase(
                engine = engine,
                holder = holder,
                looper = looper,
                frameCount = { frameCount },
            )
            assertNotNull("Observing site geometry must be computed from saved site", lastGeometry)

            assertUnfoldedPhase(
                engine = engine,
                holder = holder,
                looper = looper,
                frameCount = { frameCount },
                viewport = { lastViewport },
            )
            assertNotNull("Observing site geometry must persist across surface resize", lastGeometry)

            assertFoldRecovery(
                engine = engine,
                holder = holder,
                looper = looper,
                frameCount = { frameCount },
                viewport = { lastViewport },
            )
        } finally {
            engine.onDestroy()
            holder.release()
            controller.destroy()
        }
    }

    private fun assertFoldedPhase(
        engine: WallpaperService.Engine,
        holder: ReadyFrameHolder,
        looper: ShadowLooper,
        frameCount: () -> Int,
    ) {
        engine.onSurfaceChanged(holder, 0, FOLDABLE_FOLDED_WIDTH, FOLDABLE_FOLDED_HEIGHT)
        engine.onVisibilityChanged(true)
        assertEquals(1, frameCount())
        assertTrue(looper.nextScheduledTaskTime > Duration.ZERO)
    }

    private fun assertUnfoldedPhase(
        engine: WallpaperService.Engine,
        holder: ReadyFrameHolder,
        looper: ShadowLooper,
        frameCount: () -> Int,
        viewport: () -> DialViewport?,
    ) {
        RuntimeEnvironment.setQualifiers("sw1768dp-w2208dp-h1768dp-mdpi")
        engine.onSurfaceChanged(holder, 0, FOLDABLE_UNFOLDED_WIDTH, FOLDABLE_UNFOLDED_HEIGHT)

        assertEquals(2, frameCount())
        assertTrue(looper.nextScheduledTaskTime > Duration.ZERO)

        val unfoldedViewport = requireNotNull(viewport())
        assertEquals(FOLDABLE_UNFOLDED_WIDTH.toFloat(), unfoldedViewport.right, TOLERANCE)
        assertEquals(FOLDABLE_UNFOLDED_HEIGHT.toFloat(), unfoldedViewport.bottom, TOLERANCE)
        val placement = requireNotNull(unfoldedViewport.resolve(DialDisplaySettings()))
        val expectedRadius = FOLDABLE_UNFOLDED_HEIGHT * DialViewport.RADIUS_FRACTION
        assertEquals(expectedRadius, placement.radius, TOLERANCE)
        assertEquals(FOLDABLE_UNFOLDED_WIDTH / 2f, placement.centerX, TOLERANCE)
        assertEquals(FOLDABLE_UNFOLDED_HEIGHT / 2f, placement.centerY, TOLERANCE)
    }

    private fun assertFoldRecovery(
        engine: WallpaperService.Engine,
        holder: ReadyFrameHolder,
        looper: ShadowLooper,
        frameCount: () -> Int,
        viewport: () -> DialViewport?,
    ) {
        RuntimeEnvironment.setQualifiers("sw1080dp-w1080dp-h2400dp-port-mdpi")
        engine.onSurfaceChanged(holder, 0, FOLDABLE_FOLDED_WIDTH, FOLDABLE_FOLDED_HEIGHT)
        assertEquals(3, frameCount())
        assertTrue(looper.nextScheduledTaskTime > Duration.ZERO)
        val recovered = requireNotNull(requireNotNull(viewport()).resolve(DialDisplaySettings()))
        val expectedRadius = FOLDABLE_FOLDED_WIDTH * DialViewport.RADIUS_FRACTION
        assertEquals(expectedRadius, recovered.radius, TOLERANCE)
    }

    @Test
    fun renderLayersAcrossRatios() {
        val renderer = DialRenderer()
        val calculator = AstronomyEngineCalculator()
        val instant = Instant.parse("2026-06-21T12:00:00Z")
        val geometry = calculator.dialGeometry(instant, PRAGUE_LOCATION)
        val state = clockState(LocalTime.of(12, 0))
        val allLayers = DialLayers(isZodiacRingEnabled = true, isSunEnabled = true, isMoonEnabled = true)

        listOf(
            TABLET_LAND_WIDTH to TABLET_LAND_HEIGHT,
            TABLET_PORT_WIDTH to TABLET_PORT_HEIGHT,
            FOLDABLE_UNFOLDED_WIDTH to FOLDABLE_UNFOLDED_HEIGHT,
            FOLDABLE_FOLDED_WIDTH to FOLDABLE_FOLDED_HEIGHT,
        ).forEach { (w, h) ->
            val canvas = Canvas()
            val viewport = DialViewport.full(width = w, height = h)
            renderer.renderDisplay(
                canvas = canvas,
                state = state,
                geometry = geometry,
                layers = allLayers,
                style =
                    DialRenderStyle(
                        palette = DialStyle.DARK_PALETTE,
                        display = DialDisplaySettings(),
                        viewport = viewport,
                    ),
            )
        }
    }

    private fun assertDialFitsWithinDimensions(width: Int, height: Int) {
        val controller = Robolectric.buildService(AstronomicalClocksWallpaperService::class.java).create()
        val service = controller.get()
        service.applicationInfo.flags = service.applicationInfo.flags or ApplicationInfo.FLAG_DEBUGGABLE

        val holder =
            ReadyFrameHolder(
                delegate = SurfaceView(service).holder,
                width = width,
                height = height,
            )
        var drawnViewport: DialViewport? = null
        val engine =
            service.createEngine(
                draw = { _, _, _, _, _, _, usable -> drawnViewport = usable },
                holder = holder,
                clock = Clock.fixed(Instant.parse("2026-03-21T12:00:00Z"), ZoneOffset.UTC),
            )

        try {
            engine.onSurfaceChanged(holder, 0, width, height)
            ShadowLog.clear()
            engine.onVisibilityChanged(true)

            val logs = ShadowLog.getLogsForTag("DialDisplay").map { it.msg }
            val fields = reportFields(logs.single { it.contains("DialLayout") })
            val cx = fields.getValue("cx").toFloat()
            val cy = fields.getValue("cy").toFloat()
            val radius = fields.getValue("radius").toFloat()

            assertCenterAndRadius(width = width, height = height, cx = cx, cy = cy, radius = radius)
            assertNoEdgeClipping(width = width, height = height, cx = cx, cy = cy, radius = radius)
            assertBalancedMargins(width = width, height = height, cx = cx, radius = radius)
            assertSliderExtremes(viewport = requireNotNull(drawnViewport), width = width, height = height)
        } finally {
            engine.onDestroy()
            holder.release()
            controller.destroy()
        }
    }

    private fun assertCenterAndRadius(width: Int, height: Int, cx: Float, cy: Float, radius: Float) {
        assertEquals(width / 2f, cx, TOLERANCE)
        assertEquals(height / 2f, cy, TOLERANCE)
        val expectedRadius = minOf(a = width, b = height) * DialViewport.RADIUS_FRACTION
        assertEquals(expectedRadius, radius, TOLERANCE)
    }

    private fun assertNoEdgeClipping(width: Int, height: Int, cx: Float, cy: Float, radius: Float) {
        val extent = radius * DialViewport.STROKED_EXTENT
        assertTrue("Left edge must not clip: cx=$cx extent=$extent", cx - extent >= -TOLERANCE)
        assertTrue("Top edge must not clip: cy=$cy extent=$extent", cy - extent >= -TOLERANCE)
        assertTrue("Right edge must not clip", cx + extent <= width + TOLERANCE)
        assertTrue("Bottom edge must not clip", cy + extent <= height + TOLERANCE)
    }

    private fun assertBalancedMargins(width: Int, height: Int, cx: Float, radius: Float) {
        val extent = radius * DialViewport.STROKED_EXTENT
        if (width > height) {
            val leftMargin = cx - extent
            val rightMargin = width - (cx + extent)
            assertEquals("Horizontal margins must be balanced", leftMargin, rightMargin, TOLERANCE)
        }
    }

    private fun assertSliderExtremes(viewport: DialViewport, width: Int, height: Int) {
        for (size in listOf(50, 100, 115)) {
            for (hSlider in listOf(0, 50, 100)) {
                for (vSlider in listOf(0, 50, 100)) {
                    val settings = DialDisplaySettings(size = size, horizontal = hSlider, vertical = vSlider)
                    val p = requireNotNull(viewport.resolve(settings))
                    val ext = p.radius * DialViewport.STROKED_EXTENT
                    assertTrue(p.centerX - ext >= -TOLERANCE)
                    assertTrue(p.centerY - ext >= -TOLERANCE)
                    assertTrue(p.centerX + ext <= width + TOLERANCE)
                    assertTrue(p.centerY + ext <= height + TOLERANCE)
                }
            }
        }
    }

    private companion object {
        const val TABLET_LAND_WIDTH = 2560
        const val TABLET_LAND_HEIGHT = 1600
        const val TABLET_PORT_WIDTH = 1600
        const val TABLET_PORT_HEIGHT = 2560
        const val FOLDABLE_UNFOLDED_WIDTH = 2208
        const val FOLDABLE_UNFOLDED_HEIGHT = 1768
        const val FOLDABLE_FOLDED_WIDTH = 1080
        const val FOLDABLE_FOLDED_HEIGHT = 2400
        const val TOLERANCE = 0.5f

        val PRAGUE_LOCATION =
            ObservingLocation(
                latitude = 50.0875,
                longitude = 14.4213,
                zoneId = ZoneOffset.ofHours(1),
                source = ObservingLocation.Source.MANUAL,
            )

        val FIELDS = Regex("""(\w+)=([^ ]+)""")

        fun reportFields(line: String): Map<String, String> {
            assertTrue("unexpected layout report: $line", line.contains("DialLayout token="))
            return FIELDS.findAll(line).associate { it.groupValues[1] to it.groupValues[2] }
        }
    }
}
