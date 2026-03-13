# main.py
from database import init_db
from gui_app import SmartQBApp

if __name__ == "__main__":
    # 1. 确保数据库已初始化
    init_db()
    
    # 2. 启动 GUI 主程序
    app = SmartQBApp()
    app.mainloop()