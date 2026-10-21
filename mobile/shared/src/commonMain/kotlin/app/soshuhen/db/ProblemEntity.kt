package app.soshuhen.db

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

/**
 * The one current import problem. A second row would be a second banner.
 * The plan asked for CHECK (id = 1), which Room cannot declare on an entity;
 * a primary key that is always [ONLY_ROW], written with REPLACE, gives the
 * same guarantee. It has no default so no caller can pick another id.
 */
@Entity(tableName = "problem")
data class ProblemEntity(
    @PrimaryKey val id: Int,
    val message: String,
    val at: Long,
) {
    companion object {
        const val ONLY_ROW = 1
    }
}

@Dao
interface ProblemDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun put(problem: ProblemEntity)

    @Query("DELETE FROM problem")
    suspend fun clear()

    @Query("SELECT message FROM problem WHERE id = ${ProblemEntity.ONLY_ROW}")
    fun message(): Flow<String?>
}
