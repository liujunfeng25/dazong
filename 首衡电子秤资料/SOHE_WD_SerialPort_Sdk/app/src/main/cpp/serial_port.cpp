#include <jni.h>
#include <string>
#include <android/log.h>
#include <fcntl.h>
#include <unistd.h>
#include <termios.h>
#include <sys/ioctl.h>
#include <errno.h>

#define LOG_TAG "SerialPort"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

/**
 * 打开串口
 */
extern "C" JNIEXPORT jobject JNICALL
Java_com_sohe_serialport_sdk_SerialPortManager_nativeOpenSerialPort(
        JNIEnv *env, jobject thiz, jstring path, jint baudrate) {
    
    const char *path_utf = env->GetStringUTFChars(path, nullptr);
    LOGI("Opening serial port: %s, baudrate: %d", path_utf, baudrate);
    
    // 打开串口设备（阻塞模式，不使用 O_NDELAY/O_NONBLOCK）
    int fd = open(path_utf, O_RDWR | O_NOCTTY);
    if (fd == -1) {
        LOGE("Cannot open serial port %s: %s", path_utf, strerror(errno));
        env->ReleaseStringUTFChars(path, path_utf);
        return nullptr;
    }
    // 确保为阻塞模式
    (void)fcntl(fd, F_SETFL, 0);
    
    // 配置串口参数
    struct termios options;
    if (tcgetattr(fd, &options) != 0) {
        LOGE("Cannot get serial port attributes: %s", strerror(errno));
        close(fd);
        env->ReleaseStringUTFChars(path, path_utf);
        return nullptr;
    }
    
    // 设置波特率
    speed_t speed;
    switch (baudrate) {
        case 9600:
            speed = B9600;
            break;
        case 19200:
            speed = B19200;
            break;
        case 38400:
            speed = B38400;
            break;
        case 57600:
            speed = B57600;
            break;
        case 115200:
            speed = B115200;
            break;
        default:
            LOGE("Unsupported baudrate: %d", baudrate);
            close(fd);
            env->ReleaseStringUTFChars(path, path_utf);
            return nullptr;
    }
    
    cfsetispeed(&options, speed);
    cfsetospeed(&options, speed);
    
    // 设置数据位、停止位、校验位
    options.c_cflag &= ~PARENB;   // 无校验
    options.c_cflag &= ~CSTOPB;   // 1个停止位
    options.c_cflag &= ~CSIZE;    // 清除数据位设置
    options.c_cflag |= CS8;       // 8个数据位
    options.c_cflag |= CREAD | CLOCAL; // 启用接收器，忽略调制解调器控制线
    options.c_cflag &= ~CRTSCTS;  // 关闭硬件流控
    
    // 设置输入模式
    options.c_iflag &= ~(IXON | IXOFF | IXANY); // 关闭软件流控
    options.c_iflag &= ~(INLCR | ICRNL);        // 不转换换行符
    
    // 设置输出模式
    options.c_oflag &= ~OPOST; // 原始输出
    
    // 设置本地模式
    options.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG); // 原始模式
    
    // 设置超时（原始模式下由 VMIN/VTIME 控制）
    options.c_cc[VMIN] = 0;   // 最小字符数（0 表示按超时返回）
    options.c_cc[VTIME] = 10; // 超时时间（单位0.1s，这里为1秒）
    
    // 应用配置
    if (tcsetattr(fd, TCSANOW, &options) != 0) {
        LOGE("Cannot set serial port attributes: %s", strerror(errno));
        close(fd);
        env->ReleaseStringUTFChars(path, path_utf);
        return nullptr;
    }
    
    // 清空缓冲区
    tcflush(fd, TCIOFLUSH);
    
    LOGI("Serial port opened successfully: %s", path_utf);
    env->ReleaseStringUTFChars(path, path_utf);
    
    // 创建FileDescriptor对象
    jclass fdClass = env->FindClass("java/io/FileDescriptor");
    jmethodID fdConstructor = env->GetMethodID(fdClass, "<init>", "()V");
    jobject fileDescriptor = env->NewObject(fdClass, fdConstructor);
    
    // 设置文件描述符
    jfieldID descriptorField = env->GetFieldID(fdClass, "descriptor", "I");
    env->SetIntField(fileDescriptor, descriptorField, fd);
    
    return fileDescriptor;
}

/**
 * 关闭串口
 */
extern "C" JNIEXPORT void JNICALL
Java_com_sohe_serialport_sdk_SerialPortManager_nativeCloseSerialPort(
        JNIEnv *env, jobject thiz, jobject file_descriptor) {
    
    if (file_descriptor == nullptr) {
        LOGE("FileDescriptor is null");
        return;
    }
    
    jclass fdClass = env->GetObjectClass(file_descriptor);
    jfieldID descriptorField = env->GetFieldID(fdClass, "descriptor", "I");
    int fd = env->GetIntField(file_descriptor, descriptorField);
    
    if (fd > 0) {
        LOGI("Closing serial port fd: %d", fd);
        close(fd);
        env->SetIntField(file_descriptor, descriptorField, -1);
    }
}

/**
 * 读取串口数据 - 修改为一次性读取完整数据包
 */
