package app.soshuhen.db

import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

/** The one current import problem. A second row would be a second banner. */
@Entity(tableName = "problem")
data class ProblemEntity(
    @PrimaryKey val id: Int = 1,
    val message: String,
    val at: Long,
)

@Dao
interface ProblemDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE) suspend fun put(problem: ProblemEntity)

    @Query("DELETE FROM problem")
    suspend fun clear()

    @Query("SELECT message FROM problem WHERE id = 1")
    fun message(): Flow<String?>
}
