package io.github.godaniya.astronomicalclockswallpaper

import android.content.Context
import android.content.SharedPreferences
import android.util.Log

/** Persists the appearance theme choice separately from observing location and layer visibility. */
internal class AppearanceStore(context: Context) {
    private val preferences = context.getSharedPreferences("appearance_settings", Context.MODE_PRIVATE)

    fun load(): DialAppearance {
        val snapshot = preferences.all
        val raw = snapshot[KEY_APPEARANCE]
        if (raw != null && raw !is String) {
            Log.w("AppearanceStore", "ignoring malformed appearance setting $raw; using system default")
            return DialAppearance.SYSTEM
        }
        return DialAppearance.fromString(raw)
    }

    fun save(appearance: DialAppearance) {
        preferences
            .edit()
            .putString(KEY_APPEARANCE, appearance.name)
            .apply()
    }

    fun registerListener(listener: SharedPreferences.OnSharedPreferenceChangeListener) {
        preferences.registerOnSharedPreferenceChangeListener(listener)
    }

    fun unregisterListener(listener: SharedPreferences.OnSharedPreferenceChangeListener) {
        preferences.unregisterOnSharedPreferenceChangeListener(listener)
    }

    companion object {
        const val KEY_APPEARANCE = "appearance"
    }
}
