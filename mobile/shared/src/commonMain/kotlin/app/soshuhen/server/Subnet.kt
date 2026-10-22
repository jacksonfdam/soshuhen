package app.soshuhen.server

/**
 * Every host a scan should probe: the device's subnet minus the network and
 * broadcast addresses and the device itself.
 *
 * A prefix wider than /24 is narrowed to the /24 the device is in. Home
 * routers hand out /24s; a /16 would be sixty-five thousand probes for a
 * server that is almost certainly next door.
 */
fun subnetHosts(address: String, prefixLength: Int): List<String> {
    val parts = address.split('.').map { it.toInt() }
    val own = parts.fold(0L) { acc, part -> (acc shl 8) or part.toLong() }
    val prefix = prefixLength.coerceIn(24, 30)
    val mask = (0xFFFFFFFFL shl (32 - prefix)) and 0xFFFFFFFFL
    val network = own and mask
    val broadcast = network or (mask.inv() and 0xFFFFFFFFL)
    return ((network + 1) until broadcast)
        .filter { it != own }
        .map { ip -> (3 downTo 0).joinToString(".") { ((ip shr (it * 8)) and 0xFF).toString() } }
}
