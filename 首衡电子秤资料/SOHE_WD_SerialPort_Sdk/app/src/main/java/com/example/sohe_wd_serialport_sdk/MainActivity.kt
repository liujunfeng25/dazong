package com.example.sohe_wd_serialport_sdk

import android.annotation.SuppressLint
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.BitmapFactory
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.util.Log
// ohe SDK
import com.sohe.serialport.sdk.DataParser
import com.sohe.serialport.sdk.SoheWeightSDK
import com.sohe.serialport.sdk.WeightDataListener
// 为Sohe SDK的类添加别名
import com.sohe.serialport.sdk.WeightData as SoheWeightData
// Flutter imports (commented out for compilation)
// import io.flutter.embedding.android.FlutterActivity
// import io.flutter.embedding.engine.FlutterEngine
// import io.flutter.plugin.common.EventChannel
// import io.flutter.plugin.common.MethodChannel
import androidx.appcompat.app.AppCompatActivity
import android.widget.*
import android.view.View
import java.io.File
import java.util.Date
import java.text.SimpleDateFormat
import java.util.Locale


class MainActivity : AppCompatActivity(), WeightDataListener {
    private val methodChannel = "com.ypshengxian.method_channel"
    private val eventChannel = "com.ypshengxian.event_channel"
    // private var eventSink: EventChannel.EventSink? = null // Flutter dependency not available
    // rk3288设备的串口（兜底）
    private val sihePortName = "/dev/ttyS1"

    // Vandin SDK相关变量（如果需要使用Vandin SDK时再启用）
    // private lateinit var weightData: WeightData
    // private lateinit var control: WeightSerialPort

    private var isScaleConnected: Boolean = false
    private val actionUsbPermission = "com.ypshengxian.usb_action"

    private val mUsbManager: UsbManager by lazy {
        getSystemService(Context.USB_SERVICE) as UsbManager
    }

    // Sohe SDK实例
    private var soheWeightSDK: SoheWeightSDK? = null

	private var latestRawString: String? = null

    private var sdkTypeFromConfig: String? = null
    
    // UI组件
    private lateinit var spinnerSerialPorts: Spinner
    private lateinit var btnRefreshPorts: Button
    private lateinit var btnConnect: Button
    private lateinit var btnDisconnect: Button
    private lateinit var btnZero: Button
    private lateinit var btnTare: Button
    private lateinit var btnClearLog: Button
    private lateinit var etTareValue: EditText
    private lateinit var btnPresetTare: Button
    private lateinit var tvConnectionStatus: TextView
    private lateinit var tvProtocolType: TextView
    private lateinit var tvWeight: TextView
    private lateinit var tvStability: TextView
    private lateinit var tvWeightType: TextView
    private lateinit var tvLog: TextView
    private lateinit var statusIndicator: View
    
    private var serialPortAdapter: ArrayAdapter<String>? = null
    private val availablePorts = mutableListOf<String>()

    override fun onCreate(savedInstanceState: android.os.Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        
        // 初始化UI组件
        initViews()
        
        // 初始化串口适配器
        initSerialPortAdapter()
        
        // 扫描可用串口
        scanSerialPorts()
        
        // 设置按钮事件监听器
        setupButtonListeners()
        
        // 初始化SDK
        initSoheSDK()

        // 从配置读取SDK类型
//        val sharedPref = getSharedPreferences("app_config", Context.MODE_PRIVATE)
//        val sdkType = sharedPref.getString("sdk_type", null)
//        Log.d("DeviceInfo", "SDK类型: $sdkType")
//        if (sdkType != null) {
//            // 配置文件中已有设置，直接使用
//            setSDKType(sdkType)
//            Log.d("DeviceInfo", "从配置文件读取SDK类型: $sdkType")
//        } else {
//            Log.d("DeviceInfo", "SDK类型未设置: $sdkType")
//        }
    }
    
