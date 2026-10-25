package com.extenddisplay.client

import android.util.Log
import android.view.MotionEvent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.io.BufferedWriter
import java.io.InputStreamReader
import java.io.OutputStreamWriter

class ControlTerminalClient(
    private val config: EndpointConfig,
    private val onTerminalOutput: (stream: String, text: String) -> Unit,
    private val onRttUpdated: (rttMs: Long) -> Unit
) {
    private var connectionJob: Job? = null
    private val outboundQueue = Channel<String>(capacity = 256)

    fun start(scope: CoroutineScope) {
        stop()

        connectionJob = scope.launch(Dispatchers.IO) {
            try {
                LowLatencySocketFactory.connect(
                    host = config.host,
                    port = config.controlPort,
                    rcvBufBytes = 64 * 1024
                ).use { socket ->
                    val writer = BufferedWriter(OutputStreamWriter(socket.getOutputStream(), Charsets.UTF_8))
                    val reader = BufferedReader(InputStreamReader(socket.getInputStream(), Charsets.UTF_8))

                    // Writer Coroutine (Mengirim event sentuh, keyboard, dan perintah terminal)
                    val writerJob = launch(Dispatchers.IO) {
                        for (jsonLine in outboundQueue) {
                            if (!isActive) break
                            writer.write(jsonLine)
                            writer.write("\n")
                            writer.flush()
                        }
                    }

                    // Reader Loop (Menerima output stdout/stderr PowerShell/CMD dari PC)
                    while (isActive) {
                        val line = reader.readLine() ?: break
                        val json = JSONObject(line)
                        when (json.optString("type")) {
                            "term_out" -> {
                                val stream = json.optString("stream", "stdout")
                                val data = json.optString("data", "")
                                withContext(Dispatchers.Main) {
                                    onTerminalOutput(stream, data)
                                }
                            }
                            "pong" -> {
                                val clientTs = json.optLong("client_ts", 0L)
                                if (clientTs > 0L) {
                                    val rtt = System.currentTimeMillis() - clientTs
                                    withContext(Dispatchers.Main) {
                                        onRttUpdated(rtt)
                                    }
                                }
                            }
                        }
                    }

                    writerJob.cancel()
                }
            } catch (e: Exception) {
                Log.e("ControlTerminal", "Error pada Socket 2: ${e.message}")
            }
        }
    }

    /**
     * Mengonversi MotionEvent sentuhan layar tablet menjadi koordinat ternormalisasi (0.0 - 1.0)
     * agar di sisi PC langsung dipetakan ke monitor virtual IddSampleDriver.
     */
    fun sendTouchEvent(event: MotionEvent, viewWidth: Int, viewHeight: Int) {
        if (viewWidth <= 0 || viewHeight <= 0) return

        val normX = (event.x / viewWidth.toFloat()).coerceIn(0f, 1f)
        val normY = (event.y / viewHeight.toFloat()).coerceIn(0f, 1f)

        val action = when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> "down"
            MotionEvent.ACTION_MOVE -> "move"
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> "up"
            else -> return
        }

        val payload = JSONObject().apply {
            put("type", "mouse")
            put("action", action)
            put("x", normX.toDouble())
            put("y", normY.toDouble())
        }
        outboundQueue.trySend(payload.toString())
    }

    fun sendRightClick(normX: Float, normY: Float) {
        val payload = JSONObject().apply {
            put("type", "mouse")
            put("action", "right_click")
            put("x", normX.coerceIn(0f, 1f).toDouble())
            put("y", normY.coerceIn(0f, 1f).toDouble())
        }
        outboundQueue.trySend(payload.toString())
    }

    fun sendKeyPress(keyName: String) {
        val payload = JSONObject().apply {
            put("type", "key")
            put("action", "press")
            put("key", keyName)
        }
        outboundQueue.trySend(payload.toString())
    }

    fun sendTextInput(text: String) {
        val payload = JSONObject().apply {
            put("type", "key")
            put("action", "text")
            put("text", text)
        }
        outboundQueue.trySend(payload.toString())
    }

    /**
     * Mengirim perintah langsung ke stdin PowerShell / CMD di PC melalui pipa Socket 2.
     */
    fun sendTerminalCommand(command: String) {
        val payload = JSONObject().apply {
            put("type", "term_in")
            put("data", command)
        }
        outboundQueue.trySend(payload.toString())
    }

    fun sendPing() {
        val payload = JSONObject().apply {
            put("type", "ping")
            put("client_ts", System.currentTimeMillis())
        }
        outboundQueue.trySend(payload.toString())
    }

    fun stop() {
        connectionJob?.cancel()
    }
}
