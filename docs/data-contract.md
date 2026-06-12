# 黄金趋势分析：页面字段定义 v1.0

本文档定义静态页面、后续数据采集模块和评分引擎共同使用的 JSON 契约。首版预测对象为 `XAU/USD`，预测周期为未来 1～5 个交易日。

## 1. 顶层对象

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `schema_version` | string | 是 | 数据结构版本，使用语义化版本 |
| `model_version` | string | 是 | 生成评分所使用的规则/模型版本 |
| `analysis_id` | string | 是 | 单次分析唯一标识 |
| `generated_at` | datetime | 是 | 报告生成时间，ISO 8601 |
| `market_as_of` | datetime | 是 | 行情数据截止时间 |
| `timezone` | string | 是 | 展示时区，默认 `Asia/Shanghai` |
| `instrument` | object | 是 | 黄金当前行情 |
| `market_quotes` | array | 是 | 主页行情卡，至少包含现货黄金与 COMEX 黄金期货 |
| `forecast` | object | 是 | 核心预测结果 |
| `factors` | array | 是 | 四因素评分 |
| `reference_systems` | array | 是 | 两个参考系 |
| `drivers` | array | 是 | 主要支持因素 |
| `risks` | array | 是 | 主要风险 |
| `events` | array | 否 | 近期重要事件 |
| `indicators` | array | 是 | 原始指标和数据质量 |
| `data_quality` | object | 是 | 本次数据质量汇总 |
| `disclaimer` | string | 是 | 风险声明 |

## 2. instrument

| 字段 | 类型 | 说明 |
|---|---|---|
| `symbol` | string | 固定为 `XAUUSD` |
| `name` | string | 展示名称 |
| `currency` | string | 计价货币 |
| `price` | number/null | 最新价格 |
| `change` | number/null | 当日价格变化 |
| `change_percent` | number/null | 当日涨跌幅，数值 `0.55` 表示 `0.55%` |
| `session` | string | 当前交易时段 |

## 3. forecast

| 字段 | 类型 | 说明 |
|---|---|---|
| `horizon` | string | 预测周期 |
| `direction` | string | 中文结论 |
| `direction_code` | enum | `strong_bullish`、`cautiously_bullish`、`neutral`、`cautiously_bearish`、`strong_bearish` |
| `score` | integer | 综合分，范围 `-100～100` |
| `signal_strength` | integer | 模型一致度，范围 `20～90`，是启发式强度而非正确概率 |
| `confidence` | integer | 兼容字段，与 `signal_strength` 相同；不得解释为概率 |
| `confidence_is_probability` | boolean | 当前固定为 `false` |
| `benchmark_symbol` | string | 预测和历史验证使用的价格基准 |
| `benchmark_name` | string | 基准展示名称；首版真实数据使用 COMEX黄金期货 |
| `summary` | string | 一句话解释 |
| `expected_range.low` | number/null | 预期区间下沿，首版可为空 |
| `expected_range.high` | number/null | 预期区间上沿，首版可为空 |
| `expected_range.unit` | string | 区间单位 |

综合分到方向的默认映射：

| 分数 | `direction_code` | 展示 |
|---:|---|---|
| `40～100` | `strong_bullish` | 明显偏多 |
| `15～39` | `cautiously_bullish` | 谨慎偏多 |
| `-14～14` | `neutral` | 震荡 |
| `-39～-15` | `cautiously_bearish` | 谨慎偏空 |
| `-100～-40` | `strong_bearish` | 明显偏空 |

## 2.1 market_quotes[]

| 字段 | 类型 | 说明 |
|---|---|---|
| `symbol` | string | 行情代码，例如 `XAUUSD`、`COMEX GC` |
| `name` | string | 展示名称 |
| `description` | string | 指标含义说明 |
| `contract` | string/null | 期货合约说明；现货为空 |
| `price` | number/null | 最新价格 |
| `unit` | string | 单位 |
| `change_percent` | number/null | 当日涨跌幅 |
| `basis` | number/null | 期货相对现货价差，仅期货可用 |
| `updated_at` | datetime/null | 行情时间 |

`XAU/USD` 表示国际现货黄金兑美元的场外报价；`COMEX GC` 表示纽约商品交易所黄金期货。两者不应混为同一指标。

## 4. factors[]

数组固定包含 `fed`、`stocks`、`fund_flow`、`central_bank` 四项。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | enum | 因素代码 |
| `name` | string | 因素名称 |
| `weight` | integer | 最大绝对分值：50、10、30、10 |
| `score` | number | 当前得分，范围为 `-weight～weight` |
| `signal` | string | 中文方向 |
| `signal_code` | enum | `bullish`、`slightly_bullish`、`neutral`、`slightly_bearish`、`bearish` |
| `summary` | string | 当前得分解释 |
| `data_completeness` | integer | 因素数据完整度，`0～100` |

