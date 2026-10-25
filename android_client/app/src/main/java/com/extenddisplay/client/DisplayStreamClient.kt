package com.extenddisplay.client

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.BufferedInputStream
import java.io.DataInputStream

class DisplayStreamClient(
    private val config: EndpointConfig,
    private val onFrameDecoded: (Bitmap, Long) -> Unit,
    private val onStatusChanged: (String) -> Unit
) {
    private var readerJob: Job? = null
    private var decoderJob: Job? = null

    // Conflated Channel: selalu menyimpan HANYA 1 frame paling mutakhir (Zero Queue Lag)
    private val latestPayloadChannel = Channel<FramePacket>(Channel.CONFLATED)

    private data class FramePacket(
        val frameId: Long,
        val timestampMs: Long,
        val jpegBytes: ByteArray
    )

    fun start(scope: CoroutineScope) {
        stop()

        // Coroutine 1: Pembaca Socket Jaringan Kecepatan Tinggi
        readerJob = scope.launch(Dispatchers.IO) {
            try {
                onStatusChanged("Menghubungkan Socket 1 (Display) ke ${config.host}:${config.displayPort}...")
                LowLatencySocketFactory.connect(
                    host = config.host,
                    port = config.displayPort,
                    rcvBufBytes = config.receiveBufferBytes,
                    sendHandshakeByte = config.mode.handshakeByte
                ).use { socket ->
                    onStatusChanged("Display Terhubung (${config.mode.name})")
                    val dataIn = DataInputStream(
                        BufferedInputStream(socket.getInputStream(), config.receiveBufferBytes)
                    )

                    val magicBuf = ByteArray(2)
                    var clockOffsetMs: Long? = null

                    while (isActive) {
                        // 1. Baca Header 19-Byte (>2sIQBI)
                        dataIn.readFully(magicBuf)
                        if (magicBuf[0] != 'D'.code.toByte() || magicBuf[1] != 'S'.code.toByte()) {
                            Log.w("DisplayStream", "Sinkronisasi header hilang, menutup stream.")
                            break
                        }

                        val frameId = dataIn.readInt().toLong() and 0xFFFFFFFFL
                        val serverTsMs = dataIn.readLong()
                        val flags = dataIn.readUnsignedByte()
                        val payloadLen = dataIn.readInt()

                        if (payloadLen <= 0 || payloadLen > 15 * 1024 * 1024) {
                            break
                        }

                        val payload = ByteArray(payloadLen)
                        dataIn.readFully(payload)

                        val nowMs = System.currentTimeMillis()
                        if (clockOffsetMs == null) {
                            clockOffsetMs = nowMs - serverTsMs
                        } else {
                            // Kalibrasi offset jam secara perlahan untuk estimasi one-way delay
                            val sampleOffset = nowMs - serverTsMs
                            if (sampleOffset < clockOffsetMs) {
                                clockOffsetMs = sampleOffset
                            }
                        }

                        val estimatedLagMs = (nowMs - serverTsMs) - clockOffsetMs

                        // 2. Dynamic Frame-Dropping pada Mode Jarak Jauh (VPN):
                        // Jika ada tumpukan data baru di buffer socket dan frame ini sudah basi, buang sebelum decode!
                        if (config.mode == ConnectionMode.REMOTE_VPN &&
                            estimatedLagMs > config.maxFrameLagMs &&
                            dataIn.available() > 19
                        ) {
                            continue
                        }

                        // Kirim ke Conflated Channel (otomatis menimpa frame lama jika decoder masih sibuk)
                        latestPayloadChannel.trySend(FramePacket(frameId, estimatedLagMs, payload))
                    }
                }
            } catch (e: Exception) {
                Log.e("DisplayStream", "Error pada Socket 1: ${e.message}")
                onStatusChanged("Display Terputus: ${e.message}")
            }
        }

        // Coroutine 2: Decoder Bitmap Hardware-Accelerated
        decoderJob = scope.launch(Dispatchers.Default) {
            val bitmapOptions = BitmapFactory.Options().apply {
                inPreferredConfig = Bitmap.Config.RGB_565 // Hemat 50% memori & bandwidth GPU
                inMutable = true
            }

            for (packet in latestPayloadChannel) {
                if (!isActive) break
                val bmp = BitmapFactory.decodeByteArray(
                    packet.jpegBytes,
                    0,
                    packet.jpegBytes.size,
                    bitmapOptions
                )
                if (bmp != null) {
                    withContext(Dispatchers.Main) {
                        onFrameDecoded(bmp, packet.timestampMs)
                    }
                }
            }
        }
    }

    fun stop() {
        readerJob?.cancel()
        decoderJob?.cancel()
    }
}
