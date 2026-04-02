# Pi Logger

简单但实用的彩色日志系统，用于小说创作后端。

## 特性

- **彩色输出**：不同级别的日志使用不同颜色
- **标签系统**：为不同 Agent/模块设置标签和颜色
- **简洁 API**：`info()`, `success()`, `error()` 等直观方法
- **进度跟踪**：`step()`, `done()` 等便捷方法
- **灵活配置**：支持多种输出格式和级别过滤

## 快速开始

```python
from pi_logger import info, success, error, get_logger

# 使用全局便捷函数
info("系统启动中...")
success("操作完成", tag="Writer")
error("发生错误", code=500)

# 使用 Logger 对象
logger = get_logger("MyModule")
logger.step("开始处理")
logger.done("处理完成", tag="Agent")
```

## 日志级别

| 级别 | 颜色 | 用途 |
|------|------|------|
| `DEBUG` | 灰色 | 调试信息 |
| `INFO` | 青色 | 一般信息 |
| `SUCCESS` | 亮绿 | 成功操作 |
| `WARNING` | 亮黄 | 警告信息 |
| `ERROR` | 亮红 | 错误信息 |

## 预设标签颜色

| 标签 | 颜色 | 用途 |
|------|------|------|
| `Editor` | 亮青 | 编辑 Agent |
| `WorldBuilder` | 亮绿 | 世界观 Agent |
| `Character` | 亮黄 | 角色 Agent |
| `Plot` | 亮紫 | 剧情 Agent |
| `Chapter` | 亮蓝 | 章节 Agent |
| `Writer` | 亮红 | 写作 Agent |

## API 参考

### 全局便捷函数

```python
info(msg, tag=None, **kwargs)
success(msg, tag=None, **kwargs)
warning(msg, tag=None, **kwargs)
error(msg, tag=None, **kwargs)

step(msg, tag=None, **kwargs)    # 开始步骤
done(msg, tag=None, **kwargs)    # 完成步骤
fail(msg, tag=None, **kwargs)    # 步骤失败
```

### Logger 对象

```python
logger = get_logger("ModuleName")

logger.debug(msg, tag=None, **kwargs)
logger.info(msg, tag=None, **kwargs)
logger.success(msg, tag=None, **kwargs)
logger.warning(msg, tag=None, **kwargs)
logger.error(msg, tag=None, **kwargs)

# 便捷方法
logger.step(msg)     # ▶ 开始
logger.done(msg)     # ✓ 完成
logger.fail(msg)     # ✗ 失败
logger.file(msg)     # 📄 文件操作
```

### 进度上下文

```python
with logger.progress("正在处理"):
    # 做一些工作
    pass
# 自动输出: ▶ 正在处理
#          ✓ 正在处理
```

### 配置

```python
from pi_logger import configure

configure(
    min_level="INFO",      # 最低日志级别
    show_time=True,        # 显示时间
    show_level=True,       # 显示级别
)
```

## 完整示例

```python
from pi_logger import get_logger, success, error

logger = get_logger("NovelAgency")

# 设置标签颜色
logger.set_tag_color("MyAgent", "\033[96m")  # 亮青

logger.header("小说创作系统")
logger.info("系统初始化", version="1.0")

# 带标签的日志
logger.step("开始生成角色设定", tag="Character")
# ... 做一些工作 ...
logger.done("角色设定生成完成", tag="Character")

# 进度跟踪
with logger.progress("生成章节内容"):
    # 自动处理开始/结束
    pass

logger.separator()
logger.success("所有任务完成!")
```