    // 初始化UI组件
    private fun initViews() {
        Log.d("SoheSDK", "[UI初始化] 开始初始化UI组件")
        
        spinnerSerialPorts = findViewById(R.id.spinnerSerialPorts)
        btnRefreshPorts = findViewById(R.id.btnRefreshPorts)
        btnConnect = findViewById(R.id.btnConnect)
        btnDisconnect = findViewById(R.id.btnDisconnect)
        btnZero = findViewById(R.id.btnZero)
        btnTare = findViewById(R.id.btnTare)
        btnClearLog = findViewById(R.id.btnClearLog)
        etTareValue = findViewById(R.id.etTareValue)
        btnPresetTare = findViewById(R.id.btnPresetTare)
        tvConnectionStatus = findViewById(R.id.tvConnectionStatus)
        tvProtocolType = findViewById(R.id.tvProtocolType)
        tvWeight = findViewById(R.id.tvWeight)
        tvStability = findViewById(R.id.tvStability)
        tvWeightType = findViewById(R.id.tvWeightType)
        tvLog = findViewById(R.id.tvLog)
        statusIndicator = findViewById(R.id.statusIndicator)
        
        // 验证TextView引用是否正确
        Log.d("SoheSDK", "[UI初始化] TextView引用检查:")
        Log.d("SoheSDK", "  tvProtocolType: ${if (::tvProtocolType.isInitialized) "已初始化" else "未初始化"}")
        Log.d("SoheSDK", "  tvWeight: ${if (::tvWeight.isInitialized) "已初始化" else "未初始化"}")
        Log.d("SoheSDK", "  tvStability: ${if (::tvStability.isInitialized) "已初始化" else "未初始化"}")
        Log.d("SoheSDK", "  tvWeightType: ${if (::tvWeightType.isInitialized) "已初始化" else "未初始化"}")
        
        // 设置初始值并验证
        tvProtocolType.text = "未知"
        tvWeight.text = "0.000 kg"
        tvStability.text = "未知"
        tvWeightType.text = "未知"
        
        Log.d("SoheSDK", "[UI初始化] 初始值设置完成:")
        Log.d("SoheSDK", "  tvProtocolType.text: ${tvProtocolType.text}")
        Log.d("SoheSDK", "  tvWeight.text: ${tvWeight.text}")
        Log.d("SoheSDK", "  tvStability.text: ${tvStability.text}")
        Log.d("SoheSDK", "  tvWeightType.text: ${tvWeightType.text}")
        
        Log.d("SoheSDK", "[UI初始化] UI组件初始化完成")
    }
    
    // 初始化串口适配器
    private fun initSerialPortAdapter() {
        serialPortAdapter = ArrayAdapter<String>(this, android.R.layout.simple_spinner_item, availablePorts)
        serialPortAdapter?.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spinnerSerialPorts.adapter = serialPortAdapter
    }
    
    // 扫描可用串口
    private fun scanSerialPorts() {
        availablePorts.clear()
        
        // 扫描常见的串口设备
        val commonPorts = listOf(
            "/dev/ttyS0", "/dev/ttyS1", "/dev/ttyS2", "/dev/ttyS3", "/dev/ttyS4",
            "/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2", "/dev/ttyUSB3",
            "/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyACM2", "/dev/ttyACM3"
        )
        
        for (port in commonPorts) {
            val file = File(port)
            if (file.exists()) {
                availablePorts.add(port)
                Log.d("SerialPort", "发现串口: $port")
            }
        }
        
        if (availablePorts.isEmpty()) {
            availablePorts.add("未发现串口设备")
            Log.w("SerialPort", "未发现任何串口设备")
        }
        
        serialPortAdapter?.notifyDataSetChanged()
        Log.d("SerialPort", "串口扫描完成，共发现 ${availablePorts.size} 个设备")
    }
    
    // 设置按钮事件监听器
    private fun setupButtonListeners() {
        btnRefreshPorts.setOnClickListener {
            scanSerialPorts()
        }
        
        btnConnect.setOnClickListener {
            connectToSerialPort()
        }
        
        btnDisconnect.setOnClickListener {
            disconnectFromSerialPort()
        }
        
        btnZero.setOnClickListener {
            sendZeroCommand()
        }
        
        btnTare.setOnClickListener {
            sendTareCommand()
        }
        
        btnClearLog.setOnClickListener {
            tvLog.text = ""
        }
        
        btnPresetTare.setOnClickListener {
            sendPresetTareCommand()
        }
    }
    
    // 连接串口
    private fun connectToSerialPort() {
        val selectedPort = spinnerSerialPorts.selectedItem?.toString()
        if (selectedPort.isNullOrEmpty() || selectedPort == "未发现串口设备") {
            appendLog("请选择有效的串口设备")
            return
        }
        
        soheWeightSDK?.let { sdk ->
            val success = sdk.connect(selectedPort)
            if (success) {
                appendLog("正在连接串口: $selectedPort")
            } else {
                appendLog("连接失败: $selectedPort")
            }
        } ?: appendLog("SDK未初始化")
    }
    
    // 断开串口连接
    private fun disconnectFromSerialPort() {
        soheWeightSDK?.let { sdk ->
            sdk.disconnect()
            appendLog("已断开串口连接")
        } ?: appendLog("SDK未初始化")
    }
    
    // 发送置零命令
    private fun sendZeroCommand() {
        soheWeightSDK?.let { sdk ->
            sdk.sendZeroCommand()
            appendLog("已发送置零命令")
        } ?: appendLog("SDK未初始化")
    }
    
    // 发送去皮命令
    private fun sendTareCommand() {
        soheWeightSDK?.let { sdk ->
            sdk.sendTareCommand()
            appendLog("已发送去皮命令")
        } ?: appendLog("SDK未初始化")
    }
    
