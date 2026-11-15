# QT：两层量化研究团队插件

一个无第三方依赖的 Kimi Code 插件框架。第一层由分配组、生成组、检查组组成；第二层是更新系统，负责接收用户指令和查询整体状态。生成组与检查组只能通过分配组协作。

## 本地运行

```bash
# 用合成示例数据走通“分配 → 生成 → 检查”
python quant_system.py run "验证研究流程"

# 使用自己的价格序列（逗号分隔）
python quant_system.py run "检查动量示例" --prices "100,101,100,102,103,102,104"

# 查看系统状态、向更新层提交指令
python quant_system.py status
python quant_system.py command "下次增加交易成本检查"
```

状态写入当前目录的 `.qt/state.json`。示例回测仅用于验证框架，不构成投资建议，也不会连接实盘。

## 作为 Kimi Code 插件安装

在 Kimi Code 中执行：

```text
/plugins install D:/QT
/reload
```

安装后可使用：

- `/quant-team:research 验证研究流程`
- `/quant-team:status`
- `/quant-team:command 下次增加交易成本检查`
- `/skill:quant-team:quant-team`

本地安装后，Kimi Code 使用插件的托管副本；修改本目录后需要重新安装并 `/reload`。

## 结构

- `quant_system.py`：最小研究流程、风险检查和状态持久化。
- `agents/`：更新层、分配组、生成组、检查组的 AI 角色。
- `skills/quant-team/`：统一工作流。
- `commands/`：研究、状态和指令三个入口。
- `kimi.plugin.json`：插件清单。

插件格式依据 [Kimi Code 官方插件文档](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/plugins.html)。
