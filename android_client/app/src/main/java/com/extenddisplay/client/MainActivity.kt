package com.extenddisplay.client

import android.annotation.SuppressLint
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.view.Gravity
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope

class MainActivity : AppCompatActivity() {

    private var displayClient: DisplayStreamClient? = null
    private var controlClient: ControlTerminalClient? = null
    private var audioClient: AudioStreamClient? = null

    private lateinit var displayView: ImageView
    private lateinit var statusHudText: TextView
    private lateinit var terminalOutputText: TextView
    private lateinit var terminalScrollView: ScrollView
    private lateinit var terminalContainer: LinearLayout
    private lateinit var hostInput: EditText

    @SuppressLint("ClickableViewAccessibility", "SetTextI18n")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val rootLayout = FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
        }

        // 1. Kanvas Utama Display Stream (Socket 1) + Touch Listener (Socket 2)
        displayView = ImageView(this).apply {
            scaleType = ImageView.ScaleType.FIT_XY
            setOnTouchListener { view, event ->
                controlClient?.sendTouchEvent(event, view.width, view.height)
                true
            }
        }
        rootLayout.addView(
            displayView,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )

        // 2. Top Toolbar: Pemilih Mode Koneksi (Kabel USB vs VPN Tailscale) & HUD Status
        val topBar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setBackgroundColor(Color.parseColor("#B3000000"))
            setPadding(24, 12, 24, 12)
            gravity = Gravity.CENTER_VERTICAL
        }

        hostInput = EditText(this).apply {
            hint = "IP Tailscale / USB Tether (mis. 100.x.y.z)"
            setText("127.0.0.1")
            setTextColor(Color.WHITE)
            setHintTextColor(Color.LTGRAY)
            minWidth = 360
        }

        val btnUsbMode = Button(this).apply {
            text = "Mode Kabel (ADB 127.0.0.1)"
            setOnClickListener {
                hostInput.setText("127.0.0.1")
                connectAllSockets(
                    EndpointConfig(
                        host = "127.0.0.1",
                        mode = ConnectionMode.USB_CABLE
                    )
                )
            }
        }

        val btnVpnMode = Button(this).apply {
            text = "Mode Jarak Jauh (VPN/Tailscale)"
            setOnClickListener {
                val targetHost = hostInput.text.toString().trim().ifEmpty { "100.64.0.1" }
                connectAllSockets(
                    EndpointConfig(
                        host = targetHost,
                        mode = ConnectionMode.REMOTE_VPN
                    )
                )
            }
        }

        val btnToggleTerminal = Button(this).apply {
            text = "Terminal PS/CMD"
            setOnClickListener {
                terminalContainer.visibility =
                    if (terminalContainer.visibility == LinearLayout.VISIBLE) {
                        LinearLayout.GONE
                    } else {
                        LinearLayout.VISIBLE
                    }
            }
        }

        statusHudText = TextView(this).apply {
            text = "Status: Idle"
            setTextColor(Color.GREEN)
            setPadding(24, 0, 0, 0)
        }

        topBar.addView(hostInput)
        topBar.addView(btnUsbMode)
        topBar.addView(btnVpnMode)
        topBar.addView(btnToggleTerminal)
        topBar.addView(statusHudText)

        rootLayout.addView(
            topBar,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.TOP
            )
        )

        // 3. Panel Drawer Terminal Interaktif PowerShell / CMD (Socket 2)
        terminalContainer = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#D9121212"))
            setPadding(20, 20, 20, 20)
            visibility = LinearLayout.GONE
        }

        terminalOutputText = TextView(this).apply {
            typeface = Typeface.MONOSPACE
            setTextColor(Color.parseColor("#00FF66"))
            textSize = 12f
            text = "=== Interactive PC PowerShell / CMD Terminal ===\n"
        }

        terminalScrollView = ScrollView(this).apply {
            addView(terminalOutputText)
        }

        val terminalInput = EditText(this).apply {
            hint = "Ketik perintah PowerShell/CMD lalu tekan Enter..."
            setTextColor(Color.WHITE)
            setHintTextColor(Color.GRAY)
            typeface = Typeface.MONOSPACE
            imeOptions = EditorInfo.IME_ACTION_SEND
            setSingleLine(true)
            setOnEditorActionListener { v, _, _ ->
                val cmd = v.text.toString()
                if (cmd.isNotEmpty()) {
                    controlClient?.sendTerminalCommand(cmd)
                    v.text = ""
                }
                true
            }
        }

        terminalContainer.addView(
            terminalScrollView,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                420
            )
        )
        terminalContainer.addView(
            terminalInput,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        )

        rootLayout.addView(
            terminalContainer,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM
            )
        )

        setContentView(rootLayout)
    }

    @SuppressLint("SetTextI18n")
    private fun connectAllSockets(config: EndpointConfig) {
        disconnectAllSockets()

        // Socket 1: Display Stream
        displayClient = DisplayStreamClient(
            config = config,
            onFrameDecoded = { bitmap, lagMs ->
                displayView.setImageBitmap(bitmap)
                statusHudText.text = "${config.mode.name} | Lag: ${lagMs}ms"
            },
            onStatusChanged = { status ->
                runOnUiThread { statusHudText.text = status }
            }
        ).also { it.start(lifecycleScope) }

        // Socket 2: Touch/Mouse/Keyboard + Interactive Terminal
        controlClient = ControlTerminalClient(
            config = config,
            onTerminalOutput = { _, text ->
                terminalOutputText.append(text)
                terminalScrollView.post {
                    terminalScrollView.fullScroll(ScrollView.FOCUS_DOWN)
                }
            },
            onRttUpdated = { rttMs ->
                statusHudText.text = "${config.mode.name} | RTT: ${rttMs}ms"
            }
        ).also { it.start(lifecycleScope) }

        // Socket 3: WASAPI Audio Loopback
        audioClient = AudioStreamClient(config = config).also {
            it.start(lifecycleScope)
        }
    }

    private fun disconnectAllSockets() {
        displayClient?.stop()
        controlClient?.stop()
        audioClient?.stop()
    }

    override fun onDestroy() {
        disconnectAllSockets()
        super.onDestroy()
    }
}
