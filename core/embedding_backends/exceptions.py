"""嵌入后端异常定义。"""


class BackendUnavailableError(Exception):
    """后端依赖不可用（如 llama-cpp-python 未安装）。"""


class ModelLoadError(Exception):
    """模型加载失败（文件不存在/格式错误/内存不足）。"""