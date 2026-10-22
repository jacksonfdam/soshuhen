package app.soshuhen.core

/**
 * What a worker needs from the application. A worker is built by WorkManager,
 * not by us, so it reaches the graph through the one object that outlives it.
 */
interface ImportEnvironment {
    val graph: AppGraph
    val notifier: Notifier
}
