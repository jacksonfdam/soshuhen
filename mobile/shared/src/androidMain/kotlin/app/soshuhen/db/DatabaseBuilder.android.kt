package app.soshuhen.db

import android.content.Context
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.sqlite.driver.bundled.BundledSQLiteDriver
import kotlinx.coroutines.Dispatchers

// The name alone puts the file in app-private storage, never in the folder
// the user picked for chapters.
fun databaseBuilder(context: Context): RoomDatabase.Builder<SoshuhenDatabase> =
    Room.databaseBuilder<SoshuhenDatabase>(context.applicationContext, "soshuhen.db")
        .setDriver(BundledSQLiteDriver())
        .setQueryCoroutineContext(Dispatchers.IO)