约束：四项 `score` 相加必须等于 `forecast.score`。

## 5. reference_systems[]

数组固定包含 `commodities` 和 `currencies`。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | enum | `commodities` 或 `currencies` |
| `name` | string | 参考系名称 |
| `signal` | string | 偏多、中性或偏空 |
| `signal_code` | enum | `bullish`、`neutral`、`bearish` |
| `agreement` | integer | 组成指标方向一致度，`0～100` |
| `relationship` | enum | `同步`、`轻微背离`、`严重背离` |
| `abnormal` | boolean | 是否触发异常信号 |
| `summary` | string | 参考系解释 |
| `components` | array | 组成资产的最新行情与走势 |
| `updates` | array | 与参考系相关的最新事件和报道摘要 |

参考系默认不加入综合分，只调整置信度并辅助识别异常。

### components[]

| 字段 | 类型 | 说明 |
|---|---|---|
| `symbol` | string | 资产代码 |
| `name` | string | 资产名称 |
| `value` | number/null | 最新值 |
| `unit` | string | 单位 |
| `change_1d` | number/null | 1日涨跌幅 |
| `change_5d` | number/null | 5日涨跌幅 |
| `trend` | string | 面向用户的走势描述 |

商品参考系首版包含 WTI、白银、铜；货币参考系包含 EUR/USD、GBP/USD、AUD/USD、USD/JPY、USD/CAD。

### updates[]

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | enum | `event` 或 `news` |
| `title` | string | 标题 |
| `summary` | string | 与黄金判断相关的摘要 |
| `published_at` | datetime | 发布时间 |
| `source_name` | string | 来源名称 |

真实数据版本还需增加 `source_url`，页面点击后可打开原始来源。

## 6. drivers[] 与 risks[]

### drivers[]

| 字段 | 类型 | 说明 |
|---|---|---|
| `title` | string | 支持因素标题 |
| `detail` | string | 具体解释 |
| `impact` | number | 对综合判断的影响强度 |
| `factor_id` | string | 对应因素或参考系代码 |

### risks[]

| 字段 | 类型 | 说明 |
|---|---|---|
| `title` | string | 风险标题 |
| `detail` | string | 风险解释 |
| `severity` | enum | `low`、`medium`、`high` |

页面默认最多展示各 3 条，其余内容可进入详情区域。

## 7. events[]

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | string | 事件名称 |
| `scheduled_at` | datetime | 计划发布时间 |
| `importance` | enum | `low`、`medium`、`high` |
| `expected_effect` | string | 对黄金的潜在影响 |

## 8. indicators[]

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 唯一指标代码 |
| `name` | string | 展示名称 |
| `group` | enum | `market`、`fed`、`stocks`、`fund_flow`、`central_bank`、`commodities`、`currencies` |
| `value` | number/null | 最新值 |
| `unit` | string | 单位 |
| `change_1d` | number/null | 1日变化；价格类默认使用百分比，利率类使用百分点 |
| `change_5d` | number/null | 5日变化 |
| `signal` | string | 对黄金的方向解释，必须应用该指标的黄金敏感度 |
| `gold_sensitivity` | enum | `direct`、`inverse` 或 `manual` |
| `signal_rationale` | string | 指标变化如何映射为黄金信号的说明 |
| `updated_at` | datetime/date/null | 数据时间 |
| `source_name` | string | 来源名称 |
| `source_url` | string | 来源链接 |
| `status` | enum | `ok`、`delayed`、`missing`、`error` |

首版指标清单：

| 分组 | 指标 |
|---|---|
| 市场 | XAU/USD |
| 美联储 | 10年实际利率、10年美债收益率、美元指数、美联储资产负债表 |
| 美股 | S&P 500、纳斯达克、VIX |
| 资金流 | GLD价格、GLD成交量、黄金期货价格、期货成交量、CFTC净多仓 |
| 央行 | 人工配置的购金趋势与更新时间 |
| 商品 | WTI、白银、铜 |
| 货币 | EUR/USD、GBP/USD、AUD/USD、USD/JPY、USD/CAD |

## 9. data_quality

| 字段 | 类型 | 说明 |
|---|---|---|
| `completeness` | integer | 非缺失指标占比 |
| `freshness` | integer | 按各指标更新频率计算的新鲜度 |
| `missing_count` | integer | 缺失指标数量 |
| `delayed_count` | integer | 延迟指标数量 |
| `delayed_inputs` | array | 延迟输入代码 |
| `oldest_core_data_at` | datetime/null | 最旧核心输入时间，不等同于黄金基准行情时间 |
| `freshness_by_source` | object | 按各来源频率计算的状态、年龄和新鲜度 |
| `status` | enum | `good`、`degraded`、`poor` |
| `message` | string | 面向用户的数据质量说明 |