    // 发送预制皮重命令
    private fun sendPresetTareCommand() {
        val tareValueText = etTareValue.text.toString().trim()
        
        val tareValue = if (tareValueText.isEmpty()) {
            // 使用默认值
            "0012.34"
        } else {
            // 验证并格式化用户输入
            val formattedValue = formatTareValue(tareValueText)
            if (formattedValue == null) {
                appendLog("[错误] 皮重值格式错误，请输入有效的数字 (如: 12.34)")
                return
            }
            formattedValue
        }
        
        val command = "YARE=$tareValue"
        
        appendLog("[命令] 发送预制皮重命令: $tareValue")
        
        if (soheWeightSDK?.sendCustomCommand(command.toByteArray()) == true) {
            appendLog("[成功] 预制皮重命令发送成功")
        } else {
            appendLog("[错误] 预制皮重命令发送失败")
        }
    }
    
    // 格式化皮重值为标准格式 (如: 12.34 -> 0012.34)
    private fun formatTareValue(input: String): String? {
        return try {
            // 解析输入的数字
            val value = input.toDouble()
            
            // 检查范围 (0-9999.99)
            if (value < 0 || value > 9999.99) {
                null
            } else {
                // 格式化为 XXXX.XX 格式
                String.format("%07.2f", value)
            }
        } catch (e: NumberFormatException) {
            null
        }
    }
    
    // 添加日志
    private fun appendLog(message: String) {
        runOnUiThread {
            val timestamp = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
            val logMessage = "[$timestamp] $message\n"
            tvLog.append(logMessage)
        }
        Log.d("MainActivity", message)
    }

    // 1个sdk
    /*
    private fun initVandinSDK() {
        try {
            Log.d("VandinSDK", "开始初始化Vandin SDK...")

            // 初始化weightData
            weightData = WeightData().apply {
                port = "ttyS4"
                baudrate = 9600
            }
            Log.d("VandinSDK", "weightData初始化成功 - 端口: ${weightData.port}, 波特率: ${weightData.baudrate}")

            // 初始化control
            control = WeightSerialPort(this@MainActivity, this@MainActivity, weightData)
            Log.d("VandinSDK", "control初始化成功")

        } catch (e: Exception) {
            Log.e("VandinSDK", "SDK初始化异常: ${e.message}")
            e.printStackTrace()
        }
    }
    */

    // 初始化Sohe SDK的方法
    private fun initSoheSDK() {
        try {
            Log.d("SoheSDK", "开始初始化Sohe SDK...")
            // 检查SDK类是否可用
            checkSoheSDKClasses()

            soheWeightSDK = SoheWeightSDK()
            // 设置当前类为重量数据监听器
            Log.d("SoheSDK", "SDK实例创建成功")

            val config = SoheWeightSDK.Config()
            config.setBaudRate(9600)        // 设置波特率
            config.setAutoConnect(false)    // 禁用自动连接
            config.setPreferredPort(null)   // 不设置首选端口

            // 初始化SDK
            val initialized = soheWeightSDK?.initialize(config)
            if (initialized == true) {
                Log.d("SoheSDK","配置信息 - 波特率: ${config.getBaudRate()}, 自动连接: ${config.isAutoConnect()}")
                Log.d("SoheSDK","注意: SDK支持首衡协议和VA协议自动识别");
                Log.d("SoheSDK","首衡协议格式: [稳定标志s/w][净重标志n/g][重量数据][kg]");
                Log.d("SoheSDK","如显示VA协议，请检查串口数据格式是否符合首衡协议规范");

                Log.d("SoheSDK","===================\n");
                soheWeightSDK?.let { sdk ->
                    sdk.setWeightDataListener(this)
                    Log.d("SoheSDK","数据监听器已设置");
                } ?: Log.e("SoheSDK", "无法设置监听器：soheWeightSDK为空")
            } else {
                Log.e("SoheSDK", "SDK初始化失败")
            }
        } catch (e: Exception) {
            Log.e("SoheSDK", "SDK初始化异常: ${e.message}")
            e.printStackTrace()
        }
    }

    // 检查Sohe SDK类是否正确加载
    private fun checkSoheSDKClasses() {
        try {
            Log.d("SoheSDK", "检查SDK类加载状态:")

            Class.forName("com.sohe.serialport.sdk.SoheWeightSDK")
            Log.d("SoheSDK", "✓ SoheWeightSDK 类加载成功")

            Class.forName("com.sohe.serialport.sdk.WeightData")
            Log.d("SoheSDK", "✓ WeightData 类加载成功")

            Class.forName("com.sohe.serialport.sdk.WeightDataListener")
            Log.d("SoheSDK", "✓ WeightDataListener 类加载成功")

            Log.d("SoheSDK", "所有SDK类加载正常")
        } catch (e: ClassNotFoundException) {
            Log.e("SoheSDK", "✗ SDK类加载失败: ${e.message}")
        }
    }


