# Aurum Signal

一个本地运行的黄金趋势分析 Web 应用。每天获取最新公开市场数据，按照“四因素 + 双参考系”规则生成未来5个交易日的方向判断，并用本地 JSON 持续记录历史预测与准确率。

## 运行

```powershell
python server.py
```

打开 `http://127.0.0.1:8765/`。

只更新一次数据并退出：

```powershell
python server.py --refresh
```

运行测试：

```powershell
python -m unittest discover -s tests -v
```

## 数据来源

- 现货黄金：Gold API公开报价
- COMEX、GLD、美股、VIX、商品和外汇：Yahoo Finance Chart API
- 10年期名义与实际收益率：美国财政部官方收益率曲线
- 全球央行购金与美联储政策倾向：当前通过 `config.json` 人工维护

接口异常时系统会保留缺失状态并降低数据完整度，不会用零值伪造数据。

## 本地数据

- `data/latest.json`：最近一次成功分析
- `data/history.json`：每日预测快照及后续验证结果

历史快照不会因后续规则调整而覆盖。页面结论仅用于研究，不构成投资建议。
