from pathlib import Path
from typing import Any, Dict, Optional, Literal, List
import yaml
from pydantic import BaseModel, Field

class ServerConfig(BaseModel):
    """服务器配置模型"""
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True

class UploadConfig(BaseModel):
    """文件上传配置模型"""
    base_dir: str = "./uploads"
    max_size: int = 10485760
    allowed_types: List[str] = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "application/pdf",
        "text/plain",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ]
    chunk_size: int = 8192

class SQLiteConfig(BaseModel):
    """SQLite配置模型"""
    path: str = "./data/wxautox.db"

class MySQLConfig(BaseModel):
    """MySQL配置模型"""
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = "password"
    database: str = "wxautox"
    charset: str = "utf8mb4"

class MongoDBConfig(BaseModel):
    """MongoDB配置模型"""
    host: str = "localhost"
    port: int = 27017
    database: str = "wxautox"
    username: str = ""
    password: str = ""

class DatabaseConfig(BaseModel):
    """数据库配置模型"""
    type: Literal["sqlite", "mysql", "mongodb"] = "sqlite"
    sqlite: SQLiteConfig = Field(default_factory=SQLiteConfig)
    mysql: MySQLConfig = Field(default_factory=MySQLConfig)
    mongodb: MongoDBConfig = Field(default_factory=MongoDBConfig)

class WeChatConfig(BaseModel):
    """微信配置模型"""
    app_path: str = "C:/Program Files/WeChat/WeChat.exe"
    language: str = "cn"
    enable_file_logger: bool = True
    message_hash: bool = False
    default_message_xbias: int = 51
    force_message_xbias: bool = False
    listen_interval: int = 1
    listener_executor_workers: int = 4
    search_chat_timeout: int = 5
    note_load_timeout: int = 30

class StorageConfig(BaseModel):
    """存储配置模型"""
    default_save_path: str = "./wxauto"
    log_path: str = "./wxauto_logs"

class LoggingConfig(BaseModel):
    """日志配置模型"""
    level: str = "INFO"
    format: str = "%(asctime)s - %(levelname)s - %(message)s"
    file: str = "wxauto_api.log"

class AuthConfig(BaseModel):
    """认证配置模型"""
    token: str = "your-secret-token-here"

class APIConfig(BaseModel):
    """API配置模型"""
    prefix: str = "/v1"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"
    openapi_url: str = "/openapi.json"

class PerformanceConfig(BaseModel):
    """性能配置模型"""
    max_workers: int = 4
    timeout: int = 30
    retry_attempts: int = 3
    retry_delay: int = 1

class CallbackConfig(BaseModel):
    """回调配置模型"""
    enabled: bool = False
    url: str = ""
    secret: str = ""
    timeout: int = 10
    retry_attempts: int = 3
    retry_delay: int = 1
    notify_contact: str = ""  # 回调失败时发送通知的微信联系人，留空则不通知
    only_at_me: bool = False  # False=推送所有消息(默认); True=仅推送@我的消息
    at_all_pass: bool = True  # only_at_me=True 时, @所有人 是否也算"@我"通过过滤
    always_callback_chats: List[str] = Field(default_factory=list)  # 白名单群聊名, 无论开关是否开启都推送
    tag: str = ""  # 客户端附加标记, 每次回调请求体顶层固定携带, 用于区分不同客户端

class ListenConfig(BaseModel):
    """监听配置模型"""
    safe_contacts: List[str] = Field(default_factory=lambda: ["文件传输助手"])
    sandbox_mode: bool = True

class Settings(BaseModel):
    """总配置模型"""
    server: ServerConfig = Field(default_factory=ServerConfig)
    upload: UploadConfig = Field(default_factory=UploadConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    wechat: WeChatConfig = Field(default_factory=WeChatConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    callback: CallbackConfig = Field(default_factory=CallbackConfig)
    listen: ListenConfig = Field(default_factory=ListenConfig)

    @classmethod
    def _find_config(cls) -> Path:
        """查找 config.yaml，优先 exe 同级目录，其次源码目录"""
        import sys
        # 1. exe 同级目录（打包后用户可编辑）
        if getattr(sys, 'frozen', False):
            exe_dir = Path(sys.executable).parent
            candidate = exe_dir / "config.yaml"
            if candidate.exists():
                return candidate
        # 2. 当前工作目录
        candidate = Path("config.yaml")
        if candidate.exists():
            return candidate
        # 3. PyInstaller 内部打包的资源
        if getattr(sys, 'frozen', False):
            candidate = Path(sys._MEIPASS) / "config.yaml"
            if candidate.exists():
                return candidate
        # 4. 源码目录（app/main.py 的上级）
        candidate = Path(__file__).resolve().parent.parent.parent / "config.yaml"
        if candidate.exists():
            return candidate
        return Path("config.yaml")

    @classmethod
    def load_config(cls, config_path: Optional[str] = None) -> "Settings":
        """加载配置文件

        Args:
            config_path: 配置文件路径，如果为None则自动查找

        Returns:
            Settings: 配置对象
        """
        if config_path is None:
            config_path = cls._find_config()
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            return cls()

        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        return cls(**config_data)

# 全局配置对象
settings = Settings.load_config() 