    private fun createPermissionIntent(device: UsbDevice): PendingIntent {
        return PendingIntent.getBroadcast(
            this,
            System.currentTimeMillis().toInt(), // 唯一请求码
            Intent(actionUsbPermission).apply {
                putExtra(UsbManager.EXTRA_DEVICE, device)
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }



    /*
    private fun initPrint() {
        // 1. 查找打印机设备
        val printerDevice = mUsbManager.deviceList.values.firstOrNull { device ->
            Log.d("USB", "打印机初始化获取打印机设备：=====》 $device")
            (0 until device.interfaceCount).any { i ->
                Log.d("USB", "打印机初始化device.getInterface(i).interfaceClass：=====》 $device.getInterface(i).interfaceClass")
                device.getInterface(i).interfaceClass == 7
            }
        } ?: run {
            Log.e("USB", "未找到打印机设备")
            return
        }

        // 2. 检查已有权限
        if (mUsbManager.hasPermission(printerDevice)) {
            onUsbPermissionGranted(printerDevice)
            return
        }

        // 3. 创建新的权限请求
        val pendingIntent = createPermissionIntent(printerDevice)
        mUsbManager.requestPermission(printerDevice, pendingIntent)
    }

    // 打印相关方法（已注释，如需使用请先添加HPRTPrinterHelper依赖）
    /*
    private fun onUsbPermissionGranted(device: UsbDevice) {
        val result = HPRTPrinterHelper.PortOpen(this, device)
        // eventSink?.success(mapOf("type" to "print", "result" to result)) // Flutter dependency not available
     }
     */

    private val mUsbReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action != actionUsbPermission) return

            // 安全获取设备
            val device = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                Log.d("USB", "安全获取设备11111111111111")
                intent.getParcelableExtra(UsbManager.EXTRA_DEVICE, UsbDevice::class.java)
            } else {
                Log.d("USB", "安全获取设备2222222")
                @Suppress("DEPRECATION")
                intent.getParcelableExtra(UsbManager.EXTRA_DEVICE)
            } ?: run {
                Log.e("USB", "Intent 中未找到设备")
                return
            }
            if (intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)) {
                // onUsbPermissionGranted(device) // 已注释，打印功能暂不可用
                Log.d("USB", "USB权限已授予，但打印功能暂不可用")
            } else {
                Log.e("USB", "用户拒绝权限")
            }
        }
    }

    // 打印图片方法（已注释，打印功能暂不可用）
    /*
    private fun printImage480x320(base64: String, times: String): Boolean {
        return try {
            // 1. 将Base64字符串解码为字节数组
            val imageBytes = Base64.decode(base64, Base64.DEFAULT)

            // 2. 将字节数组转换为Bitmap
            val bitmap = BitmapFactory.decodeByteArray(imageBytes, 0, imageBytes.size)
                ?: return false // 如果解码失败返回false

            // 3. 设置打印区域大小（假设单位为点，1mm≈8点）
            HPRTPrinterHelper.printAreaSize("60", "40")

            // 4. 清空打印机缓冲区
            HPRTPrinterHelper.CLS()
            // 设置浓度
            HPRTPrinterHelper.Density("15")

            // 5. 打印图片
            HPRTPrinterHelper.printImage("5", "5", bitmap, true, false, 1)
            // HPRTPrinterHelper.Box("20", "10", "480", "320", "3")

            // 6. 执行打印
            HPRTPrinterHelper.Print("1", times) // 参数通常是打印份数和复制份数

            true // 打印成功
        } catch (e: Exception) {
            e.printStackTrace()
            false // 打印失败
        }
    }
    */
    */

    private fun setSDKType(sdkType: String) {

        Log.d("DeviceInfo", "设置的SDK类型: $sdkType, 当前SDK类型: $sdkTypeFromConfig")

        Log.d("SDKType", "sdkTypeFromConfig != sdkType: ${sdkTypeFromConfig != sdkType}")

        // 如果SDK类型发生变化，重新初始化
        if (sdkTypeFromConfig != sdkType) {
            // 断开现有连接
            if (isScaleConnected) {
                if (sdkTypeFromConfig == "sohe") {
                    soheWeightSDK?.disconnect()
                    Log.d("SDKType", "soheWeightSDK断开连接")
                } else {
                    // Vandin SDK断开连接（已注释）
                    // control.stopRead()
                    Log.d("SDKType", "vandin SDK断开连接（已注释）")
                }
                isScaleConnected = false
            }
            sdkTypeFromConfig = sdkType
            Log.d("SDKType", "$sdkTypeFromConfig == 'sohe'")
            // 重新初始化SDK
            if (sdkTypeFromConfig == "sohe") {
                initSoheSDK()
            } else {
                // Vandin SDK初始化（已注释）
                // initVandinSDK()
                Log.w("SDKType", "Vandin SDK暂时不可用，请添加相关依赖")
            }
        }

    }

    // Flutter相关方法注释，当前项目不使用Flutter依赖
    /*
    @SuppressLint("UnspecifiedRegisterReceiverFlag")
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        // 方法通道
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, methodChannel).setMethodCallHandler { call, result ->
            when (call.method) {
                // 设置SDK类型
                "setSDKType" -> {
                    try {
                        val sdkType = call.arguments as? String ?: "vandin"
                        setSDKType(sdkType)
                        result.success(true)
                    } catch (e: Exception) {
                        result.error("ERROR", "设置SDK类型失败: ${e.message}", null)
                    }
                }
                // 连接打印机（已注释，打印功能暂不可用）
                "initPrint" -> {
                    // initPrint()
                    Log.w("Print", "打印功能暂不可用")
                    result.success(false)
                }
                // 断开打印机（已注释，打印功能暂不可用）
                "closePrint" -> {
                    // eventSink?.success(mapOf("type" to "print", "result" to -1)) // Flutter dependency not available
                    // result.success(HPRTPrinterHelper.PortClose())
                    Log.w("Print", "打印功能暂不可用")
                    result.success(false)
                }
                // 获取打印机状态（已注释，打印功能暂不可用）
                "getPrinterStatus" -> {
                    // result.success(HPRTPrinterHelper.getPrinterStatus())
                    Log.w("Print", "打印功能暂不可用")
                    result.success(-1)
                }
                // 连接秤
                "initWeight" -> {
                    if (sdkTypeFromConfig == "sohe") {
                        // rk3288设备使用Sohe SDK连接串口：不再硬编码端口，改为优选可用端口
                        if (soheWeightSDK != null && !isScaleConnected) {
                            try {
                                val ports = soheWeightSDK?.getAvailableSerialPortInfos() ?: emptyList()
                                if (ports.isEmpty()) {
                                    Log.e("SoheSDK", "未发现可用串口")
                                    result.success(false)
                                } else {
                                    val preferred = ports.firstOrNull { it.getPath()?.contains("ttyS4") == true }
                                        ?: ports.firstOrNull { it.getPath()?.contains("ttyS") == true }
                                        ?: ports.firstOrNull { it.getPath()?.isNotEmpty() == true }
                                    val targetPath = preferred?.getPath() ?: sihePortName
                                    Log.d("SoheSDK", "尝试连接串口: $targetPath")
                                    val connected = soheWeightSDK!!.connect(targetPath)
                                    isScaleConnected = connected
                                    result.success(connected)
                                    Log.d("SDKType", "$sdkTypeFromConfig: 连接串口状态1: $connected")
                                }
                            } catch (e: Exception) {
                                Log.e("SoheSDK", "连接串口异常: ${e.message}")
                                result.success(false)
                            }
                        } else {
                            Log.d("SDKType", "$sdkTypeFromConfig: 连接串口状态2: true")
                            result.success(true)
                        }
                    } else {
                        // 其他设备使用原有的Vandin SDK（已注释，Vandin SDK暂不可用）
                        // if (::control.isInitialized &&!isScaleConnected) {
                        //     control.OpenScaleUart()
                        //     result.success(true)
                        // } else {
                        //     result.success(true)
                        // }
                        Log.w("Weight", "Vandin SDK暂不可用")
                        result.success(false)
                        Log.d("SDKType", "$sdkTypeFromConfig: 连接串口状态: false (Vandin SDK暂不可用)")
                    }
                }
                // 断开秤
                "closeWeight" -> {
                    if (sdkTypeFromConfig == "sohe") {
                        // rk3288设备使用Sohe SDK断开连接
                        soheWeightSDK?.disconnect()
                        Log.d("SoheSDK", "Sohe 已断开串口连接")
                    } else {
                        // 其他设备使用原有的Vandin SDK（已注释，Vandin SDK暂不可用）
                        // control.stopRead()
                        Log.w("Weight", "Vandin SDK暂不可用")
                        Log.d("SoheSDK", "Vandin SDK暂不可用，无法断开串口连接")
                    }
                    result.success(true)
                    isScaleConnected = false
                }
                // 打印图片（已注释，打印功能暂不可用）
                "printImage480x320" -> {
                    val base64 = call.argument<String>("base64")
                    val times = call.argument<String>("times") ?: "1"
                    // result.success(base64?.let { printImage480x320(it, times) })
                    Log.w("Print", "打印功能暂不可用")
                    result.success(false)
                }
                // 读取重量
                "getWeight" -> {
                    if (sdkTypeFromConfig == "sohe") {
                        // rk3288设备的重量读取逻辑需要根据Sohe SDK的API进行调整
                        // 这里只是一个示例，实际实现需要根据SDK文档进行
                        result.success(true)
                    } else {
                        // control.GetWeight() // Vandin SDK暂不可用
                        Log.w("Weight", "Vandin SDK暂不可用")
                        result.success(false)
                    }
                }
                // 发送命令
                "setUserCommandWithCmd" -> {
                    if (sdkTypeFromConfig == "sohe") {
                        // rk3288设备的命令发送逻辑需要根据Sohe SDK的API进行调整
                        result.success(true)
                    } else {
                        val cmd = call.argument<String>("cmd")
                        // control.SetUserCommand(cmd) // Vandin SDK暂不可用
                        Log.w("Weight", "Vandin SDK暂不可用")
                        result.success(false)
                    }
                }
                // 去皮
                "setTare" -> {
                    if (sdkTypeFromConfig == "sohe") {
                        // rk3288设备的去皮命令
                        val success = soheWeightSDK?.sendTareCommand() ?: false
                        result.success(success)
                    } else {
                        // control.SetTare() // Vandin SDK暂不可用
                        Log.w("Weight", "Vandin SDK暂不可用")
                        result.success(false)
                    }
                }

                // 清零
                "setZero" -> {
                    if (sdkTypeFromConfig == "sohe") {
                        Log.d("SoheSDK", "发送清零命令")
                        // rk3288设备的清零命令
                        val success = soheWeightSDK?.sendZeroCommand() ?: false
                        result.success(success)
                        Log.d("SoheSDK", "清零命令发送结果: $success")
                    } else {
                        // control.SetZero() // Vandin SDK暂不可用
                        Log.w("Weight", "Vandin SDK暂不可用")
                        result.success(false)
                    }
                }
                // 去皮/清零
                "setZeroTare" -> {
                    if (sdkTypeFromConfig == "sohe") {
                        // rk3288设备的去皮/清零命令
                        // 这里假设使用清零命令作为示例
                        val success = soheWeightSDK?.sendZeroCommand() ?: false
                        result.success(success)
                        Log.d("SoheSDK", "去皮/清零命令发送结果: $success")
                    } else {
                        // control.SetZeroTare() // Vandin SDK暂不可用
                        Log.w("Weight", "Vandin SDK暂不可用")
                        result.success(false)
                    }
                }
                // 预制去皮
                "setTareWeightWithTw" -> {
                    if (sdkTypeFromConfig == "sohe") {
                        // rk3288设备可能不支持此功能或需要不同的实现
                        result.success(false)
                    } else {
                        val tw = call.argument<String>("tw")
                        // control.SetTareWeight(tw) // Vandin SDK暂不可用
                        Log.w("Weight", "Vandin SDK暂不可用")
                        result.success(false)
                    }
                }
                else -> result.notImplemented()
            }
        }

        // 事件通道
        EventChannel(flutterEngine.dartExecutor.binaryMessenger, eventChannel).setStreamHandler(
            object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink) {
                    eventSink = events
                }
                
                override fun onCancel(arguments: Any?) {
                    eventSink = null
                }
            }
        )

        // 注册广播接收器
        val filter = IntentFilter(actionUsbPermission).apply {
            addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED)
            addAction(UsbManager.ACTION_USB_DEVICE_DETACHED)
        }

        // 注册广播接收器（适配 Android 13+）
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(mUsbReceiver, filter, Context.RECEIVER_EXPORTED)
        } else {
            registerReceiver(mUsbReceiver, filter)
        }
    }
    */
