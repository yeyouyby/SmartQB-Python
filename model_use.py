import os
import shutil

# 1. 你的源文件夹（假设就叫 'model'，和本脚本放在同一个目录下）
SOURCE_DIR = "model"

# 2. 自动获取并拼接你系统真实的 datalab 缓存路径
# 使用 os.path.expanduser("~") 会自动获取到 "C:\Users\yby12"
TARGET_DIR = os.path.join(
    os.path.expanduser("~"), 
    r"AppData\Local\datalab\datalab\Cache\models\text_recognition\2025_09_23"
)

def copy_model_files():
    print(f"🔍 检查源文件夹: {SOURCE_DIR}")
    
    # 检查源文件夹是否存在
    if not os.path.exists(SOURCE_DIR):
        print("❌ 错误: 找不到名为 'model' 的文件夹！")
        print("⚠️ 请确保本脚本和包含文件的 'model' 文件夹放在同一个地方。")
        return

    # 检查源文件夹里有没有文件
    files_to_copy = os.listdir(SOURCE_DIR)
    if not files_to_copy:
        print("❌ 错误: 'model' 文件夹是空的！请把下载好的 13 个文件放进去。")
        return

    # 自动创建目标隐藏路径（如果不存在的话）
    os.makedirs(TARGET_DIR, exist_ok=True)
    print(f"📁 目标路径已就绪: {TARGET_DIR}")
    print("-" * 50)

    # 开始复制文件
    success_count = 0
    for file_name in files_to_copy:
        src_file = os.path.join(SOURCE_DIR, file_name)
        dst_file = os.path.join(TARGET_DIR, file_name)

        # 只复制文件，跳过可能存在的子文件夹
        if os.path.isfile(src_file):
            print(f"➡️ 正在复制: {file_name} ...")
            try:
                shutil.copy2(src_file, dst_file) # copy2 会保留文件的原始修改时间等属性
                success_count += 1
            except Exception as e:
                print(f"❌ 复制 {file_name} 失败: {e}")

    print("-" * 50)
    print(f"🎉 搞定！成功将 {success_count} 个文件复制到了正确的缓存目录。")
    print("🚀 你现在可以去运行你的 gui_app.py 了！")

if __name__ == "__main__":
    copy_model_files()
