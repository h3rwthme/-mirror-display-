package com.extenddisplay.client

import java.net.InetSocketAddress
import java.net.Socket

enum class ConnectionMode(val handshakeByte: Int) {
    /**
     * Mode Kabel USB:
     * - Via `adb reverse tcp:PORT tcp:PORT` -> Host = "127.0.0.1"
     * - Via USB Tethering (RNDIS) -> Host = IP PC pada interface RNDIS (mis. 192.168.42.x)
     */
    USB_CABLE(handshakeByte = 1),

    /**
     * Mode Jarak Jauh (VPN / Tailscale / ZeroTier):
     * - Host = IP Tailscale PC (mis. 100.x.y.z)
     */
    REMOTE_VPN(handshakeByte = 2)
}

data class EndpointConfig(
    val host: String,
    val mode: ConnectionMode,
    val displayPort: Int = 5001,
    val controlPort: Int = 5002,
    val audioPort: Int = 5003
) {
    val receiveBufferBytes: Int
        get() = when (mode) {
            ConnectionMode.USB_CABLE -> 64 * 1024    // 64 KB minimal buffer (Zero-Lag)
            ConnectionMode.REMOTE_VPN -> 256 * 1024  // 256 KB dynamic buffer untuk menyerap jitter VPN
        }

    /**
     * Batas usia frame maksimum sebelum di-drop di sisi client (Frame-Dropping).
     */
    val maxFrameLagMs: Long
        get() = when (mode) {
            ConnectionMode.USB_CABLE -> 40L
            ConnectionMode.REMOTE_VPN -> 140L
        }
}

object LowLatencySocketFactory {
    /**
     * Membuka koneksi TCP yang dioptimalkan dengan TCP_NODELAY (Disable Nagle's Algorithm)
     * dan pengaturan buffer OS sesuai mode koneksi.
     */
    fun connect(
        host: String,
        port: Int,
        rcvBufBytes: Int,
        sendHandshakeByte: Int? = null,
        connectTimeoutMs: Int = 4000
    ): Socket {
        val socket = Socket()
        // WAJIB: Disable Nagle's Algorithm
        socket.tcpNoDelay = true
        socket.keepAlive = true
        // Prioritaskan paket interaktif / low-delay pada header IP ToS (IPTOS_LOWDELAY | IPTOS_THROUGHPUT)
        socket.trafficClass = 0x10 or 0x08
        socket.receiveBufferSize = rcvBufBytes
        socket.sendBufferSize = 64 * 1024

        socket.connect(InetSocketAddress(host, port), connectTimeoutMs)

        if (sendHandshakeByte != null) {
            socket.getOutputStream().apply {
                write(byteArrayOf(sendHandshakeByte.toByte()))
                flush()
            }
        }
        return socket
    }
}
