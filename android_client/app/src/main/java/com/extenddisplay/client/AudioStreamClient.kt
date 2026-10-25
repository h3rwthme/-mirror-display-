package com.extenddisplay.client

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.BufferedInputStream
import java.io.DataInputStream

class AudioStreamClient(
    private val config: EndpointConfig
) {
    private var audioJob: Job? = null

    fun start(scope: CoroutineScope) {
        stop()

        audioJob = scope.launch(Dispatchers.IO) {
            var audioTrack: AudioTrack? = null
            try {
                LowLatencySocketFactory.connect(
                    host = config.host,
                    port = config.audioPort,
                    rcvBufBytes = config.receiveBufferBytes,
                    sendHandshakeByte = config.mode.handshakeByte
                ).use { socket ->
                    val dataIn = DataInputStream(
                        BufferedInputStream(socket.getInputStream(), config.receiveBufferBytes)
                    )

                    // 1. Baca 8-byte Handshake Konfigurasi Audio (>IHH) dari WASAPI Loopback PC
                    val sampleRate = dataIn.readInt()
                    val channels = dataIn.readUnsignedShort()
                    val bitsPerSample = dataIn.readUnsignedShort()

                    val channelConfig = if (channels == 1) {
                        AudioFormat.CHANNEL_OUT_MONO
                    } else {
                        AudioFormat.CHANNEL_OUT_STEREO
                    }

                    val minBufSize = AudioTrack.getMinBufferSize(
                        sampleRate,
                        channelConfig,
                        AudioFormat.ENCODING_PCM_16BIT
                    ).coerceAtLeast(4096)

                    // Buffer Adaptif:
                    // - Mode Kabel USB: 1x minBufferSize + PERFORMANCE_MODE_LOW_LATENCY
                    // - Mode Jarak Jauh (VPN): 3x minBufferSize untuk meredam jitter seluler
                    val bufferMultiplier = if (config.mode == ConnectionMode.USB_CABLE) 1 else 3
                    val perfMode = if (config.mode == ConnectionMode.USB_CABLE) {
                        AudioTrack.PERFORMANCE_MODE_LOW_LATENCY
                    } else {
                        AudioTrack.PERFORMANCE_MODE_NONE
                    }

                    audioTrack = AudioTrack.Builder()
                        .setAudioAttributes(
                            AudioAttributes.Builder()
                                .setUsage(AudioAttributes.USAGE_MEDIA)
                                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                                .build()
                        )
                        .setAudioFormat(
                            AudioFormat.Builder()
                                .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                                .setSampleRate(sampleRate)
                                .setChannelMask(channelConfig)
                                .build()
                        )
                        .setBufferSizeInBytes(minBufSize * bufferMultiplier)
                        .setTransferMode(AudioTrack.MODE_STREAM)
                        .setPerformanceMode(perfMode)
                        .build()

                    audioTrack.play()
                    Log.i(
                        "AudioStream",
                        "AudioTrack dimulai: ${sampleRate}Hz, ${channels}ch, ${bitsPerSample}-bit (${config.mode.name})"
                    )

                    // 2. Loop Penerimaan Paket Audio (Header 16-Byte >IQI + PCM Bytes)
                    while (isActive) {
                        val seqNum = dataIn.readInt().toLong() and 0xFFFFFFFFL
                        val timestampMs = dataIn.readLong()
                        val payloadLen = dataIn.readInt()

                        if (payloadLen <= 0 || payloadLen > 256 * 1024) break

                        val pcmBytes = ByteArray(payloadLen)
                        dataIn.readFully(pcmBytes)

                        // Tulis langsung ke AudioTrack dalam mode NON_BLOCKING pada USB agar bebas lag
                        val writeMode = if (config.mode == ConnectionMode.USB_CABLE) {
                            AudioTrack.WRITE_NON_BLOCKING
                        } else {
                            AudioTrack.WRITE_BLOCKING
                        }
                        audioTrack.write(pcmBytes, 0, pcmBytes.size, writeMode)
                    }
                }
            } catch (e: Exception) {
                Log.e("AudioStream", "Error pada Socket 3 (Audio): ${e.message}")
            } finally {
                try {
                    audioTrack?.stop()
                    audioTrack?.release()
                } catch (_: Exception) {
                }
            }
        }
    }

    fun stop() {
        audioJob?.cancel()
    }
}
