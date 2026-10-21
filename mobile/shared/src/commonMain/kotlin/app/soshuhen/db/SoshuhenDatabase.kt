package app.soshuhen.db

import androidx.room.AutoMigration
import androidx.room.ConstructedBy
import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.RoomDatabaseConstructor

@Database(
    entities = [
        SnapshotEntity::class,
        MarkedEntity::class,
        DeviceChapterEntity::class,
        OutboxEntity::class,
        ImportLogEntity::class,
        ProblemEntity::class,
        ImportPartEntity::class,
    ],
    version = 2,
    autoMigrations = [AutoMigration(from = 1, to = 2)],
)
@ConstructedBy(SoshuhenDatabaseConstructor::class)
abstract class SoshuhenDatabase : RoomDatabase() {
    abstract fun snapshots(): SnapshotDao
    abstract fun marked(): MarkedDao
    abstract fun deviceChapters(): DeviceChapterDao
    abstract fun outbox(): OutboxDao
    abstract fun importLog(): ImportLogDao
    abstract fun problems(): ProblemDao
    abstract fun importParts(): ImportPartDao
}

// Room generates the actual for each target; the compiler needs this to exist.
@Suppress("KotlinNoActualForExpect", "NO_ACTUAL_FOR_EXPECT")
expect object SoshuhenDatabaseConstructor : RoomDatabaseConstructor<SoshuhenDatabase> {
    override fun initialize(): SoshuhenDatabase
}