//--------------------------------------------------------------------------------------------------
    // Vandin SDK回调方法（已注释，如需使用请先添加相关导入和接口）
    /*
    //连接状态回调
    override fun onConnect(index: Int, str: String?, isConnect: Boolean) {
        if (isConnect) {
            isScaleConnected = true
        }
        Log.d("SDKType", "onConnect: vandin连接状态： $isConnect")
        Handler(Looper.getMainLooper()).post {
            val data = mapOf(
                "type" to "connection",
                "index" to index,
                "message" to str,
                "connected" to isConnect
            )
            // eventSink?.success(data) // Flutter dependency not available
        }
    }

    //数据获取回调
    override fun onReceiveData(frame: String?, weight: String?, isSta: Boolean) {
        Handler(Looper.getMainLooper()).post {
            val data = mapOf(
                "type" to "weight",
                "frame" to frame,
                "weight" to weight,
                "stable" to isSta
            )
            // eventSink?.success(data) // Flutter dependency not available
        }
    }
    */
//--------------------------------------------------------------------------------------------------
    override fun onDestroy() {
        super.onDestroy()

        // 根据设备类型释放相应的资源
        if (sdkTypeFromConfig == "sohe") {
            // 释放Sohe SDK资源
            soheWeightSDK?.disconnect()
            soheWeightSDK = null
        } else {
            // 释放原有Vandin SDK资源（已注释）
            // if (::control.isInitialized) {
            //     control.stopRead()
            // }
        }

        // USB receiver unregistration commented out since Flutter dependencies are not available
        /*
        try {
            unregisterReceiver(mUsbReceiver)
        } catch (e: IllegalArgumentException) {
            // Receiver was not registered
        }
        */
    }

    override fun onWeightDataReceived(weightData: SoheWeightData) {
        // 处理从Sohe SDK接收的重量数据
        Log.d("MainActivity", "★★★ onWeightDataReceived 方法被调用！！！ - 当前线程: ${Thread.currentThread().name}")
        Log.d("MainActivity", "★★★ 接收到的weightData: $weightData")
        
        Handler(Looper.getMainLooper()).post {
            Log.d("MainActivity", "★★★ Handler.post 内部 - 当前线程: ${Thread.currentThread().name}")
            
            try {
                val rawString = latestRawString ?: ""
                Log.d("SoheSDK", "当前重量数据对应的原始字符串: $rawString")
                val weight = weightData.weight
                val unit = weightData.unit
                val isStable = weightData.isStable
                val weightType = "重量" // 暂时使用通用标识，因为SDK可能不支持净重/毛重区分
                
                // 检测协议类型 - 优先使用weightData对象中的协议类型
                val protocolFromWeightData = weightData.protocolType
                val detectedProtocol = DataParser.detectProtocolType(rawString)
                
                // 使用weightData中的协议类型，如果为空则使用检测结果
                val finalProtocol = protocolFromWeightData ?: detectedProtocol
                
                val protocolText = when (finalProtocol) {
                    SoheWeightData.ProtocolType.VA -> "VA协议"
                    SoheWeightData.ProtocolType.SHOUHENG -> "首衡协议"
                    null -> "未知协议"
                    else -> "未知协议"
                }
                
                // 添加调试日志
                Log.d("SoheSDK", "weightData中的协议类型: $protocolFromWeightData")
                Log.d("SoheSDK", "检测到的协议类型: $detectedProtocol")
                Log.d("SoheSDK", "最终使用的协议类型: $finalProtocol, 显示文本: $protocolText")
                
                // 更新UI显示
                Log.d("SoheSDK", "[UI更新前] 准备更新UI - weight: $weight $unit, stability: ${if (isStable) "稳定" else "不稳定"}, weightType: $weightType, protocol: $protocolText")
                
                tvWeight.text = "$weight $unit"
                tvStability.text = if (isStable) "稳定" else "不稳定"
                tvWeightType.text = weightType
                tvProtocolType.text = protocolText
                
                Log.d("SoheSDK", "[UI更新后] UI已更新 - tvWeight.text: ${tvWeight.text}, tvStability.text: ${tvStability.text}, tvWeightType.text: ${tvWeightType.text}, tvProtocolType.text: ${tvProtocolType.text}")
                Log.d("SoheSDK", "[UI更新后] TextView可见性 - tvWeight.visibility: ${tvWeight.visibility}, tvStability.visibility: ${tvStability.visibility}, tvWeightType.visibility: ${tvWeightType.visibility}, tvProtocolType.visibility: ${tvProtocolType.visibility}")
                
                // 根据稳定性设置颜色
                val stabilityColor = if (isStable) {
                    getColor(R.color.status_connected)
                } else {
                    getColor(R.color.status_warning)
                }
                tvStability.setTextColor(stabilityColor)
                
                Log.d("SoheSDK", "[ADB调试] 通过属性获取 - weight: $weight, unit: $unit, stable: $isStable")
                Log.d("SoheSDK", "[ADB调试] 通过方法获取重量："+  weightData.getWeight() + "----是否稳定:"+ weightData.isStable())
                Log.d("SoheSDK", "[ADB调试] 完整weightData对象: $weightData")

                val frame = "VA,00,28,S,T,+" + weight + "," + weight + " kg " + "od"
                Log.d("SoheSDK", "[ADB调试] 构造的frame数据: $frame")
                
                // 记录重量数据到日志
                appendLog("重量: $weight $unit (${if (isStable) "稳定" else "不稳定"}) - $weightType")
                
            } catch (e: Exception) {
                Log.e("SoheSDK", "[ADB调试] 处理重量数据时出错: ${e.message}")
                e.printStackTrace()
                appendLog("处理重量数据时出错: ${e.message}")
            }
        }
    }
    override fun onRawDataReceived(rawData: ByteArray?) {
        Handler(Looper.getMainLooper()).post {
            Log.d("MainActivity", "★★★ onRawDataReceived 方法被调用！！！")
            
            val rawString = String(rawData!!).trim { it <= ' ' }
            latestRawString = rawString // 保存原始字符串供onWeightDataReceived使用

            // 详细的原始数据调试信息
            val debugInfo = StringBuilder()
            debugInfo.append("原始数据: '").append(rawString).append("'")
            debugInfo.append(" [长度: ").append(rawData!!.size).append("]")
            debugInfo.append(" [十六进制: ")
            for (b in rawData) {
                debugInfo.append(String.format("%02X ", b))
            }
            debugInfo.append("]")

            // 检测协议类型
            val detectedType = DataParser.detectProtocolType(rawString)
            debugInfo.append(" [检测协议: ").append(detectedType?.name ?: "未知").append("]")

            Log.d("SoheSDK", "debugInfo=="  + debugInfo.toString())

            // 手动调用DataParser.parseData进行测试
            Log.d("MainActivity", "★★★ 手动测试DataParser.parseData...")
            val testWeightData = DataParser.parseData(rawData)
            if (testWeightData != null) {
                Log.d("MainActivity", "★★★ DataParser.parseData 成功解析: ${testWeightData}")
                Log.d("MainActivity", "★★★ 解析结果 - 重量: ${testWeightData.weight}, 协议: ${testWeightData.protocolType}")
            } else {
                Log.e("MainActivity", "★★★ DataParser.parseData 返回 null！！！")
                Log.e("MainActivity", "★★★ 原始数据: '$rawString'")
                Log.e("MainActivity", "★★★ 数据长度: ${rawData.size}")
            }

            // 控制台输出原始数据（用于调试）
            println("\n>>> 串口原始数据接收 <<<")
            println("字符串形式: '$rawString'")
            println("数据长度: " + rawData!!.size + " 字节")
            print("十六进制: ")
            for (b in rawData) {
                System.out.printf("%02X ", b)
            }
            println()
            print("ASCII码: ")
            for (b in rawData) {
                if (b >= 32 && b <= 126) {
                    System.out.printf("%c ", Char(b.toUShort()))
                } else {
                    System.out.printf("[%02X] ", b)
                }
            }
            println()
            println("检测协议: " + (detectedType?.name ?: "未知"))
            println("<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")

        }
    }
    // 移除错误的Java注解
    // @Override
    override fun onConnectionStatusChanged(isConnected: Boolean, portPath: String?) {
        Handler(Looper.getMainLooper()).post {
            isScaleConnected = isConnected
            
            // 更新UI显示
            if (isConnected) {
                tvConnectionStatus.text = "已连接"
                tvConnectionStatus.setTextColor(getColor(R.color.status_connected))
                (statusIndicator as? TextView)?.setBackgroundColor(getColor(R.color.status_connected))
                btnConnect.isEnabled = false
                btnDisconnect.isEnabled = true
                btnZero.isEnabled = true
                btnTare.isEnabled = true
                btnPresetTare.isEnabled = true
                appendLog("串口连接成功: $portPath")
                Log.d("SoheSDK", "\n>>>[SoheSDK] 连接状态: 已连接 <<< $portPath")
            } else {
                tvConnectionStatus.text = "未连接"
                tvConnectionStatus.setTextColor(getColor(R.color.status_disconnected))
                (statusIndicator as? TextView)?.setBackgroundColor(getColor(R.color.status_disconnected))
                btnConnect.isEnabled = true
                btnDisconnect.isEnabled = false
                btnZero.isEnabled = false
                btnTare.isEnabled = false
                btnPresetTare.isEnabled = false
                appendLog("串口连接断开")
                Log.d("SoheSDK", "\n>>>[SoheSDK] 连接状态: 已断开 <<<")
            }

            Log.d("SDKType", "onConnect: sohe连接状态： $isConnected")
            Log.d("SoheSDK", "连接状态变化: $isConnected, 端口: $portPath")
        }
    }
    override fun onError(errorCode: Int, errorMessage: String) {
        Handler(Looper.getMainLooper()).post {
            // 控制台输出详细错误信息
            Log.e("SoheSDK", "\n>>>onError SDK错误发生 <<<")
            Log.e("SoheSDK", "\n>>>onError errorCode $errorCode <<<")
            Log.e("SoheSDK", "\n>>>onError errorMessage $errorMessage <<<")
            
            // 在UI上显示错误信息
            appendLog("错误 [$errorCode]: $errorMessage")
        }
    }
    override fun onCommandResult(command: WeightDataListener.CommandType, success: Boolean) {
        Handler(Looper.getMainLooper()).post {
            val commandName = getCommandTypeString(command)
            val result = if (success) "成功" else "失败"
            Log.d("SoheSDK", "onCommandResult $commandName 命令执行 $result")
            
            // 在UI上显示命令结果
            appendLog("$commandName 命令执行 $result")
        }
    }
    private fun getCommandTypeString(command: WeightDataListener.CommandType): String {
         return when (command) {
             WeightDataListener.CommandType.ZERO -> "置零"
             WeightDataListener.CommandType.TARE -> "去皮"
             else -> "未知命令"
         }
    }

}

