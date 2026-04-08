# 参与贡献

感谢你对 Vibe Trading 项目的关注！我们欢迎任何形式的贡献。

## 如何贡献

### 报告问题

如果你发现了 bug 或者有新的功能建议：

1. 在 [GitHub Issues](https://github.com/encyc/vibe-trading/issues) 中搜索是否已有相关问题
2. 如果没有，创建新的 Issue，详细描述问题或建议

### 提交代码

1. **Fork 项目**

```bash
# 在 GitHub 上 fork 项目
# 然后克隆你的 fork
git clone https://github.com/your-username/vibe-trading.git
cd vibe-trading
```

2. **创建分支**

```bash
git checkout -b feature/your-feature-name
# 或
git checkout -b fix/your-bug-fix
```

3. **进行修改**

- 遵循项目的代码风格
- 添加必要的测试
- 更新相关文档

4. **提交更改**

```bash
git add .
git commit -m "feat: add your feature description"
```

5. **推送到你的 fork**

```bash
git push origin feature/your-feature-name
```

6. **创建 Pull Request**

在 GitHub 上创建 Pull Request，描述你的修改内容。

## 代码规范

### Python 代码

- 遵循 PEP 8 规范
- 使用 `ruff` 进行格式化：
  ```bash
  ruff check backend/src/
  ruff format backend/src/
  ```
- 使用类型注解
- 编写单元测试

### Commit 规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>: <description>

[optional body]
```

类型：
- `feat`: 新功能
- `fix`: 修复 bug
- `refactor`: 重构
- `docs`: 文档更新
- `test`: 测试相关
- `chore`: 构建/工具链相关

### 文档规范

- 使用清晰的中文描述
- 添加代码示例
- 更新相关的 API 文档

## 开发环境设置

```bash
# 1. 克隆项目
git clone https://github.com/encyc/vibe-trading.git
cd vibe-trading

# 2. 安装依赖
cd backend
uv pip install -e .

# 3. 安装开发依赖
uv pip install -e ".[dev]"

# 4. 运行测试
uv run pytest

# 5. 运行 linting
uv run ruff check src/
```

## 测试

在提交 PR 前，请确保：

- 所有测试通过
- 代码覆盖率不低于 80%
- 没有引入新的 linting 错误

```bash
# 运行所有测试
uv run pytest

# 运行特定测试
uv run pytest tests/test_technical_analysis.py

# 生成覆盖率报告
uv run pytest --cov=vibe_trading --cov-report=html
```

## 文档贡献

文档也是项目的重要组成部分，你可以：

- 修正错别字和语法错误
- 改进现有文档的清晰度
- 添加新的教程和示例
- 翻译文档到其他语言

## 行为准则

- 尊重所有贡献者
- 欢迎新手并给予帮助
- 建设性的讨论和反馈
- 关注项目本身而非个人

## 获取帮助

如果你在贡献过程中遇到问题：

- 查看 [GitHub Issues](https://github.com/encyc/vibe-trading/issues)
- 阅读 [项目文档](/)
- 在 Issue 中提问

## 许可证

通过贡献代码，你同意你的贡献将根据项目的 [MIT License](https://github.com/encyc/vibe-trading/blob/main/LICENSE) 进行许可。
