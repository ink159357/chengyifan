import requests
import os
import time
import hashlib
import json
from datetime import datetime
import sys
import random

# 请求配置
URL = "https://jxfw-443.vpn.hfu.edu.cn/cjcx/cjcx_cxXsgrcj.html?doType=query&gnmkdm=N305005"
HEADERS = {
    "Host": "jxfw-443.vpn.hfu.edu.cn",
    "Connection": "keep-alive",
    "sec-ch-ua-platform": "Windows",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Google Chrome\";v=\"138\"",
    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
    "sec-ch-ua-mobile": "?0",
    "Origin": "https://jxfw-443.vpn.hfu.edu.cn",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://jxfw-443.vpn.hfu.edu.cn/cjcx/cjcx_cxDgXscj.html?gnmkdm=N305005&layout=default",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9",
    # 更新后的Cookie
    "Cookie": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
DATA = {
    "xnm": "2024",
    "xqm": "12",
    "kcbj": "",
    "_search": "false",
    "nd": "1751805389541",
    "queryModel.showCount": "15",
    "queryModel.currentPage": "1",
    "queryModel.sortName": " ",
    "queryModel.sortOrder": "asc",
    "time": "1"
}

# 输出目录与检查间隔
OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "成绩查询数据")
CHECK_INTERVAL = 60  # 正常检查间隔（秒）
ERROR_RETRY_INTERVAL = 60  # 错误后重试间隔（秒）

# 推送配置
PUSHPLUS_TOKEN = "xxxxxxxxxxxxxxxxxxx"  # 请替换为有效Token
QMSG_KEY = "xxxxxxxxxxxxxxxxxxx"       # 请替换为有效Key
PUSHPLUS_URL = "http://www.pushplus.plus/send"
QMSG_URL = "https://qmsg.zendee.cn/send/{key}"

# 敏感词配置
SENSITIVE_WORDS = {
    "习近平新时代中国特色社会主义思想概论": "新思想",
    "敏感词2": "替换词2",
}

# 错误处理配置
MAX_RETRIES = 5  # 最大重试次数
ERROR_LOG_FILE = os.path.join(OUTPUT_DIR, "notification_debug.log")

# 初始化全局变量
last_core_hash = None
last_normal_data = None  # 保存上次正常数据
retry_count = 0  # 连续错误重试计数（0-3）
program_running = True

# 确保输出目录存在
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)
    print(f"创建输出目录: {OUTPUT_DIR}")

