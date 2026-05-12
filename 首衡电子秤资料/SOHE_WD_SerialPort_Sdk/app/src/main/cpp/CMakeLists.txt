cmake_minimum_required(VERSION 3.22.1)

# 设置项目名称
project("serialport")

# 设置C++标准
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 设置编译选项
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Wall -Wextra -O2")

# 添加库
add_library(
        # 设置库名称
        serialport
        
        # 设置库类型为共享库
        SHARED
        
        # 提供源文件的相对路径
        serial_port.cpp
)

# 设置目标属性
set_target_properties(serialport PROPERTIES
    CXX_STANDARD 14
    CXX_STANDARD_REQUIRED ON
)

# 查找预构建的NDK库并定义为变量
find_library(
        # 设置变量名称
        log-lib
        
        # 指定NDK库的名称
        log
)

# 链接目标库与NDK中的库
target_link_libraries(
        # 指定目标库
        serialport
        
        # 链接目标库到NDK中的日志库
        ${log-lib}
)