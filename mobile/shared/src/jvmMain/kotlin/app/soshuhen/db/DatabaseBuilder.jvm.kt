package app.soshuhen.db

import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.sqlite.driver.bundled.BundledSQLiteDriver
import kotlinx.coroutines.Dispatchers

// Tests only: nothing ships on this target, so the database never touches disk.
fun inMemoryDatabaseBuilder(): RoomDatabase.Builder<SoshuhenDatabase> =
    Room.inMemoryDatabaseBuilder<SoshuhenDatabase>()
        .setDriver(BundledSQLiteDriver())
        .setQueryCoroutineContext(Dispatchers.IO)