# 记录详细日志
def log_debug(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    with open(ERROR_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_entry)
    print(log_entry.strip())

# 提取核心数据
def extract_core_data(json_data):
    if not isinstance(json_data, dict) or 'items' not in json_data:
        return [], False
    
    core_data = []
    has_sensitive = False
    
    for item in json_data['items']:
        bfzcj = item.get('bfzcj', '无原始成绩')
        jxbmc = item.get('jxbmc', '无课程名')
        
        for sensitive_word, replace_word in SENSITIVE_WORDS.items():
            if sensitive_word in jxbmc:
                has_sensitive = True
                jxbmc = jxbmc.replace(sensitive_word, replace_word)
            
        core_data.append((jxbmc, bfzcj))
    return sorted(core_data), has_sensitive

# 计算数据哈希
def calculate_core_hash(core_data):
    if not core_data:
        return None
    return hashlib.sha256(json.dumps(core_data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

# 保存数据到文件
def save_to_file(core_data):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(OUTPUT_DIR, f"原始成绩_{timestamp}.txt")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        for jxbmc, bfzcj in core_data:
            f.write(f"{jxbmc}: {bfzcj}\n")
    
    return file_path

# 发送PushPlus通知
def send_pushplus_notification(title, content):
    if not PUSHPLUS_TOKEN or PUSHPLUS_TOKEN.startswith("请替换为"):
        log_debug("PushPlus Token未配置，跳过推送")
        return False
    
    log_debug("开始发送PushPlus通知")
    try:
        pushplus_data = {
            "token": PUSHPLUS_TOKEN,
            "title": title,
            "content": content,
            "template": "txt"
        }
        response = requests.post(PUSHPLUS_URL, json=pushplus_data, timeout=10)
        response.raise_for_status()
        result = response.json()
        return result.get("code") == 200
    except Exception as e:
        log_debug(f"PushPlus发送异常: {str(e)}")
        return False

# 发送Qmsg通知
def send_qmsg_notification(title, content):
    if not QMSG_KEY or QMSG_KEY.startswith("请替换为"):
        log_debug("Qmsg Key未配置，跳过推送")
        return False
    
    log_debug("开始发送Qmsg通知")
    try:
        qmsg_url = QMSG_URL.format(key=QMSG_KEY)
        qmsg_params = {"msg": f"{title}\n\n{content}"}
        response = requests.get(qmsg_url, params=qmsg_params, timeout=10)
        result = response.json()
        return result.get("code") == 0
    except Exception as e:
        log_debug(f"Qmsg发送异常: {str(e)}")
        return False

# 统一发送通知
def send_notification(core_data, has_sensitive=False):
    title = "首次成绩数据通知" if last_core_hash is None else "成绩更新通知"
    prefix = "[已过滤敏感词] " if has_sensitive else ""
    content = f"{prefix}数据如下:\n"
    content += "\n".join([f"{i+1}. {jxbmc}: {bfzcj}" for i, (jxbmc, bfzcj) in enumerate(core_data)])
    random_num = random.randint(1, 999)
    content += f"\n\n随机数: {random_num}"
    
    pushplus_success = send_pushplus_notification(title, content)
    qmsg_success = send_qmsg_notification(title, content)
    log_debug(f"推送结果 - PushPlus: {'成功' if pushplus_success else '失败'}, Qmsg: {'成功' if qmsg_success else '失败'}")
    return pushplus_success or qmsg_success

# 核心检查逻辑
def check_update():
    global last_core_hash, last_normal_data, retry_count, program_running
    
    try:
        # 处理重试等待
        if retry_count > 0:
            log_debug(f"第 {retry_count} 次重试等待中...")
            time.sleep(ERROR_RETRY_INTERVAL)

        # 初始化response变量为None
        response = None
        
        # 发送请求，超时设置为60秒
        log_debug("开始发送请求...")
        response = requests.post(URL, headers=HEADERS, data=DATA, timeout=60)
        response.raise_for_status()
        
        # 保存原始响应内容用于调试
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        response_content = response.text
        save_response_content(response_content, f"raw_response_{timestamp}.html")
        
        # 尝试解析JSON
        try:
            json_data = response.json()
        except json.JSONDecodeError as e:
            raise Exception(f"JSON解析错误: {str(e)}")
        
        # 重置重试计数（成功获取数据）
        if retry_count > 0:
            log_debug(f"第 {retry_count} 次重试成功，重置重试计数")
            retry_count = 0
        
        # 提取核心数据
        core_data, has_sensitive = extract_core_data(json_data)
        current_hash = calculate_core_hash(core_data)
        
        # 保存当前正常数据用于对比
        last_normal_data = core_data
        
        save_path = save_to_file(core_data)
        log_debug(f"数据已保存至: {save_path}")
        
        if not core_data:
            error_msg = "获取到空数据，可能是教务系统Token失效"
            raise Exception(error_msg)
        elif last_core_hash is None:
            # 首次运行，发送通知
            log_debug("首次运行，发送初始数据通知")
            last_core_hash = current_hash
            send_notification(core_data, has_sensitive)
        elif current_hash != last_core_hash:
            # 数据更新，发送通知
            log_debug("检测到数据更新，发送通知")
            last_core_hash = current_hash
            send_notification(core_data, has_sensitive)
        else:
            log_debug("数据无变化，不发送通知")
            
    except Exception as e:
        error_msg = str(e)
        log_debug(f"发生错误: {error_msg}")
        
        # 递增重试计数
        retry_count += 1
        
        if retry_count < MAX_RETRIES:
            log_debug(f"重试计数: {retry_count}/{MAX_RETRIES}，将进行重试")
            return  # 继续下一次重试
        else:
            # 达到最大重试次数，发送通知并退出
            title = "成绩监控-连续错误终止"
            content = f"连续{MAX_RETRIES}次错误，程序终止\n错误信息: {error_msg}"
            log_debug(f"达到最大重试次数({MAX_RETRIES})，发送终止通知")
            
            # 发送双平台通知
            pushplus_success = send_pushplus_notification(title, content)
            qmsg_success = send_qmsg_notification(title, content)
            log_debug(f"推送结果 - PushPlus: {'成功' if pushplus_success else '失败'}, Qmsg: {'成功' if qmsg_success else '失败'}")
            
            # 终止程序
            program_running = False
            return

# 保存响应内容用于调试
def save_response_content(content, filename):
    filepath = os.path.join(OUTPUT_DIR, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        log_debug(f"响应内容已保存至: {filepath}")
    except Exception as e:
        log_debug(f"保存响应内容失败: {str(e)}")

# 主程序入口
def main():
    global program_running
    print("=" * 50)
    print("成绩监控程序已启动")
    print(f"- 检查间隔: {CHECK_INTERVAL}秒")
    print(f"- 错误重试间隔: {ERROR_RETRY_INTERVAL}秒")
    print(f"- 最大重试次数: {MAX_RETRIES}次")
    print(f"- 输出目录: {OUTPUT_DIR}")
    print(f"- 调试日志: {ERROR_LOG_FILE}")
    print("=" * 50)
    
    try:
        while program_running:
            check_update()
            if program_running:  # 检查是否需要继续运行
                time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        log_debug("用户手动终止程序")
    finally:
        log_debug("程序已退出")
        sys.exit(0)

if __name__ == "__main__":
    main()