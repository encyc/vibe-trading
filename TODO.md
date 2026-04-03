# Vibe Trading - API 集成 TODO

本文档列出未来可以补充的 API 平台，按优先级排序。

---

## 🔴 高优先级

### 1. Whale Alert API - 大额转账监控
- **用途**: 实时监控链上大额转账
- **价格**: ✅ 免费
- **注册**: https://whale-alert.io/
- **文档**: https://docs.whale-alert.io/
- **使用场景**: 基本面分析师

```bash
# .env 添加
WHALE_ALERT_API_KEY=your_key_here
```

### 2. CryptoQuant API - 链上数据
- **用途**: 专业链上指标（活跃地址、交易所流入流出等）
- **价格**: ⚠️ 部分免费
- **注册**: https://cryptoquant.com/
- **文档**: https://cryptoquant.com/api-docs
- **使用场景**: 基本面分析师

```bash
# .env 添加
CRYPTOQUANT_API_KEY=your_key_here
```

---

## 🟡 中优先级

### 3. FRED API - 宏观经济数据
- **用途**: 美联储经济数据（利率、通胀等）
- **价格**: ✅ 完全免费
- **注册**: https://fred.stlouisfed.org/docs/api/fred/
- **使用场景**: 新闻分析师

```bash
# .env 添加
FRED_API_KEY=your_key_here  # 免费
```

### 4. Etherscan API - Gas 费数据
- **用途**: 以太坊网络 Gas 费追踪
- **价格**: ✅ 免费 (有限制)
- **注册**: https://docs.etherscan.io/
- **使用场景**: 基本面分析师

```bash
# .env 添加
ETHERSCAN_API_KEY=your_key_here  # 免费
```

### 5. Coinglass API - 跨交易所数据
- **用途**: 多交易所资金费率、持仓量对比
- **价格**: ⚠️ 部分免费
- **注册**: https://www.coinglass.com/
- **使用场景**: 基本面/情绪分析师

```bash
# .env 添加 (可选)
COINGLASS_API_KEY=your_key_here
```

---

## 🟢 低优先级

### 6. GitHub API - 项目开发活跃度
- **用途**: 追踪加密项目开发进度
- **价格**: ✅ 免费 (有限制)
- **文档**: https://docs.github.com/en/rest
- **使用场景**: 基本面分析师

```bash
# 无需 API Key，使用公开端点即可
# 或添加 (提高速率限制):
GITHUB_TOKEN=your_token_here
```

### 7. RSS 新闻源聚合
- **用途**: 补充加密货币新闻来源
- **价格**: ✅ 完全免费
- **源列表**:
  - CoinDesk: https://www.coindesk.com/arc/outboundfeeds/rss/
  - Cointelegraph: https://cointelegraph.com/rss
  - The Block: https://www.theblock.co/rss.xml
- **使用场景**: 新闻分析师

### 8. Santiment API - 链上+社交数据
- **用途**: 综合链上和社交情绪数据
- **价格**: ⚠️ 付费
- **注册**: https://santiment.net/
- **使用场景**: 基本面/情绪分析师

---

## 📊 当前已集成

| 功能 | 平台 | 状态 |
|------|------|------|
| K线数据 | Binance | ✅ 完成 |
| 技术指标 | 自计算 | ✅ 完成 |
| 资金费率 | Binance | ✅ 完成 |
| 多空比例 | Binance | ✅ 完成 |
| 新闻数据 | CryptoCompare | ✅ 完成 |
| 恐惧贪婪指数 | Alternative.me | ✅ 完成 |
| 社交情绪 | LunarCrush | ✅ 完成 |

---

## 🔧 实现说明

### 添加新 API 的步骤

1. **在 `.env` 和 `.env.example` 中添加配置**
   ```bash
   NEW_API_KEY=your_key_here
   ```

2. **在 `backend/src/vibe_trading/config/settings.py` 中添加字段**
   ```python
   new_api_key: Optional[str] = field(default_factory=lambda: os.getenv("NEW_API_KEY"))
   ```

3. **在相应工具模块中添加函数**
   - 基本面数据 → `tools/fundamental_tools.py`
   - 新闻数据 → `tools/sentiment_tools.py` (新闻模块)
   - 情绪数据 → `tools/sentiment_tools.py`

4. **在 `trading_coordinator.py` 中调用新工具**

---

## 📝 注意事项

- 所有 API 密钥请妥善保管，不要提交到 Git
- 免费层通常有请求限制，注意缓存策略
- 付费 API 在订阅前建议先试用测试期