extern "C" JNIEXPORT jint JNICALL
Java_com_sohe_serialport_sdk_SerialPortManager_nativeReadSerialPort(
        JNIEnv *env, jobject thiz, jobject file_descriptor, jbyteArray buffer) {
    
    if (file_descriptor == nullptr || buffer == nullptr) {
        LOGE("FileDescriptor or buffer is null");
        return -1;
    }
    
    jclass fdClass = env->GetObjectClass(file_descriptor);
    jfieldID descriptorField = env->GetFieldID(fdClass, "descriptor", "I");
    int fd = env->GetIntField(file_descriptor, descriptorField);
    
    if (fd <= 0) {
        LOGE("Invalid file descriptor: %d", fd);
        return -1;
    }
    
    jsize bufferLength = env->GetArrayLength(buffer);
    jbyte* bufferPtr = env->GetByteArrayElements(buffer, nullptr);
    
    int totalBytesRead = 0;
    int maxRetries = 10;  // 最大重试次数
    int retryCount = 0;
    
    // 首先检查是否有数据可读
    int bytesAvailable = 0;
    if (ioctl(fd, FIONREAD, &bytesAvailable) == 0 && bytesAvailable == 0) {
        // 没有数据可读，直接返回
        env->ReleaseByteArrayElements(buffer, bufferPtr, JNI_ABORT);
        return 0;
    }
    
    // 循环读取，直到读取到完整的数据包或超时
    while (totalBytesRead < bufferLength && retryCount < maxRetries) {
        int bytesRead = read(fd, bufferPtr + totalBytesRead, bufferLength - totalBytesRead);
        
        if (bytesRead < 0) {
            int err = errno;
            if (err == EAGAIN || err == EWOULDBLOCK || err == EINTR) {
                // 暂无数据或被中断，等待一小段时间后重试
                usleep(10000); // 等待10ms
                retryCount++;
                continue;
            }
            LOGE("Read error: %s", strerror(err));
            env->ReleaseByteArrayElements(buffer, bufferPtr, JNI_ABORT);
            return -1;
        }
        
        if (bytesRead == 0) {
            // 没有更多数据，等待一小段时间后重试
            usleep(10000); // 等待10ms
            retryCount++;
            continue;
        }
        
        totalBytesRead += bytesRead;
        
        // 检查是否读取到完整的数据包
        // 查找数据包结束标志（换行符或单位标识）
        bool foundCompletePacket = false;
        for (int i = 0; i < totalBytesRead; i++) {
            char c = (char)bufferPtr[i];
            if (c == '\n' || c == '\r') {
                foundCompletePacket = true;
                break;
            }
        }
        
        // 如果找到完整数据包，检查是否包含单位
        if (foundCompletePacket) {
            // 将读取的数据转换为字符串进行检查
            char tempStr[totalBytesRead + 1];
            memcpy(tempStr, bufferPtr, totalBytesRead);
            tempStr[totalBytesRead] = '\0';
            
            // 检查是否包含常见的重量单位
            if (strstr(tempStr, "kg") != nullptr || 
                strstr(tempStr, "g") != nullptr || 
                strstr(tempStr, "lb") != nullptr ||
                strstr(tempStr, "KG") != nullptr ||
                strstr(tempStr, "G") != nullptr ||
                strstr(tempStr, "LB") != nullptr) {
                // 找到包含单位的完整数据包，停止读取
                LOGI("Complete packet with unit found, bytes: %d", totalBytesRead);
                break;
            }
        }
        
        // 如果还没有找到完整数据包，继续等待更多数据
        // 检查是否还有更多数据可读
        bytesAvailable = 0;
        if (ioctl(fd, FIONREAD, &bytesAvailable) == 0 && bytesAvailable > 0) {
            // 还有数据可读，继续读取
            retryCount = 0; // 重置重试计数
            continue;
        } else {
            // 没有更多数据，等待一小段时间
            usleep(5000); // 等待5ms
            retryCount++;
        }
    }
    
    env->ReleaseByteArrayElements(buffer, bufferPtr, 0);
    
    if (totalBytesRead > 0) {
        LOGI("Read complete packet: %d bytes", totalBytesRead);
    }
    
    return totalBytesRead;
}

/**
 * 写入串口数据
 */
extern "C" JNIEXPORT jboolean JNICALL
Java_com_sohe_serialport_sdk_SerialPortManager_nativeWriteSerialPort(
        JNIEnv *env, jobject thiz, jobject file_descriptor, jbyteArray data) {
    
    if (file_descriptor == nullptr || data == nullptr) {
        LOGE("FileDescriptor or data is null");
        return JNI_FALSE;
    }
    
    jclass fdClass = env->GetObjectClass(file_descriptor);
    jfieldID descriptorField = env->GetFieldID(fdClass, "descriptor", "I");
    int fd = env->GetIntField(file_descriptor, descriptorField);
    
    if (fd <= 0) {
        LOGE("Invalid file descriptor: %d", fd);
        return JNI_FALSE;
    }
    
    jsize dataLength = env->GetArrayLength(data);
    jbyte* dataPtr = env->GetByteArrayElements(data, nullptr);
    
    int bytesWritten = write(fd, dataPtr, dataLength);
    
    env->ReleaseByteArrayElements(data, dataPtr, JNI_ABORT);
    
    if (bytesWritten != dataLength) {
        LOGE("Write error: expected %d bytes, wrote %d bytes", dataLength, bytesWritten);
        return JNI_FALSE;
    }
    
    return JNI_TRUE;
}