数据质量降级原则：

- 核心指标缺失时不得用 `0` 代替，字段必须为 `null`。
- 美联储因素核心指标缺失超过一半时，最高置信度限制为 `55`。
- 总完整度低于 `70` 时，不输出明确偏多或偏空，降级为“数据不足”。
- 周频和月频数据在正常发布周期内不计为过期。

## 10. 页面状态

页面至少支持以下状态：

1. `ready`：正常展示分析结果。
2. `loading`：正在更新，保留旧结果并显示更新状态。
3. `degraded`：部分数据延迟，但可继续分析。
4. `insufficient`：核心数据不足，不输出方向。
5. `error`：更新失败，展示上次成功结果及错误提示。

## 11. validation_history

历史验证用于保存过去每天生成的预测，并在预测周期结束后写入实际收盘结果。准确率只统计 `evaluated` 记录，`pending` 记录不进入分母。

### validation_history.evaluation_rule

| 字段 | 类型 | 说明 |
|---|---|---|
| `horizon_trading_days` | integer | 评价周期，首版固定为5个交易日 |
| `bullish_threshold` | number | 实际收益达到该值时判定为上涨，默认 `0.5%` |
| `bearish_threshold` | number | 实际收益低于该值时判定为下跌，默认 `-0.5%` |
| `description` | string | 页面展示的评价规则 |

方向验证规则：

- 实际收益 `>= +0.5%`：上涨。
- 实际收益 `<= -0.5%`：下跌。
- 实际收益位于 `-0.5%～+0.5%`：震荡。
- “明显偏多”和“谨慎偏多”统一映射为上涨。
- “明显偏空”和“谨慎偏空”统一映射为下跌。
- 预测方向与实际方向一致时，`direction_hit=true`。

### validation_history.records[]

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 历史预测唯一标识 |
| `model_version` | string | 生成该预测时的规则版本 |
| `forecast_date` | date | 生成预测的日期 |
| `evaluation_date` | date | 计划使用收盘价验证的日期 |
| `horizon` | string | 预测周期展示文字 |
| `prediction.direction` | string | 当时展示的预测方向 |
| `prediction.direction_group` | enum | `bullish`、`neutral`、`bearish` |
| `prediction.score` | number | 当时综合分 |
| `prediction.confidence` | number | 当时置信度 |
| `prediction.start_price` | number | 预测生成时的黄金基准价 |
| `prediction.range_low` | number/null | 当时预测区间下沿 |
| `prediction.range_high` | number/null | 当时预测区间上沿 |
| `prediction.benchmark_symbol` | string | 历史结算所使用的行情代码 |
| `prediction.benchmark_name` | string | 历史结算基准名称 |
| `outcome.status` | enum | `pending` 或 `evaluated` |
| `outcome.close_price` | number/null | 评价日黄金收盘价 |
| `outcome.return_percent` | number/null | 基准价至评价日收盘收益率 |
| `outcome.actual_direction` | string | 实际上涨、震荡或下跌 |
| `outcome.actual_direction_group` | enum/null | `bullish`、`neutral`、`bearish` |
| `outcome.direction_hit` | boolean/null | 方向是否命中 |
| `outcome.range_hit` | boolean/null | 实际收盘是否落入预测区间 |

统计口径：

```text
方向准确率 = 方向命中的已验证记录数 / 已验证记录总数
区间命中率 = 收盘价落入预测区间的已验证记录数 / 已验证记录总数
```

本地实现建议每天保存一份预测快照，文件一旦生成不得因后续规则调整而覆盖，否则会产生回看偏差。若规则版本变化，应同时保存 `schema_version` 和模型版本。

### validation_history.metrics

| 字段 | 类型 | 说明 |
|---|---|---|
| `sample_count` | integer | 已验证样本量 |
| `direction_accuracy` | number/null | 总体方向准确率 |
| `balanced_accuracy` | number/null | 各实际类别召回率的平均值 |
| `range_coverage` | number/null | 有区间结果记录的覆盖率 |
| `class_distribution` | object | 实际上涨、震荡、下跌样本数 |
| `confusion_matrix` | object | 预测类别到实际类别的混淆矩阵 |
| `probability_calibration_ready` | boolean | 非重叠样本达到校准要求前保持 `false` |

历史记录同时保存 `input_snapshot`、具体基准代码、连续合约类型和是否换月调整。当前 Yahoo `GC=F` 属于连续主力序列，`roll_adjusted=false`，因此页面不得将历史结果描述为严格可比的固定合约结算回测。
