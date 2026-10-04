package io.github.godaniya.astronomicalclockswallpaper

import android.content.Context
import android.widget.RadioButton
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 36])
class SettingsActivityAppearanceTest {
    private val application = RuntimeEnvironment.getApplication()

    @Before
    fun setUp() {
        application
            .getSharedPreferences("appearance_settings", Context.MODE_PRIVATE)
            .edit()
            .clear()
            .apply()
    }

    @Test
    fun defaultSelectionIsSystem() {
        val controller = Robolectric.buildActivity(SettingsActivity::class.java).setup()
        val activity = controller.get()
        val systemRadio = activity.findViewById<RadioButton>(R.id.appearance_system)
        assertTrue(systemRadio.isChecked)
    }

    @Test
    fun selectingLightPersistsChoice() {
        val controller = Robolectric.buildActivity(SettingsActivity::class.java).setup()
        val activity = controller.get()
        val lightRadio = activity.findViewById<RadioButton>(R.id.appearance_light)
        lightRadio.performClick()

        val store = AppearanceStore(application)
        assertEquals(DialAppearance.LIGHT, store.load())
    }

    @Test
    fun selectingDarkPersistsChoice() {
        val controller = Robolectric.buildActivity(SettingsActivity::class.java).setup()
        val activity = controller.get()
        val darkRadio = activity.findViewById<RadioButton>(R.id.appearance_dark)
        darkRadio.performClick()

        val store = AppearanceStore(application)
        assertEquals(DialAppearance.DARK, store.load())
    }

    @Test
    fun savedChoiceSurvivesRecreate() {
        val store = AppearanceStore(application)
        store.save(DialAppearance.DARK)

        val controller = Robolectric.buildActivity(SettingsActivity::class.java).setup()
        val darkRadio = controller.get().findViewById<RadioButton>(R.id.appearance_dark)
        assertTrue(darkRadio.isChecked)

        val recreated = controller.recreate().get()
        val recreatedDarkRadio = recreated.findViewById<RadioButton>(R.id.appearance_dark)
        assertTrue(recreatedDarkRadio.isChecked)
    }
}
